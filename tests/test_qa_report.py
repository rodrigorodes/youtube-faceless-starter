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
    InvalidRenderVersion,
    InvalidReportState,
    QaCoverage,
    QaFinding,
    QaGateError,
    QaReport,
    RenderSuperseded,
    RenderVersion,
    ReportForOtherRender,
    approve,
    assert_publishable,
    blocking_evidence,
    publishable_payload,
)

AT = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
SHA_A = "a" * 64
SHA_B = "b" * 64
ZWSP = "\u200b"
ZWNJ = "\u200c"
BOM = "\ufeff"


def coverage(**changes):
    values = {"status": "verified"}
    values.update(changes)
    return QaCoverage(**values)


def finding(**changes):
    values = {
        "finding_id": "f-codec",
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
    assert assert_publishable(report=qa, latest=version(), requested=version()) is None


def test_approval_returns_the_exact_approved_version_without_normalization():
    requested = version(render_id="render-1")
    approved = approve(report=report(), latest=version(), requested=requested)
    assert approved is requested or approved == requested
    assert approved.render_id == "render-1"
    assert approved.checksum == SHA_A


def test_report_with_findings_and_coverage_is_approved_when_nothing_blocks():
    qa = report(
        checks_run=("codec", "audio", "loudness"),
        findings=(
            finding(finding_id="f-loudness", check_id="loudness", severity="warning"),
            finding(finding_id="f-codec", check_id="codec", severity="info"),
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
            finding(finding_id="f-loudness", check_id="loudness", severity="warning"),
            finding(finding_id="f-audio", check_id="audio", severity="info"),
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
            finding(finding_id="f-audio", check_id="audio", severity="blocking"),
            finding(finding_id="f-codec", check_id="codec", severity="info"),
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


# --- severidade contornada por model_copy: falha fechada --------------------


def test_tampered_severity_counts_as_blocking_in_publishable():
    tampered = finding(severity="warning").model_copy(update={"severity": "BLOCKING"})
    qa = report().model_copy(update={"findings": (tampered,)})
    assert qa.is_publishable is False
    assert qa.severity_counts == {"blocking": 1, "warning": 0, "info": 0}
    assert qa.blocking_findings == (tampered,)


def test_tampered_unknown_severity_also_counts_as_blocking():
    tampered = finding(severity="warning").model_copy(update={"severity": "crit"})
    qa = report().model_copy(update={"findings": (tampered,)})
    assert qa.is_publishable is False
    assert qa.severity_counts["blocking"] == 1


def test_non_finding_item_fails_closed_in_publishable():
    qa = report().model_copy(update={"findings": ("not-a-finding",)})
    assert qa.is_publishable is False
    assert qa.severity_counts["blocking"] == 1


def blocking_iterator():
    return (finding(severity="blocking") for _ in range(2))


def test_properties_do_not_consume_single_use_findings_and_fail_closed():
    qa = report().model_copy(update={"findings": blocking_iterator()})
    assert qa.is_publishable is False
    assert qa.severity_counts["blocking"] >= 1
    assert qa.is_publishable is False
    assert qa.severity_counts["blocking"] >= 1
    assert len(qa.blocking_findings) == 1


def test_gate_rejects_single_use_findings_iterator_without_prior_read():
    qa = report().model_copy(update={"findings": blocking_iterator()})
    with pytest.raises(InvalidReportState):
        approve(report=qa, latest=version(), requested=version())


def test_gate_rejects_single_use_findings_iterator_after_prior_read():
    qa = report().model_copy(update={"findings": blocking_iterator()})
    _ = qa.severity_counts
    assert qa.is_publishable is False
    with pytest.raises(InvalidReportState):
        approve(report=qa, latest=version(), requested=version())


@pytest.mark.parametrize("collection", ["list", "set", "dict", "iterator"])
def test_gate_rejects_non_tuple_collections(collection):
    values = {
        "list": [finding(check_id="audio")],
        "set": {finding(check_id="audio")},
        "dict": {"codec": finding(check_id="audio")},
        "iterator": iter((finding(check_id="audio"),)),
    }
    qa = report().model_copy(update={"findings": values[collection]})
    with pytest.raises(InvalidReportState):
        approve(report=qa, latest=version(), requested=version())


def test_gate_rejects_non_tuple_checks_run():
    qa = report().model_copy(update={"checks_run": ["codec"]})
    with pytest.raises(InvalidReportState):
        approve(report=qa, latest=version(), requested=version())


@pytest.mark.parametrize("severity", ["BLOCKING", "crit", "blocking "])
def test_gate_rejects_tampered_finding_severity(severity):
    base = finding(severity="info")
    tampered = base.model_copy(update={"severity": severity})
    qa = report(findings=(base,)).model_copy(update={"findings": (tampered,)})
    with pytest.raises(InvalidReportState):
        approve(report=qa, latest=version(), requested=version())
    with pytest.raises(InvalidReportState):
        assert_publishable(report=qa, latest=version(), requested=version())


def test_gate_rejects_tampered_finding_referencing_unknown_check():
    tampered = finding(check_id="audio").model_copy(update={"check_id": "frame_black"})
    qa = report(findings=(finding(check_id="audio"),)).model_copy(update={"findings": (tampered,)})
    with pytest.raises(InvalidReportState):
        approve(report=qa, latest=version(), requested=version())


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


def test_unverified_coverage_is_not_publishable_and_not_approvable():
    qa = report(
        coverage=coverage(status="not_verified", reason="ffprobe indisponível no worker"),
        checks_run=(),
        findings=(),
    )
    assert qa.is_publishable is False
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


def test_tampered_blank_checks_run_is_rejected_by_the_gate():
    qa = report().model_copy(update={"checks_run": ("   ",)})
    assert qa.is_publishable is False
    with pytest.raises(CoverageNotVerified):
        approve(report=qa, latest=version(), requested=version())


def test_tampered_coverage_status_is_rejected_by_the_gate():
    qa = report().model_copy(update={"coverage": coverage().model_copy(update={"status": "verified "})})
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
        InvalidRenderVersion,
        InvalidGeneratedAt,
        InvalidReportState,
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


def test_identities_with_edge_whitespace_are_rejected_not_normalized():
    with pytest.raises(InvalidRenderId):
        approve(report=report(), latest=version(render_id=" render-1"), requested=version())
    with pytest.raises(InvalidChecksum):
        approve(report=report(), latest=version(checksum=SHA_A + " "), requested=version())
    with pytest.raises(ValidationError):
        report(render_id=" render-1")
    with pytest.raises(ValidationError):
        report(checksum=" " + SHA_A)


def test_identities_with_invisible_characters_are_rejected_by_the_gate():
    with pytest.raises(InvalidRenderId):
        approve(report=report(), latest=version(render_id="render-1" + ZWSP), requested=version())
    with pytest.raises(InvalidChecksum):
        approve(report=report(), latest=version(checksum=SHA_A + BOM), requested=version())


@pytest.mark.parametrize("field", ["latest", "requested"])
def test_gate_rejects_none_render_versions(field):
    kwargs = {"report": report(), "latest": version(), "requested": version()}
    kwargs[field] = None
    with pytest.raises(InvalidRenderVersion):
        approve(**kwargs)


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


def test_duplicate_finding_id_is_rejected():
    with pytest.raises(ValidationError):
        report(
            checks_run=("codec", "audio"),
            findings=(
                finding(finding_id="f-1", check_id="codec", severity="warning"),
                finding(finding_id="f-1", check_id="audio", severity="blocking"),
            ),
        )


def test_two_findings_for_the_same_check_are_allowed():
    qa = report(
        checks_run=("codec", "audio"),
        findings=(
            finding(
                finding_id="f-codec-color",
                check_id="codec",
                severity="warning",
                evidence="pixel format yuv420p inesperado",
                suggested_action="re-renderizar forçando yuv420p",
            ),
            finding(
                finding_id="f-codec-resolution",
                check_id="codec",
                severity="blocking",
                evidence="resolução 720x1280 em vez de 1080x1920",
                suggested_action="re-renderizar na resolução do formato",
            ),
        ),
    )
    assert qa.severity_counts == {"blocking": 1, "warning": 1, "info": 0}
    with pytest.raises(BlockingFindings) as caught:
        approve(report=qa, latest=version(), requested=version())
    assert "codec" in str(caught.value)


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


@pytest.mark.parametrize("invisible", [ZWSP, ZWNJ, BOM])
@pytest.mark.parametrize("field", ["evidence", "suggested_action", "check_id"])
def test_invisible_text_is_rejected_in_finding(field, invisible):
    with pytest.raises(ValidationError):
        finding(**{field: invisible})
    with pytest.raises(ValidationError):
        finding(**{field: "ok" + invisible})


@pytest.mark.parametrize("invisible", [ZWSP, ZWNJ, BOM])
def test_invisible_text_is_rejected_in_coverage_reason(invisible):
    with pytest.raises(ValidationError):
        coverage(status="not_verified", reason=invisible)


@pytest.mark.parametrize("separator", ["\u2028", "\u2029"])
def test_unicode_line_separators_are_rejected_in_single_line_text(separator):
    with pytest.raises(ValidationError):
        finding(suggested_action="a" + separator + "b")
    with pytest.raises(ValidationError):
        coverage(status="not_verified", reason="a" + separator + "b")
    with pytest.raises(ValidationError):
        report(render_id="render" + separator + "1")


@pytest.mark.parametrize("separator", ["\u2028", "\u2029"])
def test_unicode_line_separators_are_rejected_in_evidence(separator):
    with pytest.raises(ValidationError):
        finding(evidence="a" + separator + "b")


@pytest.mark.parametrize("space", ["\u00a0", "\u3000"])
@pytest.mark.parametrize("field", ["render_id", "checksum"])
def test_interior_unicode_spaces_are_rejected_in_report_identity(field, space):
    value = "render-1" if field == "render_id" else SHA_A
    with pytest.raises(ValidationError):
        report(**{field: value[:4] + space + value[4:]})


@pytest.mark.parametrize("space", ["\u00a0", "\u3000"])
@pytest.mark.parametrize("field", ["check_id", "finding_id"])
def test_interior_unicode_spaces_are_rejected_in_finding_identity(field, space):
    value = "codec" if field == "check_id" else "f-1"
    with pytest.raises(ValidationError):
        finding(**{field: value[:2] + space + value[2:]})


def test_gate_rejects_interior_unicode_spaces_in_identities():
    with pytest.raises(InvalidRenderId):
        approve(report=report(), latest=version(render_id="render\u00a01"), requested=version())
    with pytest.raises(InvalidChecksum):
        approve(
            report=report(),
            latest=version(checksum=SHA_A[:8] + "\u3000" + SHA_A[8:]),
            requested=version(),
        )


def test_newline_is_allowed_in_evidence_but_not_in_suggested_action():
    assert finding(evidence="linha 1\nlinha 2").evidence == "linha 1\nlinha 2"
    with pytest.raises(ValidationError):
        finding(suggested_action="linha 1\nlinha 2")


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
            finding(finding_id="f-loudness", check_id="loudness", severity="warning", evidence="pico em -1.2 dBFS"),
            finding(finding_id="f-audio", check_id="audio", severity="info", evidence="canal único detectado"),
        ),
    )
    restored = QaReport.model_validate_json(qa.model_dump_json())
    assert restored == qa
    assert restored.severity_counts == qa.severity_counts
    assert restored.is_publishable is True
    assert restored.findings[0].severity == "warning"
    assert restored.findings[0].finding_id == "f-loudness"


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


# --- leitura do relatório persistido (adoção RP-07b) -------------------------


def test_publishable_payload_reads_the_persisted_shape_and_legacy_rows():
    assert publishable_payload(report().model_dump(mode="json")) is True
    blocked = report(findings=(finding(finding_id="f-audio", check_id="audio", severity="blocking", evidence="sem áudio"),))
    assert publishable_payload(blocked.model_dump(mode="json")) is False
    # linhas gravadas ANTES da adoção (shape legado) NÃO são publicáveis: não foram produzidas
    # pelo avaliador atual e não podem "alegar QA verificado" (só override humano libera).
    assert publishable_payload({"schema_version": 1, "passed": True, "failures": [], "metrics": {}}) is False
    assert publishable_payload({"schema_version": 1, "passed": False, "failures": ["x"]}) is False
    assert publishable_payload(None) is False and publishable_payload({}) is False


def test_blocking_evidence_translates_the_findings_for_display():
    blocked = report(findings=(
        finding(finding_id="f-audio", check_id="audio", severity="blocking", evidence="sem áudio"),
        finding(finding_id="f-codec", check_id="codec", severity="warning", evidence="ffprobe: 4:2:0"),
    ))
    assert blocking_evidence(blocked) == ("sem áudio",)


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
        "pathlib",
        "json",
        "logging",
        "time",
        "random",
        "shutil",
        "glob",
        "io",
    )
    assert not {
        module
        for module in imported
        for prefix in forbidden
        if module == prefix or module.startswith(prefix + ".")
    }