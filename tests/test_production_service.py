"""Serviço `Production`: retomada transpõe o gate e **relança o worker**.

O defeito original: `POST .../resume` só trocava o estado (`coordinator.resume`) e nunca chamava
`submit`, então o run morria em `RUNNING` logo após o primeiro gate humano. Aqui o `submit` é
espionado — a prova é que ele é chamado com o `run_id` quando a transição é `APPLIED` e nunca
quando é recusada.

F03.T04: o serviço também fixa o **lifecycle**. Retomar/retentar leem o snapshot persistido e
**nunca** chamam o resolvedor; regenerate é uma execução nova de ponta a ponta (chave nova,
snapshot novo, rótulo próprio) e um run legado não finge reproduzir a configuração.
"""
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.production import (  # noqa: E402
    Production,
    ProductionMode,
    ProductionProjection,
    RunConfigUnavailable,
    has_live_lease,
    orphan_in_flight,
)
from app.studio.domain.contracts import Video, VideoFormat  # noqa: E402
from app.studio.domain.effective_config import resolve_effective_config  # noqa: E402
from app.studio.domain.production_run import (  # noqa: E402
    CreateRunResult,
    ProductionRun,
    ProductionStage,
    RunCreation,
    RunOperation,
    RunState,
    RunTransition,
    RunTransitionResult,
    StageExecution,
    StageState,
)
from app.studio.domain.run_config import RunConfigStatus, StoredRunConfig  # noqa: E402

RUN = "a" * 32
VIDEO = "b" * 32
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _run(state=RunState.WAITING_HUMAN, run_id=RUN) -> ProductionRun:
    return ProductionRun(run_id=run_id, video_id=VIDEO, idempotency_key="req-1", state=state)


def _running(stage, *, expires):
    return StageExecution(run_id=RUN, stage_id=ProductionStage(stage), state=StageState.RUNNING,
                          attempt=1, fencing_token=1, lease_owner="worker-1", lease_expires_at=expires)


def _pending(stage):
    return StageExecution(run_id=RUN, stage_id=ProductionStage(stage), state=StageState.PENDING)


def _stage(stage, state):
    return StageExecution(run_id=RUN, stage_id=ProductionStage(stage), state=StageState(state))


class _Coordinator:
    """Dublê: registra as chamadas e devolve transição/projeção combinadas."""

    mode = ProductionMode.INTERACTIVE

    def __init__(self, *, transition=None, projection=None, start_result=None, retry_error=None):
        self._transition = transition
        self._projection = projection
        self._start_result = start_result
        self._retry_error = retry_error
        self.calls = []
        self.operations = []

    def start(self, video_id, idempotency_key, *, channel_id=None, stages=None,
              effective_config_for=None, config_store=None):
        self.calls.append(("start", video_id, idempotency_key, channel_id, tuple(stages or ())))
        return self._start_result

    def record_operation(self, run_id, operation, *, reason, config=None, source_run_id=None):
        self.operations.append(SimpleNamespace(run_id=run_id, operation=operation, reason=reason,
                                               config=config, source_run_id=source_run_id))
        return SimpleNamespace(id=len(self.operations))

    def resume(self, run_id, *, expected_state=None):
        self.calls.append(("resume", run_id, expected_state))
        return self._transition

    def retry(self, run_id, *, expected_state=RunState.FAILED):
        self.calls.append(("retry", run_id, expected_state))
        if self._retry_error is not None:
            raise self._retry_error
        return self._transition

    def get(self, run_id):
        return self._projection


def _production(coordinator, submit):
    return Production(coordinator=coordinator, worker=None, submit=submit)


# -- resume/retry relançam o worker ------------------------------------------


def test_resume_applied_enqueues_the_worker_with_the_run_id():
    submitted = []
    coordinator = _Coordinator(transition=RunTransition(RunTransitionResult.APPLIED, _run(RunState.RUNNING)))
    transition = _production(coordinator, submitted.append).resume(RUN, expected_state=RunState.WAITING_HUMAN)
    assert transition.result is RunTransitionResult.APPLIED
    assert submitted == [RUN]
    assert coordinator.calls == [("resume", RUN, RunState.WAITING_HUMAN)]


