"""Testes de conformidade para V4-08 — Render Engine & Extensibility.

Valida as atividades V4-08.01 a V4-08.14:
- V4-08.01 / V4-08.11: Contrato de capacidades (RendererCapabilities) e detecção de hardware.
- V4-08.03: Separação estrita de contratos e pré-condições.
- V4-08.04: Preflight checks (evaluate_preflight) com validação de assets e espaço em disco.
- V4-08.05 / V4-08.06: Render por segmentos e cache de segmentos por hash determinístico.
- V4-08.07: Acompanhamento de progresso granular (ProgressTracker).
- V4-08.08: Cancelamento limpo via CancellationToken.
- V4-08.10: Presets preview vs produção.
"""
from __future__ import annotations

import pytest

from app.studio.adapters.render_hardware import check_disk_space_mb, detect_system_hardware
from app.studio.application.render_engine import (
    ProgressTracker,
    SegmentCacheManager,
    SegmentedRenderPlanner,
)
from app.studio.domain.contracts import VideoFormat
from app.studio.domain.render_engine import (
    CancellationToken,
    QualityPresetKind,
    RenderProgress,
    RenderProgressStage,
    RenderQualityPreset,
    RendererCapabilities,
    evaluate_preflight,
)
from app.studio.domain.render_plan import AssetReference, RenderPlan
from app.studio.domain.render_plan_builder import StoryboardScene, build_render_plan


@pytest.fixture
def sample_render_plan() -> RenderPlan:
    sha_a = "a" * 64
    sha_b = "b" * 64

    asset1 = AssetReference(
        asset_id="asset-img-01",
        asset_version=1,
        uri="media/asset1.png",
        content_sha256=sha_a,
        media_type="image",
        license="CC0",
    )
    asset2 = AssetReference(
        asset_id="asset-img-02",
        asset_version=1,
        uri="media/asset2.png",
        content_sha256=sha_b,
        media_type="image",
        license="CC0",
    )

    sb_scenes = [
        StoryboardScene(
            scene_id="scene-01",
            asset_id="asset-img-01",
            narration="Primeira cena com duração controlada de voz.",
            speech_seconds=2.0,
        ),
        StoryboardScene(
            scene_id="scene-02",
            asset_id="asset-img-02",
            narration="Segunda cena com movimento suave.",
            speech_seconds=2.0,
        ),
    ]

    return build_render_plan(
        plan_id="plan:render-engine-test",
        revision=1,
        project_id="a" * 32,
        video_id="b" * 32,
        format=VideoFormat.short,
        scenes=sb_scenes,
        assets=[asset1, asset2],
    )


class TestRenderCapabilitiesAndHardware:
    """V4-08.01 e V4-08.11: Capacidades operacionais do motor e detecção de hardware."""

    def test_default_capabilities(self):
        caps = RendererCapabilities()
        assert caps.name == "ffmpeg"
        assert "h264" in caps.supported_codecs
        assert caps.supports_segmented_render is True
        assert caps.supports_cancellation is True
        assert caps.supports_lossless_concat is True

    def test_detect_system_hardware_resilient(self):
        caps = detect_system_hardware()
        assert caps.name in ("ffmpeg", "ffmpeg-not-found")
        assert len(caps.supported_codecs) >= 2


class TestQualityPresets:
    """V4-08.10: Presets de preview e produção."""

    def test_preview_preset(self):
        preset = RenderQualityPreset.preview()
        assert preset.kind == QualityPresetKind.PREVIEW
        assert preset.crf == 28
        assert preset.preset == "ultrafast"
        assert preset.scale_factor == 0.5
        assert preset.audio_bitrate_k == 128

    def test_production_preset(self):
        preset = RenderQualityPreset.production()
        assert preset.kind == QualityPresetKind.PRODUCTION
        assert preset.crf == 20
        assert preset.preset == "medium"
        assert preset.scale_factor == 1.0
        assert preset.audio_bitrate_k == 256


