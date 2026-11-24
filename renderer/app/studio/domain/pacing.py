from __future__ import annotations

import math
from enum import StrEnum
from typing import Literal

from pydantic import model_validator
from typing_extensions import Self

from .render_plan import Motion, _PlanModel

__all__ = [
    "Motion",
    "PacingPreset",
    "ShotTiming",
    "PacingPlan",
    "PacingEngine",
]


class PacingPreset(StrEnum):
    dynamic = "dynamic"
    balanced = "balanced"
    cinematic = "cinematic"


MOTION_CYCLE: tuple[Motion, ...] = ("zoom_in", "zoom_out", "pan_left", "pan_right")

_PRESET_CONFIG: dict[PacingPreset, dict[str, float]] = {
    PacingPreset.dynamic: {
        "target_s": 2.5,
        "min_s": 1.5,
        "max_s": 3.5,
    },
    PacingPreset.balanced: {
        "target_s": 3.5,
        "min_s": 2.5,
        "max_s": 5.0,
    },
    PacingPreset.cinematic: {
        "target_s": 5.0,
        "min_s": 4.0,
        "max_s": 8.0,
    },
}


class ShotTiming(_PlanModel):
    shot_index: int
    start_tick: int
    duration_ticks: int
    motion: Motion = "none"


class PacingPlan(_PlanModel):
    scene_id: str
    shots: tuple[ShotTiming, ...] = ()
    total_duration_ticks: int

    @property
    def target_shot_durations_ticks(self) -> tuple[int, ...]:
        return tuple(s.duration_ticks for s in self.shots)

    @property
    def transition_points_ticks(self) -> tuple[int, ...]:
        return tuple(s.start_tick for s in self.shots[1:])

    @model_validator(mode="after")
    def _validate_timeline(self) -> Self:
        if self.shots:
            total_shots_duration = sum(s.duration_ticks for s in self.shots)
            if total_shots_duration != self.total_duration_ticks:
                raise ValueError(
                    f"Sum of shot durations ({total_shots_duration}) does not equal "
                    f"total_duration_ticks ({self.total_duration_ticks})"
                )
            current = 0
            for s in self.shots:
                if s.start_tick != current:
                    raise ValueError(
                        f"Shot {s.shot_index} start_tick ({s.start_tick}) does not match "
                        f"expected ({current})"
                    )
                current += s.duration_ticks
        return self


class PacingEngine:
    """Motor de cálculo determinístico e puro para cortes de cena ritmados."""

    @classmethod
    def calculate(
        cls,
        scene_id: str,
        total_duration_ticks: int,
        ticks_per_second: int,
        asset_count: int = 1,
        preset: PacingPreset | str = PacingPreset.dynamic,
        is_video_asset: bool = False,
    ) -> PacingPlan:
        if total_duration_ticks <= 0:
            raise ValueError(f"total_duration_ticks must be greater than 0, got {total_duration_ticks}")
        if ticks_per_second <= 0:
            raise ValueError(f"ticks_per_second must be greater than 0, got {ticks_per_second}")
        if asset_count <= 0:
            raise ValueError(f"asset_count must be at least 1, got {asset_count}")

        if isinstance(preset, str):
            try:
                preset = PacingPreset(preset.strip().lower())
            except ValueError:
                raise ValueError(f"Unknown pacing preset: {preset}")
        elif not isinstance(preset, PacingPreset):
            raise ValueError(f"Unknown pacing preset: {preset}")

        cfg = _PRESET_CONFIG[preset]
        target_s = cfg["target_s"]
        min_s = cfg["min_s"]
        max_s = cfg["max_s"]

        total_s = total_duration_ticks / ticks_per_second
        max_shots = max(1, int(total_s / min_s))

        if is_video_asset:
            if asset_count == 1:
                # Vídeo já possui movimento intrínseco: mantém tomada única a menos que ultrapasse dobro do teto
                if total_s > max_s * 2:
                    num_shots = max(2, math.ceil(total_s / max_s))
                else:
                    num_shots = 1
            else:
                num_shots = min(asset_count, max_shots)
        else:
            if asset_count == 1:
                if total_s > max_s:
                    num_shots = max(2, math.ceil(total_s / target_s))
                else:
                    num_shots = 1
            else:
                num_shots = min(asset_count, max_shots)

        num_shots = max(1, min(num_shots, max_shots if asset_count > 1 else max(num_shots, 1)))

        # Garantia matemática exata: divisão inteira da base e absorção de resto no último shot
        base_duration = total_duration_ticks // num_shots
        remainder = total_duration_ticks % num_shots

        durations = [base_duration] * num_shots
        durations[-1] += remainder

        shots: list[ShotTiming] = []
        current_tick = 0
        for i in range(num_shots):
            dur = durations[i]
            if is_video_asset:
                motion: Motion = "none"
            else:
                motion = MOTION_CYCLE[i % len(MOTION_CYCLE)]

            shots.append(
                ShotTiming(
                    shot_index=i,
                    start_tick=current_tick,
                    duration_ticks=dur,
                    motion=motion,
                )
            )
            current_tick += dur

        return PacingPlan(
            scene_id=scene_id,
            shots=tuple(shots),
            total_duration_ticks=total_duration_ticks,
        )
