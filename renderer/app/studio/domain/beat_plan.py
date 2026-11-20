"""Planejamento puro de beats dentro da duração de uma cena; sem I/O e sem render.

A regra distribui N beats sequencialmente a partir de 0s ao longo de
``Scene.duration_s``, preservando a ordem de entrada. Cada beat de entrada traz
apenas a *duração desejada* (``end_s - start_s``); a posição absoluta dele é
recalculada para que os beats fiquem contíguos, sem sobreposição, cobrindo a
cena. Nada aqui resolve mídia, valida licença/veracidade de proveniência nem
confirma que o asset existe: isso é auditoria (F5-08) e render (F5-06).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .contracts import Scene
from .visual_beat import VisualBeat

# Resíduo de ponto flutuante tolerado ao comparar a soma dos beats com a cena.
DEFAULT_TOLERANCE_S = 1e-6


@dataclass(frozen=True)
class SceneBeatPlan:
    """Beats reposicionados dentro da cena, na ordem de entrada."""

    scene_id: str
    duration_s: float
    beats: tuple[VisualBeat, ...]

    @property
    def coverage_s(self) -> float:
        """Soma das durações planejadas; igual a ``duration_s`` quando cobre a cena."""
        return math.fsum(beat.end_s - beat.start_s for beat in self.beats)


def plan_scene_beats(
    scene: Scene,
    beats: Sequence[VisualBeat],
    *,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> SceneBeatPlan:
    """Reposiciona ``beats`` de forma contígua em ``[0, scene.duration_s]``.

    Entradas inválidas são rejeitadas com ``ValueError``: cena sem duração
    finita positiva; lista de beats vazia; beat de outra cena; soma das durações
    que excede a cena ou não a cobre (fora de ``tolerance_s``); duração de beat
    não finita ou não positiva. A ordem de entrada é preservada e o último beat
    fecha exatamente a cena.
    """
    duration = _scene_duration(scene)
    ordered = tuple(beats)
    spans = _beat_spans(scene, ordered)
    windows = plan_beat_windows(duration, spans, tolerance_s=tolerance_s)
    placed = tuple(
        beat.model_copy(update={"start_s": start, "end_s": end})
        for beat, (start, end) in zip(ordered, windows)
    )
    return SceneBeatPlan(scene_id=scene.id, duration_s=duration, beats=placed)


def plan_beat_windows(
    scene_duration_s: float,
    beat_durations: Sequence[float],
    *,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> tuple[tuple[float, float], ...]:
    """Distribui durações de beat, contíguas, de 0 até ``scene_duration_s``.

    Núcleo numérico puro usado por :func:`plan_scene_beats`; separado para poder
    validar fronteiras (zero beats, durações não finitas/negativas, excesso ou
    cobertura incompleta) sem depender do contrato de mídia.
    """
    duration = _positive_finite(scene_duration_s, "scene duration")
    _validate_tolerance(tolerance_s)
    spans = tuple(_positive_finite(span, "beat duration") for span in beat_durations)
    if not spans:
        raise ValueError("at least one beat is required")
    total = math.fsum(spans)
    if total > duration + tolerance_s:
        raise ValueError(f"beats exceed scene duration: {total} > {duration}")
    if total < duration - tolerance_s:
        raise ValueError(f"beats do not cover scene duration: {total} < {duration}")
    windows: list[tuple[float, float]] = []
    cursor = 0.0
    for span in spans:
        windows.append((cursor, cursor + span))
        cursor += span
    # Fecha a cena exatamente, absorvendo resíduo de ponto flutuante no último beat.
    windows[-1] = (windows[-1][0], duration)
    return tuple(windows)


def _scene_duration(scene: Scene) -> float:
    if scene.duration_s is None:
        raise ValueError("scene duration must be a finite positive number")
    return _positive_finite(scene.duration_s, "scene duration")


def _beat_spans(scene: Scene, beats: Sequence[VisualBeat]) -> tuple[float, ...]:
    spans: list[float] = []
    for index, beat in enumerate(beats):
        if not isinstance(beat, VisualBeat):
            raise ValueError(f"beat {index} must be a VisualBeat")
        if beat.scene_id != scene.id:
            raise ValueError(
                f"beat {index} belongs to scene {beat.scene_id!r}, not {scene.id!r}"
            )
        spans.append(beat.end_s - beat.start_s)
    return tuple(spans)


def _positive_finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


def _validate_tolerance(tolerance_s: float) -> None:
    if isinstance(tolerance_s, bool) or not isinstance(tolerance_s, (int, float)):
        raise ValueError("tolerance must be a finite non-negative number")
    if not math.isfinite(tolerance_s) or tolerance_s < 0:
        raise ValueError("tolerance must be a finite non-negative number")