def test_resume_not_allowed_never_enqueues():
    submitted = []
    coordinator = _Coordinator(transition=RunTransition(RunTransitionResult.NOT_ALLOWED, _run(RunState.CANCELLED)))
    transition = _production(coordinator, submitted.append).resume(RUN, expected_state=RunState.WAITING_HUMAN)
    assert transition.result is RunTransitionResult.NOT_ALLOWED
    assert submitted == []


def test_resume_survives_an_unavailable_queue():
    """Fila indisponível não pode derrubar a requisição nem perder o run."""
    def boom(_run_id):
        raise RuntimeError("fila caiu")

    coordinator = _Coordinator(transition=RunTransition(RunTransitionResult.APPLIED, _run(RunState.RUNNING)))
    transition = _production(coordinator, boom).resume(RUN, expected_state=RunState.WAITING_HUMAN)
    assert transition.result is RunTransitionResult.APPLIED


def test_retry_applied_enqueues_the_worker():
    submitted = []
    coordinator = _Coordinator(transition=RunTransition(RunTransitionResult.APPLIED, _run(RunState.RUNNING)))
    transition = _production(coordinator, submitted.append).retry(RUN)
    assert transition.result is RunTransitionResult.APPLIED
    assert submitted == [RUN]
    assert coordinator.calls == [("retry", RUN, RunState.FAILED)]


def test_retry_not_allowed_never_enqueues():
    submitted = []
    coordinator = _Coordinator(transition=RunTransition(RunTransitionResult.NOT_ALLOWED, _run(RunState.RUNNING)))
    transition = _production(coordinator, submitted.append).retry(RUN)
    assert transition.result is RunTransitionResult.NOT_ALLOWED
    assert submitted == []


# -- re-drive de um RUNNING órfão (requisito B) ------------------------------


def _projection(run, stages):
    return ProductionProjection(run=run, stages=tuple(stages), next_stage=ProductionStage.FACTCHECK,
                                next_action="run", mode=ProductionMode.INTERACTIVE,
                                available_stages=(ProductionStage.SCRIPT,), unavailable_stages=())


def test_resume_redrives_an_orphan_running_without_writing_state():
    submitted = []
    run = _run(RunState.RUNNING)
    coordinator = _Coordinator(
        transition=RunTransition(RunTransitionResult.NOT_ALLOWED, run),
        projection=_projection(run, [_pending("script"), _running("factcheck", expires=datetime.now(timezone.utc) - timedelta(minutes=1))]))
    transition = _production(coordinator, submitted.append).resume(RUN, expected_state=RunState.RUNNING)
    assert transition.result is RunTransitionResult.APPLIED
    assert transition.run is run
    assert submitted == [RUN]  # re-lança o worker; nenhuma escrita de estado aconteceu


def test_resume_does_not_redrive_when_a_lease_is_alive():
    """Com lease vivo, re-lançar criaria worker duplicado: permanece NOT_ALLOWED e sem submit."""
    submitted = []
    run = _run(RunState.RUNNING)
    coordinator = _Coordinator(
        transition=RunTransition(RunTransitionResult.NOT_ALLOWED, run),
        projection=_projection(run, [_running("factcheck", expires=datetime.now(timezone.utc) + timedelta(minutes=5))]))
    transition = _production(coordinator, submitted.append).resume(RUN, expected_state=RunState.RUNNING)
    assert transition.result is RunTransitionResult.NOT_ALLOWED
    assert submitted == []


def test_resume_does_not_redrive_a_non_running_run():
    submitted = []
    run = _run(RunState.WAITING_HUMAN)
    coordinator = _Coordinator(transition=RunTransition(RunTransitionResult.NOT_ALLOWED, run),
                               projection=_projection(run, [_pending("script")]))
    transition = _production(coordinator, submitted.append).resume(RUN, expected_state=RunState.WAITING_HUMAN)
    assert transition.result is RunTransitionResult.NOT_ALLOWED
    assert submitted == []


