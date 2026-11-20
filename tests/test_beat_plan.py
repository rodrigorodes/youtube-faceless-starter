import math

import pytest
from pydantic import ValidationError

from app.studio.domain.beat_plan import (
    DEFAULT_TOLERANCE_S,
    SceneBeatPlan,
    plan_beat_windows,
    plan_scene_beats,
)
from app.studio.domain.contracts import Scene
from app.studio.domain.visual_beat import VisualBeat


def scene(duration_s=9.0, **changes):
    values = {
        "id": "scene-1",
        "video_id": "video-1",
        "idx": 0,
        "narration": "Narração de teste com cinco palavras.",
        "image_prompt": "A detailed test image prompt for the scene",
        "duration_s": duration_s,
    }
    values.update(changes)
    return Scene(**values)


def beat(duration=2.0, scene_id="scene-1", **changes):
    values = {
        "scene_id": scene_id,
        "start_s": 0,
        "end_s": duration,
        "asset_kind": "stock",
        "reference": "asset-1",
        "provenance": "Pexels",
        "license": "Pexels license",
    }
    values.update(changes)
    return VisualBeat(**values)


def assert_valid_windows(windows):
    """Contíguas, a partir de 0, finitas e com cada beat estritamente positivo."""
    assert windows, "plano não pode ser vazio"
    assert windows[0][0] == 0.0
    for start, end in windows:
        assert math.isfinite(start) and math.isfinite(end)
        assert start < end, f"span inválido: {start} -> {end}"
    for (_, prev_end), (start, end) in zip(windows, windows[1:]):
        assert prev_end == start


# ---------- núcleo numérico: plan_beat_windows ----------


def test_windows_reject_empty_beat_list():
    with pytest.raises(ValueError):
        plan_beat_windows(5.0, [])


@pytest.mark.parametrize("duration", [0, -1.0, math.inf, -math.inf, math.nan, None, True, "5"])
def test_windows_reject_invalid_scene_duration(duration):
    with pytest.raises(ValueError):
        plan_beat_windows(duration, [1.0])


@pytest.mark.parametrize("span", [0, -1.0, math.inf, -math.inf, math.nan, None, True, "1"])
def test_windows_reject_invalid_beat_duration(span):
    with pytest.raises(ValueError):
        plan_beat_windows(5.0, [span])


def test_windows_reject_beats_exceeding_scene():
    with pytest.raises(ValueError):
        plan_beat_windows(5.0, [3.0, 3.0])


def test_windows_reject_beats_not_covering_scene():
    with pytest.raises(ValueError):
        plan_beat_windows(5.0, [1.0, 1.0])


@pytest.mark.parametrize(
    "spans",
    [
        [5.0, 1e-7],        # overflow dentro de tolerance_s: NÃO pode zerar o último beat
        [5.0000005, 1e-7],  # overflow dentro de tolerance_s: NÃO pode inverter o último beat
    ],
)
def test_windows_reject_overflow_within_caller_tolerance(spans):
    # Política: excesso real é REJEITADO. `tolerance_s` só admite sobra (gap),
    # nunca overflow; a única folga de overflow é resíduo de ponto flutuante.
    with pytest.raises(ValueError):
        plan_beat_windows(5.0, spans)


def test_windows_never_emit_non_positive_span_on_float_residue():
    # Overflow que é apenas resíduo de ponto flutuante (<~1e-9) é aceito, mas
    # nenhum beat pode sair com span <= 0 nem start >= end.
    windows = plan_beat_windows(5.0, [5.0, 5e-10])
    assert_valid_windows(windows)
    assert windows[-1][1] >= 5.0


def test_windows_single_beat_covers_whole_scene():
    assert plan_beat_windows(5.0, [5.0]) == ((0.0, 5.0),)


def test_windows_are_contiguous_in_input_order():
    windows = plan_beat_windows(9.0, [2.0, 3.0, 4.0])
    assert windows == ((0.0, 2.0), (2.0, 5.0), (5.0, 9.0))
    assert_valid_windows(windows)


def test_windows_close_scene_on_floating_residue():
    windows = plan_beat_windows(1.0, [1 / 3, 1 / 3, 1 / 3])
    assert_valid_windows(windows)
    assert windows[-1][1] == 1.0  # fecha exatamente quando a soma não excede a cena
    assert windows[1] == (pytest.approx(1 / 3), pytest.approx(2 / 3))


