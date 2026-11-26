"""Módulo de Aplicação do Piloto Profissional (V4-13).

Pureza arquitetural: orquestração desacoplada de dependências de infraestrutura.
Coordena:
- Execução pareada dos perfis com o mesmo roteiro de referência
- Coleta de métricas observáveis (LUFS, Peak, Sync Drift, Tempo, Custos)
- Validação de kill switch de publicação
- Geração do relatório consolidado de comparação para Avaliação Humana
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Callable, Mapping, Sequence

from ..domain.professional_pilot import (
    PilotBenchmarkMetrics,
    PilotComparisonReport,
    PilotComplianceError,
    PilotProfile,
    SceneRegenerationCost,
)

logger = logging.getLogger(__name__)


class ProfessionalPilotOrchestrator:
    """Orquestrador do Piloto Profissional para comparação cega e pareada."""

    def __init__(self, publication_kill_switch_enabled: bool = True) -> None:
        self.publication_kill_switch_enabled = publication_kill_switch_enabled

    def run_benchmark_for_profile(
        self,
        profile: PilotProfile,
        video_format: str,
        total_duration_seconds: float,
        scenes_count: int,
        integrated_lufs: float,
        true_peak_db: float,
        sync_drift_ms: float,
        render_wall_time_seconds: float,
        total_cost_usd: Decimal,
        human_intervention_minutes: float,
        scene_regenerations: Sequence[SceneRegenerationCost] = (),
    ) -> PilotBenchmarkMetrics:
        """Registra e valida as métricas reais observadas para um perfil."""
        metrics = PilotBenchmarkMetrics(
            profile=profile,
            video_format=video_format,
            total_duration_seconds=total_duration_seconds,
            scenes_count=scenes_count,
            integrated_lufs=integrated_lufs,
            true_peak_db=true_peak_db,
            sync_drift_ms=sync_drift_ms,
            render_wall_time_seconds=render_wall_time_seconds,
            total_cost_usd=total_cost_usd,
            human_intervention_minutes=human_intervention_minutes,
            publication_blocked=self.publication_kill_switch_enabled,
            scene_regenerations=scene_regenerations,
        )
        metrics.validate_compliance()
        return metrics

    def build_comparison_report(
        self,
        script_reference_id: str,
        script_topic: str,
        profiles_metrics: Mapping[PilotProfile, PilotBenchmarkMetrics],
    ) -> PilotComparisonReport:
        """Consolida o relatório comparativo pareado entre os perfis."""
        report = PilotComparisonReport(
            script_reference_id=script_reference_id,
            script_topic=script_topic,
            metrics_by_profile=dict(profiles_metrics),
        )
        report.validate_all()
        return report