# -- predicado puro de lease vivo --------------------------------------------


def test_has_live_lease_is_false_for_an_expired_or_absent_lease():
    assert has_live_lease([], NOW) is False
    assert has_live_lease([_pending("script")], NOW) is False
    assert has_live_lease([_running("script", expires=NOW - timedelta(seconds=1))], NOW) is False


def test_has_live_lease_boundary_and_future():
    assert has_live_lease([_running("script", expires=NOW)], NOW) is False   # exatamente agora: expirado
    assert has_live_lease([_running("script", expires=NOW + timedelta(seconds=1))], NOW) is True
    assert has_live_lease([_pending("script"), _running("factcheck", expires=NOW + timedelta(minutes=1))],
                          NOW) is True


# -- regra pura da recuperação de boot (PROD-03) -----------------------------


def test_orphan_in_flight_skips_a_running_run_whose_lease_is_alive():
    """Lease vivo: o dono ainda pode escrever, então re-dirigir criaria worker duplicado."""
    run = _run(RunState.RUNNING)
    assert orphan_in_flight([(run, [_running("script", expires=NOW + timedelta(minutes=5))])], NOW) == ()


def test_orphan_in_flight_takes_a_running_run_with_an_expired_or_boundary_lease():
    run = _run(RunState.RUNNING)
    assert orphan_in_flight([(run, [_running("script", expires=NOW - timedelta(seconds=1))])], NOW) == (RUN,)
    # limite: exatamente agora o lease já não vale mais (mesma semântica de has_live_lease).
    assert orphan_in_flight([(run, [_running("script", expires=NOW)])], NOW) == (RUN,)


def test_orphan_in_flight_takes_a_running_run_without_any_lease():
    assert orphan_in_flight([(_run(RunState.RUNNING), [_pending("script")])], NOW) == (RUN,)


def test_orphan_in_flight_takes_created_and_never_terminal_states():
    """`CREATED` (fila indisponível no start) entra; terminais nunca, mesmo se a leitura os trouxer."""
    in_flight = [
        (_run(RunState.FAILED, "c" * 32), [_pending("script")]),
        (_run(RunState.SUCCEEDED, "d" * 32), [_pending("script")]),
        (_run(RunState.CANCELLED, "e" * 32), [_pending("script")]),
        (_run(RunState.CREATED, "f" * 32), [_pending("script")]),
    ]
    assert orphan_in_flight(in_flight, NOW) == ("f" * 32,)


def test_orphan_in_flight_keeps_only_orphans_and_preserves_the_port_order():
    live = _run(RunState.RUNNING, "a" * 32)
    pending_run = _run(RunState.RUNNING, "b" * 32)
    created = _run(RunState.CREATED, "c" * 32)
    in_flight = [
        (live, [_running("script", expires=NOW + timedelta(minutes=1))]),
        (pending_run, [_pending("script"), _pending("factcheck")]),
        (created, [_pending("script")]),
    ]
    assert orphan_in_flight(in_flight, NOW) == ("b" * 32, "c" * 32)


# -- serviço: re-drive dos órfãos no boot ------------------------------------


class _Reader:
    """Dublê da porta `ProductionRunInFlightReader` (PROD-03); registra se foi lida."""

    def __init__(self, in_flight):
        self._in_flight = tuple(in_flight)
        self.calls = 0

    def list_in_flight(self):
        self.calls += 1
        return self._in_flight


def _recovery_service(in_flight, submit):
    coordinator = _Coordinator(transition=RunTransition(RunTransitionResult.NOT_ALLOWED, _run(RunState.RUNNING)))
    return Production(coordinator=coordinator, worker=None, submit=submit, in_flight=_Reader(in_flight))