def test_default_tolerance_is_small_and_positive():
    assert 0 < DEFAULT_TOLERANCE_S < 1e-3


@pytest.mark.parametrize("tolerance", [-1, math.inf, -math.inf, math.nan, None, True, "1"])
def test_windows_reject_invalid_tolerance(tolerance):
    with pytest.raises(ValueError):
        plan_beat_windows(3.0, [3.0], tolerance_s=tolerance)


def test_windows_reject_non_iterable_beat_durations():
    with pytest.raises(ValueError):
        plan_beat_windows(3.0, 3.0)


# ---------- regra por cena: plan_scene_beats ----------


def test_plan_requires_at_least_one_beat():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(9.0), [])


def test_plan_rejects_non_iterable_beats():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(9.0), 5)


def test_scene_without_duration_is_rejected():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(None), [beat(9.0)])


def test_scene_with_zero_duration_is_rejected():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(0.0), [beat(1.0)])


@pytest.mark.parametrize("duration", [math.inf, -math.inf, math.nan, -1.0, True, "9"])
def test_scene_with_malformed_duration_is_rejected(duration):
    # model_copy contorna a validação do contrato para simular dado inválido persistido
    malformed = scene(9.0).model_copy(update={"duration_s": duration})
    with pytest.raises(ValueError):
        plan_scene_beats(malformed, [beat(9.0)])


def test_beats_exceeding_scene_are_rejected():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(5.0), [beat(3.0), beat(3.0)])


def test_beats_not_covering_scene_are_rejected():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(5.0), [beat(1.0), beat(1.0)])


def test_plan_rejects_overflow_within_caller_tolerance():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(5.0), [beat(5.0), beat(1e-7)])


def test_single_beat_covers_scene():
    source = beat(4.0, reference="only")
    plan = plan_scene_beats(scene(4.0), [source])
    assert isinstance(plan, SceneBeatPlan)
    assert plan.scene_id == "scene-1"
    assert plan.duration_s == 4.0
    assert [(b.start_s, b.end_s) for b in plan.beats] == [(0.0, 4.0)]
    assert plan.beats[0].reference == "only"
    assert plan.coverage_s == 4.0
    assert plan.beats[0] is not source  # reconstruído, não mutado


def test_multiple_distinct_beats_are_distributed_in_order():
    beats = [beat(2.0, reference="a"), beat(3.0, reference="b"), beat(4.0, reference="c")]
    plan = plan_scene_beats(scene(9.0), beats)
    assert [b.reference for b in plan.beats] == ["a", "b", "c"]
    assert [(b.start_s, b.end_s) for b in plan.beats] == [(0.0, 2.0), (2.0, 5.0), (5.0, 9.0)]
    assert plan.duration_s == 9.0
    assert plan.coverage_s == 9.0
    # Cobertura derivada das janelas contíguas, coerente com os próprios beats.
    assert plan.coverage_s == plan.beats[-1].end_s - plan.beats[0].start_s


def test_plan_beats_are_all_valid_visual_beats():
    plan = plan_scene_beats(scene(9.0), [beat(2.0), beat(3.0), beat(4.0)])
    for placed in plan.beats:
        assert placed.start_s < placed.end_s
        assert placed.duration_s > 0
        # revalidação sobrevive ao round-trip do contrato (invariante garantida)
        assert VisualBeat.model_validate(placed.model_dump()) == placed


def test_plan_preserves_media_fields_and_scene_id():
    source = beat(3.0, asset_kind="ai_clip", reference="clip-9", transition="crossfade",
                  provenance="Veo", license="CC-BY")
    out = plan_scene_beats(scene(3.0), [source]).beats[0]
    assert (out.asset_kind, out.reference, out.transition, out.provenance, out.license) == (
        "ai_clip", "clip-9", "crossfade", "Veo", "CC-BY",
    )
    assert out.scene_id == "scene-1"


def test_beat_from_another_scene_is_rejected():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(3.0), [beat(3.0, scene_id="scene-2")])


