"""RP-010 — ponte exata entre segundos (autoria) e ticks inteiros (plano).

A autoria humana (`VisualBeat`/`beat_plan`) trabalha em segundos float; o
`RenderPlan` mede em ticks inteiros. Estes testes provam que a conversão:

1. arredonda ao tick mais próximo com o valor binário exato do float;
2. é idempotente no round-trip `ticks -> segundos -> ticks` (sem deriva);
3. preserva contiguidade e cobertura ao converter janelas de `plan_scene_beats`;
4. rejeita um span menor que meio tick com erro claro (não emite janela vazia),
   espelhando a política da fatia B.
"""
import math
import random

import pytest

from app.studio.domain.beat_plan import plan_scene_beats
from app.studio.domain.contracts import Scene
from app.studio.domain.ticks import (
    seconds_to_ticks,
    tick_windows,
    ticks_to_seconds,
)
from app.studio.domain.visual_beat import VisualBeat


# --------------------------------------------------------------------------- #
# Conversão pontual
# --------------------------------------------------------------------------- #

def test_seconds_to_ticks_rounds_to_nearest_tick():
    assert seconds_to_ticks(0.0, 25) == 0
    assert seconds_to_ticks(1.0, 25) == 25
    assert seconds_to_ticks(0.021, 25) == 1
    assert seconds_to_ticks(0.019, 25) == 0
    assert seconds_to_ticks(2.0, 25) == 50


def test_ticks_to_seconds_is_plain_division():
    assert ticks_to_seconds(25, 25) == 1.0
    assert ticks_to_seconds(50, 25) == 2.0
    assert ticks_to_seconds(3, 1) == 3.0


@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan, True, "1", None])
def test_seconds_to_ticks_rejects_non_numbers(bad):
    with pytest.raises(ValueError):
        seconds_to_ticks(bad, 25)


@pytest.mark.parametrize("bad", [0, -1, True, 25.0, "25", None])
def test_conversion_rejects_bad_tick_rate(bad):
    with pytest.raises(ValueError):
        seconds_to_ticks(1.0, bad)
    with pytest.raises(ValueError):
        ticks_to_seconds(1, bad)


@pytest.mark.parametrize("bad", [1.0, True, "1", None])
def test_ticks_to_seconds_rejects_non_integer_ticks(bad):
    with pytest.raises(ValueError):
        ticks_to_seconds(bad, 25)


# --------------------------------------------------------------------------- #
# Round-trip sem deriva
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("tps", [1, 24, 25, 30, 50, 1000, 30000])
def test_round_trip_is_identity_for_a_range_of_rates(tps):
    ticks = list(range(0, 500)) + [10**6, 10**9, 25 * 10**6, 2**40]
    for t in ticks:
        assert seconds_to_ticks(ticks_to_seconds(t, tps), tps) == t


def test_round_trip_fuzz_is_identity():
    rng = random.Random(20261120)
    rates = [1, 24, 25, 30, 50, 60, 1000, 30000]
    for _ in range(5000):
        tps = rng.choice(rates)
        t = rng.randint(0, 10**8)
        assert seconds_to_ticks(ticks_to_seconds(t, tps), tps) == t


# --------------------------------------------------------------------------- #
# Janelas: conversão, contiguidade e cobertura
# --------------------------------------------------------------------------- #

def test_tick_windows_convert_contiguous_windows_and_close_the_duration():
    windows = [(0.0, 2.0), (2.0, 5.0)]
    assert tick_windows(windows, 25, duration_s=5.0) == ((0, 50), (50, 125))


def test_tick_windows_ignore_duration_when_absent():
    assert tick_windows([(0.0, 1.0)], 25) == ((0, 25),)


def test_tick_windows_reject_a_span_below_half_a_tick():
    # 1e-9 s < meio tick (1/50 s) em 25 ticks/s: viraria a janela (25, 25).
    with pytest.raises(ValueError, match="not representable"):
        tick_windows([(0.0, 1.0), (1.0, 1.0 + 1e-9)], 25)


def test_tick_windows_reject_contiguity_break():
    with pytest.raises(ValueError, match="contigu"):
        tick_windows([(0.0, 1.0), (1.5, 2.0)], 25)


def test_tick_windows_reject_coverage_drift():
    with pytest.raises(ValueError, match="coverage|ends at"):
        tick_windows([(0.0, 1.0)], 25, duration_s=2.0)


@pytest.mark.parametrize("bad", [5.0, 42, None])
def test_tick_windows_reject_non_pairs(bad):
    with pytest.raises(ValueError):
        tick_windows(bad, 25)


# --------------------------------------------------------------------------- #
# Ponte com a fatia B: plan_scene_beats -> ticks sem reintroduzir deriva
# --------------------------------------------------------------------------- #

def _beat(scene_id, duration, reference):
    return VisualBeat(
        scene_id=scene_id,
        start_s=0.0,
        end_s=duration,
        asset_kind="stock",
        reference=reference,
        provenance="Pexels",
        license="Pexels license",
    )


def _contract_scene(duration_s, scene_id="scene-1"):
    return Scene(
        id=scene_id,
        video_id="video-1",
        idx=0,
        narration="Narração de teste com cinco palavras.",
        image_prompt="A detailed test image prompt for the scene",
        duration_s=duration_s,
    )


def test_beat_plan_windows_convert_without_drift():
    scene = _contract_scene(9.0)
    beats = [_beat("scene-1", 2.0, "a"), _beat("scene-1", 3.0, "b"), _beat("scene-1", 4.0, "c")]
    plan = plan_scene_beats(scene, beats)
    windows = [(b.start_s, b.end_s) for b in plan.beats]
    ticks = tick_windows(windows, 25, duration_s=plan.duration_s)
    assert ticks == ((0, 50), (50, 125), (125, 225))
    assert ticks[-1][1] == seconds_to_ticks(plan.duration_s, 25)
    # quantos ticks cada janela cobre: soma == duração, sem sobra nem buraco
    assert sum(end - start for start, end in ticks) == seconds_to_ticks(plan.duration_s, 25)


def test_beat_plan_conversion_keeps_contiguity_and_coverage_under_fuzz():
    rng = random.Random(7)
    for _ in range(1500):
        frames = rng.randint(50, 2500)          # duração alinhada a quadro, >= 2 s
        duration_s = frames / 25
        scene_id = "scene-fuzz"
        count = rng.randint(1, 8)
        weights = [rng.uniform(0.5, 3.0) for _ in range(count)]
        total = sum(weights)
        target = duration_s - 1e-9                              # sobra dentro da tolerância do beat_plan
        spans = [w / total * target for w in weights]
        if min(spans) < 0.02:                     # cada beat precisa caber em >= 1 tick
            continue
        beats = [_beat(scene_id, span, f"ref-{i}") for i, span in enumerate(spans)]
        plan = plan_scene_beats(_contract_scene(duration_s, scene_id), beats)
        windows = [(b.start_s, b.end_s) for b in plan.beats]
        ticks = tick_windows(windows, 25, duration_s=duration_s)   # rejeita contiguidade/cobertura quebradas
        assert ticks[0][0] == 0
        assert ticks[-1][1] == seconds_to_ticks(duration_s, 25)
        # conversão bit-exata: voltar para segundos e reconverter não muda nada
        for start, end in ticks:
            assert seconds_to_ticks(ticks_to_seconds(start, 25), 25) == start
            assert seconds_to_ticks(ticks_to_seconds(end, 25), 25) == end
