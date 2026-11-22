"""QA técnico do overlay + declaração semântica (W3.3/VE-05).

Duas fronteiras:

* **Domínio puro** (``domain.quality``): plano sem overlay mantém o QA de hoje; plano com
  overlay ganha os checks técnicos de presença/janela/tamanho e a semântica explícita
  (``not_verified`` → ``info``; ``failed`` → ``blocking``; nunca "passou" inventado).
* **Adaptador** (``adapters.quality_ffmpeg``): o verificador técnico mede o vídeo
  renderizado com ffprobe/ffmpeg (presença pela descontinuidade nas bordas da janela) e
  não é chamado quando o plano não tem overlay — o caminho de hoje fica intacto.
"""
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.quality_ffmpeg import (  # noqa: E402
    FfmpegOverlayVerifier,
    FfmpegQualityEvaluator,
    FfmpegQualityProbe,
)
from app.studio.adapters.quality_semantic import NotVerifiedSemanticChecker  # noqa: E402
from app.studio.domain.asset_resolver import AssetDescriptor  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.qa_report import (  # noqa: E402
    BlockingFindings,
    CoverageNotVerified,
    RenderVersion,
    approve,
)
from app.studio.domain.quality import (  # noqa: E402
    CHECK_OVERLAY,
    CHECK_SEMANTIC,
    MULTIMODAL_EVALUATION,
    MIN_OVERLAY_COVERAGE,
    OverlayEvidence,
    QualityEvidence,
    SemanticResult,
    evaluate_quality,
)
from app.studio.domain.render_plan import AssetReference, StyleSnapshot  # noqa: E402
from app.studio.domain.render_plan_builder import (  # noqa: E402
    StoryboardOverlay,
    StoryboardScene,
    build_render_plan,
)

SHA = "a" * 64
RENDER_ID = "r" * 64
CHECKSUM = "c" * 64
AT = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def make_plan(*, overlay=True, fit="contain", overlay_start=1.0, overlay_duration=1.0,
              scene_seconds=3.0):
    assets = [AssetReference(asset_id="asset0", asset_version=1, uri="assets/0.png",
                             content_sha256=SHA, media_type="image", license="CC0")]
    overlays = []
    if overlay:
        assets.append(AssetReference(asset_id="asset-overlay", asset_version=1, uri="assets/overlay.png",
                                     content_sha256=SHA, media_type="image", license="CC0"))
        overlays.append(StoryboardOverlay(scene_id="scene0", asset_id="asset-overlay",
                                          start_s=overlay_start, duration_s=overlay_duration, fit=fit))
    scene = StoryboardScene(scene_id="scene0", asset_id="asset0",
                            narration="Narração do teste automatizado.",
                            speech_seconds=max(0.0, scene_seconds - 0.8), label="SELO")
    return build_render_plan(plan_id="plan:overlay", revision=1, project_id="p", video_id="v",
                             format=VideoFormat.short, scenes=[scene], assets=assets,
                             style_snapshot=StyleSnapshot(style_id="s", version=1), music=True,
                             overlays=overlays)


def descriptors_for(plan, *, width=1080, height=1920):
    return tuple(
        AssetDescriptor(asset_id=ref.asset_id, asset_version=ref.asset_version, uri=ref.uri,
                        content_sha256=ref.content_sha256, media_type=ref.media_type, license="CC0",
                        available=True, codec="png", width=width, height=height)
        for ref in plan.asset_manifest
    )


def good_metrics(plan):
    expected = plan.timeline.duration_ticks / plan.timeline.ticks_per_second
    return {"duration_s": round(expected, 3), "width": 1080, "height": 1920, "has_audio": True,
            "integrated_lufs": -16.0, "silence_ratio": 0.1, "black_ratio": 0.0,
            "narration_lufs": -18.0, "narration_silence_ratio": 0.1}


def evidence(plan, *, media=True, assets=None, overlays=(), semantic=None):
    return QualityEvidence(
        render_id=RENDER_ID, checksum=CHECKSUM,
        media=good_metrics(plan) if media else None,
        assets=descriptors_for(plan) if assets is None else assets,
        generated_at=AT, overlays=tuple(overlays), semantic=semantic,
    )


def overlay_shot(plan):
    return plan.timeline.scenes[0].overlay_shots[0]


