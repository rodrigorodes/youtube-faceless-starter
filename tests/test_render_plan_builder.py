"""RP-015/RP-016 — builder puro do ``RenderPlan`` (storyboard -> plano válido).

Cobre a fatia 4 (RP-03) do design: o storyboard real (``Scene`` + ``Asset`` medidas após o
TTS — R1) vira um ``RenderPlan`` válido **sem** conhecer renderer, FFmpeg nem banco; a
identidade do canal entra como ``StyleSnapshot`` por **chave + versão** (R4/RP-016), nunca
como objeto nem texto de estilo.

A ponte autoria->plano é a da fatia 3 (``domain/ticks``), com o arredondamento de quadro de
``scene_length`` (fatia B): o teste de ida-e-volta prova que o builder não reintroduz deriva.
"""
import json
import math
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.channel import ChannelProfile  # noqa: E402
from app.studio.domain.contracts import Asset, AssetKind, Scene as StoryboardRow, VideoFormat  # noqa: E402
from app.studio.domain.render import FPS, LEAD, TAIL, scene_length  # noqa: E402
from app.studio.domain.render_plan import (  # noqa: E402
    AssetReference,
    RenderPlan,
    StyleSnapshot,
    Timebase,
)
from app.studio.domain.render_plan_builder import (  # noqa: E402
    DEFAULT_TICKS_PER_SECOND,
    PlanBuildError,
    StoryboardOverlay,
    StoryboardScene,
    asset_reference_for,
    build_render_plan,
    storyboard_scene,
    style_snapshot_for_channel,
)
from app.studio.domain.ticks import seconds_to_ticks, tick_windows, ticks_to_seconds  # noqa: E402

SHA_A = "a" * 64
SHA_B = "b" * 64


def asset_ref(asset_id="asset-01", **overrides):
    data = dict(
        asset_id=asset_id,
        asset_version=1,
        uri=f"storage/img/{asset_id}.png",
        content_sha256=SHA_A,
        media_type="image",
        license="Imagem gerada por IA",
    )
    data.update(overrides)
    return AssetReference(**data)


def story(scene_id="scene-01", asset_id="asset-01", speech=2.0, narration="Primeira cena do vídeo.", **overrides):
    data = dict(scene_id=scene_id, asset_id=asset_id, narration=narration, speech_seconds=speech)
    data.update(overrides)
    return StoryboardScene(**data)


def build(**overrides):
    data = dict(
        plan_id="plan-001",
        revision=1,
        project_id="project-001",
        video_id="video-001",
        format=VideoFormat.short,
        scenes=[story()],
        assets=[asset_ref()],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=3),
        builder_version="render-plan-builder/1",
    )
    data.update(overrides)
    return build_render_plan(**data)


# --------------------------------------------------------------------------- builder


def test_builder_produces_a_valid_render_plan_from_the_storyboard():
    plan = build(scenes=[story(speech=2.0), story("scene-02", "asset-02", 3.0, "Segunda cena do vídeo.")],
                 assets=[asset_ref(), asset_ref("asset-02", content_sha256=SHA_B, uri="storage/img/asset-02.png")])

    assert isinstance(plan, RenderPlan)
    assert plan.schema_version == 2
    assert plan.plan_id == "plan-001" and plan.project_id == "project-001" and plan.video_id == "video-001"
    assert plan.output.format is VideoFormat.short
    assert (plan.output.width, plan.output.height) == (1080, 1920)
    assert plan.provenance.builder_version == "render-plan-builder/1"
    # round-trip sem perda (RP-009) sobre o plano gerado
    assert RenderPlan.model_validate_json(plan.model_dump_json()) == plan


