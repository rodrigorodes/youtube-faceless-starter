"""Catálogo e biblioteca de áudio profissional (V4-03 / Professional Audio).

Gerencia trilhas musicais, efeitos sonoros (SFX) e ambiências com:
- Categorização tipada (música, SFX, ambiência).
- Metadados semânticos de mood, BPM e gênero.
- Registro obrigatório de licença e proveniência (CC0, CC-BY, Royalty-Free).
- Suporte a busca contextual e filtragem precisa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AudioCategory(str, Enum):
    """Categorias funcionais de faixas no design de som audiovisual."""

    VOICE = "voice"
    MUSIC = "music"
    SFX = "sfx"
    AMBIENCE = "ambience"


@dataclass(frozen=True)
class AudioTrack:
    """Metadados de uma faixa sonora licenciada no catálogo do Studio."""

    id: str
    category: AudioCategory
    title: str
    creator: str = ""
    license: str = "cc0"             # Obrigatória: recusa áudio sem licença registrada
    file_path: str = ""
    duration_s: float = 0.0
    bpm: int | None = None
    mood_tags: tuple[str, ...] = ()
    gain_db: float = 0.0             # Ganho pré-mixagem calibrado (offset em dB)
    sha256: str = ""
    attribution: str = ""

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("track id cannot be empty")
        if not self.title.strip():
            raise ValueError("track title cannot be empty")
        if not self.license.strip():
            raise ValueError(f"track '{self.id}' must declare a valid license")
        if self.duration_s < 0:
            raise ValueError("duration_s cannot be negative")


@dataclass(frozen=True)
class AudioCatalog:
    """Biblioteca imutável de áudio com pesquisa contextual."""

    tracks: tuple[AudioTrack, ...] = ()

    def get_track(self, track_id: str) -> AudioTrack | None:
        target = track_id.strip()
        for t in self.tracks:
            if t.id == target:
                return t
        return None

    def find_tracks(
        self,
        category: AudioCategory | None = None,
        mood: str | None = None,
        bpm_range: tuple[int, int] | None = None,
    ) -> list[AudioTrack]:
        """Localiza faixas compatíveis com os filtros fornecidos."""
        results = list(self.tracks)

        if category is not None:
            results = [t for t in results if t.category == category]

        if mood is not None and mood.strip():
            target_mood = mood.strip().lower()
            results = [
                t for t in results
                if any(target_mood in tag.lower() for tag in t.mood_tags)
            ]

        if bpm_range is not None:
            min_bpm, max_bpm = bpm_range
            results = [
                t for t in results
                if t.bpm is not None and min_bpm <= t.bpm <= max_bpm
            ]

        return results

    def with_track(self, track: AudioTrack) -> AudioCatalog:
        """Retorna uma nova instância do catálogo incluindo a faixa informada."""
        existing = [t for t in self.tracks if t.id != track.id]
        return AudioCatalog(tracks=tuple(existing + [track]))
