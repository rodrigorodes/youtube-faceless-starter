"""Testes da UX da aba Qualidade com QaReport v2 (Onda 5 / Task 5)."""
import sys
from pathlib import Path
from datetime import datetime, timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.qa_report import QaCoverage, QaFinding, QaReport  # noqa: E402

AT = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
SHA = "e" * 64


def test_quality_page_renders_scene_badge_and_action_hints(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    repo = PostgresVideoRepository(connect)
    project = repo.create_project("Canal QA V2")
    video = repo.create_video(project.id, "Tema QA V2", VideoFormat.short)

    finding1 = QaFinding(
        finding_id="f_rep",
        check_id="render.repeated_assets",
        category="editorial",
        severity="warning",
        evidence="Asset 'ast_456' repetido da cena anterior",
        suggested_action="Substituir por outro asset",
        scene_id="scene_003",
        auto_fixable=True,
    )
    finding2 = QaFinding(
        finding_id="f_audio",
        check_id="render.true_peak",
        category="technical",
        severity="blocking",
        evidence="True peak excede 0.0 dBTP",
        suggested_action="Reduzir ganho geral de áudio",
        needs_human=True,
    )
    report = QaReport(
        render_id="r_v2",
        checksum=SHA,
        generated_at=AT,
        coverage=QaCoverage(status="verified"),
        checks_run=("render.repeated_assets", "render.true_peak"),
        findings=(finding1, finding2),
    )

    # Persiste qa_report no vídeo
    with connect() as c, c.cursor() as cur:
        import json
        cur.execute("UPDATE studio.videos SET qa_report = %s WHERE id = %s",
                    (json.dumps(report.model_dump(), default=str), video.id))
        c.commit()

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    res = client.get(f"/studio/panel/videos/{video.id}/qualidade")
    assert res.status_code == 200, res.text
    html = res.text

    assert "Cena scene_003" in html
    assert "⚡ Auto-correção" in html
    assert "👤 Requer operador" in html
    assert "Reduzir ganho geral de áudio" in html
    assert "Substituir por outro asset" in html