def overlay_evidence(plan, **overrides):
    shot = overlay_shot(plan)
    tps = plan.timeline.ticks_per_second
    base = dict(
        shot_id=shot.shot_id,
        scene_id=plan.timeline.scenes[0].scene_id,
        start_s=shot.start_tick / tps,
        end_s=(shot.start_tick + shot.duration_ticks) / tps,
        present=True,
        window_ok=True,
        measured=True,
        coverage_ratio=0.8,
        width=1080,
        height=1920,
        frame_width=1080,
        frame_height=1920,
        reason="overlay boundary detected at the planned window",
    )
    base.update(overrides)
    return OverlayEvidence(**base)


def gate(report):
    version = RenderVersion(render_id=RENDER_ID, checksum=CHECKSUM)
    return approve(report=report, latest=version, requested=version)


# ------------------------------------------------------------------ plano sem overlay

def test_plan_without_overlay_keeps_todays_qa_untouched():
    plan = make_plan(overlay=False)
    report = evaluate_quality(plan, evidence(plan))
    assert report.coverage.status == "verified"
    assert CHECK_OVERLAY not in report.checks_run
    assert CHECK_SEMANTIC not in report.checks_run
    assert not any(f.check_id in (CHECK_OVERLAY, CHECK_SEMANTIC) for f in report.findings)
    assert report.is_publishable


# ------------------------------------------------------------------ overlay: presença/janela

def test_overlay_inside_the_window_is_detected_and_verified():
    plan = make_plan()
    report = evaluate_quality(plan, evidence(plan, overlays=(overlay_evidence(plan),)))
    assert report.coverage.status == "verified"
    assert CHECK_OVERLAY in report.checks_run
    assert report.blocking_findings == ()
    assert report.is_publishable


def test_overlay_without_measurement_is_not_verified_and_never_approves():
    plan = make_plan()
    report = evaluate_quality(plan, evidence(plan, overlays=()))
    assert report.coverage.status == "not_verified"
    assert "overlay" in report.coverage.reason
    with pytest.raises(CoverageNotVerified):
        gate(report)


def test_unmeasured_overlay_is_not_verified_not_blocking():
    plan = make_plan()
    item = overlay_evidence(plan, measured=False, present=False, reason="overlay analysis timed out")
    report = evaluate_quality(plan, evidence(plan, overlays=(item,)))
    assert report.coverage.status == "not_verified"
    assert "timed out" in report.coverage.reason


def test_overlay_absent_from_the_render_is_blocking():
    plan = make_plan()
    item = overlay_evidence(plan, present=False, reason="no overlay boundary detected at the planned window")
    report = evaluate_quality(plan, evidence(plan, overlays=(item,)))
    assert report.coverage.status == "verified"
    assert any(f.check_id == CHECK_OVERLAY and f.severity == "blocking" for f in report.blocking_findings)
    with pytest.raises(BlockingFindings):
        gate(report)


def test_overlay_window_outside_the_render_is_blocking():
    plan = make_plan()
    item = overlay_evidence(plan, window_ok=False, reason="overlay is outside the render/base window")
    report = evaluate_quality(plan, evidence(plan, overlays=(item,)))
    assert any(f.check_id == CHECK_OVERLAY and "window" in f.evidence for f in report.blocking_findings)


def test_overlay_evidence_window_must_match_the_plan():
    plan = make_plan()
    item = overlay_evidence(plan, start_s=0.0, end_s=0.5)  # não é a janela do plano (1.0-2.0)
    report = evaluate_quality(plan, evidence(plan, overlays=(item,)))
    assert any(f.check_id == CHECK_OVERLAY and "plan puts it" in f.evidence for f in report.blocking_findings)


def test_overlay_cover_smaller_than_the_frame_is_blocking():
    plan = make_plan(fit="cover")
    small = descriptors_for(plan, width=320, height=240)
    item = overlay_evidence(plan, width=320, height=240, frame_width=320, frame_height=240)
    report = evaluate_quality(plan, evidence(plan, assets=small, overlays=(item,)))
    assert any(f.check_id == CHECK_OVERLAY and "upscale" in f.evidence for f in report.blocking_findings)


