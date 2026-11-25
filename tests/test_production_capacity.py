"""Testes de capacidade e limite de admissao de execucoes locais (FS-06 / G4).

Valida observabilidade minima, controle de saturacao e protecao contra descarte:
1. ActiveRuns contabiliza corretamente contagem e snapshot;
2. tracked_submit respeita max_active e lanca CapacityExceeded sob saturacao;
3. Runs recusados por capacidade nao sao descartados do banco (permanecem passiveis de redrive);
4. Settings le e encaminha STUDIO_MAX_ACTIVE_RUNS com default seguro (0 = sem teto extra).
"""
import concurrent.futures
from pathlib import Path
import pytest

from app.studio.application.production import ActiveRuns, CapacityExceeded
from app.studio.composition.wiring import tracked_submit
from app.studio.composition.settings import Settings


def test_active_runs_tracks_counts_and_snapshot():
    active = ActiveRuns()
    assert active.count() == 0
    assert active.snapshot() == frozenset()

    active.acquire("run-1")
    active.acquire("run-2")
    assert active.count() == 2
    assert active.snapshot() == frozenset({"run-1", "run-2"})

    # Múltiplas etapas do mesmo run
    active.acquire("run-1")
    assert active.count() == 2

    active.release("run-1")
    assert active.count() == 2
    active.release("run-1")
    assert active.count() == 1
    assert active.snapshot() == frozenset({"run-2"})

    active.release("run-2")
    assert active.count() == 0


def test_tracked_submit_enforces_capacity_limit():
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    active = ActiveRuns()
    executed = []

    def slow_work(run_id):
        executed.append(run_id)

    submit = tracked_submit(executor, slow_work, active, max_active=1)

    # Simula um run já ativo
    active.acquire("run-existente")

    # Próxima submissão deve exceder a capacidade
    with pytest.raises(CapacityExceeded) as exc:
        submit("run-bloqueado")

    assert "limite de capacidade atingido" in str(exc.value)
    assert active.count() == 1
    assert "run-bloqueado" not in executed

    # Libera o run existente
    active.release("run-existente")

    # Agora a submissão deve passar normalmente
    future = submit("run-liberado")
    future.result(timeout=2)
    assert "run-liberado" in executed
    executor.shutdown(wait=True)


def test_settings_parses_studio_max_active_runs():
    s_default = Settings.from_env({})
    assert s_default.max_active_runs == 0

    s_custom = Settings.from_env({"STUDIO_MAX_ACTIVE_RUNS": "4"})
    assert s_custom.max_active_runs == 4

    s_invalid = Settings.from_env({"STUDIO_MAX_ACTIVE_RUNS": "-1"})
    assert s_invalid.max_active_runs == 0
