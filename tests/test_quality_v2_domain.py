"""Testes dos novos checks determinísticos de qualidade (Onda 5 / Task 2)."""
from datetime import datetime, timezone
import pytest

from app.studio.domain.asset_resolver import AssetDescriptor
from app.studio.domain.contracts import VideoFormat
from app.studio.domain.qa_report import QaReport
from app.studio.domain.quality import (
    CHECK_CODEC,
    CHECK_FROZEN_FRAMES,
    CHECK_REPEATED_ASSETS,
    CHECK_TRUE_PEAK,
    QualityEvidence,
    evaluate_quality,
)
from app.studio.domain.render_plan import AssetReference, StyleSnapshot
from app.studio.domain.render_plan_builder import StoryboardScene, build_render_plan

AT = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
SHA = "b" * 64


def _dummy_plan(scene_asset_pairs: list[str]) -> tuple:
    assets = []
    scenes = []
    seen = set()
    for aid in scene_asset_pairs:
        if aid not in seen:
            seen.add(aid)
            assets.append(AssetReference(
                asset_id=aid,
                asset_version=1,
                uri=f"cache/{aid}.png",
                content_sha256=SHA,
                media_type="image",
                license="CC0",
            ))
    for idx, aid in enumerate(scene_asset_pairs):
        scenes.append(StoryboardScene(
            scene_id=f"scene_{idx}",
            asset_id=aid,
            narration="Texto falado do teste.",
            speech_seconds=2.0,
            label="LBL",
        ))

    plan = build_render_plan(
        plan_id="plan:v2",
        revision=1,
        project_id="proj_1",
        video_id="vid_1",
        format=VideoFormat.short,
        scenes=scenes,
        assets=assets,
        style_snapshot=StyleSnapshot(style_id="s1", version=1),
        music=False,
    )
    return plan


def _base_media(duration_s=6.0):
    return {
        "duration_s": duration_s,
        "width": 1080,
        "height": 1920,
        "has_audio": True,
        "integrated_lufs": -16.0,
        "silence_ratio": 0.05,
        "black_ratio": 0.0,
        "narration_lufs": -16.0,
        "narration_silence_ratio": 0.05,
    }


def _descriptors(asset_ids: list[str]) -> tuple[AssetDescriptor, ...]:
    return tuple(
        AssetDescriptor(
            asset_id=aid,
            asset_version=1,
            uri=f"cache/{aid}.png",
            content_sha256=SHA,
            media_type="image",
            license="CC0",
            available=True,
            codec="png",
            width=1080,
            height=1920,
        )
        for aid in set(asset_ids)
    )


def test_true_peak_clipping_generates_blocking_finding():
    plan = _dummy_plan(["ast1", "ast2"])
    media = _base_media()
    media["true_peak_dbtp"] = 0.8  # Acima de 0.0 dBTP -> clipping
    evidence = QualityEvidence(
        render_id="r1",
        checksum=SHA,
        media=media,
        assets=_descriptors(["ast1", "ast2"]),
        generated_at=AT,
    )
    report = evaluate_quality(plan, evidence)
    assert CHECK_TRUE_PEAK in report.checks_run
    peak_findings = [f for f in report.findings if f.check_id == CHECK_TRUE_PEAK]
    assert len(peak_findings) == 1
    assert peak_findings[0].severity == "blocking"
    assert "0.8" in peak_findings[0].evidence or "clipping" in peak_findings[0].evidence.lower()


def test_true_peak_warning_when_above_minus_one_dbtp():
    plan = _dummy_plan(["ast1", "ast2"])
    media = _base_media()
    media["true_peak_dbtp"] = -0.5  # Entre -1.0 e 0.0 dBTP -> warning
    evidence = QualityEvidence(
        render_id="r2",
        checksum=SHA,
        media=media,
        assets=_descriptors(["ast1", "ast2"]),
        generated_at=AT,
    )
    report = evaluate_quality(plan, evidence)
    assert CHECK_TRUE_PEAK in report.checks_run
    peak_findings = [f for f in report.findings if f.check_id == CHECK_TRUE_PEAK]
    assert len(peak_findings) == 1
    assert peak_findings[0].severity == "warning"


def test_codec_check_fails_on_incompatible_video_codec():
    plan = _dummy_plan(["ast1", "ast2"])
    media = _base_media()
    media["video_codec"] = "vp9"
    media["audio_codec"] = "aac"
    evidence = QualityEvidence(
        render_id="r3",
        checksum=SHA,
        media=media,
        assets=_descriptors(["ast1", "ast2"]),
        generated_at=AT,
    )
    report = evaluate_quality(plan, evidence)
    assert CHECK_CODEC in report.checks_run
    codec_findings = [f for f in report.findings if f.check_id == CHECK_CODEC]
    assert len(codec_findings) == 1
    assert codec_findings[0].severity == "blocking"
    assert "vp9" in codec_findings[0].evidence


def test_repeated_assets_in_adjacent_scenes_generates_warning():
    # Cena 0 e Cena 1 usam o mesmo asset 'ast1' em um vídeo com outros assets no manifesto
    plan = _dummy_plan(["ast1", "ast1", "ast2"])
    media = _base_media(duration_s=7.5)
    evidence = QualityEvidence(
        render_id="r4",
        checksum=SHA,
        media=media,
        assets=_descriptors(["ast1", "ast2"]),
        generated_at=AT,
    )
    report = evaluate_quality(plan, evidence)
    assert CHECK_REPEATED_ASSETS in report.checks_run
    rep_findings = [f for f in report.findings if f.check_id == CHECK_REPEATED_ASSETS]
    assert len(rep_findings) == 1
    assert rep_findings[0].severity == "warning"
    assert rep_findings[0].scene_id == "scene_1"
    assert rep_findings[0].auto_fixable is True


def test_frozen_frames_excess_generates_warning():
    plan = _dummy_plan(["ast1", "ast2"])
    media = _base_media()
    media["frozen_ratio"] = 0.35  # 35% de quadros congelados
    evidence = QualityEvidence(
        render_id="r5",
        checksum=SHA,
        media=media,
        assets=_descriptors(["ast1", "ast2"]),
        generated_at=AT,
    )
    report = evaluate_quality(plan, evidence)
    assert CHECK_FROZEN_FRAMES in report.checks_run
    frz_findings = [f for f in report.findings if f.check_id == CHECK_FROZEN_FRAMES]
    assert len(frz_findings) == 1
    assert frz_findings[0].severity == "warning"
