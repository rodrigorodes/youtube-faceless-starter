import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.trend_cards import SEARCH_SOURCE, build_trend_cards  # noqa: E402

T0 = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)


@dataclass
class Rec:
    topic: str
    source_name: str
    observed_at: datetime
    evidence: list = field(default_factory=list)
    metric_value: float | None = None
    source_url: str = "https://www.youtube.com/feed/trending"
    category_id: str | None = None


def ev(vid, channel, views, title="Título"):
    return {"title": f"{title} {vid}", "url": f"https://youtube.com/watch?v={vid}", "channel": channel, "views": views}


def popular(vid, channel, views, at=T0):
    return Rec(f"Título {vid}", "YouTube Brasil (Em Alta)", at, [ev(vid, channel, views)], float(views))


def test_the_same_video_collected_many_times_appears_once_with_the_latest_collection():
    records = [popular("aaaaaaaaaaa", "Canal A", 100, T0 + timedelta(hours=h)) for h in range(5)]
    records[-1].metric_value = 999.0
    cards = build_trend_cards(records)
    assert len(cards) == 1 and cards[0].metric_value == 999.0 and cards[0].observed_at == T0 + timedelta(hours=4)


def test_a_search_row_becomes_one_card_per_video_with_the_term_kept():
    row = Rec("Tchami", SEARCH_SOURCE, T0, [ev("v1111111111", "A", 10), ev("v2222222222", "B", 30), ev("v3333333333", "C", 20)],
              60.0, "https://www.googleapis.com/youtube/v3/search")
    cards = build_trend_cards([row])
    assert [c.topic for c in cards] == ["Título v2222222222", "Título v3333333333", "Título v1111111111"]  # por visualizações
    assert {c.query for c in cards} == {"Tchami"}
    assert [c.metric_value for c in cards] == [30.0, 20.0, 10.0]  # a métrica é a do vídeo, não a soma do termo


def test_one_channel_takes_at_most_two_cards_keeping_the_most_viewed():
    records = [popular(f"vid{n:08d}", "Mega Canal", 1000 - n) for n in range(5)] + [popular("outro0000000", "Pequeno", 1)]
    cards = build_trend_cards(records)
    assert [c.channel for c in cards] == ["Mega Canal", "Mega Canal", "Pequeno"]
    assert [c.metric_value for c in cards[:2]] == [1000.0, 999.0]


def test_the_channel_cap_is_case_insensitive_and_unknown_channels_are_not_capped():
    cards = build_trend_cards([popular("a0000000001", "Canal X", 5), popular("a0000000002", "canal x", 4), popular("a0000000003", "CANAL X", 3)]
                              + [popular(f"s{n:010d}", "", 2) for n in range(4)])
    assert sum(1 for c in cards if c.channel.lower() == "canal x") == 2
    assert sum(1 for c in cards if not c.channel) == 4


def test_the_same_video_from_search_and_trending_is_one_card():
    row = Rec("Tchami", SEARCH_SOURCE, T0 + timedelta(hours=1), [ev("same0000001", "A", 10)], 10.0)
    assert len(build_trend_cards([popular("same0000001", "A", 10), row])) == 1


def test_other_sources_keep_one_card_per_record():
    rec = Rec("Tema do n8n", "Fonte externa", T0, [ev("x0000000001", "A", 1), ev("x0000000002", "B", 2)], 3.0)
    cards = build_trend_cards([rec])
    assert len(cards) == 1 and cards[0].topic == "Tema do n8n" and len(cards[0].evidence) == 1


def test_per_channel_zero_disables_the_cap():
    assert len(build_trend_cards([popular(f"vid{n:08d}", "Mesmo", 10 - n) for n in range(4)], per_channel=0)) == 4
