"""Módulo de Domínio do Piloto Profissional (V4-13).

Pureza arquitetural: sem I/O, sem banco, sem subprocess, sem dependências externas.
Implementa modelos e regras para:
- Perfis de produção do piloto (Econômico, Equilibrado, Premium)
- Métricas comparativas audiovisuais pareadas (LUFS, Peak, Sync, Custo/minuto)
- Custos de regeneração pontual de cenas vs produção completa
- Validação estrita de compliance antes de publicação controlada
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence


class PilotProfile(str, Enum):
    ECONOMIC = "ECONOMIC"
    BALANCED = "BALANCED"
    PREMIUM = "PREMIUM"


class PilotComplianceError(Exception):
    """Violação dos critérios de conformidade do Piloto Profissional."""


@dataclass(frozen=True)
class SceneRegenerationCost:
    """Custo e tempo de regeneração de uma única cena sem refazer o projeto inteiro."""

    scene_id: str
    asset_cost_usd: Decimal
    render_time_seconds: float
    full_pipeline_avoided_seconds: float

    def __post_init__(self) -> None:
        if not self.scene_id:
            raise ValueError("scene_id não pode ser vazio")
        if self.asset_cost_usd < 0:
            raise ValueError("asset_cost_usd deve ser >= 0")


@dataclass(frozen=True)
class PilotBenchmarkMetrics:
    """Métricas observáveis reais de execução de um piloto."""

    profile: PilotProfile
    video_format: str  # "short" (9:16) ou "documentary" (16:9)
    total_duration_seconds: float
    scenes_count: int
    integrated_lufs: float  # EBU R128 (ex: -14.0 LUFS para short, -16.0 para long)
    true_peak_db: float  # dBFS (deve ser <= -1.0 dBFS)
    sync_drift_ms: float  # desvio medido áudio/legenda em ms
    render_wall_time_seconds: float
    total_cost_usd: Decimal
    human_intervention_minutes: float
    publication_blocked: bool = True
    scene_regenerations: Sequence[SceneRegenerationCost] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.total_duration_seconds <= 0:
            raise ValueError("total_duration_seconds deve ser > 0")
        if self.scenes_count <= 0:
            raise ValueError("scenes_count deve ser > 0")
        if self.render_wall_time_seconds < 0:
            raise ValueError("render_wall_time_seconds deve ser >= 0")
        if self.total_cost_usd < 0:
            raise ValueError("total_cost_usd deve ser >= 0")

    @property
    def cost_per_minute_usd(self) -> Decimal:
        """Calcula o custo por minuto em USD."""
        minutes = Decimal(str(self.total_duration_seconds)) / Decimal("60.0")
        if minutes == 0:
            return Decimal("0.00")
        return (self.total_cost_usd / minutes).quantize(Decimal("0.01"))

    @property
    def realtime_render_factor(self) -> float:
        """Fator de tempo de renderização em relação ao tempo real do vídeo."""
        return round(self.render_wall_time_seconds / self.total_duration_seconds, 2)

    def validate_compliance(self) -> None:
        """Valida gates técnicos estritos de conformidade."""
        # 1. True Peak não pode ultrapassar -1.0 dBFS (risco de clipping/distorção)
        if self.true_peak_db > -1.0:
            raise PilotComplianceError(
                f"True Peak ({self.true_peak_db:.2f} dBFS) violou o teto de -1.0 dBFS (risco de clipping)"
            )
        # 2. Desvio de sincronia áudio/legenda não pode exceder 50ms
        if abs(self.sync_drift_ms) > 50.0:
            raise PilotComplianceError(
                f"Desvio de sincronia áudio/legenda ({self.sync_drift_ms:.1f}ms) excedeu o teto de 50ms"
            )
        # 3. Publicação em ambiente de teste DEVE estar bloqueada
        if not self.publication_blocked:
            raise PilotComplianceError(
                "Publicação externa não foi bloqueada pelo kill switch durante o piloto"
            )


@dataclass(frozen=True)
class PilotComparisonReport:
    """Relatório pareado comparando perfis com o mesmo roteiro de referência."""

    script_reference_id: str
    script_topic: str
    metrics_by_profile: Mapping[PilotProfile, PilotBenchmarkMetrics]
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def get_profile(self, profile: PilotProfile) -> PilotBenchmarkMetrics:
        if profile not in self.metrics_by_profile:
            raise KeyError(f"Perfil {profile} não encontrado no relatório pareado")
        return self.metrics_by_profile[profile]

    def validate_all(self) -> None:
        for p, m in self.metrics_by_profile.items():
            m.validate_compliance()
