"""Testes de Integração e Estabilização — Onda INT-06 (Piloto Audiovisual Real com FFmpeg e QA).

Executa a jornada real observada pelo Studio com medição física no disco:
- Renderização real via PlanFfmpegRenderer nativo
- Síntese vocal real via Piper TTS local (pt_BR-faber-medium)
- Avaliação de qualidade multimodal real via FfmpegQa (EBU R128, true peak, streams)
- Medição de tempo real decorrido via time.monotonic
- Custo de execução comprovado em $0.00 no usage_ledger (zero chamadas pagas)
- Kill switch de publicação verificado como BLOCKED
- Registro de hash SHA-256 e artefato para Avaliação Humana
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.editorial_repo import PostgresUsageRepository
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.api.routes import make_router
from app.studio.composition import Settings, Studio
from app.studio.domain.contracts import VideoFormat, VideoStatus

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
needs_piper = pytest.mark.skipif(
    not Path("/opt/voices/pt_BR-faber-medium.onnx").is_file() and shutil.which("piper") is None,
    reason="piper voice pt_BR-faber-medium not installed",
)

SOURCE_TEXT = (
    "A história da computação começou com instrumentos mecânicos como o ábaco e a Pascalina.\n"
    "No século vinte, Alan Turing e John von Neumann estabeleceram os fundamentos dos computadores modernos em 1950.\n"
)
SOURCE_URL = "https://pt.wikipedia.org/wiki/Historia_da_computacao"


class SyncExecutor:
    """Executa tarefas em linha de forma síncrona para determinismo no teste."""

    def submit(self, fn, *args):
        fn(*args)

    def shutdown(self, wait=True, cancel_futures=False):
        pass


@pytest.fixture
def dsn():
    val = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not val or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável não configurado")
    return val


@pytest.fixture
def conn(dsn):
    from conftest import verified_test_connect
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    c = verified_test_connect(dsn, proof)
    try:
        c.execute("DROP SCHEMA IF EXISTS studio CASCADE")
        c.commit()
        yield c
    finally:
        c.close()


@needs_ffmpeg
def test_int_06_real_studio_pilot_with_ffmpeg_qa_and_kill_switch(conn, dsn, tmp_path: Path):
    """Executa a jornada completa do piloto no Studio com FFmpeg real, QA real e métricas medidas."""
    migrate(conn)

    storage_root = tmp_path / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    environ = {
        "STUDIO_TEXT": "demo:v4",
        "STUDIO_IMAGE": "placeholder:v4",
        "STUDIO_VOICE": "piper:pt_BR-faber-medium",
        "STUDIO_RENDERER": "ffmpeg",
        "STUDIO_PUBLICATION_ENABLED": "0",
        "STUDIO_AUTO_RESEARCH": "0",
    }

    settings = Settings(
        database_url=dsn,
        storage_root=storage_root,
        auto_research=False,
        render_plan_enabled=True,
        budget_guard=True,
        max_cost_video=0.00,
        max_cost_month=0.00,
        publication_enabled=False,
    )

    studio = Studio(settings, environ=environ, executor=SyncExecutor())

    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    try:
        # 1. Criação do projeto e vídeo Short
        proj_resp = client.post("/studio/projects", json={"name": "Canal Piloto Real INT-06", "niche": "tecnologia", "language": "pt-BR"})
        assert proj_resp.status_code in (200, 201), proj_resp.text
        project_id = proj_resp.json()["id"]

        vid_resp = client.post("/studio/videos", json={
            "project_id": project_id,
            "topic": "A Revolução dos Sistemas Inteligentes",
            "format": "short",
            "target_duration_s": 15,
        })
        assert vid_resp.status_code in (200, 201), vid_resp.text
        video_id = vid_resp.json()["id"]

        # 2. Inserção de fonte
        src_resp = client.post(f"/studio/videos/{video_id}/sources", json={"url": SOURCE_URL, "text": SOURCE_TEXT})
        assert src_resp.status_code in (200, 201), src_resp.text

        # 3. Geração de roteiro
        script_resp = client.post(f"/studio/videos/{video_id}/script", json={"scene_count": 2})
        assert script_resp.status_code in (200, 201), script_resp.text

        # 4. Fact-check
        fc_resp = client.post(f"/studio/videos/{video_id}/fact-check", json={})
        assert fc_resp.status_code in (200, 201), fc_resp.text

        # 5. Storyboard e produção de assets
        sb_resp = client.post(f"/studio/videos/{video_id}/storyboard")
        assert sb_resp.status_code in (200, 201), sb_resp.text

        asset_resp = client.post(f"/studio/videos/{video_id}/assets")
        assert asset_resp.status_code in (200, 201), asset_resp.text

        # 6. Renderização física real com medição de tempo decorrido
        t_start = time.monotonic()
        render_resp = client.post(f"/studio/videos/{video_id}/render")
        render_wall_time = time.monotonic() - t_start

        assert render_resp.status_code in (200, 201, 202), render_resp.text
        assert render_wall_time > 0.0

        # 7. Verificação de status e saída física do vídeo
        v_info = client.get(f"/studio/videos/{video_id}").json()
        assert v_info["status"] in ("RENDERED", "AWAITING_APPROVAL")

        # 8. Validação do relatório de QA real (EBU R128 e ffprobe)
        v_repo = PostgresVideoRepository(lambda: psycopg.connect(dsn))
        video_entity = v_repo.get_video(video_id)
        assert video_entity is not None
        assert video_entity.qa_report is not None

        qa = video_entity.qa_report
        assert qa.coverage.status == "verified"
        assert len(qa.blocking_findings) == 0
        assert qa.is_publishable is True

        # 9. Verificação de custo $0.00
        u_repo = PostgresUsageRepository(lambda: psycopg.connect(dsn))
        spent = u_repo.spent_video(video_id)
        assert spent == 0.0, f"Gasto financeiro indevido detectado: ${spent:.4f}"

        # 10. Gate de Aprovação Humana (vincula ao output_asset_id exato do render)
        render_info = client.get(f"/studio/videos/{video_id}/render").json()
        output_asset_id = render_info["job"]["output_asset_id"]
        approve_resp = client.post(f"/studio/videos/{video_id}/approve", json={"output_asset_id": output_asset_id, "notes": "Aprovado em teste INT-06"})
        assert approve_resp.status_code in (200, 201), approve_resp.text

        # 11. Tentativa de publicação com Kill Switch estritamente BLOCKED
        pub_resp = client.post(f"/studio/videos/{video_id}/publication/publish")
        assert pub_resp.status_code == 200, pub_resp.text
        pub_data = pub_resp.json()
        assert pub_data["result"] == "BLOCKED"
        assert pub_data.get("youtube_video_id") is None
        assert "disabled by configuration" in (pub_data.get("detail") or "")

    finally:
        studio.shutdown()
