"""Domínio do estilo visual (VS-01): parâmetros, extensão (`extra`) e versionamento. Puro."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.render_plan import Motion  # noqa: E402
from app.studio.domain.visual_style import (  # noqa: E402
    MOTIONS,
    VisualStyle,
    VisualStyleNameInvalid,
    VisualStyleParamsInvalid,
    VisualStyleVersionInvalid,
    clean_params,
)

SID = "a" * 32


def style(**kwargs):
    return VisualStyle(id=SID, name="Documentário Cinemático", **kwargs)


def test_minimal_style_has_no_params_and_version_one():
    s = style()
    assert s.params == {} and s.version == 1 and s.archived is False and s.organization_id is None


def test_motions_mirror_the_plan_contract_not_a_copy():
    # A lista válida de movimento é a do contrato do plano: se o plano ganhar um movimento,
    # o estilo acompanha sem edição (uma fonte só).
    from typing import get_args

    assert MOTIONS == frozenset(get_args(Motion))


def test_valid_params_round_trip():
    params = {
        "motion": ["zoom_in", "zoom_out", "pan_right", "pan_left"],
        "music": {"bpm": 122, "seed": 7},
        "transition": {"kind": "fade", "duration_ticks": 8},
        "caption": {"font_size": 58, "bottom": 1560},
        "palette": {"caption_text": "#FFFFFF", "caption_box": "#000000A5", "accent": "#FF008C"},
        "voice": {"model": "pt_BR-faber-medium"},
        "extra": {"lut": "warm"},
    }
    assert style(params=params).params == params


def test_motion_deduplicates_and_rejects_unknown():
    assert clean_params({"motion": ["zoom_in", "zoom_in"]})["motion"] == ["zoom_in"]
    with pytest.raises(VisualStyleParamsInvalid, match="motion"):
        clean_params({"motion": ["nope"]})
    with pytest.raises(VisualStyleParamsInvalid, match="motion"):
        clean_params({"motion": []})
    with pytest.raises(VisualStyleParamsInvalid, match="motion"):
        clean_params({"motion": "zoom_in"})


def test_music_bounds_and_requires_a_field():
    assert clean_params({"music": {"bpm": 120}})["music"] == {"bpm": 120}
    assert clean_params({"music": {"seed": 3}})["music"] == {"seed": 3}
    for bad in ({"bpm": 10}, {"bpm": 400}, {}):
        with pytest.raises(VisualStyleParamsInvalid, match="music"):
            clean_params({"music": bad})


def test_transition_none_has_no_duration_and_fade_needs_one():
    assert clean_params({"transition": {"kind": "none"}})["transition"] == {"kind": "none", "duration_ticks": 0}
    assert clean_params({"transition": {"kind": "fade", "duration_ticks": 8}})["transition"]["kind"] == "fade"
    with pytest.raises(VisualStyleParamsInvalid, match="transition"):
        clean_params({"transition": {"kind": "none", "duration_ticks": 5}})
    with pytest.raises(VisualStyleParamsInvalid, match="transition"):
        clean_params({"transition": {"kind": "fade"}})
    with pytest.raises(VisualStyleParamsInvalid, match="transition"):
        clean_params({"transition": {"kind": "wipe", "duration_ticks": 3}})


def test_palette_needs_hex_colors():
    assert clean_params({"palette": {"accent": "#FF008C"}})["palette"] == {"accent": "#FF008C"}
    assert clean_params({"palette": {"accent": "#FF008CAA"}})["palette"] == {"accent": "#FF008CAA"}
    with pytest.raises(VisualStyleParamsInvalid, match="palette"):
        clean_params({"palette": {"accent": "red"}})
    with pytest.raises(VisualStyleParamsInvalid, match="palette"):
        clean_params({"palette": {}})


def test_voice_requires_a_non_empty_model():
    assert clean_params({"voice": {"model": " pt_BR-faber-medium "}})["voice"] == {"model": "pt_BR-faber-medium"}
    with pytest.raises(VisualStyleParamsInvalid, match="voice"):
        clean_params({"voice": {"model": "  "}})


def test_extra_is_the_extension_escape_hatch():
    assert clean_params({"extra": {"lut": "warm", "beat_grid": [0, 1, 2]}})["extra"]["lut"] == "warm"


def test_unknown_top_level_key_is_rejected_not_silently_dropped():
    with pytest.raises(VisualStyleParamsInvalid, match="unknown params key"):
        clean_params({"colour": "#fff"})  # a extensão é `extra`, não chute


def test_params_are_a_deep_copy_isolated_from_the_caller():
    shared = {"extra": {"nested": {"x": 1}}}
    s = style(params=shared)
    s.params["extra"]["nested"]["x"] = 999
    assert shared["extra"]["nested"]["x"] == 1  # o agregado não compartilha estrutura mutável


def test_blank_or_long_name_is_refused():
    for bad in ("", "   ", "x" * 121, 42):
        with pytest.raises(VisualStyleNameInvalid):
            VisualStyle(id=SID, name=bad)


def test_version_must_be_a_positive_integer():
    for bad in (0, -1, "1", 1.5, True):
        with pytest.raises(VisualStyleVersionInvalid):
            style(version=bad)