class TestPreflightEvaluation:
    """V4-08.04: Preflight checks de assets e recursos."""

    def test_preflight_success(self, sample_render_plan):
        report = evaluate_preflight(
            plan=sample_render_plan,
            available_asset_keys={"asset-img-01", "asset-img-02"},
            disk_free_mb=1000.0,
            required_free_mb=100.0,
        )
        assert report.is_valid is True
        assert len(report.missing_asset_keys) == 0
        assert len(report.errors) == 0

    def test_preflight_missing_assets(self, sample_render_plan):
        report = evaluate_preflight(
            plan=sample_render_plan,
            available_asset_keys={"asset-img-01"},  # falta asset-img-02
            disk_free_mb=1000.0,
        )
        assert report.is_valid is False
        assert "asset-img-02" in report.missing_asset_keys
        assert any("Missing 1 required assets" in err for err in report.errors)

    def test_preflight_low_disk_space(self, sample_render_plan):
        report = evaluate_preflight(
            plan=sample_render_plan,
            available_asset_keys={"asset-img-01", "asset-img-02"},
            disk_free_mb=10.0,  # Apenas 10MB disponíveis
            required_free_mb=100.0,
        )
        assert report.is_valid is False
        assert any("Insufficient disk space" in err for err in report.errors)


class TestSegmentedRenderAndCache:
    """V4-08.05 e V4-08.06: Render por segmentos e cache determinístico."""

    def test_segmented_planner_with_cache_miss_and_hit(self, sample_render_plan):
        cache_manager = SegmentCacheManager()
        preset = RenderQualityPreset.production()

        # 1. Primeira execução: tudo miss
        plan1 = SegmentedRenderPlanner.plan(sample_render_plan, cache_manager, preset)
        assert plan1.total_segments == 2
        assert plan1.cached_count == 0
        assert plan1.to_render_count == 2
        assert plan1.can_skip_all_renders is False

        # 2. Registra o primeiro segmento no cache
        first_digest = plan1.items[0].digest
        cache_manager.put(first_digest, "/tmp/seg-01.mp4", duration_ticks=50, preset_kind=preset.kind)

        # 3. Segunda execução: 1 hit, 1 miss
        plan2 = SegmentedRenderPlanner.plan(sample_render_plan, cache_manager, preset)
        assert plan2.cached_count == 1
        assert plan2.to_render_count == 1
        assert plan2.items[0].is_cached is True
        assert plan2.items[0].cached_path == "/tmp/seg-01.mp4"
        assert plan2.items[1].is_cached is False


class TestProgressAndCancellation:
    """V4-08.07 e V4-08.08: Progresso e cancelamento gracioso."""

    def test_progress_tracking(self):
        progress_events: list[RenderProgress] = []

        def on_progress(p: RenderProgress):
            progress_events.append(p)

        tracker = ProgressTracker(total_segments=2, callback=on_progress)
        tracker.update_stage(RenderProgressStage.PREFLIGHT, "Validando")
        tracker.advance_segment("Render shot 1")
        tracker.advance_segment("Render shot 2")
        tracker.update_stage(RenderProgressStage.CONCATENATING, "Concatenando")
        tracker.complete("Concluído")

        assert len(progress_events) == 5
        assert progress_events[0].percent == 5.0
        assert progress_events[-1].percent == 100.0
        assert progress_events[-1].stage == RenderProgressStage.COMPLETED

    def test_cancellation_aborts_execution(self):
        token = CancellationToken()
        tracker = ProgressTracker(total_segments=5, cancellation_token=token)

        tracker.update_stage(RenderProgressStage.PREFLIGHT)
        tracker.advance_segment("Shot 1 pronto")

        # Operador clica em Cancelar
        token.cancel()
        assert token.is_cancelled is True

        with pytest.raises(InterruptedError, match="cancelled by operator"):
            tracker.advance_segment("Shot 2")
