"""Coleta de tendências: termos do pilar/nicho, intercalação, teto e intervalo de cota, Em Alta por categoria."""
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.categories import (MAX_SEARCH_TERMS_PER_REFRESH, SEARCH_COOLDOWN, NoSearchTerms,  # noqa: E402
                                               RefreshTrends)
from app.studio.application.ports import TrendRecord  # noqa: E402
from app.studio.domain.categories import ProjectCategory  # noqa: E402
from app.studio.domain.trend_cards import SEARCH_SOURCE  # noqa: E402
from app.studio.domain.trends import Evidence, TrendItem  # noqa: E402

NOW = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)
P = uuid.uuid4().hex


def item(topic, source="YouTube Data API", url="https://youtube.com/watch?v=abcdefghijk"):
    return TrendItem(topic=topic, source_name=source, source_url="https://www.googleapis.com/youtube/v3/search",
                     observed_at=NOW, window_start=NOW - timedelta(days=7), window_end=NOW, metric_name="views",
                     metric_value=10.0, evidence=[Evidence(title=topic, url=url, channel="C", views=10)])


@dataclass
class Project:
    niche: str


class Videos:
    def __init__(self, niche=""):
        self.niche = niche

    def get_project(self, project_id):
        return Project(self.niche)


class Cats:
    def __init__(self, cats):
        self.cats = cats

    def list(self, project_id):
        return self.cats


class Trends:
    def __init__(self, records=()):
        self.records = list(records)

    def list(self, project_id, since):
        return [r for r in self.records if r.observed_at >= since]


class Ingest:
    def __init__(self, trends=None):
        self.trends_repo = trends or Trends()
        self.batches = []

    def execute(self, project_id, items):
        self.batches.append(list(items))
        return len(items)

    @property
    def items(self):
        return [i for b in self.batches for i in b]


def cat(name, queries):
    return ProjectCategory(uuid.uuid4().hex, P, name, queries)


def build(cats=(), niche="", trends=None, popular=None):
    searched, called = [], []
    ingest = Ingest(trends)

    def fetcher(key, queries):
        searched.append(list(queries))
        return [item(q) for q in queries]

    def pop(key, region, n, category_id=None):
        called.append((region, category_id))
        return [item(f"Em Alta {region} {category_id}", "YouTube Brasil (Em Alta)",
                     f"https://youtube.com/watch?v={region}{category_id}aaaaaaaaa"[:43])]

    refresh = RefreshTrends(repo=Cats(list(cats)), ingest=ingest, fetcher=fetcher,
                            popular_fetcher=popular if popular is not None else pop, videos_repo=Videos(niche),
                            environ={"YOUTUBE_API_KEY": "k"}, clock=lambda: NOW)
    return refresh, ingest, searched, called


def test_without_pillars_the_channel_niche_is_the_only_search_term():
    refresh, _, searched, _ = build(niche="Cachorros")
    refresh.execute(P)
    assert searched == [["Cachorros"]]  # nada de música eletrônica


def test_no_pillar_no_niche_is_a_clear_refusal_not_an_invented_subject():
    refresh, _, searched, called = build()
    with pytest.raises(NoSearchTerms):
        refresh.execute(P)
    assert searched == [] and called == []


def test_terms_are_interleaved_across_pillars_and_capped_to_protect_the_quota():
    cats = [cat(f"Pilar{n}", [f"p{n}-t{m}" for m in range(5)]) for n in range(3)]
    refresh, _, searched, _ = build(cats)
    refresh.execute(P)
    terms = searched[0]
    assert len(terms) == MAX_SEARCH_TERMS_PER_REFRESH == 6
    assert terms[:3] == ["p0-t0", "p1-t0", "p2-t0"]  # todo pilar entra antes de qualquer 2º termo
    assert terms[3:] == ["p0-t1", "p1-t1", "p2-t1"]