def test_non_visual_beat_is_rejected():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(3.0), [{"scene_id": "scene-1"}])


@pytest.mark.parametrize(
    "malformed",
    [
        {"start_s": 5.0, "end_s": 3.0},  # duração negativa
        {"end_s": math.inf},             # duração não finita
        {"end_s": 0.0},                  # duração zero
    ],
)
def test_malformed_beat_span_is_rejected(malformed):
    bad = beat(2.0).model_copy(update=malformed)
    with pytest.raises(ValueError):
        plan_scene_beats(scene(9.0), [bad, beat(4.0)])


@pytest.mark.parametrize("tolerance", [-1, math.inf, -math.inf, math.nan, None, True, "1"])
def test_plan_rejects_invalid_tolerance(tolerance):
    with pytest.raises(ValueError):
        plan_scene_beats(scene(3.0), [beat(3.0)], tolerance_s=tolerance)


# ---------- magnitude / representabilidade em ponto flutuante ----------
# Política: um beat cujo span não avança o cursor (cursor + span == cursor) é
# IMPOSSÍVEL de posicionar naquela magnitude e a entrada é REJEITADA com
# ValueError claro do núcleo — nunca aceita com span 0 nem ValidationError
# enganosa do contrato.


@pytest.mark.parametrize(
    "duration,spans",
    [
        (1e16, [1e16, 1.0]),
        (2.0**53, [2.0**53, 1.0]),
        (1e16, [1e16] + [1.0] * 100),
        (1.0, [1.0, 5e-324]),                      # denormal abaixo de ulp(1.0)/2
        (1.0, [1.0, 1e-17]),
        (1e16, [1e16, math.nextafter(1.0, 0.0)]),  # 0.9999... < ulp(1e16)/2
    ],
)
def test_windows_reject_unrepresentable_span_with_clear_error(duration, spans):
    with pytest.raises(ValueError) as excinfo:
        plan_beat_windows(duration, spans)
    assert "not representable" in str(excinfo.value)


def test_windows_sequential_overshoot_beyond_residue_is_rejected():
    # A acumulação sequencial real excede o resíduo documentado -> rejeita
    # (não aceita e depois emite janelas de span 0).
    with pytest.raises(ValueError) as excinfo:
        plan_beat_windows(1e16, [1e16] + [3.0] * 5)
    assert "exceed" in str(excinfo.value)


def test_windows_reject_non_representable_span_at_fractional_magnitude():
    with pytest.raises(ValueError) as excinfo:
        plan_beat_windows(1.0, [0.5, math.ulp(0.5) / 4])
    assert "not representable" in str(excinfo.value)


def test_windows_accept_span_exactly_one_ulp_at_large_magnitude():
    windows = plan_beat_windows(1e16, [1e16, 2.0])  # ulp(1e16) == 2.0
    assert_valid_windows(windows)
    assert windows[-1][1] - windows[-1][0] == 2.0


def test_windows_accept_nextafter_just_above_half_ulp():
    span = math.nextafter(1.0, 2.0)  # > 1.0 == ulp(1e16)/2
    windows = plan_beat_windows(1e16, [1e16, span])
    assert_valid_windows(windows)
    assert windows[-1][1] - windows[-1][0] == 2.0  # arredonda para um ulp


def test_windows_small_magnitude_nextafter_is_valid():
    windows = plan_beat_windows(1.0, [0.5, math.nextafter(0.5, 0.0)])
    assert_valid_windows(windows)
    assert windows[-1][1] == 1.0  # fecha a cena absorvendo o resíduo mínimo


def test_plan_scene_beats_rejects_unrepresentable_span_with_clear_error():
    beats = [beat(1e16, reference="big"), beat(1.0, reference="tiny")]
    with pytest.raises(ValueError) as excinfo:
        plan_scene_beats(scene(1e16), beats)
    assert not isinstance(excinfo.value, ValidationError)  # erro do núcleo, não do contrato
    assert "not representable" in str(excinfo.value)


def test_plan_scene_beats_accepts_representable_span_at_large_magnitude():
    plan = plan_scene_beats(scene(1e16), [beat(1e16), beat(2.0)])
    for placed in plan.beats:
        assert placed.start_s < placed.end_s
        assert placed.duration_s > 0
