"""Contrato HTTP dos endpoints de produção (D2/F1-04/F2-03/F2-05).

Erro de negócio nunca pode sair como 500; ações condicionadas ao estado; eventos sem segredos.
"""
from datetime import datetime, timezone
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.studio.api.routes import make_router  # noqa: E402
from app.studio.application.production import (  # noqa: E402
    ProductionMode,
    ProductionProjection,
    RunNotFound,
    StageCapabilityUnavailable,
)
from app.studio.domain.production_run import (  # noqa: E402
    CreateRunResult,
    InvalidIdempotencyKey,
    InvalidPipeline,
    OutboxEvent,
    ProductionIdempotencyConflict,
    ProductionRun,
    ProductionRunLockTimeout,
    ProductionRunReferencedEntityNotFound,
    ProductionStage,
    ProgressEventType,
    RunCreation,
    RunState,
    RunTransition,
    RunTransitionResult,
    StageExecution,
    StageState,
)
from app.studio.domain.ids import check_id  # noqa: E402

VIDEO = "b" * 32
RUN = "a" * 32


def _run(state=RunState.CREATED, video=VIDEO):
    return ProductionRun(run_id=RUN, video_id=video, idempotency_key="req-1", state=state)


def _stage(stage, state):
    return StageExecution(run_id=RUN, stage_id=ProductionStage(stage), state=StageState(state))


def _projection(state=RunState.CREATED, video=VIDEO, next_action="run", next_stage=ProductionStage.SCRIPT,
                stages=None):
    return ProductionProjection(
        run=_run(state, video),
        stages=tuple(stages or [_stage("script", "PENDING"), _stage("factcheck", "PENDING")]),
        next_stage=next_stage, next_action=next_action, mode=ProductionMode.INTERACTIVE,
        available_stages=(ProductionStage.SCRIPT, ProductionStage.APPROVAL),
        unavailable_stages=((ProductionStage.RESEARCH, "sem research"),))


class _Coordinator:
    """Dublê do coordenador: devolve projeções/transições e pode simular erros."""

    mode = ProductionMode.INTERACTIVE

    def __init__(self, *, projection=None, start_result=None, start_error=None, transition=None,
                 retry_error=None, events=()):
        self._projection = projection
        self._start_result = start_result
        self._start_error = start_error
        self._transition = transition
        self._retry_error = retry_error
        self._events = list(events)
        self.started = []

    def start(self, video_id, key, *, channel_id=None, stages=None):
        if self._start_error is not None:
            raise self._start_error
        self.started.append((check_id(video_id), key, channel_id, stages))
        return self._start_result

    def get(self, run_id):
        return self._projection

    def events(self, run_id, limit=100):
        return self._events

    def pause(self, run_id, reason):
        return self._transition

    def resume(self, run_id, *, expected_state=None):
        return self._transition

    def cancel(self, run_id, reason):
        return self._transition

    def retry(self, run_id, *, expected_state=RunState.FAILED):
        if self._retry_error is not None:
            raise self._retry_error
        return self._transition

    def regenerate(self, run_id, *, revision=1, reason=None):
        if self._retry_error is not None:
            raise self._retry_error
        self.regenerated = (run_id, revision, reason)
        return self._start_result


class _Production:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.worker = None

    def start(self, video_id, key, *, channel_id=None, stages=None):
        return self.coordinator.start(video_id, key, channel_id=channel_id, stages=stages)

    def resume(self, run_id, *, expected_state=None):
        return self.coordinator.resume(run_id, expected_state=expected_state)

    def retry(self, run_id):
        return self.coordinator.retry(run_id)

    def regenerate(self, run_id, *, revision=1, reason=None):
        return self.coordinator.regenerate(run_id, revision=revision, reason=reason)


class _UseCases:
    def __init__(self, production):
        self.production = production


def client(coordinator):
    app = FastAPI()
    app.include_router(make_router(lambda: _UseCases(_Production(coordinator)), lambda: True))
    return TestClient(app, headers={"Authorization": "Bearer test-worker-token"})


def _creation(result=CreateRunResult.CREATED):
    return RunCreation(result, _run())


