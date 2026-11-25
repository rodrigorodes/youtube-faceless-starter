"""Jornada real do Studio: Short (V4-00 / Homologação).

Complementa a validação com uma execução real ponta a ponta no formato Short:
1. Studio Composition real (`Studio`) com rotas FastAPI e banco PostgreSQL descartável.
2. Provedores locais gratuitos:
   - Texto: `demo` (offline, sem API)
   - Imagem: `placeholder` (PIL local)
   - Voz: `piper` (local ONNX pt_BR-faber-medium)
   - Renderer: `ffmpeg` (`PlanFfmpegRenderer` nativo)
   - QA: `FfmpegQualityEvaluator` com `FfmpegQa` real (EBU R128, ffprobe)
3. Persistência real em banco:
   - Projeto, vídeo, fontes, roteiro, fact-check, assets, render job, plano e qa_report.
4. BudgetGuard real:
   - Teto rígido com custo de API zero ($0.00).
5. Gate de aprovação humana e bloqueio de publicação externa:
   - Render aprovado pelo operador no gate F6.
   - Publicação externa estritamente desabilitada via kill switch (Settings.publication_enabled=False).
"""
from __future__ import annotations

import os
import shutil
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
needs_piper = pytest.mark.skipif(not Path("/opt/voices/pt_BR-faber-medium.onnx").is_file() and shutil.which("piper") is None,
                                 reason="piper voice pt_BR-faber-medium not installed")

SOURCE_TEXT = (
    "A história da computação começou com instrumentos mecânicos como o ábaco e a Pascalina.\n"
    "No século vinte, Alan Turing e John von Neumann estabeleceram os fundamentos dos computadores modernos.\n"
)
SOURCE_URL = "https://pt.wikipedia.org/wiki/Historia_da_computacao"


class SyncExecutor:
    """Executa tarefas em linha de forma síncrona para determinismo no teste."""

    def submit(self, fn, *args):
        fn(*args)

    def shutdown(self, wait=True, cancel_futures=False):
        pass


@needs_ffmpeg
def test_v4_studio_real_flow_complete_journey(conn, dsn, tmp_path: Path):
    """Executa a jornada completa do Studio com providers reais, FFmpeg, QA e BudgetGuard."""
    migrate(conn)

    storage_root = tmp_path / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    # Configuração com provedores locais gratuitos e publicação bloqueada
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

    executor = SyncExecutor()
    studio = Studio(settings, environ=environ, executor=executor)

    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    try:
        # 1. Criação do Projeto e Vídeo (formato Short para execução ágil com FFmpeg real)
        proj_resp = client.post("/studio/projects", json={"name": "Canal História Tech", "niche": "História", "language": "pt-BR"})
        assert proj_resp.status_code in (200, 201), proj_resp.text
        project_id = proj_resp.json()["id"]

        vid_resp = client.post("/studio/videos", json={
            "project_id": project_id,
            "topic": "Origens da Computação",
            "format": "short",
            "target_duration_s": 15,
        })
        assert vid_resp.status_code in (200, 201), vid_resp.text
        video_id = vid_resp.json()["id"]

        # 2. Ingestão de Fontes e Geração de Roteiro
        src_resp = client.post(f"/studio/videos/{video_id}/sources", json={"url": SOURCE_URL, "text": SOURCE_TEXT})
        assert src_resp.status_code in (200, 201), src_resp.text

        script_resp = client.post(f"/studio/videos/{video_id}/script", json={"scene_count": 2})
        assert script_resp.status_code in (200, 201), script_resp.text

        # 3. Fact-Check
        fc_resp = client.post(f"/studio/videos/{video_id}/fact-check", json={})
        assert fc_resp.status_code in (200, 201), fc_resp.text

        # 4. Storyboard
        sb_resp = client.post(f"/studio/videos/{video_id}/storyboard")
        assert sb_resp.status_code in (200, 201), sb_resp.text

        # 5. Assets (produção com PlaceholderImage local)
        asset_resp = client.post(f"/studio/videos/{video_id}/assets")
        assert asset_resp.status_code in (200, 201), asset_resp.text

        # 6. Renderização real via FFmpeg e QA real via FfmpegQa
        render_resp = client.post(f"/studio/videos/{video_id}/render")
        assert render_resp.status_code in (200, 201, 202), render_resp.text

        # 7. Validação do estado pós-render (QA aprovado avança o vídeo para AWAITING_APPROVAL)
        v_info = client.get(f"/studio/videos/{video_id}").json()
        assert v_info["status"] in ("RENDERED", "AWAITING_APPROVAL"), f"Esperado status pós-render, obtido: {v_info['status']}"

        # 8. Validação da persistência de QA Report no banco
        v_repo = PostgresVideoRepository(lambda: psycopg.connect(dsn))
        video_entity = v_repo.get_video(video_id)
        assert video_entity is not None
        assert video_entity.qa_report is not None

        qa = video_entity.qa_report
        assert qa.coverage.status == "verified"
        assert len(qa.blocking_findings) == 0
        assert qa.is_publishable is True

        # 9. Gate de Aprovação Humana (vincula ao output_asset_id exato do render revisado)
        render_info = client.get(f"/studio/videos/{video_id}/render").json()
        output_asset_id = render_info["job"]["output_asset_id"]
        approve_resp = client.post(f"/studio/videos/{video_id}/approve", json={"output_asset_id": output_asset_id, "notes": "Aprovado pelo operador"})
        assert approve_resp.status_code in (200, 201), approve_resp.text

        v_approved = client.get(f"/studio/videos/{video_id}").json()
        assert v_approved["status"] == "APPROVED"

        # 10. Bloqueio Seguro de Publicação Externa
        # Com publication_enabled=False configurado na Settings, o kill switch bloqueia especificamente
        # o executor retornando PublicationResult.BLOCKED, garantindo isolamento total e ausência de chamadas externas.
        pub_resp = client.post(f"/studio/videos/{video_id}/publication/publish")
        assert pub_resp.status_code == 200, pub_resp.text
        pub_data = pub_resp.json()
        assert pub_data["result"] == "BLOCKED", (
            f"Esperado resultado BLOCKED pelo kill switch, obtido: {pub_data.get('result')!r}"
        )
        assert pub_data.get("youtube_video_id") is None, "Upload externo efetuado indevidamente!"
        assert "disabled by configuration" in (pub_data.get("detail") or ""), (
            f"Mensagem de bloqueio esperada não encontrada no detail: {pub_data.get('detail')!r}"
        )

        # 11. Governança de Custos (BudgetGuard)
        u_repo = PostgresUsageRepository(lambda: psycopg.connect(dsn))
        spent = u_repo.spent_video(video_id)
        assert spent == 0.0, f"Gasto financeiro indevido detectado: ${spent:.4f}"

    finally:
        studio.shutdown()
