"""Ponte exata segundos (autoria) <-> ticks inteiros (plano) — RP-010.

A autoria humana (``VisualBeat``/``beat_plan``) trabalha em segundos float; o
``RenderPlan`` mede o tempo em ticks inteiros com uma timebase explícita. Este é
o único ponto onde os dois mundos se encontram, e existe para **não** reintroduzir
a deriva que a fatia B fechou (``beat_plan`` acumula sequencialmente e rejeita
span não representável).

Decisões:

- ``seconds_to_ticks`` converte o valor binário **exato** do float
  (``Fraction(float)``) e arredonda ao inteiro mais próximo (empate ao par, como
  ``round``). Não há multiplicação em ponto flutuante intermediária: duas
  fronteiras float iguais viram o **mesmo** tick, então janelas contíguas em
  segundos continuam contíguas em ticks.
- ``ticks_to_seconds`` só serve para exibição/comparação; o plano nunca guarda
  segundos.
- ``tick_windows`` exige contiguidade, rejeita span abaixo de meio tick com erro
  claro (nunca emite janela de span 0) e, quando recebe ``duration_s``, confere
  que a última janela fecha a duração — a cobertura é reproduzível, sem sobra
  nem buraco.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from fractions import Fraction

Pair = tuple[float, float]


def _tick_rate(ticks_per_second: object) -> int:
    if isinstance(ticks_per_second, bool) or not isinstance(ticks_per_second, int):
        raise ValueError("ticks_per_second must be a positive integer")
    if ticks_per_second <= 0:
        raise ValueError("ticks_per_second must be a positive integer")
    return ticks_per_second


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def seconds_to_ticks(seconds: float, ticks_per_second: int) -> int:
    """Converte segundos no tick mais próximo usando o valor binário exato do float."""
    tps = _tick_rate(ticks_per_second)
    value = _finite(seconds, "seconds")
    return round(Fraction(value) * tps)


def ticks_to_seconds(ticks: int, ticks_per_second: int) -> float:
    """Converte ticks em segundos (float) só para exibição/comparação."""
    tps = _tick_rate(ticks_per_second)
    if isinstance(ticks, bool) or not isinstance(ticks, int):
        raise ValueError("ticks must be an integer")
    return ticks / tps


def _as_pairs(windows: Iterable[Pair]) -> tuple[Pair, ...]:
    if isinstance(windows, (str, bytes, bytearray)):
        raise ValueError("windows must be an iterable of (start_s, end_s) pairs")
    try:
        items = tuple(windows)
    except TypeError as exc:
        raise ValueError("windows must be an iterable of (start_s, end_s) pairs") from exc
    pairs: list[Pair] = []
    for index, item in enumerate(items):
        if isinstance(item, (str, bytes, bytearray)):
            raise ValueError(f"window {index} must be a (start_s, end_s) pair")
        try:
            start_s, end_s = item
        except (TypeError, ValueError) as exc:
            raise ValueError(f"window {index} must be a (start_s, end_s) pair") from exc
        pairs.append((_finite(start_s, f"window {index} start"),
                      _finite(end_s, f"window {index} end")))
    return tuple(pairs)


def tick_windows(
    windows: Iterable[Pair],
    ticks_per_second: int,
    *,
    duration_s: float | None = None,
) -> tuple[tuple[int, int], ...]:
    """Converte janelas de segundos (ex.: ``SceneBeatPlan``) em ticks inteiros.

    Rejeita com ``ValueError``: taxa/duração inválidas; entrada não iterável ou
    com itens que não são pares; **span abaixo de meio tick** (viraria janela de
    span 0 — espelha a política de representabilidade da fatia B); quebra de
    contiguidade entre janelas; e, quando ``duration_s`` é dada, cobertura que não
    fecha a duração. A ordem e a contiguidade de entrada são preservadas.
    """
    tps = _tick_rate(ticks_per_second)
    pairs = _as_pairs(windows)
    if not pairs:
        raise ValueError("at least one window is required")
    out: list[tuple[int, int]] = []
    previous_end: int | None = None
    for index, (start_s, end_s) in enumerate(pairs):
        start = seconds_to_ticks(start_s, tps)
        end = seconds_to_ticks(end_s, tps)
        if end <= start:
            raise ValueError(
                f"window {index} span {end_s - start_s!r}s is not representable at "
                f"{tps} ticks/s (resolves to {start}..{end} ticks); use a finer timebase"
            )
        if previous_end is not None and start != previous_end:
            raise ValueError(
                f"window {index} starts at tick {start} but the previous window ends at "
                f"{previous_end}: intervals must be contiguous"
            )
        out.append((start, end))
        previous_end = end
    if duration_s is not None:
        expected = seconds_to_ticks(_finite(duration_s, "duration_s"), tps)
        if out[-1][1] != expected:
            raise ValueError(
                f"coverage drift: last window ends at {out[-1][1]} ticks, expected "
                f"{expected} ({duration_s!r}s)"
            )
    return tuple(out)
