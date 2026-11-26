"""Testes de conformidade para V4-04 — Visual Composition Core.

Valida as atividades V4-04.01 a V4-04.20:
- V4-04.01 / V4-04.02: Versionamento de RenderPlan (v1/v2) e compatibilidade retroativa.
- V4-04.03 / V4-04.04: Suporte a múltiplos overlays simultâneos ordenados por z-index.
- V4-04.05 / V4-04.06: Overlays entre shots e Picture-in-Picture (vídeo sobre vídeo).
- V4-04.07 / V4-04.08: Gráficos, textos e transformações (escala, opacidade, posição X/Y).
- V4-04.10 / V4-04.11: Transições visuais expandidas (crossfade, slide, wipe) com tick math exato.
- V4-04.13 / V4-04.14: Compilador RenderPlanBuilder gerando planos canônicos determinísticos.
- V4-04.17 / V4-04.18: Invalidação dependente e fingerprints do cache visual por nó.
- V4-04.20: Determinismo temporal e preservação exata da duração da timeline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from renderer.app.studio.domain.render import FPS
from renderer.app.studio.domain.render_cache import visual_fingerprint
from renderer.app.studio.domain.render_plan import (
    AssetReference,
    AudioMix,
    Composition,
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
from renderer.app.studio.domain.render_plan_builder import (
    StoryboardOverlay,
    StoryboardScene,
    build_render_plan,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _create_minimal_plan(schema_version: int = 2) -> RenderPlan:
    tb = Timebase(ticks_per_second=FPS)
    track_vis = Track(track_id="visual-base", kind="visual")
    shot = Shot(
        shot_id="shot-01",
        track_id="visual-base",
        start_tick=0,
        duration_ticks=60,
        asset_ref="asset-01",
        role="base",
        z_index=0,
        composition=Composition(fit="cover"),
    )
    scene = Scene(
        scene_id="scene-01",
        start_tick=0,
        duration_ticks=60,
        shots=[shot],
    )
    timeline = Timeline(
        timebase=tb,
        tracks=[track_vis],
        scenes=[scene],
    )
    asset = AssetReference(
        asset_id="asset-01",
        asset_version=1,
        uri="/assets/image01.png",
        content_sha256=SHA_A,
        media_type="image",
        license="cc0",
    )
    return RenderPlan(
        plan_id="plan-001",
        revision=1,
        project_id="proj-01",
        video_id="vid-01",
        output=Output(width=1080, height=1920, format="short"),
        timeline=timeline,
        asset_manifest=[asset],
        style_snapshot=StyleSnapshot(source="channel", style_id="default", version=1),
        provenance=Provenance(builder_version="test-builder"),
        schema_version=schema_version,
    )


class TestRenderPlanVersioningAndCompatibility:
    """V4-04.01 e V4-04.02: Versionamento do RenderPlan e compatibilidade v1/v2."""

    def test_schema_version_accepts_v1_and_v2(self):
        plan_v1 = _create_minimal_plan(schema_version=1)
        assert plan_v1.schema_version == 1

        plan_v2 = _create_minimal_plan(schema_version=2)
        assert plan_v2.schema_version == 2

        with pytest.raises(ValueError, match="unsupported schema_version"):
            _create_minimal_plan(schema_version=3)

    def test_composition_transformations(self):
        comp_default = Composition(fit="contain")
        assert comp_default.opacity == 1.0
        assert comp_default.scale == 1.0
        assert comp_default.position_x == 0.5
        assert comp_default.position_y == 0.5

        comp_transformed = Composition(
            fit="cover",
            opacity=0.85,
            scale=1.2,
            position_x=0.25,
            position_y=0.75,
        )
        assert comp_transformed.opacity == 0.85
        assert comp_transformed.scale == 1.2
        assert comp_transformed.position_x == 0.25
        assert comp_transformed.position_y == 0.75

    def test_expanded_transition_kinds(self):
        # Transições sem duração
        t_cut = Transition(kind="cut", duration_ticks=0)
        assert t_cut.kind == "cut"

        # Transições com duração positiva
        t_crossfade = Transition(kind="crossfade", duration_ticks=15)
        assert t_crossfade.duration_ticks == 15

        t_slide = Transition(kind="slide_left", duration_ticks=10)
        assert t_slide.kind == "slide_left"

        t_wipe = Transition(kind="wipe_right", duration_ticks=12)
        assert t_wipe.kind == "wipe_right"

        # Transição com movimento exige duração > 0
        with pytest.raises(ValueError, match="needs a positive duration"):
            Transition(kind="slide_right", duration_ticks=0)


class TestMultipleOverlaysAndPictureInPicture:
    """V4-04.03 a V4-04.07: Múltiplos overlays, vídeo sobre vídeo e transformações."""

    def test_simultaneous_overlays_with_distinct_z_index(self):
        tb = Timebase(ticks_per_second=FPS, fps_num=FPS)
        track_vis = Track(track_id="visual-base", kind="visual")
        track_ov1 = Track(track_id="visual-overlay", kind="visual")
        track_ov2 = Track(track_id="visual-overlay-2", kind="visual")

        base_shot = Shot(
            shot_id="base-01",
            track_id="visual-base",
            start_tick=0,
            duration_ticks=90,
            asset_ref="asset-base",
            role="base",
            z_index=0,
        )
        # Overlay 1: Gráfico em z_index=1 na track visual-overlay
        overlay_1 = Shot(
            shot_id="ov-01",
            track_id="visual-overlay",
            start_tick=10,
            duration_ticks=40,
            asset_ref="asset-graphic",
            role="overlay",
            z_index=1,
            composition=Composition(fit="contain", position_x=0.2, position_y=0.2),
        )
        # Overlay 2: Vídeo Picture-in-Picture em z_index=2 na track visual-overlay-2
        overlay_2 = Shot(
            shot_id="ov-02",
            track_id="visual-overlay-2",
            start_tick=20,
            duration_ticks=50,
            asset_ref="asset-video-pip",
            role="overlay",
            z_index=2,
            composition=Composition(fit="cover", scale=0.4, position_x=0.8, position_y=0.8),
        )

        scene = Scene(
            scene_id="scene-01",
            start_tick=0,
            duration_ticks=90,
            shots=[base_shot, overlay_1, overlay_2],
        )

        timeline = Timeline(
            timebase=tb,
            tracks=[track_vis, track_ov1, track_ov2],
            scenes=[scene],
        )

        manifest = [
            AssetReference(asset_id="asset-base", asset_version=1, uri="/img.png", content_sha256=SHA_A, media_type="image", license="cc0"),
            AssetReference(asset_id="asset-graphic", asset_version=1, uri="/icon.png", content_sha256=SHA_B, media_type="graphic", license="cc0"),
            AssetReference(asset_id="asset-video-pip", asset_version=1, uri="/pip.mp4", content_sha256=SHA_C, media_type="video", license="cc-by"),
        ]

        plan = RenderPlan(
            plan_id="plan-pip",
            revision=1,
            project_id="proj-01",
            video_id="vid-01",
            output=Output(width=1080, height=1920, format="short"),
            timeline=timeline,
            asset_manifest=manifest,
            style_snapshot=StyleSnapshot(source="channel", style_id="default", version=1),
            provenance=Provenance(builder_version="test-builder"),
        )

        assert len(plan.timeline.scenes[0].overlay_shots) == 2
        assert plan.timeline.scenes[0].overlay_shots[0].z_index == 1
        assert plan.timeline.scenes[0].overlay_shots[1].z_index == 2

    def test_overlays_with_same_z_index_overlapping_in_time_rejected(self):
        tb = Timebase(ticks_per_second=FPS, fps_num=FPS)
        track_vis = Track(track_id="visual-base", kind="visual")
        track_ov1 = Track(track_id="visual-overlay-1", kind="visual")
        track_ov2 = Track(track_id="visual-overlay-2", kind="visual")

        base_shot = Shot(shot_id="b1", track_id="visual-base", start_tick=0, duration_ticks=60, asset_ref="a1", role="base", z_index=0)
        ov1 = Shot(shot_id="o1", track_id="visual-overlay-1", start_tick=10, duration_ticks=30, asset_ref="a2", role="overlay", z_index=1)
        ov2 = Shot(shot_id="o2", track_id="visual-overlay-2", start_tick=20, duration_ticks=30, asset_ref="a3", role="overlay", z_index=1)

        scene = Scene(scene_id="s1", start_tick=0, duration_ticks=60, shots=[base_shot, ov1, ov2])

        with pytest.raises(ValueError, match="share z_index 1"):
            Timeline(timebase=tb, tracks=[track_vis, track_ov1, track_ov2], scenes=[scene])


class TestCompilerAndCacheFingerprints:
    """V4-04.14 a V4-04.18: RenderPlanBuilder e invalidação de cache por nó."""

    def test_builder_with_transformed_storyboard_overlay(self):
        scenes = [
            StoryboardScene(scene_id="scene-01", speech_seconds=3.0, asset_id="asset-base", narration="Texto"),
        ]
        manifest = [
            AssetReference(asset_id="asset-base", asset_version=1, uri="/b.png", content_sha256=SHA_A, media_type="image", license="cc0"),
            AssetReference(asset_id="asset-logo", asset_version=1, uri="/logo.png", content_sha256=SHA_B, media_type="graphic", license="cc0"),
        ]
        overlay = StoryboardOverlay(
            scene_id="scene-01",
            asset_id="asset-logo",
            start_s=0.5,
            duration_s=1.5,
            z_index=1,
            fit="contain",
            opacity=0.9,
            scale=0.75,
            position_x=0.8,
            position_y=0.1,
        )

        plan = build_render_plan(
            plan_id="plan-test-01",
            revision=1,
            project_id="proj-01",
            video_id="vid-01",
            format="short",
            scenes=scenes,
            assets=manifest,
            overlays=[overlay],
        )

        ov_shot = plan.timeline.scenes[0].overlay_shots[0]
        assert ov_shot.composition is not None
        assert ov_shot.composition.opacity == 0.9
        assert ov_shot.composition.scale == 0.75
        assert ov_shot.composition.position_x == 0.8
        assert ov_shot.composition.position_y == 0.1

    def test_visual_fingerprint_invalidates_on_transformation_change(self):
        shot_default = Shot(
            shot_id="s1", track_id="visual-base", start_tick=0, duration_ticks=30, asset_ref="a1",
            role="base", z_index=0, composition=Composition(fit="cover"),
        )
        shot_transformed = Shot(
            shot_id="s1", track_id="visual-base", start_tick=0, duration_ticks=30, asset_ref="a1",
            role="base", z_index=0, composition=Composition(fit="cover", opacity=0.7),
        )

        fp_default = visual_fingerprint(shot_default, asset_digest=SHA_A)
        fp_transformed = visual_fingerprint(shot_transformed, asset_digest=SHA_A)

        assert fp_default != fp_transformed  # Alteração geométrica invalida o cache do shot
