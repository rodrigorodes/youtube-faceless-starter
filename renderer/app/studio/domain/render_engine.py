"""Contratos e modelos de domínio da Engine de Renderização (V4-08 / Render Engine).

Núcleo puro de renderização:
- Capacidades de hardware e features do renderer (RendererCapabilities).
- Presets de qualidade (preview vs produção).
- Tokens e estados de cancelamento gracioso (CancellationToken).
- Verificação pura de preflight de assets e plano (evaluate_preflight).
- Acompanhamento granular de progresso de renderização (RenderProgress).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .render_plan import RenderPlan

__all__ = [
    "QualityPresetKind",
    "RenderQualityPreset",
    "RendererCapabilities",
    "CancellationToken",
    "PreflightReport",
    "RenderProgressStage",
    "RenderProgress",
    "evaluate_preflight",
]


class QualityPresetKind(str, Enum):
    """Presets padrão de renderização."""

    PREVIEW = "preview"
    PRODUCTION = "production"


class RenderQualityPreset(BaseModel):
    """Preset determinístico de qualidade e velocidade de renderização."""

    model_config = ConfigDict(frozen=True)

    kind: QualityPresetKind = QualityPresetKind.PRODUCTION
    crf: int = Field(default=21, ge=0, le=51)
    preset: str = Field(default="medium", min_length=1)
    scale_factor: float = Field(default=1.0, gt=0.0, le=1.0)
    audio_bitrate_k: int = Field(default=192, ge=64, le=320)

    @classmethod
    def preview(cls) -> RenderQualityPreset:
        """Preset ultrarrápido para rascunhos e visualização imediata no estúdio."""
        return cls(
            kind=QualityPresetKind.PREVIEW,
            crf=28,
            preset="ultrafast",
            scale_factor=0.5,
            audio_bitrate_k=128,
        )

    @classmethod
    def production(cls) -> RenderQualityPreset:
        """Preset de alta fidelidade para entrega final broadcast."""
        return cls(
            kind=QualityPresetKind.PRODUCTION,
            crf=20,
            preset="medium",
            scale_factor=1.0,
            audio_bitrate_k=256,
        )


class RendererCapabilities(BaseModel):
    """Declaração de capacidades operacionais do motor de renderização."""

    model_config = ConfigDict(frozen=True)

    name: str = "ffmpeg"
    supported_codecs: tuple[str, ...] = ("h264", "hevc", "aac", "pcm_s16le")
    hardware_acceleration: str | None = None  # e.g. "videotoolbox", "nvenc", "vaapi"
    max_resolution: tuple[int, int] = (3840, 2160)
    supports_segmented_render: bool = True
    supports_cancellation: bool = True
    supports_lossless_concat: bool = True


class CancellationToken:
    """Token cooperativo de cancelamento para abortar execuções de renderização longas."""

    def __init__(self) -> None:
        self._is_cancelled: bool = False

    def cancel(self) -> None:
        """Sinaliza cancelamento para os executores e pipelines em andamento."""
        self._is_cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """Informa se o cancelamento foi solicitado."""
        return self._is_cancelled


@dataclass(frozen=True)
class PreflightReport:
    """Relatório estruturado de validação prévia de renderização."""

    is_valid: bool
    missing_asset_keys: tuple[str, ...] = ()
    disk_free_mb: float = 0.0
    estimated_required_mb: float = 0.0
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class RenderProgressStage(str, Enum):
    """Estágios macro do ciclo de vida de renderização."""

    PREFLIGHT = "preflight"
    RENDERING_SEGMENTS = "rendering_segments"
    CONCATENATING = "concatenating"
    MIXING_AUDIO = "mixing_audio"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class RenderProgress:
    """Snapshot imutável do progresso da renderização."""

    stage: RenderProgressStage
    completed_segments: int = 0
    total_segments: int = 0
    percent: float = 0.0
    message: str = ""


def evaluate_preflight(
    plan: RenderPlan,
    available_asset_keys: Sequence[str] | set[str],
    disk_free_mb: float,
    required_free_mb: float = 100.0,
) -> PreflightReport:
    """Executa verificação prévia estrita do plano sem chamadas de I/O de baixo nível."""
    available_set = set(available_asset_keys)
    missing: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Verifica se todos os assets declarados no asset_manifest existem na base resolvida
    for asset in plan.asset_manifest:
        if asset.asset_id not in available_set:
            missing.append(asset.asset_id)

    if missing:
        errors.append(f"Missing {len(missing)} required assets: {', '.join(sorted(missing))}")

    # 2. Estimativa de espaço em disco proporcional à duração
    duration_s = 0.0
    if plan.timeline and plan.timeline.ticks_per_second > 0:
        duration_s = plan.timeline.duration_ticks / plan.timeline.ticks_per_second

    # Estimativa de 3 MB/s para 1080p full render + temp segments
    estimated_required_mb = max(required_free_mb, duration_s * 3.0)

    if disk_free_mb < estimated_required_mb:
        errors.append(
            f"Insufficient disk space: {disk_free_mb:.1f}MB available, "
            f"{estimated_required_mb:.1f}MB required"
        )

    # 3. Avisos de segurança do plano
    if not plan.timeline or not plan.timeline.scenes:
        errors.append("RenderPlan contains no scenes")

    is_valid = len(errors) == 0

    return PreflightReport(
        is_valid=is_valid,
        missing_asset_keys=tuple(missing),
        disk_free_mb=disk_free_mb,
        estimated_required_mb=estimated_required_mb,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
