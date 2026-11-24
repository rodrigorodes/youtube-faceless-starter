"""Testes de contrato do RenderPlan v2 e upconversion (Onda 1 - Fundação).

Valida:
- AudioMix (modelo, defaults, validação, imutabilidade)
- Transition (cut, crossfade, fade, none e duração correspondente)
- Shot.asset_offset_ticks (default 0, valores positivos, rejeição de negativos)
- RenderPlan (audio_mix default, schema_version 1 e 2 suportados, 3+ rejeitados)
- upconvert_v1_to_v2 (conversão sem mutação, injeção de audio_mix, bump de schema_version)
"""
import copy
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.render_plan import (  # noqa: E402
    AssetReference,
    AudioMix,
    Output,
    Provenance,
    RenderPlan,
    Scene,
    Shot,
    StyleSnapshot,
    Timebase,
    Timeline,
    Track,
    Transition,
    upconvert_v1_to_v2,
)

SHA_A = "a" * 64


def make_asset(asset_id="asset-image-01", **overrides):
    data = dict(
        asset_id=asset_id,
        asset_version=1,
        uri="storage/img/asset-image-01.png",
        content_sha256=SHA_A,
        media_type="image",
    )
    data.update(overrides)
    return AssetReference(**data)


def make_shot(**overrides):
    data = dict(
        shot_id="shot-01",
        track_id="visual-main",
        start_tick=0,
        duration_ticks=250,
        asset_ref="asset-image-01",
    )
    data.update(overrides)
    return Shot(**data)


def make_scene(**overrides):
    data = dict(scene_id="scene-01", start_tick=0, duration_ticks=250, shots=[make_shot()])
    data.update(overrides)
    return Scene(**data)


def make_timeline(**overrides):
    data = dict(
        timebase=Timebase(ticks_per_second=25),
        tracks=[Track(track_id="visual-main", kind="visual")],
        scenes=[make_scene()],
    )
    data.update(overrides)
    return Timeline(**data)


def make_plan(**overrides):
    data = dict(
        plan_id="plan-01",
        revision=1,
        project_id="project-01",
        video_id="video-01",
        output=Output(format=VideoFormat.short, width=1080, height=1920),
        timeline=make_timeline(),
        asset_manifest=[make_asset()],
        style_snapshot=StyleSnapshot(style_id="channel-01", version=3),
        provenance=Provenance(builder_version="1.0.0"),
    )
    data.update(overrides)
    return RenderPlan(**data)


# ===========================================================================
# AudioMix
# ===========================================================================


def test_audio_mix_defaults():
    mix = AudioMix()
    assert mix.music_gain == 0.40
    assert mix.ducking_threshold == 0.02
    assert mix.ducking_ratio == 10.0
    assert mix.afade_in_s == 0.25
    assert mix.afade_out_s == 0.25
    assert mix.loudnorm_i == -16.0
    assert mix.loudnorm_tp == -1.5
    assert mix.loudnorm_lra == 11.0


def test_audio_mix_custom_values_and_immutability():
    mix = AudioMix(
        music_gain=0.25,
        ducking_threshold=0.05,
        ducking_ratio=8.0,
        afade_in_s=0.5,
        afade_out_s=0.5,
        loudnorm_i=-14.0,
        loudnorm_tp=-1.0,
        loudnorm_lra=9.0,
    )
    assert mix.music_gain == 0.25
    assert mix.loudnorm_i == -14.0

    with pytest.raises(Exception):
        mix.music_gain = 0.50


def test_audio_mix_forbids_extra_fields():
    with pytest.raises(ValidationError):
        AudioMix(extra_field=123)


def test_audio_mix_type_validation():
    with pytest.raises(ValidationError):
        AudioMix(music_gain="not_a_float")


# ===========================================================================
# Transition
# ===========================================================================


def test_transition_none_accepts_zero_duration_only():
    t = Transition(kind="none")
    assert t.kind == "none"
    assert t.duration_ticks == 0

    t_zero = Transition(kind="none", duration_ticks=0)
    assert t_zero.duration_ticks == 0

    with pytest.raises(ValidationError):
        Transition(kind="none", duration_ticks=5)


def test_transition_cut_accepts_zero_duration_only():
    t = Transition(kind="cut")
    assert t.kind == "cut"
    assert t.duration_ticks == 0

    t_zero = Transition(kind="cut", duration_ticks=0)
    assert t_zero.duration_ticks == 0

    with pytest.raises(ValidationError):
        Transition(kind="cut", duration_ticks=5)