def test_builder_lays_scenes_contiguously_in_frame_aligned_ticks():
    plan = build(scenes=[story(speech=2.0), story("scene-02", "asset-02", 3.0, "Segunda cena do vídeo.")],
                 assets=[asset_ref(), asset_ref("asset-02")])

    windows = tick_windows(
        [(0.0, scene_length(2.0)), (scene_length(2.0), scene_length(2.0) + scene_length(3.0))],
        DEFAULT_TICKS_PER_SECOND,
        duration_s=scene_length(2.0) + scene_length(3.0),
    )
    scenes = sorted(plan.timeline.scenes, key=lambda s: s.start_tick)
    assert [(s.start_tick, s.duration_ticks) for s in scenes] == [(a, b - a) for a, b in windows]
    assert plan.timeline.duration_ticks == windows[-1][1]
    # quadro é tick inteiro (a timebase contém toda fronteira de frame)
    assert plan.timeline.timebase.ticks_per_frame == DEFAULT_TICKS_PER_SECOND // FPS
    for scene in scenes:
        for shot in scene.shots:
            assert shot.start_tick % plan.timeline.timebase.ticks_per_frame == 0
            assert shot.duration_ticks % plan.timeline.timebase.ticks_per_frame == 0


def test_builder_does_not_reintroduce_rounding_drift_in_the_seconds_bridge():
    lengths = [scene_length(1.7), scene_length(2.3), scene_length(0.9)]
    offsets, cursor = [], 0.0
    for length in lengths:
        offsets.append(cursor)
        cursor += length
    scenes = [story(f"scene-0{i + 1}", f"asset-0{i + 1}", speech, f"Narração da cena {i + 1}.") for i, speech in enumerate((1.7, 2.3, 0.9))]
    plan = build(scenes=scenes, assets=[asset_ref(f"asset-0{i + 1}") for i in range(3)])

    placed = sorted(plan.timeline.scenes, key=lambda s: s.start_tick)
    for scene, start_s, length_s in zip(placed, offsets, lengths):
        assert scene.start_tick == seconds_to_ticks(start_s, DEFAULT_TICKS_PER_SECOND)
        assert scene.duration_ticks == seconds_to_ticks(length_s, DEFAULT_TICKS_PER_SECOND)
        # ida-e-volta dentro de meio tick: nenhuma deriva acumulada
        assert abs(ticks_to_seconds(scene.start_tick, DEFAULT_TICKS_PER_SECOND) - start_s) <= 0.5 / DEFAULT_TICKS_PER_SECOND


def test_builder_emits_one_visual_shot_covering_each_scene():
    plan = build(scenes=[story(speech=2.0)])
    scene = plan.timeline.scenes[0]
    [shot] = scene.shots
    assert shot.track_id == "visual-main"
    assert shot.start_tick == scene.start_tick
    assert shot.duration_ticks == scene.duration_ticks
    assert shot.asset_ref == "asset-01"
    assert shot.effects.motion == "none"  # explícito, sem `index % 4` (R3)


def test_builder_uses_the_declared_ticks_per_second_and_rejects_a_bad_one():
    plan = build(timebase=Timebase(ticks_per_second=FPS, fps_num=FPS, fps_den=1))
    assert plan.timeline.ticks_per_second == FPS
    with pytest.raises(ValidationError):
        build(timebase=Timebase(ticks_per_second=30, fps_num=FPS, fps_den=1))


def test_builder_writes_narration_and_subtitles_on_their_tracks():
    plan = build(scenes=[story(speech=2.0, narration="Primeira frase. Segunda frase da cena!")])
    scene = plan.timeline.scenes[0]
    tracks = {t.track_id: t.kind for t in plan.timeline.tracks}
    assert tracks["visual-main"] == "visual" and tracks["narration-main"] == "narration" and tracks["subtitle-main"] == "subtitle"

    [cue] = plan.timeline.narration
    assert cue.scene_id == scene.scene_id and cue.track_id == "narration-main"
    assert cue.source_ref in {g.source_id for g in plan.generated_audio}
    # a narração começa depois do LEAD e dura a fala
    assert cue.start_tick == seconds_to_ticks(LEAD, DEFAULT_TICKS_PER_SECOND)
    assert cue.duration_ticks == seconds_to_ticks(2.0, DEFAULT_TICKS_PER_SECOND)

    assert plan.timeline.subtitles, "uma fala tem de produzir legenda por trecho"
    for cue in plan.timeline.subtitles:
        assert cue.scene_id == scene.scene_id and cue.track_id == "subtitle-main"
        assert cue.start_tick >= scene.start_tick and cue.start_tick + cue.duration_ticks <= scene.start_tick + scene.duration_ticks