def test_a_term_searched_within_the_cooldown_does_not_spend_quota_again():
    recent = TrendRecord(id="1", project_id=P, topic="Tchami", topic_key="tchami", source_name=SEARCH_SOURCE,
                         source_url="https://www.googleapis.com/youtube/v3/search", observed_at=NOW - timedelta(hours=1),
                         window_start=NOW, window_end=NOW, metric_name=None, metric_value=None, evidence=[])
    refresh, _, searched, _ = build([cat("Bass", ["Tchami", "Bass House"])], trends=Trends([recent]))
    refresh.execute(P)
    assert searched == [["Bass House"]]


def test_everything_searched_recently_stores_nothing_and_calls_nothing():
    old = [TrendRecord(id=str(n), project_id=P, topic=t, topic_key=t.lower(), source_name=SEARCH_SOURCE, source_url="https://x",
                       observed_at=NOW - timedelta(minutes=5), window_start=NOW, window_end=NOW, metric_name=None,
                       metric_value=None, evidence=[]) for n, t in enumerate(["Tchami"])]
    refresh, _, searched, called = build([cat("Bass", ["Tchami"])], trends=Trends(old), popular=lambda *a, **k: [])
    assert refresh.execute(P) == 0
    assert searched == []


def test_a_term_searched_after_the_cooldown_is_searched_again():
    stale = TrendRecord(id="1", project_id=P, topic="Tchami", topic_key="tchami", source_name=SEARCH_SOURCE, source_url="https://x",
                        observed_at=NOW - SEARCH_COOLDOWN - timedelta(minutes=1), window_start=NOW, window_end=NOW,
                        metric_name=None, metric_value=None, evidence=[])
    refresh, _, searched, _ = build([cat("Bass", ["Tchami"])], trends=Trends([stale]))
    refresh.execute(P)
    assert searched == [["Tchami"]]


def test_trending_is_per_category_of_the_pillar_and_not_the_whole_platform():
    refresh, ingest, _, called = build([cat("Games", ["GTA 6"]), cat("Música", ["Alok"])])
    refresh.execute(P)
    assert called == [("BR", "20"), ("US", "20"), ("BR", "10"), ("US", "10")]
    trending = [i for i in ingest.items if i.source_name.endswith("(Em Alta)")]
    assert {i.category_id for i in trending} == {c.id for c in refresh.repo.cats}  # ligado ao pilar de origem


def test_pillar_without_a_known_youtube_category_gets_no_trending_at_all():
    refresh, _, searched, called = build([cat("Cane Corso", ["cane corso filhote"])])
    refresh.execute(P)
    assert called == [] and searched == [["cane corso filhote"]]


def test_search_items_carry_the_pillar_that_produced_the_term():
    c1, c2 = cat("A", ["alfa"]), cat("B", ["beta"])
    refresh, ingest, _, _ = build([c1, c2], popular=lambda *a, **k: [])
    refresh.execute(P)
    assert {i.topic: i.category_id for i in ingest.items} == {"alfa": c1.id, "beta": c2.id}


def test_trending_uses_at_most_three_categories():
    cats = [cat("Games", ["xxx"]), cat("Música", ["yyy"]), cat("Esportes", ["zzz"]), cat("Tecnologia", ["www"])]
    refresh, _, _, called = build(cats)
    refresh.execute(P)
    assert {c for _, c in called} == {"20", "10", "17"}


def test_large_collections_are_ingested_in_batches_of_fifty():
    refresh, ingest, _, _ = build([cat("Games", ["aaa"])], popular=lambda *a, **k: [
        item(f"Vídeo {n}", "YouTube Brasil (Em Alta)", f"https://youtube.com/watch?v=vid{n:08d}") for n in range(60)])
    refresh.execute(P)
    assert [len(b) for b in ingest.batches] == [50, 50, 21]  # 1 termo + 60 vídeos em cada região (BR e US são fontes distintas)


def test_custom_queries_skip_the_trending_and_the_cooldown():
    refresh, _, searched, called = build([cat("Games", ["aaa"])])
    refresh.execute(P, custom_queries=["tema solto"])
    assert searched == [["tema solto"]] and called == []
