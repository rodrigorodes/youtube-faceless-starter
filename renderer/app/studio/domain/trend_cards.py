"""Do que foi coletado ao que a tela mostra: um cartão por VÍDEO, sem repetição e com variedade de canais (sem I/O).

A coleta grava linhas novas a cada "Buscar agora" (a chave inclui a hora da coleta) e a busca por termo grava UMA linha
com até vários vídeos. Mostrar isso cru gera o mesmo vídeo repetido e um cartão por termo que esconde os outros
vídeos. Aqui:
  1. a linha da busca por termo vira um cartão por vídeo (o título do vídeo é o tema; o termo fica em `query`);
  2. o mesmo vídeo coletado várias vezes fica só com a coleta mais recente;
  3. um canal ocupa no máximo `per_channel` cartões (os mais vistos), para a lista não virar um canal só.
"""
from __future__ import annotations

import dataclasses
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .trend_priority import PriorityBreakdown, calculate_priority

SEARCH_SOURCE = "YouTube Data API"
MAX_CARDS_PER_CHANNEL = 2
_VIDEO_ID = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{6,})")


def format_velocity(views_per_hour: float) -> str:
    if views_per_hour >= 1_000_000:
        val = views_per_hour / 1_000_000.0
        s = f"{val:.1f}".replace(".", ",")
        if s.endswith(",0"):
            s = s[:-2]
        return f"{s} mi/h"
    elif views_per_hour >= 1_000:
        val = views_per_hour / 1_000.0
        if val >= 10.0:
            s = f"{int(round(val))}"
        else:
            s = f"{val:.1f}".replace(".", ",")
            if s.endswith(",0"):
                s = s[:-2]
        return f"{s} mil/h"
    else:
        return f"{int(round(views_per_hour))}/h"


def format_niche_ratio(ratio: float) -> str:
    s = f"{ratio:.1f}".replace(".", ",")
    if ratio >= 1.0:
        return f"▲ {s}×"
    else:
        return f"▼ {s}×"


def format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _parse_published_at(ev: dict, default_at: datetime) -> datetime:
    pub = ev.get("published_at")
    if isinstance(pub, datetime):
        return pub
    if isinstance(pub, str) and pub:
        try:
            return datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except Exception:
            pass
    return default_at


@dataclass(frozen=True)
class TrendCard:
    topic: str
    source_name: str
    source_url: str
    observed_at: datetime
    metric_value: float | None
    evidence: list[dict]  # exatamente a evidência do vídeo do cartão
    category_id: str | None
    query: str | None  # termo de busca que originou o cartão (None no Em Alta)
    priority_score: int = 0
    priority_summary: str = ""
    priority_breakdown: PriorityBreakdown | None = None
    risk_status: str = "Sem risco detectado"
    risk_level: str = "ok"
    is_evergreen: bool = False
    velocity_text: str = ""
    niche_ratio_text: str = ""
    duration_text: str = ""
    views_per_hour: float = 0.0
    niche_ratio: float = 1.0

    @property
    def channel(self) -> str:
        return str((self.evidence[0].get("channel") if self.evidence else "") or "").strip()


TrendItemCard = TrendCard


def video_identity(topic: str, evidence: list[dict]) -> str:
    """Mesmo vídeo = mesma identidade, venha de que coleta vier."""
    url = str((evidence[0].get("url") if evidence else "") or "")
    match = _VIDEO_ID.search(url)
    if match:
        return "yt:" + match.group(1)
    return "u:" + (url.strip().lower() or topic.strip().lower())


def _cards_of(record: Any) -> list[TrendCard]:
    evidence = [ev for ev in (record.evidence or []) if isinstance(ev, dict)]
    category_id = getattr(record, "category_id", None)
    if record.source_name == SEARCH_SOURCE and evidence:
        res = []
        for ev in evidence:
            dur = ev.get("duration") or (format_duration(int(ev["duration_s"])) if ev.get("duration_s") else "")
            res.append(TrendCard(
                topic=str(ev.get("title") or record.topic)[:300], source_name=record.source_name, source_url=record.source_url,
                observed_at=record.observed_at, metric_value=(float(ev["views"]) if ev.get("views") is not None else None),
                evidence=[ev], category_id=category_id, query=record.topic,
                duration_text=str(dur or ""),
            ))
        return res
    dur = ""
    if evidence:
        ev0 = evidence[0]
        dur = ev0.get("duration") or (format_duration(int(ev0["duration_s"])) if ev0.get("duration_s") else "")
    return [TrendCard(
        topic=record.topic, source_name=record.source_name, source_url=record.source_url, observed_at=record.observed_at,
        metric_value=record.metric_value, evidence=evidence[:1], category_id=category_id, query=None,
        duration_text=str(dur or ""),
    )]


