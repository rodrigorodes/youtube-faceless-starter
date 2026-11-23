"""Do que foi coletado ao que a tela mostra: um cartão por VÍDEO, sem repetição e com variedade de canais (sem I/O).

A coleta grava linhas novas a cada "Buscar agora" (a chave inclui a hora da coleta) e a busca por termo grava UMA linha
com até vários vídeos. Mostrar isso cru gera o mesmo vídeo repetido e um cartão por termo que esconde os outros
vídeos. Aqui:
  1. a linha da busca por termo vira um cartão por vídeo (o título do vídeo é o tema; o termo fica em `query`);
  2. o mesmo vídeo coletado várias vezes fica só com a coleta mais recente;
  3. um canal ocupa no máximo `per_channel` cartões (os mais vistos), para a lista não virar um canal só.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

SEARCH_SOURCE = "YouTube Data API"
MAX_CARDS_PER_CHANNEL = 2
_VIDEO_ID = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{6,})")


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

    @property
    def channel(self) -> str:
        return str((self.evidence[0].get("channel") if self.evidence else "") or "").strip()


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
        return [TrendCard(
            topic=str(ev.get("title") or record.topic)[:300], source_name=record.source_name, source_url=record.source_url,
            observed_at=record.observed_at, metric_value=(float(ev["views"]) if ev.get("views") is not None else None),
            evidence=[ev], category_id=category_id, query=record.topic,
        ) for ev in evidence]
    return [TrendCard(
        topic=record.topic, source_name=record.source_name, source_url=record.source_url, observed_at=record.observed_at,
        metric_value=record.metric_value, evidence=evidence[:1], category_id=category_id, query=None,
    )]


def build_trend_cards(records: Iterable[Any], *, per_channel: int = MAX_CARDS_PER_CHANNEL) -> list[TrendCard]:
    latest: dict[str, TrendCard] = {}
    for record in records:
        for card in _cards_of(record):
            key = video_identity(card.topic, card.evidence)
            kept = latest.get(key)
            if kept is None or card.observed_at > kept.observed_at:
                latest[key] = card
    ordered = sorted(latest.values(), key=lambda c: (-(c.metric_value if c.metric_value is not None else -1.0),
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
