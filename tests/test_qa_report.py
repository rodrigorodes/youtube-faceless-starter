"""Contrato de QA e gate de aprovação: a versão aprovada é a versão publicável.

Estes testes fixam a regra da F6-07: só a versão mais recente, com relatório QA
da mesma versão e sem achados bloqueantes, pode ser aprovada. A execução real dos
checks de mídia não é testada aqui — só o contrato que os representa.
"""

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.studio.domain.contracts import SCHEMA_VERSION, load_versioned
from app.studio.domain.qa_report import (
    BlockingFindings,
    CoverageNotVerified,
    InvalidChecksum,
    InvalidGeneratedAt,
    InvalidRenderId,
    QaCoverage,
    QaFinding,
    QaGateError,
    QaReport,
    RenderSuperseded,
    RenderVersion,
    ReportForOtherRender,
    approve,
    assert_publishable,
)

AT = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
SHA_A = "a" * 64
SHA_B = "b" * 64


def coverage(**changes):
    values = {"status": "verified"}
    values.update(changes)
    return QaCoverage(**values)


def finding(**changes):
    values = {
        "check_id": "codec",
        "category": "technical",
        "severity": "warning",
        "evidence": "ffprobe: h264 1080x1920 25fps, 4:2:0",
        "suggested_action": "re-renderizar o trecho com o mesmo preset",
    }
    values.update(changes)
    return QaFinding(**values)


def report(**changes):
    values = {
        "render_id": "render-1",
        "checksum": SHA_A,
        "generated_at": AT,
        "coverage": coverage(),
        "checks_run": ("codec", "audio"),
        "findings": (),
    }
    values.update(changes)
    return QaReport(**values)


def version(render_id="render-1", checksum=SHA_A):
    return RenderVersion(render_id=render_id, checksum=checksum)


# --- relatório aprovado ------------------------------------------------------


def test_clean_report_on_latest_render_is_approved():
    qa = report()
    approved = approve(report=qa, latest=version(), requested=version())
    assert approved == version()
    assert_publishable(report=qa, latest=version(), requested=version()) is None


def test_approval_returns_the_exact_approved_version():
    approved = approve(report=report(), latest=version(), requested=version())
    assert (approved.render_id, approved.checksum) == ("render-1", SHA_A)


def test_report_with_findings_and_coverage_is_approved_when_nothing_blocks():
    qa = report(
        checks_run=("codec", "audio", "loudness"),
        findings=(
            finding(check_id="loudness", severity="warning"),
            finding(check_id="codec", severity="info"),
        ),
    )
    assert approve(report=qa, latest=version(), requested=version()) == version()


# --- severidades -------------------------------------------------------------


def test_blocking_finding_rejects_approval():
    qa = report(findings=(finding(check_id="audio", severity="blocking"),))
    with pytest.raises(BlockingFindings) as caught:
        approve(report=qa, latest=version(), requested=version())
    assert "audio" in str(caught.value)
    assert issubclass(BlockingFindings, QaGateError)


def test_warning_and_info_do_not_block_but_are_counted():
    qa = report(
        checks_run=("codec", "audio", "loudness"),
        findings=(
            finding(check_id="loudness", severity="warning"),
            finding(check_id="audio", severity="info"),
        ),
    )
    assert qa.is_publishable is True
    assert qa.severity_counts == {"blocking": 0, "warning": 1, "info": 1}
    assert approve(report=qa, latest=version(), requested=version()) == version()


def test_zero_severities_are_counted_explicitly_not_omitted():
    counts = report().severity_counts
    assert counts == {"blocking": 0, "warning": 0, "info": 0}
    assert set(counts) == {"blocking", "warning", "info"}


def test_is_publishable_is_false_with_any_blocking_finding():
    qa = report(
        checks_run=("codec", "audio"),
        findings=(
            finding(check_id="audio", severity="blocking"),
            finding(check_id="codec", severity="info"),
        ),
    )
    assert qa.is_publishable is False
    assert qa.severity_counts["blocking"] == 1


def test_unknown_severity_is_rejected():
    with pytest.raises(ValidationError):
        finding(severity="critical")
    with pytest.raises(ValidationError):
        finding(severity="")
    with pytest.raises(ValidationError):
        finding(severity="BLOCKING")


