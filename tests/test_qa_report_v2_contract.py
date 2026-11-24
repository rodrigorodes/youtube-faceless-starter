"""Testes do contrato QaFinding v2 com metadados de cena e automação (Onda 5 / Task 1)."""
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.studio.domain.qa_report import QaCoverage, QaFinding, QaReport

AT = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def test_qafinding_v2_optional_fields_defaults():
    finding = QaFinding(
        finding_id="f1",
        check_id="check.audio",
        category="technical",
        severity="blocking",
        evidence="Clipping detectado em 0.5 dBTP",
        suggested_action="Abaixar ganho geral",
    )
    assert finding.scene_id is None
    assert finding.shot_id is None
    assert finding.auto_fixable is False
    assert finding.needs_human is False


def test_qafinding_v2_with_scene_and_automation_flags():
    finding = QaFinding(
        finding_id="f2",
        check_id="check.repeated_asset",
        category="editorial",
        severity="warning",
        evidence="Asset 'ast_123' repetido da cena anterior",
        suggested_action="Trocar por candidato alternativo",
        scene_id="scene_002",
        shot_id="shot_001",
        auto_fixable=True,
        needs_human=False,
    )
    assert finding.scene_id == "scene_002"
    assert finding.shot_id == "shot_001"
    assert finding.auto_fixable is True
    assert finding.needs_human is False


def test_qareport_serializes_and_deserializes_v2_findings():
    finding = QaFinding(
        finding_id="f3",
        check_id="check.visual",
        category="editorial",
        severity="warning",
        evidence="Enquadramento necessita revisão manual",
        suggested_action="Revisar enquadramento no storyboard",
        scene_id="scene_005",
        needs_human=True,
    )
    report = QaReport(
        render_id="render_v2",
        checksum=SHA,
        generated_at=AT,
        coverage=QaCoverage(status="verified"),
        checks_run=("check.visual",),
        findings=(finding,),
    )
    dumped = report.model_dump()
    assert dumped["findings"][0]["scene_id"] == "scene_005"
    assert dumped["findings"][0]["needs_human"] is True
    assert dumped["findings"][0]["auto_fixable"] is False

    reloaded = QaReport.model_validate(dumped)
    assert reloaded.findings[0].scene_id == "scene_005"
    assert reloaded.findings[0].needs_human is True