def test_builder_cues_are_contiguous_and_cover_the_speech():
    plan = build(scenes=[story(speech=4.0, narration="Uma frase longa o suficiente para virar mais de um trecho de legenda, com vírgula, e ponto.")])
    cues = sorted(plan.timeline.subtitles, key=lambda c: c.start_tick)
    assert len(cues) >= 2
    for previous, current in zip(cues, cues[1:]):
        assert previous.start_tick + previous.duration_ticks == current.start_tick
    assert cues[0].start_tick == seconds_to_ticks(LEAD, DEFAULT_TICKS_PER_SECOND)


def test_builder_skips_narration_and_subtitles_for_a_silent_scene():
    plan = build(
        scenes=[story(speech=0.0), story("scene-02", "asset-02", 2.0, "Segunda cena do vídeo.")],
        assets=[asset_ref(), asset_ref("asset-02")],
    )
    silent, spoken = sorted(plan.timeline.scenes, key=lambda s: s.start_tick)
    assert silent.duration_ticks == seconds_to_ticks(scene_length(0.0), DEFAULT_TICKS_PER_SECOND)
    assert all(cue.scene_id != silent.scene_id for cue in plan.timeline.narration)
    assert all(cue.scene_id != silent.scene_id for cue in plan.timeline.subtitles)
    assert [g.source_id for g in plan.generated_audio if g.kind == "voice"] == ["voice:scene-02"]
    assert [cue.scene_id for cue in plan.timeline.narration] == [spoken.scene_id]


def test_builder_generates_one_voice_source_per_spoken_scene():
    plan = build(scenes=[story(speech=2.0), story("scene-02", "asset-02", 0.0, "Cena muda."), story("scene-03", "asset-03", 1.0, "Outra fala.")],
                 assets=[asset_ref(), asset_ref("asset-02"), asset_ref("asset-03")])
    voices = [g for g in plan.generated_audio if g.kind == "voice"]
    assert [g.source_id for g in voices] == ["voice:scene-01", "voice:scene-03"]
    assert all(g.duration_ticks > 0 for g in voices)


def test_builder_represents_the_generated_music_with_params():
    plan = build(music=True)
    [music] = [g for g in plan.generated_audio if g.kind == "music"]
    assert music.source_id == "music" and music.silent is False
    assert music.params["bpm"] == 122 and music.params["seed"] == 7
    assert music.duration_ticks == plan.timeline.duration_ticks + DEFAULT_TICKS_PER_SECOND


def test_builder_represents_music_false_as_a_silent_track_of_the_same_length():
    plan = build(music=False)
    [music] = [g for g in plan.generated_audio if g.kind == "music"]
    assert music.silent is True and music.params == {}
    assert music.duration_ticks == plan.timeline.duration_ticks + DEFAULT_TICKS_PER_SECOND


def test_builder_keeps_the_content_hash_it_is_given_and_never_derives_it_from_cache_key():
    # C1: assets.cache_key é hash de ENTRADA; o manifest usa content_sha256 do conteúdo
    plan = build(assets=[asset_ref(content_sha256=SHA_B)])
    [reference] = plan.asset_manifest
    assert reference.content_sha256 == SHA_B
    assert reference.content_sha256 != "c" * 64