def test_recover_in_flight_submits_only_the_orphans_and_reports_them():
    live = _run(RunState.RUNNING, "a" * 32)
    orphan = _run(RunState.RUNNING, "b" * 32)
    created = _run(RunState.CREATED, "c" * 32)
    in_flight = [
        (live, [_running("script", expires=NOW + timedelta(minutes=5))]),
        (orphan, [_pending("script")]),
        (created, [_pending("script")]),
        (_run(RunState.FAILED, "d" * 32), [_pending("script")]),
    ]
    submitted = []
    service = _recovery_service(in_flight, submitted.append)
    recovered = service.recover_in_flight(now=NOW)
    assert recovered == ("b" * 32, "c" * 32)
    assert submitted == ["b" * 32, "c" * 32]


def test_recover_in_flight_isolates_a_failing_submit_and_never_propagates():
    """Um `submit` quebrado não impede os outros nem derruba o boot."""
    def submit(run_id):
        submitted.append(run_id)
        if run_id == "b" * 32:
            raise RuntimeError("fila caiu")

    submitted = []
    service = _recovery_service(
        [(_run(RunState.CREATED, "b" * 32), [_pending("script")]),
         (_run(RunState.CREATED, "c" * 32), [_pending("script")])],
        submit)
    recovered = service.recover_in_flight(now=NOW)
    assert submitted == ["b" * 32, "c" * 32]  # tentou o segundo apesar da falha do primeiro
    assert recovered == ("b" * 32, "c" * 32)


def test_recover_in_flight_is_a_noop_without_the_reader():
    service = Production(coordinator=_Coordinator(
        transition=RunTransition(RunTransitionResult.NOT_ALLOWED, _run(RunState.RUNNING))),
        worker=None, submit=lambda run_id: None)
    assert service.recover_in_flight() == ()


# -- F03.T04: lifecycle e compatibilidade (pause/resume/retry/regenerate/new run)


def _video(video_id=VIDEO):
    return Video(id=video_id, project_id="c" * 32, topic="tema", format=VideoFormat.short)


def _config(video_id=VIDEO, **options):
    return resolve_effective_config(video=_video(video_id), **options)


def _resolved(config=None):
    return StoredRunConfig(RunConfigStatus.RESOLVED, config or _config())


class _ConfigStore:
    """Dublê da porta de leitura do snapshot: conta leituras e nunca escreve."""

    def __init__(self, stored):
        self.stored = stored
        self.calls = 0

    def run_config(self, run_id):
        self.calls += 1
        return self.stored


def _lifecycle(coordinator, *, store=None, resolver=None, submit=None):
    return Production(coordinator=coordinator, worker=None, submit=submit,
                      effective_config_for=resolver, config_store=store)


def _source_projection(key="req-1"):
    run = ProductionRun(run_id=RUN, video_id=VIDEO, idempotency_key=key, state=RunState.RUNNING,
                        channel_id="d" * 32)
    return _projection(run, [_stage("script", "SUCCEEDED"), _stage("factcheck", "PENDING")])


def test_resume_delegates_without_any_second_resolution_path():
    """O serviço não re-resolve nem relê o snapshot: quem decide a política é o coordenador.

    O serviço já carrega o resolvedor e a porta de leitura para o `start`; se a retomada passasse
    por eles haveria um segundo caminho de configuração. A garantia é que nenhum dos dois é tocado.
    """
    def resolver(_video):  # chamar isto na retomada seria re-resolver a configuração
        raise AssertionError("resume re-resolved the effective config")

    store = _ConfigStore(_resolved())
    coordinator = _Coordinator(transition=RunTransition(RunTransitionResult.APPLIED, _run(RunState.RUNNING)))
    transition = _lifecycle(coordinator, store=store, resolver=resolver).resume(
        RUN, expected_state=RunState.WAITING_HUMAN)

    assert transition.result is RunTransitionResult.APPLIED
    assert store.calls == 0  # a decisão/leitura do snapshot é do coordenador, num lugar só
    assert coordinator.calls == [("resume", RUN, RunState.WAITING_HUMAN)]