def test_unknown_category_is_rejected():
    with pytest.raises(ValidationError):
        finding(category="legal")
    with pytest.raises(ValidationError):
        finding(category="")


# --- cobertura: vazio não é aprovável ---------------------------------------


def test_verified_report_without_any_executed_check_is_rejected():
    with pytest.raises(ValidationError):
        report(coverage=coverage(status="verified"), checks_run=(), findings=())


def test_unverified_coverage_requires_a_reason():
    with pytest.raises(ValidationError):
        coverage(status="not_verified")
    with pytest.raises(ValidationError):
        coverage(status="not_verified", reason="   ")


def test_verified_coverage_must_not_carry_a_gap_reason():
    with pytest.raises(ValidationError):
        coverage(status="verified", reason="tudo certo")


def test_unverified_coverage_is_not_approvable():
    qa = report(
        coverage=coverage(status="not_verified", reason="ffprobe indisponível no worker"),
        checks_run=(),
        findings=(),
    )
    assert qa.is_publishable is True  # sem achados bloqueantes, mas cobertura não verificada
    with pytest.raises(CoverageNotVerified):
        approve(report=qa, latest=version(), requested=version())
    with pytest.raises(CoverageNotVerified):
        assert_publishable(report=qa, latest=version(), requested=version())


def test_tampered_report_without_coverage_is_rejected_by_the_gate():
    qa = QaReport.model_construct(
        render_id="render-1",
        checksum=SHA_A,
        generated_at=AT,
        coverage=coverage(status="verified"),
        checks_run=(),
        findings=(),
    )
    with pytest.raises(CoverageNotVerified):
        approve(report=qa, latest=version(), requested=version())


# --- gate por versão: o teste central ---------------------------------------


def test_superseded_render_is_rejected_even_with_a_clean_report():
    stale = version(checksum=SHA_A)
    qa = report(checksum=SHA_A)
    with pytest.raises(RenderSuperseded):
        approve(report=qa, latest=version(checksum=SHA_B), requested=stale)
    with pytest.raises(RenderSuperseded):
        assert_publishable(report=qa, latest=version(checksum=SHA_B), requested=stale)


def test_superseded_render_by_id_is_rejected():
    with pytest.raises(RenderSuperseded):
        approve(
            report=report(render_id="render-1"),
            latest=version(render_id="render-2"),
            requested=version(render_id="render-1"),
        )


def test_report_for_another_render_is_rejected():
    with pytest.raises(ReportForOtherRender):
        approve(
            report=report(render_id="render-old", checksum=SHA_B),
            latest=version(),
            requested=version(),
        )


def test_report_with_other_checksum_for_same_render_is_rejected():
    with pytest.raises(ReportForOtherRender):
        approve(
            report=report(checksum=SHA_B),
            latest=version(),
            requested=version(checksum=SHA_A),
        )


def test_report_identity_matches_requested_not_latest():
    # O relatório é de outro render que também não é o mais recente: o gate
    # recusa primeiro a versão superada.
    with pytest.raises(RenderSuperseded):
        approve(
            report=report(render_id="render-0", checksum=SHA_B),
            latest=version(),
            requested=version(render_id="render-0", checksum=SHA_B),
        )


def test_gate_error_types_are_distinct_and_explicit():
    reasons = [
        InvalidRenderId,
        InvalidChecksum,
        InvalidGeneratedAt,
        RenderSuperseded,
        ReportForOtherRender,
        CoverageNotVerified,
        BlockingFindings,
    ]
    assert len(set(reasons)) == len(reasons)
    for reason in reasons:
        assert issubclass(reason, QaGateError)
        assert issubclass(reason, ValueError)


def test_blank_render_id_is_rejected_by_the_gate():
    with pytest.raises(InvalidRenderId):
        approve(report=report(), latest=version(render_id="  "), requested=version())


def test_blank_checksum_is_rejected_by_the_gate():
    with pytest.raises(InvalidChecksum):
        approve(report=report(), latest=version(checksum=""), requested=version(checksum=""))


def test_tampered_blank_report_checksum_is_rejected_by_the_gate():
    qa = QaReport.model_construct(
        render_id="render-1",
        checksum="",
        generated_at=AT,
        coverage=coverage(),
        checks_run=("codec",),
        findings=(),
    )
    with pytest.raises(InvalidChecksum):
        approve(report=qa, latest=version(), requested=version())