def test_builder_propagates_explicit_motion_and_paid_operation_keys():
    plan = build(
        scenes=[story(paid_operation_key="voice:scene-01"), story("scene-02", "asset-02", paid_operation_key="voice:scene-02")],
        assets=[asset_ref(), asset_ref("asset-02")],
        motions={"scene-01": "zoom_in", "scene-02": "pan_right"},
    )
    placed = sorted(plan.timeline.scenes, key=lambda s: s.start_tick)
    assert [s.shots[0].effects.motion for s in placed] == ["zoom_in", "pan_right"]
    assert [s.shots[0].paid_operation_key for s in placed] == ["voice:scene-01", "voice:scene-02"]


def test_builder_disclosure_lives_in_the_output_and_defaults_to_the_ai_notice():
    assert build().output.disclosure == "Ilustração gerada por IA"
    assert build(disclosure="Imagens ilustrativas").output.disclosure == "Imagens ilustrativas"


def test_builder_rejects_an_unknown_asset_reference():
    with pytest.raises(PlanBuildError, match="asset"):
        build(scenes=[story(asset_id="asset-missing")], assets=[asset_ref()])


def test_builder_rejects_duplicate_scene_ids():
    with pytest.raises(PlanBuildError, match="duplicate"):
        build(scenes=[story(), story()], assets=[asset_ref()])


def test_builder_rejects_no_scenes():
    with pytest.raises(PlanBuildError, match="scene"):
        build(scenes=[])


def test_builder_rejects_a_non_finite_or_negative_speech_duration():
    for bad in (-1.0, math.inf, math.nan):
        with pytest.raises(PlanBuildError):
            build(scenes=[story(speech=bad)])


def test_builder_rejects_a_motion_for_an_unknown_scene():
    with pytest.raises(PlanBuildError, match="motion"):
        build(motions={"scene-does-not-exist": "zoom_in"})


def test_builder_refuses_a_plan_whose_duration_breaks_the_output_format():
    # 200 s > 175 s do short; o contrato já recusa — o builder não pode gerar um plano inválido
    with pytest.raises(ValidationError, match="short"):
        build(scenes=[story(speech=199.0)])


# --------------------------------------------------------------- conversões puras


def test_asset_reference_for_turns_a_storyboard_asset_into_a_manifest_reference():
    asset = Asset(
        id="1" * 32, kind=AssetKind.image, cache_key="c" * 64, path="img/1.png",
        provider="opencode", model="img", license="Imagem gerada por IA",
        attribution="Estúdio", source_url="https://example.test/a",
    )
    reference = asset_reference_for(asset, content_sha256=SHA_A, media_type="image")
    assert reference.asset_id == asset.id
    assert reference.uri == asset.path
    assert reference.content_sha256 == SHA_A
    assert reference.media_type == "image"
    assert reference.license == asset.license
    assert reference.attribution == asset.attribution and reference.source_url == asset.source_url
    assert reference.metadata == {"asset_kind": "image"}


def test_asset_reference_for_never_uses_the_cache_key_as_content_hash():
    asset = Asset(id="2" * 32, kind=AssetKind.image, cache_key="d" * 64, path="img/2.png",
                  provider="p", model="m", license="licença")
    reference = asset_reference_for(asset, content_sha256=SHA_B, media_type="image")
    assert reference.content_sha256 == SHA_B != asset.cache_key


def test_asset_reference_for_requires_an_explicit_content_hash():
    asset = Asset(id="3" * 32, kind=AssetKind.image, cache_key="e" * 64, path="img/3.png",
                  provider="p", model="m", license="licença")
    with pytest.raises(ValueError):
        asset_reference_for(asset, content_sha256="not-a-hash", media_type="image")


def test_style_snapshot_consumes_the_versioned_channel_identity_by_key_and_version():
    profile = ChannelProfile(id="4" * 32, project_id="5" * 32, name="Canal", visual_identity="texto livre de estilo", version=7)
    snapshot = style_snapshot_for_channel(profile)
    assert snapshot == StyleSnapshot(style_id=profile.id, version=7)
    # não carrega o objeto nem o texto de identidade visual (R4)
    assert "texto livre" not in json.dumps(snapshot.model_dump())


