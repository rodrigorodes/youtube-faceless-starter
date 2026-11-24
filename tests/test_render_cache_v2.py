"""Testes do cache de render com invalidação precisa (Onda 1 - Task 5).

Verifica os refinamentos em `visual_fingerprint`, `music_fingerprint` e
`DependencyGraph.build`:
- Transições de shot (kind e duration) afetam o fingerprint visual.
- Offset temporal do asset (asset_offset_ticks) afeta o fingerprint visual.
- style_digest afeta o fingerprint visual para estilos de legenda/texto.
- Parâmetros de AudioMix afetam o fingerprint de música.
- Invalidação seletiva no grafo funciona de forma precisa para essas mudanças.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import Asset, AssetKind, VideoFormat
from app.studio.domain.render_cache import (
    CachePolicy,
    DependencyGraph,
    NodeId,
    music_fingerprint,
    plan_graph,
    selective_invalidation,
    visual_fingerprint,
)
from app.studio.domain.render_plan import (
    AudioMix,
    GeneratedAudioSource,
    RenderPlan,
    Shot,
    StyleSnapshot,
    Transition,
)
from app.studio.domain.render_plan_builder import (
    StoryboardScene,
    asset_reference_for,
    build_render_plan,
)

SHA_A = "a" * 64
SHA_B = "b" * 64

A_VISUAL = NodeId("visual", "shot:scene-01")
B_VISUAL = NodeId("visual", "shot:scene-02")
A_NARRATION = NodeId("narration", "scene-01")
B_NARRATION = NodeId("narration", "scene-02")
MUSIC = NodeId("music", "music")
CONCAT = NodeId("concat", "video")
FINAL = NodeId("final", "video")


def image_ref(asset_id="asset-01", sha=SHA_A, **overrides):
    reference = asset_reference_for(
        Asset(
            id=asset_id,
            kind=AssetKind.image,
            cache_key="c" * 64,
            path=f"img/{asset_id}.png",
            provider="p",
            model="m",
            license="Imagem gerada por IA",
        ),
        content_sha256=sha,
        media_type="image",
    )
    return reference.model_copy(update=overrides) if overrides else reference


def make_plan(*, revision=1, audio_mix=None, **overrides):
    scenes = [
        StoryboardScene(
            scene_id="scene-01",
            asset_id="asset-01",
            narration="Primeira cena.",
            speech_seconds=2.0,
        ),
        StoryboardScene(
            scene_id="scene-02",
            asset_id="asset-02",
            narration="Segunda cena.",
            speech_seconds=2.0,
        ),
    ]
    data = dict(
        plan_id="plan:video-v2-001",
        revision=revision,
        project_id="project-001",
        video_id="video-001",
        format=VideoFormat.short,
        scenes=scenes,
        assets=[image_ref("asset-01", SHA_A), image_ref("asset-02", SHA_B)],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=1),
    )
    data.update(overrides)
    plan = build_render_plan(**data)
    if audio_mix is not None:
        plan = plan.model_copy(update={"audio_mix": audio_mix})
    return plan


def test_visual_fingerprint_changes_with_transition():
    shot_none = Shot(
        shot_id="shot-01",
        track_id="track-01",
        start_tick=0,
        duration_ticks=100,
        asset_ref="asset-01",
    )
    shot_fade_30 = shot_none.model_copy(
        update={"transition": Transition(kind="fade", duration_ticks=30)}
    )
    shot_fade_60 = shot_none.model_copy(
        update={"transition": Transition(kind="fade", duration_ticks=60)}
    )
    shot_cut = shot_none.model_copy(
        update={"transition": Transition(kind="cut", duration_ticks=0)}
    )

    fp_none = visual_fingerprint(shot_none, asset_digest=SHA_A)
    fp_fade_30 = visual_fingerprint(shot_fade_30, asset_digest=SHA_A)
    fp_fade_60 = visual_fingerprint(shot_fade_60, asset_digest=SHA_A)
    fp_cut = visual_fingerprint(shot_cut, asset_digest=SHA_A)

    assert len(fp_none) == 64
    assert fp_none != fp_fade_30
    assert fp_fade_30 != fp_fade_60
    assert fp_fade_30 != fp_cut
    assert fp_none != fp_cut


def test_visual_fingerprint_changes_with_asset_offset_ticks():
    shot_0 = Shot(
        shot_id="shot-01",
        track_id="track-01",
        start_tick=0,
        duration_ticks=100,
        asset_ref="asset-01",
        asset_offset_ticks=0,
    )
    shot_100 = shot_0.model_copy(update={"asset_offset_ticks": 100})
    shot_200 = shot_0.model_copy(update={"asset_offset_ticks": 200})

    fp_0 = visual_fingerprint(shot_0, asset_digest=SHA_A)
    fp_100 = visual_fingerprint(shot_100, asset_digest=SHA_A)
    fp_200 = visual_fingerprint(shot_200, asset_digest=SHA_A)

    assert fp_0 != fp_100
    assert fp_100 != fp_200
    assert fp_0 != fp_200


def test_visual_fingerprint_changes_with_style_digest():
    shot = Shot(
        shot_id="shot-01",
        track_id="track-01",
        start_tick=0,
        duration_ticks=100,
        asset_ref="asset-01",
    )

    fp_none = visual_fingerprint(shot, asset_digest=SHA_A, style_digest=None)
    fp_style_a = visual_fingerprint(shot, asset_digest=SHA_A, style_digest="style:caption-yellow")
    fp_style_b = visual_fingerprint(shot, asset_digest=SHA_A, style_digest="style:caption-white")

    assert fp_none != fp_style_a
    assert fp_style_a != fp_style_b
    assert fp_none != fp_style_b


def test_music_fingerprint_changes_with_audio_mix():
    source = GeneratedAudioSource(
        source_id="music",
        kind="music",
        duration_ticks=1000,
        params={"bpm": 120, "seed": 42},
    )

    fp_no_mix = music_fingerprint(source, audio_mix=None)
    fp_mix_default = music_fingerprint(source, audio_mix=AudioMix())
    fp_mix_gain_80 = music_fingerprint(source, audio_mix=AudioMix(music_gain=0.80))
    fp_mix_ducking = music_fingerprint(source, audio_mix=AudioMix(ducking_threshold=0.05))

    assert len(fp_no_mix) == 64
    assert fp_mix_default != fp_mix_gain_80
    assert fp_mix_default != fp_mix_ducking
    assert fp_mix_gain_80 != fp_mix_ducking


def test_dependency_graph_build_class_method():
    plan = make_plan()
    graph_from_build = DependencyGraph.build(plan)
    graph_from_plan_graph = plan_graph(plan)

    assert isinstance(graph_from_build, DependencyGraph)
    assert graph_from_build == graph_from_plan_graph


def test_dependency_graph_tracks_asset_offset_ticks_and_invalidates_selectively():
    plan_v1 = make_plan(revision=1)
    # Alterar asset_offset_ticks do shot da primeira cena
    scene_01 = plan_v1.timeline.scenes[0]
    updated_shots = [scene_01.shots[0].model_copy(update={"asset_offset_ticks": 50})] + list(scene_01.shots[1:])
    updated_scene = scene_01.model_copy(update={"shots": updated_shots})
    scenes_v2 = [updated_scene, plan_v1.timeline.scenes[1]]
    plan_v2 = plan_v1.model_copy(
        update={
            "revision": 2,
            "timeline": plan_v1.timeline.model_copy(update={"scenes": scenes_v2}),
        }
    )

    g1 = DependencyGraph.build(plan_v1)
    g2 = DependencyGraph.build(plan_v2)

    assert g1.fingerprint(A_VISUAL) != g2.fingerprint(A_VISUAL)
    assert g1.fingerprint(B_VISUAL) == g2.fingerprint(B_VISUAL)
    assert g1.fingerprint(A_NARRATION) == g2.fingerprint(A_NARRATION)

    inv = selective_invalidation(g1, g2)
    assert A_VISUAL in inv.invalidated
    assert CONCAT in inv.invalidated
    assert FINAL in inv.invalidated
    assert B_VISUAL in inv.reusable
    assert A_NARRATION in inv.reusable
    assert B_NARRATION in inv.reusable
    assert MUSIC in inv.reusable


def test_dependency_graph_tracks_style_digest():
    plan = make_plan()
    g_default = DependencyGraph.build(plan)
    g_styled_1 = DependencyGraph.build(plan, style_digest="style:yellow-bold")
    g_styled_2 = DependencyGraph.build(plan, style_digest="style:white-italic")

    assert g_default.fingerprint(A_VISUAL) != g_styled_1.fingerprint(A_VISUAL)
    assert g_styled_1.fingerprint(A_VISUAL) != g_styled_2.fingerprint(A_VISUAL)


def test_dependency_graph_tracks_audio_mix_and_invalidates_precisely():
    plan_v1 = make_plan(revision=1, audio_mix=AudioMix(music_gain=0.40))
    plan_v2 = make_plan(revision=2, audio_mix=AudioMix(music_gain=0.75))

    g1 = DependencyGraph.build(plan_v1)
    g2 = DependencyGraph.build(plan_v2)

    assert g1.fingerprint(MUSIC) != g2.fingerprint(MUSIC)
    # Cenas visuais e narração não foram afetadas pela mixagem de áudio
    assert g1.fingerprint(A_VISUAL) == g2.fingerprint(A_VISUAL)
    assert g1.fingerprint(B_VISUAL) == g2.fingerprint(B_VISUAL)
    assert g1.fingerprint(A_NARRATION) == g2.fingerprint(A_NARRATION)
    assert g1.fingerprint(B_NARRATION) == g2.fingerprint(B_NARRATION)

    inv = selective_invalidation(g1, g2)
    assert MUSIC in inv.invalidated
    assert FINAL in inv.invalidated  # FINAL depende de MUSIC
    assert CONCAT in inv.reusable    # CONCAT só depende de visual_nodes
    assert A_VISUAL in inv.reusable
    assert B_VISUAL in inv.reusable
    assert A_NARRATION in inv.reusable
    assert B_NARRATION in inv.reusable