def test_start_returns_202_with_run_id_and_is_idempotent():
    coordinator = _Coordinator(start_result=_creation())
    response = client(coordinator).post(f"/studio/videos/{VIDEO}/production-runs", headers={"Idempotency-Key": "req-1"})
    assert response.status_code == 202
    body = response.json()
    assert body == {"run_id": RUN, "state": "CREATED", "mode": "INTERACTIVE", "created": True}

    replay = _Coordinator(start_result=_creation(CreateRunResult.EXISTING))
    again = client(replay).post(f"/studio/videos/{VIDEO}/production-runs", headers={"Idempotency-Key": "req-1"})
    assert again.status_code == 202 and again.json()["created"] is False


def test_start_requires_an_idempotency_key():
    coordinator = _Coordinator(start_result=_creation())
    response = client(coordinator).post(f"/studio/videos/{VIDEO}/production-runs", json={})
    assert response.status_code == 400
    assert coordinator.started == []


def test_start_accepts_key_from_body_and_unknown_stage_is_422():
    coordinator = _Coordinator(start_result=_creation())
    assert client(coordinator).post(f"/studio/videos/{VIDEO}/production-runs",
                                    json={"idempotency_key": "req-1"}).status_code == 202
    assert client(coordinator).post(f"/studio/videos/{VIDEO}/production-runs",
                                    json={"idempotency_key": "req-1", "stages": ["nope"]}).status_code == 422


@pytest.mark.parametrize(("error", "status"), [
    (ProductionIdempotencyConflict("k"), 409),
    (InvalidIdempotencyKey("k"), 422),
    (ProductionRunLockTimeout("locked"), 409),
    (ProductionRunReferencedEntityNotFound("missing"), 404),
    (StageCapabilityUnavailable(ProductionStage.PUBLISH, "sem publicação"), 409),
    (InvalidPipeline("cycle"), 422),
    (RunNotFound(RUN), 404),
])
def test_business_errors_never_become_500(error, status):
    coordinator = _Coordinator(start_error=error)
    response = client(coordinator).post(f"/studio/videos/{VIDEO}/production-runs",
                                        headers={"Idempotency-Key": "req-1"})
    assert response.status_code == status
    assert "Traceback" not in response.text


def test_get_returns_projection_next_action_and_events_without_secrets():
    event = OutboxEvent(id=1, run_id=RUN, event_type=ProgressEventType.STAGE_CLAIMED, stage_id=ProductionStage.SCRIPT,
                        payload={"run_id": RUN, "stage_id": "script", "attempt": 1, "fencing_token": 1,
                                 "lease_owner": "worker-1", "lease_expires_at": None},
                        created_at=datetime.now(timezone.utc))
    coordinator = _Coordinator(projection=_projection(), events=[event])
    response = client(coordinator).get(f"/studio/videos/{VIDEO}/production-runs/{RUN}")
    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == "run" and body["next_stage"] == "script"
    assert {item["stage"] for item in body["unavailable_stages"]} == {"research"}
    assert body["events"][0]["event_type"] == "production.stage.claimed"
    assert "token" not in str(body).lower().replace("fencing_token", "")


def test_get_is_404_for_unknown_run_or_other_video():
    assert client(_Coordinator(projection=None)).get(
        f"/studio/videos/{VIDEO}/production-runs/{RUN}").status_code == 404
    other = _Coordinator(projection=_projection(video="9" * 32))
    assert client(other).get(f"/studio/videos/{VIDEO}/production-runs/{RUN}").status_code == 404


@pytest.mark.parametrize("action", ["pause", "resume", "cancel"])
def test_actions_map_state_conflict_to_409(action):
    not_allowed = _Coordinator(projection=_projection(), transition=RunTransition(RunTransitionResult.NOT_ALLOWED, _run()))
    assert client(not_allowed).post(f"/studio/videos/{VIDEO}/production-runs/{RUN}/{action}").status_code == 409

    applied = _Coordinator(projection=_projection(), transition=RunTransition(RunTransitionResult.APPLIED, _run(RunState.RUNNING)))
    response = client(applied).post(f"/studio/videos/{VIDEO}/production-runs/{RUN}/{action}")
    assert response.status_code == 200 and response.json()["state"] == "RUNNING"