def test_retry_delegates_without_any_second_resolution_path():
    def resolver(_video):
        raise AssertionError("retry re-resolved the effective config")

    store = _ConfigStore(_resolved())
    coordinator = _Coordinator(transition=RunTransition(RunTransitionResult.APPLIED, _run(RunState.RUNNING)))
    _lifecycle(coordinator, store=store, resolver=resolver).retry(RUN)
    assert store.calls == 0
    assert coordinator.calls == [("retry", RUN, RunState.FAILED)]


def test_retry_propagates_the_legacy_refusal_with_a_clear_message():
    """Serviço não engole a recusa: um run legado não finge reproduzir a configuração."""
    error = RunConfigUnavailable("retry needs the frozen run config: this run is legacy")
    coordinator = _Coordinator(transition=RunTransition(RunTransitionResult.NOT_ALLOWED, _run()),
                               retry_error=error)
    with pytest.raises(RunConfigUnavailable, match="legacy"):
        _lifecycle(coordinator, store=_ConfigStore(StoredRunConfig(RunConfigStatus.LEGACY))).retry(RUN)
    assert coordinator.calls == [("retry", RUN, RunState.FAILED)]
    assert coordinator.operations == []


def test_regenerate_is_an_explicit_new_run_and_never_a_disguised_resume():
    source_key = "req-1"
    new_run = ProductionRun(run_id="e" * 32, video_id=VIDEO, idempotency_key=f"{source_key}.regenerate",
                            state=RunState.CREATED, channel_id="d" * 32)
    submitted = []
    coordinator = _Coordinator(start_result=RunCreation(CreateRunResult.CREATED, new_run),
                               projection=_source_projection(source_key))
    creation = _lifecycle(coordinator, store=_ConfigStore(_resolved()), resolver=_config,
                          submit=submitted.append).regenerate(RUN)

    assert creation.result is CreateRunResult.CREATED
    assert creation.run.run_id == new_run.run_id
    # Execução nova: chave nova, mesmas etapas/canal da origem, nunca uma retomada.
    assert coordinator.calls == [("start", VIDEO, f"{source_key}.regenerate", "d" * 32,
                                  (ProductionStage.SCRIPT, ProductionStage.FACTCHECK))]
    assert submitted == [new_run.run_id]
    [decision] = coordinator.operations
    assert decision.operation is RunOperation.REGENERATE
    assert decision.run_id == new_run.run_id and decision.source_run_id == RUN
    assert "regenerate" in decision.reason.lower() or "nova execução" in decision.reason.lower()


def test_regenerate_replay_does_not_duplicate_the_decision():
    new_run = ProductionRun(run_id="e" * 32, video_id=VIDEO, idempotency_key="req-1.regenerate")
    coordinator = _Coordinator(start_result=RunCreation(CreateRunResult.EXISTING, new_run),
                               projection=_source_projection())
    creation = _lifecycle(coordinator, store=_ConfigStore(_resolved()), resolver=_config).regenerate(RUN)
    assert creation.result is CreateRunResult.EXISTING
    assert coordinator.operations == []  # a decisão já foi gravada na criação real


def test_regenerate_refuses_without_a_resolver_instead_of_creating_a_legacy_run():
    coordinator = _Coordinator(projection=_source_projection())
    with pytest.raises(RunConfigUnavailable, match="snapshot"):
        _lifecycle(coordinator).regenerate(RUN)
    assert coordinator.calls == []


def test_regenerate_is_404_for_an_unknown_source_run():
    from app.studio.application.production import RunNotFound

    coordinator = _Coordinator(projection=None)
    with pytest.raises(RunNotFound):
        _lifecycle(coordinator, store=_ConfigStore(_resolved()), resolver=_config).regenerate(RUN)