def test_overlay_with_tiny_coverage_is_a_warning():
    plan = make_plan()
    item = overlay_evidence(plan, coverage_ratio=MIN_OVERLAY_COVERAGE / 2)
    report = evaluate_quality(plan, evidence(plan, overlays=(item,)))
    assert any(f.check_id == CHECK_OVERLAY and f.severity == "warning" for f in report.findings)
    assert report.is_publishable


def test_unmeasured_overlay_requires_a_reason():
    with pytest.raises(ValueError):
        OverlayEvidence(shot_id="shot", scene_id="scene", start_s=0.0, end_s=1.0, measured=False)


# ------------------------------------------------------------------ semântica explícita

def test_semantic_not_verified_is_info_and_keeps_the_report_publishable():
    plan = make_plan()
    semantic = SemanticResult(verdict="not_verified", reason="no semantic/vision provider is configured")
    report = evaluate_quality(plan, evidence(plan, overlays=(overlay_evidence(plan),), semantic=semantic))
    assert report.coverage.status == "verified"
    assert report.is_publishable
    findings = [f for f in report.findings if f.check_id == CHECK_SEMANTIC]
    assert findings and findings[0].severity == "info" and findings[0].category == "editorial"


def test_semantic_failed_is_blocking():
    plan = make_plan()
    semantic = SemanticResult(verdict="failed", reason="narration and image do not match")
    report = evaluate_quality(plan, evidence(plan, overlays=(overlay_evidence(plan),), semantic=semantic))
    assert any(f.check_id == CHECK_SEMANTIC and f.severity == "blocking" for f in report.blocking_findings)
    with pytest.raises(BlockingFindings):
        gate(report)


def test_semantic_verified_adds_no_finding():
    plan = make_plan()
    semantic = SemanticResult(verdict="verified")
    report = evaluate_quality(plan, evidence(plan, overlays=(overlay_evidence(plan),), semantic=semantic))
    assert CHECK_SEMANTIC in report.checks_run
    assert not any(f.check_id == CHECK_SEMANTIC for f in report.findings)
    assert report.is_publishable


def test_semantic_result_requires_a_reason_when_not_verified():
    with pytest.raises(ValueError):
        SemanticResult(verdict="not_verified")
    with pytest.raises(ValueError):
        SemanticResult(verdict="failed")
    with pytest.raises(ValueError):
        SemanticResult(verdict="invented")


def test_the_default_semantic_checker_declares_not_verified_honestly():
    result = NotVerifiedSemanticChecker().check(make_plan(), media_path=Path("/tmp/none.mp4"))
    assert result.verdict == "not_verified" and result.reason
    assert MULTIMODAL_EVALUATION == "out_of_scope_without_provider"


# ------------------------------------------------------------------ integração do adaptador

class _FakeAnalyzer:
    def analyze(self, path, narration=None):
        return {"duration_s": 3.0, "width": 1080, "height": 1920, "has_audio": True,
                "integrated_lufs": -16.0, "silence_ratio": 0.1, "black_ratio": 0.0,
                "narration_lufs": -18.0, "narration_silence_ratio": 0.1}


class _ExplodingOverlayVerifier:
    def verify(self, plan, *, media_path, descriptors=()):
        raise AssertionError("overlay verifier must not run without an overlay")


class _ExplodingSemanticChecker:
    def check(self, plan, *, media_path, narration_path=None, descriptors=()):
        raise AssertionError("semantic checker must not run without an overlay")


class _FixedOverlayVerifier:
    def __init__(self, evidence):
        self._evidence = evidence

    def verify(self, plan, *, media_path, descriptors=()):
        return tuple(self._evidence)


def test_evaluator_does_not_touch_overlay_or_semantic_without_overlay():
    plan = make_plan(overlay=False)
    evaluator = FfmpegQualityEvaluator(
        probe=FfmpegQualityProbe(analyzer=_FakeAnalyzer()),
        overlay_verifier=_ExplodingOverlayVerifier(),
        semantic_checker=_ExplodingSemanticChecker(),
    )
    report = evaluator.evaluate(plan, media_path=Path("/tmp/none.mp4"), descriptors=descriptors_for(plan),
                                render_id=RENDER_ID, checksum=CHECKSUM)
    assert report.coverage.status == "verified"
    assert CHECK_OVERLAY not in report.checks_run and CHECK_SEMANTIC not in report.checks_run


