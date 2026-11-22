"""Fluxo de produção ponta-a-ponta pelo painel/HTTP contra o Postgres descartável.

Cria o run direto no coordenador (sem disparar o worker) para as ações serem determinísticas; a
API lê a projeção real e valida as transições condicionadas ao estado (F2-03/F2-05).
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.studio.api.routes import make_router  # noqa: E402
from app.studio.application.production import StageCapabilityUnavailable  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.production_run import ProductionStage  # noqa: E402


@pytest.fixture()
def studio(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    return Studio(Settings(database_url=dsn, storage_root=tmp_path))


@pytest.fixture()
def client(studio):
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return TestClient(app, headers={"Authorization": "Bearer test-worker-token"})


@pytest.fixture()
def video_id(client):
    pid = client.post("/studio/projects", json={"name": "canal"}).json()["id"]
    return client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": "short"}).json()["id"]


def _start(studio, video_id, key="flow-1"):
    uc = studio.use_cases()
    assert uc is not None and uc.production is not None
    return uc.production.coordinator.start(video_id, key)


def test_production_flow_get_actions_and_events(studio, client, video_id):
    creation = _start(studio, video_id)
    run_id = creation.run.run_id

    response = client.get(f"/studio/videos/{video_id}/production-runs/{run_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "CREATED"
    assert body["next_action"] == "run" and body["next_stage"] == "script"
    assert [item["stage"] for item in body["stages"]] == [
        "script", "factcheck", "storyboard", "assets", "render", "qa", "approval", "publish"]
    assert {item["stage"] for item in body["unavailable_stages"]} == {"research"}
    assert body["events"][0]["event_type"] == "production.run.created"

    assert client.post(f"/studio/videos/{video_id}/production-runs/{run_id}/pause",
                       json={"reason": "revisão"}).status_code == 200
    assert client.get(f"/studio/videos/{video_id}/production-runs/{run_id}").json()["state"] == "WAITING_HUMAN"
    assert client.get(f"/studio/videos/{video_id}/production-runs/{run_id}").json()["next_action"] == "resume"

    assert client.post(f"/studio/videos/{video_id}/production-runs/{run_id}/resume").status_code == 200
    assert client.post(f"/studio/videos/{video_id}/production-runs/{run_id}/cancel",
                       json={"reason": "desistiu"}).status_code == 200
    assert client.post(f"/studio/videos/{video_id}/production-runs/{run_id}/cancel").status_code == 409
    assert client.post(f"/studio/videos/{video_id}/production-runs/{run_id}/pause").status_code == 409
    assert client.post(f"/studio/videos/{video_id}/production-runs/{run_id}/retry").status_code == 409


def test_production_flow_idempotent_start_does_not_duplicate(studio, video_id):
    first = _start(studio, video_id, "flow-2")
    replay = _start(studio, video_id, "flow-2")
    assert first.result.value == "CREATED" and replay.result.value == "EXISTING"
    assert replay.run.run_id == first.run.run_id


def test_production_flow_rejects_unavailable_stage(studio, video_id):
    uc = studio.use_cases()
    with pytest.raises(StageCapabilityUnavailable):
        uc.production.coordinator.start(video_id, "flow-3", stages=[ProductionStage.RESEARCH])


def test_production_run_of_another_video_is_404(studio, client, video_id):
    run_id = _start(studio, video_id, "flow-4").run.run_id
    # Outro vídeo (inexistente) com o mesmo run_id não confunde o roteador: o run não é dele.
    assert client.get(f"/studio/videos/{'9' * 32}/production-runs/{run_id}").status_code == 404


# -- F03.T02: a subida real (composition) congela a configuração no start ---------


def test_composition_start_persists_an_immutable_effective_config(studio, video_id):
    """A fiação única resolve a config e grava o snapshot junto do run, antes de qualquer efeito."""
    from app.studio.domain.run_config import RunConfigStatus

    uc = studio.use_cases()
    production = uc.production
    assert production is not None and production.effective_config_for is not None
    creation = production.coordinator.start(
        video_id, "flow-cfg-1",
        effective_config_for=production.effective_config_for, config_store=production.config_store)

    stored = production.config_for(creation.run.run_id)
    assert stored is not None and stored.status is RunConfigStatus.RESOLVED
    assert stored.config is not None
    assert stored.config.project_id and stored.config.video_id == video_id
    # Sem canal/estilo no projeto, valem os defaults explícitos do motor (não um snapshot vazio).
    assert stored.config.language == "pt-BR"
    assert stored.config.provenance["editorial.language"] == "engine_default"
    assert stored.config.provenance["style"] == "engine_default"

    replay = production.coordinator.start(
        video_id, "flow-cfg-1",
        effective_config_for=production.effective_config_for, config_store=production.config_store)
    assert replay.result.value == "EXISTING"
    assert production.config_for(replay.run.run_id).config.content_hash == stored.config.content_hash
