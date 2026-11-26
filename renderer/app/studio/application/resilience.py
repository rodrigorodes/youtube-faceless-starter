"""Utilitários de prontidão do sistema (Readiness Probe — V4-12).

A orquestração real de etapas, leases, fencing e operações pagas reside exclusivamente
nos módulos canônicos `application/production.py` (`ProductionCoordinator`) e
`application/budget.py` (`PaidOperationGuard`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from ..domain.resilience import BackpressureController


@dataclass(frozen=True)
class SystemReadinessReport:
    """Relatório consolidado de prontidão (Readiness Probe)."""

    database: str
    storage: str
    ffmpeg: str
    budget_guard: str
    active_jobs: int
    max_jobs: int
    is_ready: bool
    details: Mapping[str, Any] = field(default_factory=dict)


class ReadinessChecker:
    """Verificador consolidado de prontidão do sistema."""

    def __init__(
        self,
        check_db: Callable[[], bool],
        check_storage: Callable[[], bool],
        check_ffmpeg: Callable[[], bool],
        check_budget: Callable[[], bool],
        backpressure: BackpressureController,
    ) -> None:
        self.check_db = check_db
        self.check_storage = check_storage
        self.check_ffmpeg = check_ffmpeg
        self.check_budget = check_budget
        self.backpressure = backpressure

    def check(self) -> SystemReadinessReport:
        db_ok = self.check_db()
        storage_ok = self.check_storage()
        ffmpeg_ok = self.check_ffmpeg()
        budget_ok = self.check_budget()

        is_ready = bool(
            db_ok
            and storage_ok
            and ffmpeg_ok
            and budget_ok
            and not self.backpressure.is_saturated
        )

        return SystemReadinessReport(
            database="ok" if db_ok else "unavailable",
            storage="ok" if storage_ok else "unavailable",
            ffmpeg="ok" if ffmpeg_ok else "unavailable",
            budget_guard="ok" if budget_ok else "blocked",
            active_jobs=self.backpressure.active_jobs,
            max_jobs=self.backpressure.config.max_concurrent_jobs,
            is_ready=is_ready,
            details={
                "saturated": self.backpressure.is_saturated,
                "queued_jobs": self.backpressure.queued_jobs,
            },
        )
