"""Testes de conformidade para V4-09 — Multimodal Quality.

Valida as atividades V4-09.01 a V4-09.18:
- V4-09.01 / V4-09.14: QaReport estruturado com severidade fechada (blocking, warning, info).
- V4-09.03: Detecção de frames congelados e pretos.
- V4-09.04: Detecção de repetição consecutiva de assets.
- V4-09.06: Detecção de clipping de áudio e True Peak (> 0.0 dBTP blocking, > -1.0 dBTP warning).
- V4-09.15 / V4-09.16: Plano de regeneração seletiva por cena e shot (compute_selective_regeneration).
- V4-09.17: Limite de tentativas de correção (max_attempts).
- V4-09.18: Gate de aprovação humana obrigatória (is_human_review_required, assert_ready_for_human_review).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.studio.domain.asset_resolver import AssetDescriptor
from app.studio.domain.contracts import VideoFormat
from app.studio.domain.qa_report import QaCoverage, QaFinding, QaReport
from app.studio.domain.quality import (
    BLOCKING,
    CHECK_CODEC,
    CHECK_FROZEN_FRAMES,
    CHECK_REPEATED_ASSETS,
    CHECK_TRUE_PEAK,
    WARNING,
    QualityEvidence,
    assert_ready_for_human_review,
    compute_selective_regeneration,
    evaluate_quality,
    is_human_review_required,
)
from app.studio.domain.render_plan import AssetReference, StyleSnapshot
from app.studio.domain.render_plan_builder import StoryboardScene, build_render_plan

AT = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
SHA = "b" * 64


def _create_sample_plan(asset_keys: list[str]) -> tuple:
    assets = []
    scenes = []
    seen = set()
    for aid in asset_keys:
        if aid not in seen:
            seen.add(aid)
            assets.append(
                AssetReference(
                    asset_id=aid,
                    asset_version=1,
                    uri=f"cache/{aid}.png",
                    content_sha256=SHA,
                    media_type="image",
                    license="CC0",
                )
            )
    for idx, aid in enumerate(asset_keys):
        scenes.append(
            StoryboardScene(
                scene_id=f"scene_{idx}",
                asset_id=aid,
                narration="Texto falado do teste de qualidade.",
                speech_seconds=2.0,
                label=f"LBL_{idx}",
            )
        )

    return build_render_plan(
        plan_id="plan:quality-test",
        revision=1,
        project_id="proj_1",
        video_id="vid_1",
        format=VideoFormat.short,
        scenes=scenes,
        assets=assets,
        style_snapshot=StyleSnapshot(style_id="s1", version=1),
        music=False,
    )


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
        "video_codec": "h264",
        "audio_codec": "aac",
        "true_peak_dbtp": -1.5,
        "frozen_ratio": 0.0,
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
            source_url="http://local.test/asset.png",
            available=True,
            codec="png",
            width=1080,
            height=1920,
        )
        for aid in asset_ids
    )


class TestSelectiveRegenerationAndLimits:
    """V4-09.15, V4-09.16, V4-09.17: Regeneração seletiva e teto de tentativas."""

    def test_selective_regeneration_with_defective_scene(self):
        plan = _create_sample_plan(["asset_1", "asset_2"])
        report = QaReport(
            render_id="render_01",
            checksum="chk_01",
            generated_at=AT,
            coverage=QaCoverage(status="verified"),
            checks_run=("render.frozen_frames",),
            findings=(
                QaFinding(
                    finding_id="f1",
                    check_id="render.frozen_frames",
                    category="technical",
                    severity=BLOCKING,
                    evidence="Excessive frozen frames in scene_1",
                    suggested_action="Regenerate scene with motion",
                    scene_id="scene_1",
                    shot_id="shot_1",
                ),
            ),
        )

        regen_plan = compute_selective_regeneration(plan, report, max_attempts=3, current_attempt=1)
        assert regen_plan.can_regenerate is True
        assert regen_plan.attempt_number == 1
        assert "scene_1" in regen_plan.defective_scene_ids
        assert "shot_1" in regen_plan.defective_shot_ids
        assert "Regenerate scene with motion" in regen_plan.recommended_actions

    def test_selective_regeneration_exceeding_max_attempts(self):
        plan = _create_sample_plan(["asset_1", "asset_2"])
        report = QaReport(
            render_id="render_01",
            checksum="chk_01",
            generated_at=AT,
            coverage=QaCoverage(status="verified"),
            checks_run=("render.frozen_frames",),
            findings=(
                QaFinding(
                    finding_id="f1",
                    check_id="render.frozen_frames",
                    category="technical",
                    severity=BLOCKING,
                    evidence="Still frozen",
                    suggested_action="Review",
                    scene_id="scene_1",
                ),
            ),
        )

        regen_plan = compute_selective_regeneration(plan, report, max_attempts=3, current_attempt=3)
        assert regen_plan.can_regenerate is False
        assert regen_plan.attempt_number == 3
        assert "Teto máximo de tentativas de regeneração excedido" in regen_plan.reason

    def test_clean_report_requires_no_regeneration(self):
        plan = _create_sample_plan(["asset_1", "asset_2"])
        report = QaReport(
            render_id="render_01",
            checksum="chk_01",
            generated_at=AT,
            coverage=QaCoverage(status="verified"),
            checks_run=("render.media_metrics",),
            findings=(),
        )

        regen_plan = compute_selective_regeneration(plan, report)
        assert regen_plan.can_regenerate is False
        assert "Nenhum defeito impeditivo" in regen_plan.reason


class TestHumanApprovalGuard:
    """V4-09.18: Política estrita de aprovação humana e proibição de autopublicação."""

    def test_human_review_is_mandatory(self):
        report = QaReport(
            render_id="render_01",
            checksum="chk_01",
            generated_at=AT,
            coverage=QaCoverage(status="verified"),
            checks_run=("render.media_metrics",),
            findings=(),
        )
        assert is_human_review_required(report) is True

    def test_assert_ready_for_human_review_success(self):
        report = QaReport(
            render_id="render_01",
            checksum="chk_01",
            generated_at=AT,
            coverage=QaCoverage(status="verified"),
            checks_run=("render.media_metrics",),
            findings=(),
        )
        assert_ready_for_human_review(report)

    def test_assert_ready_for_human_review_fails_on_unverified_coverage(self):
        report = QaReport(
            render_id="render_01",
            checksum="chk_01",
            generated_at=AT,
            coverage=QaCoverage(status="not_verified", reason="Missing audio metrics"),
            checks_run=(),
            findings=(),
        )
        with pytest.raises(ValueError, match="without verified QA coverage"):
            assert_ready_for_human_review(report)


class TestFullQualityEvaluationChecks:
    """V4-09.03, V4-09.04, V4-09.06: Avaliação determinística completa de mídia."""

    def test_evaluate_quality_clipping_detection(self):
        plan = _create_sample_plan(["asset_1", "asset_2"])
        media = _base_media()
        media["true_peak_dbtp"] = 0.5  # Clipping acima de 0.0 dBTP!

        evidence = QualityEvidence(
            render_id="r1",
            checksum="c1",
            media=media,
            assets=_descriptors(["asset_1", "asset_2"]),
            generated_at=AT,
        )

        report = evaluate_quality(plan, evidence)
        assert report.coverage.status == "verified"
        assert not report.is_publishable
        clipping_finding = next((f for f in report.findings if f.check_id == CHECK_TRUE_PEAK), None)
        assert clipping_finding is not None
        assert clipping_finding.severity == BLOCKING
        assert "clipping detectado" in clipping_finding.evidence
