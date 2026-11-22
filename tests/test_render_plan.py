"""RP-009 — serialização, validação e round-trip do contrato do Render Plan (RP-006).

Contrato puro (`app.studio.domain.render_plan`): sem I/O, sem FFmpeg, sem banco.
Cobre as validações obrigatórias do §9 do writing-block e as decisões R1..R7/C1..C4
do design: ticks inteiros, ids únicos, shot→asset existente, duração pelo formato de
saída, fonte de áudio gerada distinta de `AssetReference` e round-trip sem perda.

A timeline (timebase racional, tracks, intervalos e sincronização) é da fatia 3 e
tem suíte própria em `tests/test_render_plan_timeline.py`; aqui ficam as bases do
contrato, já sobre o modelo estendido.
"""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import VideoFormat, load_versioned  # noqa: E402
from app.studio.domain.render_plan import (  # noqa: E402
    AssetReference,
    Composition,
    Effects,
    GeneratedAudioSource,
    NarrationCue,
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
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def asset(asset_id="asset-image-01", **overrides):
    data = dict(
        asset_id=asset_id,
        asset_version=1,
        uri="storage/img/asset-image-01.png",
        content_sha256=SHA_A,
        media_type="image",
    )
    data.update(overrides)
    return AssetReference(**data)


def shot(**overrides):
    data = dict(
        shot_id="shot-01",
        track_id="visual-main",
        start_tick=0,
        duration_ticks=250,
        asset_ref="asset-image-01",
    )
    data.update(overrides)
    return Shot(**data)


def scene(**overrides):
    data = dict(scene_id="scene-01", start_tick=0, duration_ticks=250, shots=[shot()])
    data.update(overrides)
    return Scene(**data)


def timeline(**overrides):
    data = dict(
        timebase=Timebase(ticks_per_second=25),
        tracks=[Track(track_id="visual-main", kind="visual")],
        scenes=[scene()],
    )
    data.update(overrides)
    return Timeline(**data)


def plan(**overrides):
    data = dict(
        plan_id="plan-01",
        revision=1,
        project_id="project-01",
        video_id="video-01",
        output=Output(format=VideoFormat.short, width=1080, height=1920),
        timeline=timeline(),
        asset_manifest=[asset()],
        style_snapshot=StyleSnapshot(style_id="channel-01", version=3),
        provenance=Provenance(builder_version="1.0.0"),
    )
    data.update(overrides)
    return RenderPlan(**data)


# --------------------------------------------------------------------------- #
# Serialização e round-trip
# --------------------------------------------------------------------------- #

def test_minimal_plan_is_valid_and_versioned():
    p = plan()
    assert p.schema_version == 1
    assert p.timeline.duration_ticks == 250


def test_plan_round_trips_through_json_without_loss():
    original = plan(
        asset_manifest=[asset(license="CC0", attribution="Pexels", metadata={"prompt": "x"})],
        generated_audio=[
            GeneratedAudioSource(source_id="voice-01", kind="voice", duration_ticks=250),
            GeneratedAudioSource(source_id="music-01", kind="music", duration_ticks=250,
                                 params={"bpm": 90, "seed": 7}),
        ],
        timeline=timeline(
            tracks=[Track(track_id="visual-main", kind="visual"),
                    Track(track_id="voice", kind="narration")],
            narration=[NarrationCue(scene_id="scene-01", track_id="voice", source_ref="voice-01",
                                    start_tick=0, duration_ticks=250)],
            scenes=[scene(shots=[shot(composition=Composition(fit="contain"),
                                     effects=Effects(motion="zoom_in"),
                                     transition=Transition(kind="fade", duration_ticks=6),
                                     paid_operation_key="voice:video-01:0")],
                         paid_operation_key="voice:video-01:0")],
        ),
    )
    dumped = original.model_dump_json()
    again = RenderPlan.model_validate_json(dumped)
    assert again == original
    assert again.model_dump_json() == dumped


def test_generated_audio_is_distinct_from_asset_reference():
    # C2/R3: a música é fonte gerada com parâmetros, não um AssetReference persistido.
    music = GeneratedAudioSource(source_id="music-01", kind="music", duration_ticks=250, params={"bpm": 90})
    assert not isinstance(music, AssetReference)
    assert "content_sha256" not in music.model_dump()
    with pytest.raises(ValidationError):
        # AssetReference exige hash de conteúdo (C1: cache_key não serve).
        asset(content_sha256=None)


def test_generated_music_is_representable_with_and_without_silent_track():
    # C2: `music=False` grava trilha silenciosa; o contrato representa os dois modos.
    loud = GeneratedAudioSource(source_id="music-01", kind="music", duration_ticks=250,
                                silent=False, params={"bpm": 90, "seed": 7})
    silent = GeneratedAudioSource(source_id="music-01", kind="music", duration_ticks=250, silent=True)
    assert loud.silent is False and silent.silent is True
    assert silent.params == {}


def test_silent_track_carries_no_synthesis_params_and_only_music_may_be_silent():
    with pytest.raises(ValidationError):
        GeneratedAudioSource(source_id="music-01", kind="music", duration_ticks=250,
                             silent=True, params={"bpm": 90})
    with pytest.raises(ValidationError):
        GeneratedAudioSource(source_id="voice-01", kind="voice", duration_ticks=250, silent=True)


# --------------------------------------------------------------------------- #
# Schema inválido é rejeitado
# --------------------------------------------------------------------------- #

def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        plan(surprise=1)
    with pytest.raises(ValidationError):
        shot(surprise=1)


def test_ticks_are_strict_integers_not_seconds():
    with pytest.raises(ValidationError):
        Timebase(ticks_per_second=25.0)
    with pytest.raises(ValidationError):
        shot(duration_ticks=10.0)
    with pytest.raises(ValidationError):
        shot(duration_ticks=True)


def test_missing_required_fields_are_rejected():
    with pytest.raises(ValidationError):
        RenderPlan(plan_id="plan-01", revision=1, project_id="p", video_id="v",
                   timeline=timeline(),
                   style_snapshot=StyleSnapshot(style_id="c", version=1),
                   provenance=Provenance(builder_version="1.0.0"))


def test_unknown_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        plan(schema_version=2)
    with pytest.raises(ValueError, match="schema_version"):
        load_versioned(RenderPlan, {**plan().model_dump(mode="json"), "schema_version": 2})


def test_plan_is_immutable():
    p = plan()
    with pytest.raises(Exception):
        p.revision = 2


# --------------------------------------------------------------------------- #
# IDs únicos (no escopo correto) e referências existentes
# --------------------------------------------------------------------------- #

def test_duplicate_scene_ids_are_rejected():
    with pytest.raises(ValidationError):
        timeline(scenes=[
            scene(scene_id="scene-01", start_tick=0),
            scene(scene_id="scene-01", start_tick=250, shots=[shot(shot_id="shot-02", start_tick=250)]),
        ])


def test_duplicate_shot_ids_are_rejected_within_scene():
    with pytest.raises(ValidationError):
        Scene(scene_id="scene-01", start_tick=0, duration_ticks=250, shots=[
            shot(shot_id="shot-01", start_tick=0, duration_ticks=100),
            shot(shot_id="shot-01", start_tick=100, duration_ticks=150),
        ])


def test_duplicate_asset_ids_are_rejected():
    with pytest.raises(ValidationError):
        plan(asset_manifest=[asset("asset-image-01"), asset("asset-image-01")])


def test_duplicate_generated_audio_ids_are_rejected():
    with pytest.raises(ValidationError):
        plan(generated_audio=[
            GeneratedAudioSource(source_id="music-01", kind="music", duration_ticks=250),
            GeneratedAudioSource(source_id="music-01", kind="voice", duration_ticks=250),
        ])


def test_shot_referencing_missing_asset_is_rejected():
    with pytest.raises(ValidationError):
        plan(asset_manifest=[], timeline=timeline(scenes=[
            scene(shots=[shot(asset_ref="asset-does-not-exist")])
        ]))


def test_narration_cue_referencing_missing_media_is_rejected():
    with pytest.raises(ValidationError):
        plan(
            generated_audio=[],
            timeline=timeline(
                tracks=[Track(track_id="visual-main", kind="visual"),
                        Track(track_id="voice", kind="narration")],
                narration=[NarrationCue(scene_id="scene-01", track_id="voice",
                                        source_ref="voice-missing", start_tick=0, duration_ticks=250)],
            ),
        )


def test_shot_must_fit_inside_its_scene():
    with pytest.raises(ValidationError):
        Scene(scene_id="scene-01", start_tick=0, duration_ticks=100, shots=[
            shot(shot_id="shot-01", start_tick=0, duration_ticks=100),
            shot(shot_id="shot-02", start_tick=80, duration_ticks=50),  # 130 > 100
        ])


# --------------------------------------------------------------------------- #
# Duração respeita o formato de saída
# --------------------------------------------------------------------------- #

def test_resolution_must_match_output_format():
    with pytest.raises(ValidationError):
        plan(output=Output(format=VideoFormat.short, width=1920, height=1080))


def test_duration_must_respect_output_format_limit():
    ticks = 25 * 200  # 200 s > 175 s do short
    big = scene(scene_id="scene-01", start_tick=0, duration_ticks=ticks,
                shots=[shot(duration_ticks=ticks)])
    with pytest.raises(ValidationError):
        plan(output=Output(format=VideoFormat.short, width=1080, height=1920),
             timeline=timeline(scenes=[big]))
    # o mesmo plano em `long` (1920x1080, teto 1200 s) é válido
    long_plan = plan(output=Output(format=VideoFormat.long, width=1920, height=1080),
                     timeline=timeline(scenes=[big]))
    assert long_plan.timeline.duration_ticks == ticks


# --------------------------------------------------------------------------- #
# Efeitos, disclosure e estilo (R3/R4)
# --------------------------------------------------------------------------- #

def test_motion_is_explicit_per_shot_and_defaults_to_none():
    assert shot().effects.motion == "none"
    assert shot(effects=Effects(motion="pan_right")).effects.motion == "pan_right"
    with pytest.raises(ValidationError):
        Effects(motion="index_mod_4")


def test_disclosure_lives_in_output():
    assert plan().output.disclosure == "Ilustração gerada por IA"
    assert plan(output=Output(format=VideoFormat.short, width=1080, height=1920,
                              disclosure="Imagens ilustrativas")).output.disclosure == "Imagens ilustrativas"


def test_style_snapshot_references_channel_by_key_and_version_not_object():
    snap = plan().style_snapshot
    assert snap.style_id == "channel-01" and snap.version == 3
    assert set(snap.model_dump()) == {"source", "style_id", "version"}


def test_transition_duration_is_consistent_with_kind():
    with pytest.raises(ValidationError):
        Transition(kind="none", duration_ticks=6)
    with pytest.raises(ValidationError):
        Transition(kind="fade", duration_ticks=0)
    assert Transition(kind="fade", duration_ticks=6).duration_ticks == 6


# --------------------------------------------------------------------------- #
# F03.T03: referência da configuração efetiva (aditiva e compatível)
# --------------------------------------------------------------------------- #

def test_the_config_snapshot_is_optional_and_records_hash_version_and_provenance():
    from app.studio.domain.render_plan import ConfigSnapshot

    assert plan().config_snapshot is None  # plano sem a referência continua válido

    snapshot = ConfigSnapshot(content_hash=SHA_B, schema_version=1,
                              provenance={"style": "channel", "audiovisual.music.bpm": "style"})
    documented = plan(config_snapshot=snapshot)
    assert documented.config_snapshot.content_hash == SHA_B
    assert documented.config_snapshot.schema_version == 1
    assert documented.config_snapshot.provenance["audiovisual.music.bpm"] == "style"
    restored = RenderPlan.model_validate_json(documented.model_dump_json())
    assert restored == documented


def test_a_plan_persisted_before_the_config_snapshot_still_loads():
    """Compatibilidade de leitura: documento antigo (sem o campo) valida com a referência nula."""
    old_document = plan().model_dump(mode="json")
    old_document.pop("config_snapshot")
    restored = RenderPlan.model_validate(old_document)
    assert restored.config_snapshot is None
    assert restored.schema_version == 1