def build_trend_cards(
    records: Iterable[Any],
    *,
    per_channel: int = MAX_CARDS_PER_CHANNEL,
    now: datetime | None = None,
    recent_channel_titles: list[str] | None = None,
) -> list[TrendCard]:
    ref_now = now or datetime.now(timezone.utc)
    latest: dict[str, TrendCard] = {}
    for record in records:
        for card in _cards_of(record):
            key = video_identity(card.topic, card.evidence)
            kept = latest.get(key)
            if kept is None or card.observed_at > kept.observed_at:
                latest[key] = card

    cat_views: dict[str | None, list[float]] = defaultdict(list)
    all_views: list[float] = []
    for card in latest.values():
        if card.metric_value is not None and card.metric_value > 0:
            cat_views[card.category_id].append(float(card.metric_value))
            all_views.append(float(card.metric_value))

    overall_median = statistics.median(all_views) if all_views else 1.0
    cat_medians: dict[str | None, float] = {}
    for cat_id, v_list in cat_views.items():
        cat_medians[cat_id] = statistics.median(v_list) if v_list else overall_median

    enriched: dict[str, TrendCard] = {}
    for key, card in latest.items():
        ev = card.evidence[0] if card.evidence else {}
        published_at = _parse_published_at(ev, card.observed_at)
        views = int(card.metric_value or 0)

        if published_at is not None:
            pub = published_at
            if pub.tzinfo is None and ref_now.tzinfo is not None:
                pub = pub.replace(tzinfo=timezone.utc)
            elif pub.tzinfo is not None and ref_now.tzinfo is None:
                pub = pub.replace(tzinfo=None)
            delta_s = max(0.0, (ref_now - pub).total_seconds())
            hours = max(1.0, delta_s / 3600.0)
        else:
            hours = 24.0

        views_per_hour = max(0.0, float(views)) / hours
        velocity_text = format_velocity(views_per_hour)

        median = cat_medians.get(card.category_id, overall_median)
        niche_ratio = max(0.0, float(views)) / max(1.0, median)
        niche_ratio_text = format_niche_ratio(niche_ratio)

        is_trending = ("Em Alta" in card.source_name) or (card.query is None and card.source_name != SEARCH_SOURCE)
        has_category = bool(card.category_id)

        breakdown = calculate_priority(
            views=views,
            published_at=published_at,
            niche_median_views=median,
            is_trending_chart=is_trending,
            has_category=has_category,
            recent_channel_titles=recent_channel_titles or [],
            title=card.topic,
            now=ref_now,
        )

        dur = card.duration_text or str(ev.get("duration") or "")
        if not dur and ev.get("duration_s"):
            dur = format_duration(int(ev["duration_s"]))

        enriched[key] = dataclasses.replace(
            card,
            priority_score=breakdown.total_score,
            priority_summary=breakdown.summary,
            priority_breakdown=breakdown,
            risk_status=breakdown.risk_status,
            risk_level=breakdown.risk_level,
            is_evergreen=breakdown.is_evergreen,
            velocity_text=velocity_text,
            niche_ratio_text=niche_ratio_text,
            duration_text=dur,
            views_per_hour=views_per_hour,
            niche_ratio=niche_ratio,
        )

    ordered = sorted(enriched.values(), key=lambda c: (-(c.metric_value if c.metric_value is not None else -1.0),
                                                       -c.observed_at.timestamp(), c.topic))
    if per_channel <= 0:
        return ordered
    taken: dict[str, int] = {}
    cards: list[TrendCard] = []
    for card in ordered:
        channel = card.channel.casefold()
        if channel:
            if taken.get(channel, 0) >= per_channel:
                continue
            taken[channel] = taken.get(channel, 0) + 1
        cards.append(card)
    return cards
