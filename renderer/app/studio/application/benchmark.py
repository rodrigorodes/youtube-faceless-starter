"""Métricas do benchmark audiovisual (RP-031) — puro, sem I/O.

As metas do pedido (§10) são **alvo a medir**, não promessa (design §9): este módulo
computa só o que foi **medido** e rotula cada métrica como **Real** (número medido) ou
**Estimado** (sem medição). Sem medição o valor é ``None`` — nunca um número inventado.
O custo de provedor e o cache hit dependem de peças fora deste escopo (o cache de render
é RP-06); quando não há medição, eles saem como **Estimado** com valor ausente e nota
explícita, em vez de zero disfarçado de resultado.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

REAL = "Real"
ESTIMATED = "Estimado"


@dataclass(frozen=True)
class Metric:
    """Uma métrica rotulada: ``value`` é medido (Real) ou ausente (Estimado)."""

    name: str
    unit: str
    label: str
    value: float | None
    note: str = ""


@dataclass(frozen=True)
class BenchmarkSample:
    """Uma execução de render medida: segundos de vídeo, de parede e desfecho do QA.

    ``cost_usd`` só entra se foi medido (senão ``None``). ``cache_hits``/``cache_lookups``
    só entram se o caminho persistiu cache (hoje não): ausentes viram métrica Estimada.
    """

    video_seconds: float
    render_seconds: float
    qa_passed: bool
    cost_usd: float | None = None
    cache_hits: int | None = None
    cache_lookups: int | None = None


def summarize(samples: Sequence[BenchmarkSample]) -> tuple[Metric, ...]:
    """Resume as amostras em quatro métricas rotuladas Real/Estimado.

    Sem amostras as frações ficam ``None`` (não medido), não zero.
    """
    rows = tuple(samples)
    total_video = sum(sample.video_seconds for sample in rows)
    total_render = sum(sample.render_seconds for sample in rows)
    minutes = total_video / 60.0

    render_per_minute = total_render / minutes if rows and minutes > 0 else None
    failure_rate = (sum(1 for sample in rows if not sample.qa_passed) / len(rows)) if rows else None

    costs = [sample.cost_usd for sample in rows]
    cost_measured = bool(rows) and all(cost is not None for cost in costs)
    cost_per_minute = (sum(costs) / minutes) if cost_measured and minutes > 0 else None

    lookups = [sample.cache_lookups for sample in rows]
    hits = [sample.cache_hits for sample in rows]
    cache_measured = (bool(rows) and all(value is not None for value in lookups)
                      and sum(lookups) > 0)
    cache_hit_rate = (sum(hits) / sum(lookups)) if cache_measured else None

    return (
        Metric("render_seconds_per_video_minute", "s/min", REAL, render_per_minute),
        Metric("failure_rate", "fração", REAL, failure_rate),
        Metric(
            "cost_per_video_minute", "USD/min",
            REAL if cost_measured else ESTIMATED, cost_per_minute,
            "" if cost_measured else "sem medição de custo de provedor neste benchmark",
        ),
        Metric(
            "cache_hit_rate", "fração",
            REAL if cache_measured else ESTIMATED, cache_hit_rate,
            "" if cache_measured else "cache de render é RP-06; não medi no caminho de render",
        ),
    )
