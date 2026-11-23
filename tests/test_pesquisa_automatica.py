"""Pesquisa automática do tema (Piloto vindo de Tendências): fonte lida de verdade, com proveniência.

Bug: o Piloto criado a partir de Tendências caía em Fontes pedindo uma fonte, porque a etapa de pesquisa
não existia. Agora a pesquisa busca texto real na Wikipédia (sem inventar nada) e registra a URL do artigo.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.wikipedia_research import (WikipediaResearch, article_text, search_queries,  # noqa: E402
                                                    wiki_language)
from app.studio.application.editorial import SourceRefused, SourceUnavailable  # noqa: E402
from app.studio.application.ports import ResearchDocument  # noqa: E402
from app.studio.application.production import (COORDINATOR_DAG_WITH_RESEARCH, ProductionStage,  # noqa: E402
                                               ResearchHandler, StageExecutionFailed)
from app.studio.application.research import AutoResearch  # noqa: E402
from app.studio.domain.contracts import SourceSnapshot  # noqa: E402

FACT = ("Grand Theft Auto VI is an action-adventure game developed by Rockstar Games and set in 2026 "
        "in the state of Leonida, a fictional Florida.")
ARTICLE = (FACT + "\n" + "\n".join([f"Rockstar Games announced in {2020 + i} that the studio kept working on the project." for i in range(6)])
           + "\nSee also\nNot a fact worth keeping, Rockstar 2026 list.")


def _wiki(handler_log=None, hits=None, extract=ARTICLE, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if handler_log is not None:
            handler_log.append(request)
        params = request.url.params
        if status != 200:
            return httpx.Response(status)
        if params.get("list") == "search":
            found = hits if hits is not None else [{"title": "Grand Theft Auto VI", "wordcount": 22000}]
            return httpx.Response(200, json={"query": {"search": found}})
        return httpx.Response(200, json={"query": {"pages": [{"title": params["titles"], "extract": extract}]}})
    return WikipediaResearch(transport=httpx.MockTransport(handler))


def test_queries_prefer_acronyms_and_numbers_over_the_clickbait_title():
    queries = search_queries("If You Steal a Car in GTA 6, I'll Pay For It!")
    assert queries[0] == "GTA 6"
    assert queries[1].startswith("If You Steal a Car in GTA 6")


@pytest.mark.parametrize("code,expected", [("pt-BR", "pt"), ("en-US", "en"), ("es_ES", "es"), (None, "en"),
                                           ("../evil", "en"), ("x", "en")])
def test_language_code_is_validated_before_it_becomes_a_host(code, expected):
    assert wiki_language(code) == expected


def test_article_text_drops_trailing_reference_sections():
    assert "Not a fact" not in article_text(ARTICLE) and "Leonida" in article_text(ARTICLE)


def test_search_returns_the_article_text_and_the_article_url_as_provenance():
    log: list = []
    docs = _wiki(log).search("If You Steal a Car in GTA 6, I'll Pay For It!", "en-US")
    assert [d.url for d in docs] == ["https://en.wikipedia.org/wiki/Grand_Theft_Auto_VI"]
    assert "Leonida" in docs[0].text
    assert {r.url.host for r in log} == {"en.wikipedia.org"}
    assert all(r.headers["user-agent"].startswith("faceless-studio") for r in log)  # a Wikimedia exige UA próprio


def test_stubs_and_disambiguation_pages_are_not_sources():
    assert _wiki(hits=[{"title": "GTA", "wordcount": 40}]).search("GTA 6", "en") == []


def test_falls_back_to_english_when_the_channel_language_has_no_article():
    log: list = []

    def handler(request):
        log.append(request.url.host)
        if request.url.host.startswith("pt.") and request.url.params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": []}})
        if request.url.params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": [{"title": "Mary Celeste", "wordcount": 8000}]}})
        return httpx.Response(200, json={"query": {"pages": [{"title": "Mary Celeste", "extract": ARTICLE}]}})
    docs = WikipediaResearch(transport=httpx.MockTransport(handler)).search("Mary Celeste", "pt-BR")
    assert docs and docs[0].url.startswith("https://en.wikipedia.org/")
    assert "pt.wikipedia.org" in log


def test_definitive_refusal_is_source_unavailable_without_retry():
    log: list = []
    with pytest.raises(SourceUnavailable, match="HTTP 403"):
        _wiki(log, status=403).search("GTA 6", "en")
    assert len(log) == 1


def test_transient_failure_is_retried_once_and_then_reported_with_the_reason():
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        if request.url.params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": [{"title": "GTA VI", "wordcount": 9000}]}})
        return httpx.Response(200, json={"query": {"pages": [{"title": "GTA VI", "extract": ARTICLE}]}})
    docs = WikipediaResearch(transport=httpx.MockTransport(flaky), sleep=lambda s: None).search("GTA 6", "en")
    assert docs and calls["n"] == 3
    always = WikipediaResearch(transport=httpx.MockTransport(lambda r: httpx.Response(503)), sleep=lambda s: None)
    with pytest.raises(SourceUnavailable, match="HTTP 503"):
        always.search("GTA 6", "en")


class _Videos:
    def __init__(self, topic="GTA 6", language="pt-BR"):
        self.video = SimpleNamespace(id="v1", project_id="p1", topic=topic)
        self.project = SimpleNamespace(language=language)

    def get_video(self, video_id):
        return self.video if video_id == "v1" else None

    def get_project(self, project_id):
        return self.project


class _Snaps:
    def __init__(self, existing=()):
        self.items = list(existing)

    def list(self, video_id):
        return list(self.items)

    def add(self, video_id, url, text):
        snap = SourceSnapshot(id=f"s{len(self.items)}", video_id=video_id, url=url, content_sha256="x", text=text,
                              fetched_at=datetime.now(timezone.utc))
        self.items.append(snap)
        return snap


class _Provider:
    name = "fake"

    def __init__(self, docs=(), error=None):
        self.docs, self.error, self.calls = list(docs), error, []

    def search(self, topic, language):
        self.calls.append((topic, language))
        if self.error:
            raise self.error
        return self.docs


def test_research_records_each_article_as_a_source_with_the_channel_language():
    provider, snaps = _Provider([ResearchDocument("https://en.wikipedia.org/wiki/GTA_VI", "GTA VI", ARTICLE)]), _Snaps()
    result = AutoResearch(provider, snaps, _Videos()).execute("v1")
    assert provider.calls == [("GTA 6", "pt-BR")]
    assert [s.url for s in result.snapshots] == ["https://en.wikipedia.org/wiki/GTA_VI"] and not result.reused
    assert snaps.items[0].text.startswith("Grand Theft Auto VI")


def test_research_never_overrides_sources_the_human_already_added():
    existing = SourceSnapshot(id="s0", video_id="v1", url="https://x.test/a", content_sha256="x", text=ARTICLE)
    provider = _Provider([ResearchDocument("https://en.wikipedia.org/wiki/X", "X", ARTICLE)])
    result = AutoResearch(provider, _Snaps([existing]), _Videos()).execute("v1")
    assert result.reused and provider.calls == []  # nenhuma busca externa


def test_research_refuses_text_without_checkable_claims():
    provider = _Provider([ResearchDocument("https://en.wikipedia.org/wiki/X", "X", "texto curto sem fatos")])
    snaps = _Snaps()
    with pytest.raises(SourceRefused):
        AutoResearch(provider, snaps, _Videos()).execute("v1")
    assert snaps.items == []


def test_research_with_no_results_is_refused_not_invented():
    with pytest.raises(SourceRefused):
        AutoResearch(_Provider([]), _Snaps(), _Videos()).execute("v1")


def _context():
    return SimpleNamespace(run=SimpleNamespace(video_id="v1"), checkpoint_version=1)


def test_handler_turns_failures_into_a_human_readable_stage_failure():
    for error, fragment in ((SourceUnavailable("x"), "não conseguiu acessar"), (None, "não achou uma fonte")):
        provider = _Provider([], error=error)
        with pytest.raises(StageExecutionFailed, match=fragment):
            ResearchHandler(AutoResearch(provider, _Snaps(), _Videos())).execute(_context())


def test_handler_checkpoint_carries_the_provenance():
    provider = _Provider([ResearchDocument("https://en.wikipedia.org/wiki/GTA_VI", "GTA VI", ARTICLE)])
    outcome = ResearchHandler(AutoResearch(provider, _Snaps(), _Videos())).execute(_context())
    assert outcome.checkpoint is not None and ResearchHandler.available


def test_pipeline_with_research_runs_research_before_script():
    order = COORDINATOR_DAG_WITH_RESEARCH.topological_order()
    assert order[0] is ProductionStage.RESEARCH and order.index(ProductionStage.SCRIPT) == 1
