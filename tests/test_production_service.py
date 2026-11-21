"""Serviço `Production`: retomada transpõe o gate e **relança o worker**.

O defeito original: `POST .../resume` só trocava o estado (`coordinator.resume`) e nunca chamava
`submit`, então o run morria em `RUNNING` logo após o primeiro gate humano. Aqui o `submit` é
espionado — a prova é que ele é chamado com o `run_id` quando a transição é `APPLIED` e nunca
quando é recusada.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.production import (  # noqa: E402
    Production,
    ProductionMode,
    ProductionProjection,
    has_live_lease,
    orphan_in_flight,
)
from app.studio.domain.production_run import (  # noqa: E402
    ProductionRun,
    ProductionStage,
    RunState,
    RunTransition,
    RunTransitionResult,
    StageExecution,
    StageState,
)

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


class _Coordinator:
    """Dublê: registra as chamadas e devolve transição/projeção combinadas."""

    mode = ProductionMode.INTERACTIVE

    def __init__(self, *, transition, projection=None):
        self._transition = transition
        self._projection = projection
        self.calls = []

    def resume(self, run_id, *, expected_state=None):
        self.calls.append(("resume", run_id, expected_state))
        return self._transition

    def retry(self, run_id, *, expected_state=RunState.FAILED):
        self.calls.append(("retry", run_id, expected_state))
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
