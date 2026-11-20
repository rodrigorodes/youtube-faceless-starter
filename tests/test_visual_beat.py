import math

import pytest
from pydantic import ValidationError

from app.studio.domain.visual_beat import VisualBeat


def beat(**changes):
    values = {
        "scene_id": "scene-1",
        "start_s": 0,
        "end_s": 2.5,
        "asset_kind": "stock",
        "reference": "asset-1",
        "provenance": "Pexels",
        "license": "Pexels license",
    }
    values.update(changes)
    return VisualBeat(**values)


@pytest.mark.parametrize("kind", ["stock", "ai_image", "ai_clip", "diagram", "screen_capture"])
def test_media_beats_preserve_provenance_and_license(kind):
    result = beat(asset_kind=kind, transition="crossfade")
    assert (result.asset_kind, result.provenance, result.license, result.transition) == (
        kind, "Pexels", "Pexels license", "crossfade",
    )


def test_local_text_animation_needs_no_provenance_or_license():
    result = beat(asset_kind="text_animation", provenance=None, license=None)
    assert result.start_s == 0
    assert result.end_s == 2.5
    assert result.provenance is None
    assert result.license is None


@pytest.mark.parametrize("kind", ["stock", "ai_image", "ai_clip", "diagram", "screen_capture"])
@pytest.mark.parametrize("field", ["provenance", "license"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_media_requires_nonblank_provenance_and_license(kind, field, value):
    with pytest.raises(ValidationError):
        beat(asset_kind=kind, **{field: value})


@pytest.mark.parametrize("field", ["scene_id", "reference", "transition", "provenance", "license"])
def test_supplied_strings_must_not_be_blank(field):
    with pytest.raises(ValidationError):
        beat(asset_kind="text_animation", **{field: "  "})


@pytest.mark.parametrize("field", ["start_s", "end_s"])
@pytest.mark.parametrize("value", [-1, math.inf, -math.inf, math.nan, True, "1", None])
def test_invalid_times_are_rejected(field, value):
    with pytest.raises(ValidationError):
        beat(**{field: value})


@pytest.mark.parametrize("start,end", [(0, 0), (2, 1), (2, 2)])
def test_interval_must_have_positive_duration(start, end):
    with pytest.raises(ValidationError):
        beat(start_s=start, end_s=end)


def test_unknown_kind_and_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        beat(asset_kind="audio")
    with pytest.raises(ValidationError):
        beat(unexpected="value")


def test_contract_cannot_be_mutated_into_invalid_state():
    result = beat()
    with pytest.raises(ValidationError):
        result.end_s = -1


def test_round_trip_preserves_contract():
    original = beat()
    assert VisualBeat.model_validate_json(original.model_dump_json()) == original
