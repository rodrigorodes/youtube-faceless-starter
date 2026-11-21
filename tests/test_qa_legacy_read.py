"""Regressão RP-07b: leitura tolerante do ``qa_report`` legado (``passed``/``failures``/``metrics``).

Linhas gravadas antes da unificação do QA continuam no shape antigo. O adapter
(``adapters/postgres/repo.py``) precisa fazer o *upcast* para o contrato novo em vez de
estourar (o 500 da prévia); e, como o relatório legado não foi produzido pelo avaliador
atual, ele nunca é publicável sem override humano (cobertura ``not_verified``) — um legado
não pode "alegar QA verificado" para passar o gate de publicação da F8.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

psycopg = pytest.importorskip("psycopg")

from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository, _qa_report  # noqa: E402
from app.studio.application.publication_execution import PublicationResult, RunPublication  # noqa: E402
from app.studio.domain.contracts import Publication, PublicationStatus  # noqa: E402
from app.studio.domain.qa_report import QaCoverage, QaReport, publishable_payload  # noqa: E402
from test_publication_execution import (  # noqa: E402
    CK, NOW, OUT, PUB, R, V, Approvals, Assets, Files, Intents, Jobs, Pubs, Scripts, Snaps, Tokens, Uploads, intent,
)

P = "b" * 32
# O id exato da linha legada que existe no banco do app (AWAITING_APPROVAL, aprovada pela métrica antiga).
LEGACY_ID = "b68b62d9ad994bc5b1b6d9bf7675784f"
# Shape legado exato, como gravado por `contracts.QaReport` antes da adoção do contrato novo.
LEGACY = {
    "passed": True,
    "failures": [],
    "metrics": {"width": 1080, "height": 1920, "has_audio": True, "duration_s": 19.6, "expected_s": 19.6,
                "black_ratio": 0.0, "silence_ratio": 0.0, "narration_lufs": -15.9, "integrated_lufs": -15.4,
                "narration_silence_ratio": 0.1372},
    "schema_version": 1,
}


def seed(conn, video_id=LEGACY_ID, payload=LEGACY, status="AWAITING_APPROVAL"):
    from psycopg.types.json import Jsonb
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p') ON CONFLICT DO NOTHING", (P,))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format, status, qa_report) "
                 "VALUES (%s, %s, 'ADE 2026', 'short', %s, %s)", (video_id, P, status, Jsonb(payload)))
    conn.commit()


@pytest.fixture()
def migrated(conn):
    migrate(conn)
    return conn


# -- upcast (puro, sem banco) ----------------------------------------------------------------

def test_upcast_marks_legacy_as_not_verified_and_preserves_everything():
    report = _qa_report(dict(LEGACY))
    assert isinstance(report, QaReport)
    # Identidade declarada como perdida, nunca fabricada com um valor plausível.
    assert report.render_id == "legacy" and report.checksum == "legacy"
    assert report.coverage.status == "not_verified" and report.coverage.reason
    assert report.checks_run == ("render.legacy_report",)
    assert report.is_publishable is False
    # Nada descartado em silêncio: o payload legado inteiro — inclusive `metrics` — é evidência.
    assert json.dumps(LEGACY, sort_keys=True, ensure_ascii=True) in report.findings[0].evidence
    assert report.findings[0].severity == "info"
    assert publishable_payload(LEGACY) is False and publishable_payload({"passed": True}) is False


def test_upcast_does_not_touch_a_valid_new_report():
    new = QaReport(render_id="a" * 32, checksum="c" * 64, generated_at=datetime(2026, 11, 21, tzinfo=timezone.utc),
                   coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics",))
    assert _qa_report(new.model_dump(mode="json")) == new


def test_corrupt_new_shape_still_fails_loud():
    from pydantic import ValidationError
    corrupt = {"render_id": "a" * 32, "checksum": "c" * 64, "generated_at": "not-a-date",
               "coverage": {"status": "verified"}}
    with pytest.raises(ValidationError):  # não é legado: corrupção do formato novo falha alta
        _qa_report(corrupt)


def test_unknown_schema_version_is_not_tolerated():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):  # shape legado na versão desconhecida não é adivinhado
        _qa_report({"schema_version": 99, "passed": True})


# -- leitura no banco real -------------------------------------------------------------------

def test_get_video_reads_a_legacy_row(migrated, dsn):
    seed(migrated)
    repo = PostgresVideoRepository(lambda: psycopg.connect(dsn))
    video = repo.get_video(LEGACY_ID)  # antes da tolerância: ValidationError (7 erros) → 500 na prévia
    assert video is not None and video.qa_report is not None
    assert video.qa_report.render_id == "legacy"
    assert video.qa_report.coverage.status == "not_verified"
    assert video.qa_report.is_publishable is False
    # A tolerância é só na leitura: a linha no banco continua no shape legado.
    raw = migrated.execute("SELECT qa_report->>'passed' FROM studio.videos WHERE id=%s", (LEGACY_ID,)).fetchone()[0]
    assert raw == "true"


def test_preview_returns_200_for_a_legacy_row(migrated, dsn, tmp_path):
    from test_render_api import make_client

    seed(migrated)
    client, _ = make_client(dsn, tmp_path)
    response = client.get(f"/studio/videos/{LEGACY_ID}/preview")
    assert response.status_code == 200, response.text[:500]
    assert "not_verified" in response.text


# -- gate de publicação ----------------------------------------------------------------------

class RepoVideos:
    """VideoRepository real: lê o ``qa_report`` legado pelo adapter — o ponto sob teste."""

    def __init__(self, repo):
        self._repo = repo

    def get_video(self, video_id):
        return self._repo.get_video(video_id)


def _publish(tmp_path, repo, *, qa_override):
    uploads, tokens = Uploads(), Tokens()
    run = RunPublication(
        RepoVideos(repo), Scripts(), Assets(), Jobs(), Snaps(), Approvals(),
        Intents(intent(qa_passed=False, qa_override=qa_override)),
        Pubs(pub=Publication(id=PUB, video_id=V, status=PublicationStatus.UPLOADING, attempt=1, publish_at=None)),
        Files(tmp_path), uploads, tokens, clock=lambda: NOW)
    return run.execute(), uploads, tokens


def test_legacy_video_cannot_publish_without_override(migrated, dsn, tmp_path):
    seed(migrated, video_id=V)
    repo = PostgresVideoRepository(lambda: psycopg.connect(dsn))
    result, uploads, tokens = _publish(tmp_path, repo, qa_override=False)
    assert result.result is PublicationResult.BLOCKED and "QA" in result.detail
    assert uploads.uploads == [] and tokens.calls == 0  # nada chegou ao provedor


def test_legacy_video_publishes_only_with_a_recorded_override(migrated, dsn, tmp_path):
    seed(migrated, video_id=V)
    repo = PostgresVideoRepository(lambda: psycopg.connect(dsn))
    result, uploads, _ = _publish(tmp_path, repo, qa_override=True)
    assert result.result is PublicationResult.UPLOADED and len(uploads.uploads) == 1