def test_naive_report_instant_is_rejected_by_the_gate():
    qa = QaReport.model_construct(
        render_id="render-1",
        checksum=SHA_A,
        generated_at=datetime(2026, 11, 20, 12, 0),
        coverage=coverage(),
        checks_run=("codec",),
        findings=(),
    )
    with pytest.raises(InvalidGeneratedAt):
        approve(report=qa, latest=version(), requested=version())


# --- integridade dos achados -------------------------------------------------


def test_duplicate_check_id_is_rejected():
    with pytest.raises(ValidationError):
        report(
            checks_run=("codec", "audio"),
            findings=(
                finding(check_id="codec", severity="warning"),
                finding(check_id="codec", severity="blocking"),
            ),
        )


def test_duplicate_checks_run_entry_is_rejected():
    with pytest.raises(ValidationError):
        report(checks_run=("codec", "codec"))


def test_finding_must_reference_an_executed_check():
    with pytest.raises(ValidationError):
        report(checks_run=("audio",), findings=(finding(check_id="codec"),))


def test_empty_evidence_is_rejected():
    with pytest.raises(ValidationError):
        finding(evidence="")
    with pytest.raises(ValidationError):
        finding(evidence="   \n\t ")


def test_empty_suggested_action_is_rejected():
    with pytest.raises(ValidationError):
        finding(suggested_action="")
    with pytest.raises(ValidationError):
        finding(suggested_action="  ")


def test_blank_check_id_is_rejected():
    with pytest.raises(ValidationError):
        finding(check_id="  ")


def test_extra_fields_are_rejected_at_every_level():
    with pytest.raises(ValidationError):
        finding(score=0.9)
    with pytest.raises(ValidationError):
        report(summary="tudo certo")
    with pytest.raises(ValidationError):
        coverage(notes="ok")


def test_blank_report_identity_is_rejected():
    with pytest.raises(ValidationError):
        report(checksum="")
    with pytest.raises(ValidationError):
        report(render_id="   ")


def test_naive_generated_at_is_rejected():
    with pytest.raises(ValidationError):
        report(generated_at=datetime(2026, 11, 20, 12, 0))


# --- imutabilidade e serialização -------------------------------------------


def test_report_is_deeply_immutable():
    qa = report(findings=(finding(check_id="audio", severity="warning"),))
    assert isinstance(qa.findings, tuple)
    assert isinstance(qa.checks_run, tuple)
    with pytest.raises(ValidationError):
        qa.findings = ()
    with pytest.raises(ValidationError):
        qa.checks_run = ()
    with pytest.raises(ValidationError):
        qa.findings[0].severity = "blocking"


def test_round_trip_preserves_the_contract():
    qa = report(
        checks_run=("codec", "audio", "loudness"),
        findings=(
            finding(check_id="loudness", severity="warning", evidence="pico em -1.2 dBFS"),
            finding(check_id="audio", severity="info", evidence="canal único detectado"),
        ),
    )
    restored = QaReport.model_validate_json(qa.model_dump_json())
    assert restored == qa
    assert restored.severity_counts == qa.severity_counts
    assert restored.is_publishable is True
    assert restored.findings[0].severity == "warning"


def test_round_trip_through_load_versioned():
    qa = report()
    payload = qa.model_dump(mode="json")
    assert payload["schema_version"] == SCHEMA_VERSION
    assert load_versioned(QaReport, payload) == qa


def test_unknown_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        QaReport.model_validate({**report().model_dump(mode="json"), "schema_version": SCHEMA_VERSION + 1})
    with pytest.raises(ValueError):
        load_versioned(QaReport, {**report().model_dump(mode="json"), "schema_version": 99})


# --- arquitetura -------------------------------------------------------------


def test_qa_report_module_has_no_outward_or_io_imports():
    source = (
        Path(__file__).resolve().parents[1]
        / "renderer"
        / "app"
        / "studio"
        / "domain"
        / "qa_report.py"
    )
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    forbidden = (
        "app.studio.application",
        "app.studio.adapters",
        "app.studio.api",
        "app.studio.composition",
        "fastapi",
        "psycopg",
        "httpx",
        "subprocess",
        "requests",
        "os",
        "socket",
        "sqlalchemy",
        "urllib",
    )
    assert not {
        module
        for module in imported
        for prefix in forbidden
        if module == prefix or module.startswith(prefix + ".")
    }