def test_transition_fade_requires_positive_duration():
    t = Transition(kind="fade", duration_ticks=10)
    assert t.kind == "fade"
    assert t.duration_ticks == 10

    with pytest.raises(ValidationError):
        Transition(kind="fade")

    with pytest.raises(ValidationError):
        Transition(kind="fade", duration_ticks=0)


def test_transition_crossfade_requires_positive_duration():
    t = Transition(kind="crossfade", duration_ticks=15)
    assert t.kind == "crossfade"
    assert t.duration_ticks == 15

    with pytest.raises(ValidationError):
        Transition(kind="crossfade")

    with pytest.raises(ValidationError):
        Transition(kind="crossfade", duration_ticks=0)


def test_transition_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        Transition(kind="dissolve", duration_ticks=10)


# ===========================================================================
# Shot.asset_offset_ticks
# ===========================================================================


def test_shot_asset_offset_ticks_default_zero():
    s = make_shot()
    assert s.asset_offset_ticks == 0


def test_shot_asset_offset_ticks_positive_value():
    s = make_shot(asset_offset_ticks=50)
    assert s.asset_offset_ticks == 50


def test_shot_asset_offset_ticks_rejects_negative():
    with pytest.raises(ValidationError):
        make_shot(asset_offset_ticks=-1)


def test_shot_asset_offset_ticks_rejects_non_integer():
    with pytest.raises(ValidationError):
        make_shot(asset_offset_ticks=2.5)


# ===========================================================================
# RenderPlan v2 & Backwards Compatibility
# ===========================================================================


def test_render_plan_defaults_to_v2_with_default_audio_mix():
    p = make_plan()
    assert p.schema_version == 2
    assert p.audio_mix == AudioMix()


def test_render_plan_accepts_custom_audio_mix():
    custom_mix = AudioMix(music_gain=0.15)
    p = make_plan(audio_mix=custom_mix)
    assert p.audio_mix.music_gain == 0.15


def test_render_plan_accepts_schema_version_1():
    p = make_plan(schema_version=1)
    assert p.schema_version == 1
    assert p.audio_mix == AudioMix()


def test_render_plan_accepts_schema_version_2():
    p = make_plan(schema_version=2)
    assert p.schema_version == 2


def test_render_plan_rejects_unsupported_schema_versions():
    with pytest.raises(ValidationError):
        make_plan(schema_version=0)
    with pytest.raises(ValidationError):
        make_plan(schema_version=3)
    with pytest.raises(ValidationError):
        make_plan(schema_version=99)


# ===========================================================================
# upconvert_v1_to_v2
# ===========================================================================


def test_upconvert_v1_to_v2_adds_audio_mix_and_sets_version_2():
    v1_plan = make_plan(schema_version=1)
    v1_dict = v1_plan.model_dump(mode="json")
    v1_dict["schema_version"] = 1
    v1_dict.pop("audio_mix", None)

    original_copy = copy.deepcopy(v1_dict)
    v2_dict = upconvert_v1_to_v2(v1_dict)

    # Imutabilidade da entrada
    assert v1_dict == original_copy

    # Transformação
    assert v2_dict["schema_version"] == 2
    assert "audio_mix" in v2_dict
    assert v2_dict["audio_mix"] == AudioMix().model_dump(mode="json")

    # O dict resultante valida perfeitamente em RenderPlan
    restored = RenderPlan.model_validate(v2_dict)
    assert restored.schema_version == 2
    assert restored.audio_mix == AudioMix()


def test_upconvert_v1_to_v2_preserves_existing_audio_mix():
    custom_mix_dict = AudioMix(music_gain=0.10).model_dump(mode="json")
    v1_dict = make_plan(schema_version=1).model_dump(mode="json")
    v1_dict["schema_version"] = 1
    v1_dict["audio_mix"] = custom_mix_dict

    v2_dict = upconvert_v1_to_v2(v1_dict)
    assert v2_dict["schema_version"] == 2
    assert v2_dict["audio_mix"]["music_gain"] == 0.10


def test_upconvert_v1_to_v2_rejects_invalid_schema_version():
    with pytest.raises(ValueError, match="schema_version"):
        upconvert_v1_to_v2({"schema_version": 99})
