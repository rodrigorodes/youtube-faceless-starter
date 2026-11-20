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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .contracts import Scene
from .visual_beat import VisualBeat

# Sobra máxima (soma dos beats abaixo da cena) tolerada por padrão.
DEFAULT_TOLERANCE_S = 1e-6
# Folga máxima de overflow: apenas resíduo de soma em ponto flutuante, nunca
# descasamento real. Beats que somam mais que a cena além disso são rejeitados.
_FLOAT_RESIDUE_S = 1e-9
# Quantos ulps da duração são aceitos como resíduo de soma no limite superior.
_RESIDUE_ULPS = 8


@dataclass(frozen=True)
class SceneBeatPlan:
    """Beats reposicionados dentro da cena, na ordem de entrada."""

    scene_id: str
    duration_s: float
    beats: tuple[VisualBeat, ...]

    @property
    def coverage_s(self) -> float:
        """Cobertura derivada das janelas contíguas planejadas.

        Igual a ``duration_s`` quando a soma dos beats não excede a cena (o
        último beat é fechado nela). No resíduo raro de overflow em ponto
        flutuante, é a extensão cumulativa real, ainda coerente com os beats.
        """
        if not self.beats:
            return 0.0
        return self.beats[-1].end_s - self.beats[0].start_s


def plan_scene_beats(
    scene: Scene,
    beats: Iterable[VisualBeat],
    *,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> SceneBeatPlan:
    """Reposiciona ``beats`` de forma contígua em ``[0, scene.duration_s]``.

    Entradas inválidas são rejeitadas com ``ValueError``: cena sem duração
    finita positiva; ``beats`` não iterável; lista de beats vazia; beat de outra
    cena ou que não é :class:`VisualBeat`; duração de beat não finita ou não
    positiva; soma que **excede** a cena (fora do resíduo de ponto flutuante) ou
    que **não a cobre** (fora de ``tolerance_s``). A ordem de entrada é
    preservada. Quando a soma não excede a cena, o último beat fecha exatamente
    ``scene.duration_s``; nenhum beat pode sair com span <= 0 ou start >= end.
    """
    duration = _scene_duration(scene)
    _validate_tolerance(tolerance_s)
    ordered = _as_tuple(beats, "beats")
    spans = _beat_spans(scene, ordered)
    windows = plan_beat_windows(duration, spans, tolerance_s=tolerance_s)
    placed = tuple(
        # Reconstrução com revalidação (em pydantic v2, model_copy NÃO revalida):
        # a invariante start_s < end_s é garantida por construção e conferida aqui.
        VisualBeat.model_validate({**beat.model_dump(), "start_s": start, "end_s": end})
        for beat, (start, end) in zip(ordered, windows)
    )
    return SceneBeatPlan(scene_id=scene.id, duration_s=duration, beats=placed)


def plan_beat_windows(
    scene_duration_s: float,
    beat_durations: Iterable[float],
    *,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> tuple[tuple[float, float], ...]:
    """Distribui durações de beat, contíguas, de 0 até ``scene_duration_s``.

    Núcleo numérico puro usado por :func:`plan_scene_beats`; separado para poder
    validar fronteiras (zero beats, durações não finitas/negativas, excesso ou
    cobertura incompleta) sem depender do contrato de mídia.

    Política de excedente: a soma dos beats pode ficar até ``tolerance_s``
    **abaixo** da cena (sobra), mas nunca acima além do resíduo de soma em ponto
    flutuante (poucos ulps) — excesso real é rejeitado. As janelas são
    cumulativas e cada beat recebe exatamente sua duração; o último beat só é
    fechado em ``scene_duration_s`` quando isso não zera nem inverte o span.
    """
    duration = _positive_finite(scene_duration_s, "scene duration")
    _validate_tolerance(tolerance_s)
    durations = _as_tuple(beat_durations, "beat durations")
    spans = tuple(_positive_finite(span, "beat duration") for span in durations)
    if not spans:
        raise ValueError("at least one beat is required")
    total = math.fsum(spans)
    overflow_epsilon = max(_FLOAT_RESIDUE_S, math.ulp(duration) * _RESIDUE_ULPS)
    if total > duration + overflow_epsilon:
        raise ValueError(f"beats exceed scene duration: {total} > {duration}")
    if total < duration - tolerance_s:
        raise ValueError(f"beats do not cover scene duration: {total} < {duration}")
    windows: list[tuple[float, float]] = []
    cursor = 0.0
    for span in spans:
        windows.append((cursor, cursor + span))
        cursor += span
    last_start = windows[-1][0]
    if duration > last_start:
        # Fecha a cena; o último beat cresce apenas o resíduo aceito (<= overflow).
        windows[-1] = (last_start, duration)
    # Se ``duration <= last_start`` (overflow em resíduo), mantém as janelas
    # cumulativas: nenhum beat é encolhido, então span <= 0 e start >= end são
    # impossíveis por construção.
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


def _as_tuple(values: Iterable, name: str) -> tuple:
    if isinstance(values, (str, bytes, bytearray)):
        raise ValueError(f"{name} must be an iterable of items, not {type(values).__name__}")
    try:
        return tuple(values)
    except TypeError as exc:
        raise ValueError(f"{name} must be iterable") from exc


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
