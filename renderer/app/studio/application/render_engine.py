"""Serviços de aplicação da Engine de Renderização (V4-08).

Implementa:
- Gestão de cache de segmentos renderizados por hash determinístico (SegmentCacheManager).
- Planejamento de renderização segmentada com detecção de cache hit / miss (SegmentedRenderPlanner).
- Rastreamento e cálculo de progresso granular (ProgressTracker).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from ..domain.render_engine import (
    CancellationToken,
    QualityPresetKind,
    RenderProgress,
    RenderProgressStage,
    RenderQualityPreset,
)
from ..domain.render_plan import RenderPlan, Shot

__all__ = [
    "CachedSegment",
    "SegmentCacheManager",
    "SegmentPlanItem",
    "SegmentedRenderPlan",
    "SegmentedRenderPlanner",
    "ProgressTracker",
]


@dataclass(frozen=True)
class CachedSegment:
    """Metadados de um segmento de vídeo renderizado disponível em cache."""

    digest: str
    file_path: str
    duration_ticks: int
    preset_kind: QualityPresetKind


class SegmentCacheManager:
    """Gerenciador em memória do cache de segmentos com chave por digest e preset."""

    def __init__(self) -> None:
        self._cache: dict[str, CachedSegment] = {}

    def _make_key(self, digest: str, preset_kind: QualityPresetKind) -> str:
        return f"{preset_kind.value}:{digest}"

    def has(self, digest: str, preset_kind: QualityPresetKind = QualityPresetKind.PRODUCTION) -> bool:
        return self._make_key(digest, preset_kind) in self._cache

    def get(self, digest: str, preset_kind: QualityPresetKind = QualityPresetKind.PRODUCTION) -> CachedSegment | None:
        return self._cache.get(self._make_key(digest, preset_kind))

    def put(
        self,
        digest: str,
        file_path: str,
        duration_ticks: int,
        preset_kind: QualityPresetKind = QualityPresetKind.PRODUCTION,
    ) -> CachedSegment:
        entry = CachedSegment(
            digest=digest,
            file_path=file_path,
            duration_ticks=duration_ticks,
            preset_kind=preset_kind,
        )
        self._cache[self._make_key(digest, preset_kind)] = entry
        return entry

    def evict(self, digest: str, preset_kind: QualityPresetKind = QualityPresetKind.PRODUCTION) -> bool:
        key = self._make_key(digest, preset_kind)
        return self._cache.pop(key, None) is not None

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


@dataclass(frozen=True)
class SegmentPlanItem:
    """Item individual da montagem segmentada com indicação de reuso por cache."""

    shot_id: str
    scene_idx: int
    digest: str
    is_cached: bool
    cached_path: str | None = None


@dataclass(frozen=True)
class SegmentedRenderPlan:
    """Planejamento consolidado de segmentos a renderizar vs reutilizar."""

    items: tuple[SegmentPlanItem, ...]
    total_segments: int
    cached_count: int
    to_render_count: int

    @property
    def can_skip_all_renders(self) -> bool:
        return self.to_render_count == 0


class SegmentedRenderPlanner:
    """Analisa um RenderPlan e mapeia cada cena/shot contra o cache de segmentos."""

    @classmethod
    def plan(
        cls,
        plan: RenderPlan,
        cache_manager: SegmentCacheManager,
        preset: RenderQualityPreset,
    ) -> SegmentedRenderPlan:
        items: list[SegmentPlanItem] = []
        cached_count = 0

        for scene_idx, scene in enumerate(plan.timeline.scenes):
            for shot in scene.shots:
                asset_key = shot.asset_ref
                motion = shot.effects.motion if (shot.effects and shot.effects.motion) else "none"
                content_sig = f"{shot.shot_id}:{asset_key}:{motion}:{shot.duration_ticks}:{preset.crf}"
                import hashlib
                digest = hashlib.sha256(content_sig.encode("utf-8")).hexdigest()

                cached = cache_manager.get(digest, preset.kind)
                if cached:
                    items.append(
                        SegmentPlanItem(
                            shot_id=shot.shot_id,
                            scene_idx=scene_idx,
                            digest=digest,
                            is_cached=True,
                            cached_path=cached.file_path,
                        )
                    )
                    cached_count += 1
                else:
                    items.append(
                        SegmentPlanItem(
                            shot_id=shot.shot_id,
                            scene_idx=scene_idx,
                            digest=digest,
                            is_cached=False,
                            cached_path=None,
                        )
                    )

        total = len(items)
        return SegmentedRenderPlan(
            items=tuple(items),
            total_segments=total,
            cached_count=cached_count,
            to_render_count=total - cached_count,
        )


class ProgressTracker:
    """Calculador de progresso com suporte a callback e token de cancelamento."""

    def __init__(
        self,
        total_segments: int,
        callback: Callable[[RenderProgress], None] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        self._total_segments = max(1, total_segments)
        self._completed_segments = 0
        self._callback = callback
        self._cancellation_token = cancellation_token
        self._current_stage = RenderProgressStage.PREFLIGHT

    def check_cancellation(self) -> None:
        if self._cancellation_token and self._cancellation_token.is_cancelled:
            self._current_stage = RenderProgressStage.CANCELLED
            self._notify("Render cancelled by operator")
            from ..domain.render_engine import CancellationToken
            raise InterruptedError("Render operation was cancelled by operator")

    def update_stage(self, stage: RenderProgressStage, message: str = "") -> RenderProgress:
        self.check_cancellation()
        self._current_stage = stage
        return self._notify(message)

    def advance_segment(self, message: str = "") -> RenderProgress:
        self.check_cancellation()
        self._completed_segments = min(self._total_segments, self._completed_segments + 1)
        self._current_stage = RenderProgressStage.RENDERING_SEGMENTS
        return self._notify(message)

    def complete(self, message: str = "Render successfully completed") -> RenderProgress:
        self.check_cancellation()
        self._completed_segments = self._total_segments
        self._current_stage = RenderProgressStage.COMPLETED
        return self._notify(message)

    def _notify(self, message: str) -> RenderProgress:
        # Ponderação dos estágios:
        # Preflight: 5%
        # Segments: 5% a 80%
        # Concat: 80% a 90%
        # Mixing: 90% a 100%
        stage = self._current_stage
        if stage == RenderProgressStage.PREFLIGHT:
            pct = 5.0
        elif stage == RenderProgressStage.RENDERING_SEGMENTS:
            segment_fraction = self._completed_segments / self._total_segments
            pct = 5.0 + (segment_fraction * 75.0)
        elif stage == RenderProgressStage.CONCATENATING:
            pct = 85.0
        elif stage == RenderProgressStage.MIXING_AUDIO:
            pct = 95.0
        elif stage == RenderProgressStage.COMPLETED:
            pct = 100.0
        elif stage in (RenderProgressStage.CANCELLED, RenderProgressStage.FAILED):
            pct = 0.0
        else:
            pct = 0.0

        progress = RenderProgress(
            stage=stage,
            completed_segments=self._completed_segments,
            total_segments=self._total_segments,
            percent=round(pct, 1),
            message=message,
        )
        if self._callback:
            self._callback(progress)
        return progress