def test_evaluator_runs_the_overlay_and_semantic_layers_when_the_plan_has_overlay():
    plan = make_plan()
    evaluator = FfmpegQualityEvaluator(
        probe=FfmpegQualityProbe(analyzer=_FakeAnalyzer()),
        overlay_verifier=_FixedOverlayVerifier((overlay_evidence(plan),)),
    )
    report = evaluator.evaluate(plan, media_path=Path("/tmp/none.mp4"), descriptors=descriptors_for(plan),
                                render_id=RENDER_ID, checksum=CHECKSUM)
    assert CHECK_OVERLAY in report.checks_run
    assert report.coverage.status == "verified"
    assert any(f.check_id == CHECK_SEMANTIC and f.severity == "info" for f in report.findings)
    assert report.is_publishable


def test_evaluator_default_semantic_checker_never_invents_a_pass():
    plan = make_plan()
    evaluator = FfmpegQualityEvaluator(
        probe=FfmpegQualityProbe(analyzer=_FakeAnalyzer()),
        overlay_verifier=_FixedOverlayVerifier((overlay_evidence(plan),)),
    )
    report = evaluator.evaluate(plan, media_path=Path("/tmp/none.mp4"), descriptors=descriptors_for(plan),
                                render_id=RENDER_ID, checksum=CHECKSUM)
    semantic = [f for f in report.findings if f.check_id == CHECK_SEMANTIC]
    assert semantic and semantic[0].severity == "info"
    assert "not verified" in semantic[0].evidence.lower()


# ------------------------------------------------------------------ verificador ffmpeg real

def synth_clip(path, *, overlay_start=1.0, overlay_end=2.0, seconds=3.0, size=(320, 480)):
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=blue:s={size[0]}x{size[1]}:r=24:d={seconds}",
        "-vf", f"drawbox=x=0:y=0:w={size[0]}:h={size[1]}:color=red:t=fill:"
               f"enable='between(t,{overlay_start},{overlay_end})'",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ], check=True, capture_output=True)


@needs_ffmpeg
def test_ffmpeg_overlay_verifier_detects_the_overlay_in_its_window(tmp_path):
    clip = tmp_path / "overlay.mp4"
    synth_clip(clip, overlay_start=1.0, overlay_end=2.0)
    plan = make_plan(overlay_start=1.0, overlay_duration=1.0)
    measured = FfmpegOverlayVerifier().verify(
        plan, media_path=clip, descriptors=descriptors_for(plan, width=320, height=480))
    assert len(measured) == 1
    item = measured[0]
    assert item.measured and item.window_ok and item.present
    assert item.frame_width == 320 and item.frame_height == 480
    assert item.coverage_ratio is not None and item.coverage_ratio > 0.5


@needs_ffmpeg
def test_ffmpeg_overlay_verifier_does_not_invent_presence_without_the_overlay(tmp_path):
    clip = tmp_path / "plain.mp4"
    synth_clip(clip, overlay_start=5.0, overlay_end=6.0)  # a janela planejada fica sem overlay
    plan = make_plan(overlay_start=1.0, overlay_duration=1.0)
    measured = FfmpegOverlayVerifier().verify(
        plan, media_path=clip, descriptors=descriptors_for(plan, width=320, height=480))
    assert len(measured) == 1
    assert measured[0].measured and not measured[0].present


@needs_ffmpeg
def test_ffmpeg_overlay_verifier_reports_unmeasured_when_the_media_is_missing(tmp_path):
    plan = make_plan()
    measured = FfmpegOverlayVerifier().verify(
        plan, media_path=tmp_path / "missing.mp4", descriptors=descriptors_for(plan))
    assert measured and all(not item.measured for item in measured)
    assert measured[0].reason


@needs_ffmpeg
def test_ffmpeg_overlay_verifier_reports_unmeasured_when_the_window_covers_everything(tmp_path):
    clip = tmp_path / "full.mp4"
    synth_clip(clip, overlay_start=0.0, overlay_end=3.0)
    plan = make_plan(overlay_start=0.0, overlay_duration=3.0)
    measured = FfmpegOverlayVerifier().verify(
        plan, media_path=clip, descriptors=descriptors_for(plan, width=320, height=480))
    assert len(measured) == 1
    item = measured[0]
    assert not item.measured and "boundary" in item.reason