def test_new_run_records_the_new_execution_decision():
    new_run = ProductionRun(run_id="e" * 32, video_id=VIDEO, idempotency_key="req-2")
    coordinator = _Coordinator(start_result=RunCreation(CreateRunResult.CREATED, new_run))
    creation = _lifecycle(coordinator, store=_ConfigStore(_resolved()), resolver=_config).new_run(
        VIDEO, "req-2", stages=[ProductionStage.SCRIPT])
    assert creation.run.run_id == new_run.run_id
    [decision] = coordinator.operations
    assert decision.operation is RunOperation.NEW_RUN and decision.run_id == new_run.run_id


def test_new_run_replay_does_not_duplicate_the_decision():
    new_run = ProductionRun(run_id="e" * 32, video_id=VIDEO, idempotency_key="req-2")
    coordinator = _Coordinator(start_result=RunCreation(CreateRunResult.EXISTING, new_run))
    _lifecycle(coordinator, store=_ConfigStore(_resolved()), resolver=_config).new_run(VIDEO, "req-2")
    assert coordinator.operations == []


# -- projeção: referência da configuração, nunca o documento -----------------


def test_projection_exposes_only_the_config_reference_and_no_secret():
    projection = ProductionProjection(
        run=_run(RunState.WAITING_HUMAN), stages=(_pending("script"),), next_stage=ProductionStage.SCRIPT,
        next_action="resume", mode=ProductionMode.INTERACTIVE, available_stages=(ProductionStage.SCRIPT,),
        unavailable_stages=(), config_status=RunConfigStatus.RESOLVED, config_hash="a" * 64)
    body = json.dumps(asdict(projection), default=str).lower()
    assert projection.config_status is RunConfigStatus.RESOLVED
    assert projection.config_hash == "a" * 64
    # A projeção carrega a referência (status + hash), nunca o documento nem credencial.
    assert "config_snapshot" not in body and "provenance" not in body and "document" not in body
    assert "api_key" not in body and "password" not in body and "secret" not in body
    assert "authorization" not in body and "credential" not in body


def test_projection_defaults_to_no_config_reference_when_there_is_no_store():
    projection = _projection(_run(RunState.CREATED), [_pending("script")])
    assert projection.config_status is None and projection.config_hash is None


def test_regenerate_with_a_revision_is_another_new_execution_with_a_new_key():
    new_run = ProductionRun(run_id="e" * 32, video_id=VIDEO, idempotency_key="req-1.regenerate.2")
    coordinator = _Coordinator(start_result=RunCreation(CreateRunResult.CREATED, new_run),
                               projection=_source_projection())
    _lifecycle(coordinator, store=_ConfigStore(_resolved()), resolver=_config).regenerate(RUN, revision=2)
    assert coordinator.calls[0][2] == "req-1.regenerate.2"


@pytest.mark.parametrize("revision", [0, -1, True, "2"])
def test_regenerate_revision_must_be_a_positive_integer(revision):
    coordinator = _Coordinator(start_result=None, projection=_source_projection())
    with pytest.raises(ValueError):
        _lifecycle(coordinator, store=_ConfigStore(_resolved()), resolver=_config).regenerate(
            RUN, revision=revision)
    assert coordinator.calls == []


# -- R02: o coordenador renova o lease e nunca finaliza sem posse -------------------------


