"""Contrato HTTP: erros do guard de orçamento não podem sair como 500."""
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
from app.studio.application.budget import (  # noqa: E402
    BudgetDenied, InvalidOperationTransition, OperationInProgress, OperationSettled, OperationUncertain,
)

VIDEO = "b" * 32


class _Raises:
    def __init__(self, exc):
        self.exc = exc

    def execute(self, *args, **kwargs):
        raise self.exc


class _Editorial:
    def __init__(self, exc):
        self.generate = _Raises(exc)

    def get_script(self, *args, **kwargs):  # nunca alcançado: generate levanta antes
        return None


class _UseCases:
    def __init__(self, exc):
        self.editorial = _Editorial(exc)


def _client(exc):
    app = FastAPI()
    app.include_router(make_router(lambda: _UseCases(exc), lambda: True))
    return TestClient(app, headers={"Authorization": "Bearer test-worker-token"})


@pytest.mark.parametrize(("exc", "status"), [
    (BudgetDenied("budget denied for paid operation secret-key"), 403),
    (OperationInProgress("paid operation secret-key is already in progress"), 409),
    (OperationSettled("paid operation secret-key was already confirmed"), 409),
    (OperationUncertain("paid operation secret-key is uncertain"), 409),
    (InvalidOperationTransition("cannot confirm a RELEASED operation"), 409),
])
def test_paid_operation_errors_have_explicit_http_status(exc, status):
    response = _client(exc).post(f"/studio/videos/{VIDEO}/script", json={})
    assert response.status_code == status
    assert "secret-key" not in response.text  # mensagem pública, sem detalhe interno
    assert "RELEASED" not in response.text


def test_cost_cap_still_maps_to_403():
    from app.studio.domain.policy import CostRefused

    response = _client(CostRefused("monthly cost cap exceeded")).post(f"/studio/videos/{VIDEO}/script", json={})
    assert response.status_code == 403