def test_retry_is_only_for_failed_runs():
    blocked = _Coordinator(projection=_projection(), transition=RunTransition(RunTransitionResult.NOT_ALLOWED, _run(RunState.RUNNING)))
    assert client(blocked).post(f"/studio/videos/{VIDEO}/production-runs/{RUN}/retry").status_code == 409
    applied = _Coordinator(projection=_projection(), transition=RunTransition(RunTransitionResult.APPLIED, _run(RunState.RUNNING)))
    assert client(applied).post(f"/studio/videos/{VIDEO}/production-runs/{RUN}/retry").status_code == 200


def test_actions_are_404_for_an_unknown_run():
    coordinator = _Coordinator(projection=None)
    assert client(coordinator).post(f"/studio/videos/{VIDEO}/production-runs/{RUN}/pause").status_code == 404


# -- F03.T04: lifecycle — o legado recusa com mensagem clara e a trilha é pública --


def test_retry_on_a_legacy_run_is_409_with_a_clear_message():
    """Run legado não finge reproduzir a configuração: a recusa chega com o motivo, não como 500."""
    from app.studio.application.production import RunConfigUnavailable

    error = RunConfigUnavailable(
        "this operation needs the frozen run config, but the run was created without a snapshot "
        "(legacy): its inputs cannot be reproduced. Start a new run to adopt a new revision.")
    coordinator = _Coordinator(projection=_projection(), transition=None, retry_error=error)
    response = client(coordinator).post(f"/studio/videos/{VIDEO}/production-runs/{RUN}/retry")
    assert response.status_code == 409
    assert "legacy" in response.json()["detail"] and "new run" in response.json()["detail"]
    assert "Traceback" not in response.text


def test_get_exposes_the_lifecycle_decision_event_without_secrets():
    event = OutboxEvent(id=9, run_id=RUN, event_type=ProgressEventType.RUN_OPERATION,
                        payload={"run_id": RUN, "operation": "regenerate", "label": "Gerar novamente (execução nova)",
                                 "reason": "regenerate; execução nova", "config_status": "resolved",
                                 "config_hash": "a" * 64, "source_run_id": "c" * 32,
                                 "uses_frozen_config": False},
                        created_at=datetime.now(timezone.utc))
    coordinator = _Coordinator(projection=_projection(state=RunState.CREATED), events=[event])
    body = client(coordinator).get(f"/studio/videos/{VIDEO}/production-runs/{RUN}").json()

    assert body["events"][0]["event_type"] == "production.run.operation"
    payload = body["events"][0]["payload"]
    assert payload["operation"] == "regenerate" and payload["source_run_id"] == "c" * 32
    dumped = str(body).lower().replace("fencing_token", "")
    for forbidden in ("api_key", "password", "secret", "config_snapshot", "authorization"):
        assert forbidden not in dumped


def test_regenerate_is_a_new_run_and_forwards_revision():
    """F03.T04: regenerar é execução nova — a rota responde 202 com a criação nova."""
    coordinator = _Coordinator(projection=_projection(), start_result=_creation())
    response = client(coordinator).post(f"/studio/videos/{VIDEO}/production-runs/{RUN}/regenerate",
                                        json={"revision": 2, "reason": "nova revisão"})
    assert response.status_code == 202
    assert response.json()["run_id"] == RUN and response.json()["created"] is True
    assert coordinator.regenerated == (RUN, 2, "nova revisão")


def test_regenerate_unknown_run_is_404_and_bad_revision_is_422():
    coordinator = _Coordinator(projection=None, start_result=_creation())
    assert client(coordinator).post(f"/studio/videos/{VIDEO}/production-runs/{RUN}/regenerate").status_code == 404
    ok = _Coordinator(projection=_projection(), start_result=_creation())
    assert client(ok).post(f"/studio/videos/{VIDEO}/production-runs/{RUN}/regenerate",
                           json={"revision": 0}).status_code == 422