def _lease_harness(monkeypatch, *, renew_result, handler_exc=None, lease_seconds=300):
    from app.studio.application import production as production_module
    from app.studio.application.production import (
        ProductionCoordinator, StageExecutionFailed, StageOutcome, WorkerStepResult)
    from app.studio.domain.production_run import (
        Checkpoint, LeaseResult, StageClaim, StageClaimResult, StageDag, StageTransition, StageTransitionResult)

    calls = []
    run = ProductionRun(run_id=RUN, video_id=VIDEO, idempotency_key="k")
    execution = StageExecution(run_id=RUN, stage_id=ProductionStage.SCRIPT, state=StageState.RUNNING, attempt=1,
                               fencing_token=7, lease_owner="w", lease_expires_at=NOW)
    renewed = __import__("threading").Event()

    class Runs:
        def get_run(self, run_id):
            return run

        def claim_stage(self, *args):
            return StageClaim(StageClaimResult.CLAIMED, execution)

        def renew_lease(self, *args):
            calls.append(("renew", args))
            renewed.set()
            return renew_result

        def complete_stage(self, *args, **kwargs):
            calls.append(("complete", None))
            return StageTransition(StageTransitionResult.APPLIED)

        def fail_stage(self, *args, **kwargs):
            calls.append(("fail", None))
            return StageTransition(StageTransitionResult.APPLIED, execution)

        def pause_run(self, *args, **kwargs):
            calls.append(("pause", None))
            return RunTransition(RunTransitionResult.NOT_ALLOWED)

        def list_stages(self, run_id):
            return ()

    seen = {}

    class Handler:
        available = True

        def execute(self, context):
            seen["lease"] = context.lease
            assert renewed.wait(5)
            import time
            deadline = time.monotonic() + 2
            while renew_result != LeaseResult.RENEWED and not context.lease.lost and time.monotonic() < deadline:
                time.sleep(0.01)
            if handler_exc is not None:
                raise handler_exc
            return StageOutcome(checkpoint=Checkpoint({"s": 1}, context.checkpoint_version))

    real_stop = production_module.LeaseHeartbeat.stop

    def stop(self):
        calls.append(("stop", None))
        real_stop(self)

    monkeypatch.setattr(production_module.LeaseHeartbeat, "stop", stop, raising=False)
    coordinator = ProductionCoordinator(Runs(), handlers={ProductionStage.SCRIPT: Handler()},
                                        pipeline=StageDag({ProductionStage.SCRIPT: ()}), lease_seconds=lease_seconds)
    return coordinator, calls, seen, StageExecutionFailed, WorkerStepResult


def test_handler_runs_under_a_heartbeat_that_renews_with_the_exact_identity(monkeypatch):
    from app.studio.domain.production_run import LeaseResult
    coordinator, calls, seen, _, Result = _lease_harness(monkeypatch, renew_result=LeaseResult.RENEWED)
    step = coordinator.step(RUN, owner="w")
    assert step.result is Result.COMPLETED
    assert seen["lease"] is not None
    assert ("renew", (RUN, ProductionStage.SCRIPT, "w", 7, 300)) in calls
    names = [name for name, _ in calls]
    assert names.index("stop") < names.index("complete")


def test_lease_lost_during_the_handler_never_completes(monkeypatch):
    from app.studio.domain.production_run import LeaseResult
    coordinator, calls, _, _, Result = _lease_harness(monkeypatch, renew_result=LeaseResult.LOST)
    step = coordinator.step(RUN, owner="w")
    assert step.result is Result.LOST
    assert step.detail == "lease lost during stage execution"
    assert not {"complete", "fail", "pause"} & {name for name, _ in calls}


def test_a_failure_after_losing_the_lease_never_fails_the_stage(monkeypatch):
    from app.studio.application.production import StageExecutionFailed
    from app.studio.domain.production_run import LeaseResult
    coordinator, calls, _, _, Result = _lease_harness(
        monkeypatch, renew_result=LeaseResult.LOST, handler_exc=StageExecutionFailed("boom"))
    step = coordinator.step(RUN, owner="w")
    assert step.result is Result.LOST
    assert not {"complete", "fail", "pause"} & {name for name, _ in calls}


def test_a_lease_lost_exception_from_the_handler_maps_to_lost(monkeypatch):
    from app.studio.application.lease_heartbeat import LeaseLost
    from app.studio.domain.production_run import LeaseResult
    coordinator, calls, _, _, Result = _lease_harness(
        monkeypatch, renew_result=LeaseResult.RENEWED, handler_exc=LeaseLost("x"))
    step = coordinator.step(RUN, owner="w")
    assert step.result is Result.LOST
    assert not {"complete", "fail", "pause"} & {name for name, _ in calls}
