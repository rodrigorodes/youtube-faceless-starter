"""Benchmark audiovisual (RP-031) — honestidade das métricas rotuladas Real/Estimado.

As metas do pedido são **alvo a medir**, não promessa (design §9). Este teste prova que o
resumo só rotula ``Real`` o que foi medido, e que a ausência de medição de custo/cache sai
como ``Estimado`` com valor ``None`` — nunca um zero disfarçado de resultado.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.benchmark import (  # noqa: E402
    ESTIMATED,
    REAL,
    BenchmarkSample,
    summarize,
)


def by_name(metrics):
    return {metric.name: metric for metric in metrics}


def test_render_time_and_failure_rate_are_real_measured_values():
    metrics = by_name(summarize([
        BenchmarkSample(video_seconds=3.0, render_seconds=6.0, qa_passed=True),
        BenchmarkSample(video_seconds=3.0, render_seconds=9.0, qa_passed=False),
    ]))
    assert metrics["render_seconds_per_video_minute"].label == REAL
    assert metrics["render_seconds_per_video_minute"].value == 150.0  # 15 s de render / 0,1 min de vídeo
    assert metrics["failure_rate"].label == REAL and metrics["failure_rate"].value == 0.5


def test_cost_and_cache_without_measurement_are_estimated_without_a_number():
    metrics = by_name(summarize([BenchmarkSample(video_seconds=3.0, render_seconds=6.0, qa_passed=True)]))
    cost, cache = metrics["cost_per_video_minute"], metrics["cache_hit_rate"]
    assert cost.label == ESTIMATED and cost.value is None and cost.note
    assert cache.label == ESTIMATED and cache.value is None and cache.note


def test_measured_cost_and_cache_become_real():
    metrics = by_name(summarize([
        BenchmarkSample(video_seconds=30.0, render_seconds=60.0, qa_passed=True,
                        cost_usd=0.5, cache_hits=3, cache_lookups=4),
        BenchmarkSample(video_seconds=30.0, render_seconds=60.0, qa_passed=True,
                        cost_usd=0.5, cache_hits=1, cache_lookups=4),
    ]))
    assert metrics["cost_per_video_minute"].label == REAL and metrics["cost_per_video_minute"].value == 1.0
    assert metrics["cache_hit_rate"].label == REAL and metrics["cache_hit_rate"].value == 0.5


def test_no_samples_never_invents_a_zero():
    metrics = by_name(summarize([]))
    assert all(metric.value is None for metric in metrics.values())
    assert metrics["render_seconds_per_video_minute"].label == REAL  # o rótulo é da natureza da métrica