def test_storyboard_row_is_the_input_shape_the_builder_converts():
    # o builder consome a cena editorial real (com a fala medida pós-TTS), não uma cópia
    row = StoryboardRow(id="6" * 32, video_id="7" * 32, idx=0, narration="Narração da cena.", image_prompt="prompt de imagem", asset_id="asset-01", label="DADOS")
    scene = storyboard_scene(row, speech_seconds=1.5)
    assert isinstance(scene, StoryboardScene)
    assert (scene.scene_id, scene.asset_id, scene.narration, scene.label) == (row.id, "asset-01", row.narration, "DADOS")
    plan = build(scenes=[scene], assets=[asset_ref()])
    assert plan.timeline.scenes[0].scene_id == row.id


def test_storyboard_scene_requires_an_asset():
    row = StoryboardRow(id="8" * 32, video_id="7" * 32, idx=0, narration="Narração da cena.", image_prompt="prompt de imagem", asset_id=None)
    with pytest.raises(PlanBuildError, match="asset"):
        storyboard_scene(row, speech_seconds=1.0)

# --------------------------------------------------------------------------- builder (F03.T03)


def test_builder_carries_the_frozen_config_reference_into_the_plan():
    from app.studio.domain.render_plan import ConfigSnapshot

    snapshot = ConfigSnapshot(content_hash="c" * 64, schema_version=1,
                              provenance={"style": "video", "audiovisual.motion": "video"})
    plan = build(config_snapshot=snapshot)
    assert plan.config_snapshot == snapshot
    assert build().config_snapshot is None  # sem referência, o plano é o de antes


# --------------------------------------------------------------------------- VE-01 — overlay


def test_T17_builder_hosts_one_overlay_inside_the_base_with_stable_identity():
    plan = build(
        assets=[asset_ref(), asset_ref("overlay-asset")],
        overlays=[StoryboardOverlay(scene_id="scene-01", asset_id="overlay-asset",
                                    start_s=0.5, duration_s=1.0, z_index=2, fit="cover")],
    )
    scene = plan.timeline.scenes[0]
    overlays = [shot for shot in scene.shots if shot.role == "overlay"]
    assert len(overlays) == 1
    [overlay] = overlays
    assert overlay.shot_id == "overlay:scene-01:0"
    assert overlay.track_id == "visual-overlay"
    assert overlay.z_index == 2
    assert overlay.composition.fit == "cover"
    assert "visual-overlay" in [track.track_id for track in plan.timeline.tracks]
    assert scene.base_shots[0].role == "base"


def test_T17_plan_without_overlay_is_identical_to_the_current_shape():
    plain = build()
    with_empty = build(overlays=[])
    assert plain == with_empty
    assert [track.track_id for track in plain.timeline.tracks] == [
        "visual-main", "narration-main", "subtitle-main",
    ]
    assert all(shot.role == "base" for scene in plain.timeline.scenes for shot in scene.shots)


def test_T18_builder_rejects_invalid_overlay_windows_and_references():
    with pytest.raises(PlanBuildError):
        build(overlays=[StoryboardOverlay(scene_id="unknown", asset_id="asset-01",
                                          start_s=0.0, duration_s=0.5)])
    with pytest.raises(PlanBuildError):
        build(overlays=[StoryboardOverlay(scene_id="scene-01", asset_id="missing",
                                          start_s=0.0, duration_s=0.5)])
    with pytest.raises(PlanBuildError):
        build(overlays=[StoryboardOverlay(scene_id="scene-01", asset_id="asset-01",
                                          start_s=-0.1, duration_s=0.5)])
    with pytest.raises(PlanBuildError):
        build(overlays=[StoryboardOverlay(scene_id="scene-01", asset_id="asset-01",
                                          start_s=0.0, duration_s=0.0)])
    with pytest.raises(PlanBuildError):
        build(overlays=[StoryboardOverlay(scene_id="scene-01", asset_id="asset-01",
                                          start_s=2.0, duration_s=2.0)])
