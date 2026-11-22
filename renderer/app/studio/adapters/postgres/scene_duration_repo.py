"""W4.3: leitura/escrita da duração real medida por cena em ``studio.scenes.duration_s``.

A coluna existe desde a migração 0001 e era lida pelo repositório editorial, mas nada a gravava.
Aqui ela é gravada depois da síntese da voz — sempre com a medida do WAV, nunca com estimativa.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

import psycopg

from ...domain.ids import check_id
from .repo import _translated


class PostgresSceneDurationRepository:
    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self._connect = connect

    def save_durations(self, video_id: str, durations: Mapping[str, float]) -> None:
        if not durations:
            return
        video = check_id(video_id)
        with _translated(), self._connect() as conn:
            for scene_id, seconds in durations.items():
                conn.execute("UPDATE studio.scenes SET duration_s = %s WHERE id = %s AND video_id = %s",
                             (float(seconds), check_id(scene_id), video))

    def durations(self, video_id: str) -> dict[str, float]:
        with _translated(), self._connect() as conn:
            rows = conn.execute("SELECT id, duration_s FROM studio.scenes "
                                "WHERE video_id = %s AND duration_s IS NOT NULL",
                                (check_id(video_id),)).fetchall()
        return {row[0]: float(row[1]) for row in rows}
