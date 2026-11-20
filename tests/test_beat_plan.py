import math

import pytest

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


# ---------- núcleo numérico: plan_beat_windows ----------


def test_empty_beat_list_is_rejected():
    with pytest.raises(ValueError):
        plan_beat_windows(5.0, [])


@pytest.mark.parametrize("duration", [0, -1.0, math.inf, -math.inf, math.nan, None, True, "5"])
def test_invalid_scene_duration_is_rejected(duration):
    with pytest.raises(ValueError):
        plan_beat_windows(duration, [1.0])


@pytest.mark.parametrize("span", [0, -1.0, math.inf, -math.inf, math.nan, None, True, "1"])
def test_invalid_beat_duration_is_rejected(span):
    with pytest.raises(ValueError):
        plan_beat_windows(5.0, [span])


def test_beats_exceeding_scene_are_rejected():
    with pytest.raises(ValueError):
        plan_beat_windows(5.0, [3.0, 3.0])


def test_beats_not_covering_scene_are_rejected():
    with pytest.raises(ValueError):
        plan_beat_windows(5.0, [1.0, 1.0])


def test_single_beat_covers_whole_scene():
    assert plan_beat_windows(5.0, [5.0]) == ((0.0, 5.0),)


def test_windows_are_contiguous_in_input_order():
    assert plan_beat_windows(9.0, [2.0, 3.0, 4.0]) == ((0.0, 2.0), (2.0, 5.0), (5.0, 9.0))


def test_tolerance_absorbs_floating_residue_and_closes_scene():
    windows = plan_beat_windows(1.0, [1 / 3, 1 / 3, 1 / 3])
    assert windows[-1][1] == pytest.approx(1.0)
    assert windows[-1][1] == 1.0
    assert windows[1] == (pytest.approx(1 / 3), pytest.approx(2 / 3))


def test_default_tolerance_is_small_and_positive():
    assert 0 < DEFAULT_TOLERANCE_S < 1e-3


# ---------- regra por cena: plan_scene_beats ----------


def test_plan_requires_at_least_one_beat():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(9.0), [])


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


def test_single_beat_covers_scene():
    source = beat(4.0, reference="only")
    plan = plan_scene_beats(scene(4.0), [source])
    assert isinstance(plan, SceneBeatPlan)
    assert plan.scene_id == "scene-1"
    assert plan.duration_s == 4.0
    assert [(b.start_s, b.end_s) for b in plan.beats] == [(0.0, 4.0)]
    assert plan.beats[0].reference == "only"
    assert plan.coverage_s == 4.0
    assert plan.beats[0] is not source  # reposicionado, não mutado


def test_multiple_distinct_beats_are_distributed_in_order():
    beats = [beat(2.0, reference="a"), beat(3.0, reference="b"), beat(4.0, reference="c")]
    plan = plan_scene_beats(scene(9.0), beats)
    assert [b.reference for b in plan.beats] == ["a", "b", "c"]
    assert [(b.start_s, b.end_s) for b in plan.beats] == [(0.0, 2.0), (2.0, 5.0), (5.0, 9.0)]
    assert plan.coverage_s == 9.0
    assert plan.beats[-1].end_s == 9.0


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


def test_invalid_tolerance_is_rejected():
    with pytest.raises(ValueError):
        plan_scene_beats(scene(3.0), [beat(3.0)], tolerance_s=-1)
