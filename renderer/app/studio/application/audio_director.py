from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Sequence

from ..domain.music import MusicCatalog, MusicTrack
from ..domain.render_plan import AudioMix

__all__ = [
    "AudioDirector",
    "load_music_catalog",
]


def load_music_catalog(
    manifest_path: Path,
    storage_root: Path | None = None,
) -> MusicCatalog:
    """Lê o arquivo de manifesto JSON e constrói o catálogo musical."""
    return MusicCatalog.load_from_manifest(manifest_path, storage_root=storage_root)


class AudioDirector:
    """Seleciona a melhor faixa musical para o tom do roteiro e configura o AudioMix."""

    @classmethod
    def select_track(
        cls,
        tone: str,
        catalog: MusicCatalog | Sequence[MusicTrack],
        format: Any = None,
    ) -> MusicTrack | None:
        """Seleciona a melhor faixa com base no tom solicitado ou fallback."""
        tracks: tuple[MusicTrack, ...]
        if isinstance(catalog, MusicCatalog):
            tracks = catalog.tracks
        else:
            tracks = tuple(catalog)

        if not tracks:
            return None

        tone_lower = (tone or "").lower()
        raw_tokens = set(re.findall(r"\w+", tone_lower))
        if "sci-fi" in tone_lower or "scifi" in tone_lower:
            raw_tokens.add("scifi")

        best_track: MusicTrack | None = None
        best_score = 0

        for track in tracks:
            score = 0
            for tag in track.mood_tags:
                tag_lower = tag.lower()
                tag_norm = tag_lower.replace("-", "")
                if tag_lower in raw_tokens or tag_norm in raw_tokens:
                    score += 1
                elif any(tok in tag_lower for tok in raw_tokens if len(tok) >= 4):
                    score += 1

            if score > best_score:
                best_score = score
                best_track = track

        if best_track is not None and best_score > 0:
            return best_track

        # Fallback para a primeira faixa se nenhuma bateu
        return tracks[0]

    @classmethod
    def build_audio_mix(
        cls,
        music_gain: float = 0.35,
        ducking_ratio: float = 12.0,
        afade_in_s: float = 0.5,
        afade_out_s: float = 1.0,
        **kwargs: Any,
    ) -> AudioMix:
        """Cria e retorna instância declarativa de AudioMix com parâmetros profissionais."""
        return AudioMix(
            music_gain=music_gain,
            ducking_ratio=ducking_ratio,
            afade_in_s=afade_in_s,
            afade_out_s=afade_out_s,
            **kwargs,
        )
