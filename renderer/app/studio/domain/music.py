from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = [
    "MusicTrack",
    "MusicCatalog",
    "infer_mood_tags",
]


def infer_mood_tags(title: str, note: str = "") -> tuple[str, ...]:
    """Infere tags semânticas de humor/tom com base no título e notas da faixa."""
    text = f"{title} {note}".lower()
    tags: list[str] = []

    def _add(*new_tags: str) -> None:
        for t in new_tags:
            if t not in tags:
                tags.append(t)

    if "ambient" in text:
        _add("ambient", "calm")
    if "lofi" in text:
        _add("lofi", "chill", "relaxed")
    if "sci-fi" in text or "scifi" in text:
        _add("scifi", "dark", "tension")
    if "cinematic" in text or "tension" in text:
        _add("cinematic", "tension", "dramatic")
    if "space" in text or "organ" in text:
        _add("ambient", "space", "mysterious")
    if "electronic" in text:
        _add("electronic", "ambient")

    return tuple(tags)


class MusicTrack(BaseModel):
    """Metadados de uma trilha sonora pura licenciada."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    creator: str = ""
    license: str = "cc0"
    file_path: str
    duration_s: float
    sha256: str = ""
    mood_tags: tuple[str, ...] = ()


class MusicCatalog(BaseModel):
    """Catálogo imutável de faixas musicais disponíveis."""

    model_config = ConfigDict(frozen=True)

    tracks: tuple[MusicTrack, ...] = ()

    def find_tracks(self, mood: str | None = None) -> list[MusicTrack]:
        """Filtra faixas pelo humor/tag solicitado. Retorna todas se None/vazio."""
        if not mood or not mood.strip():
            return list(self.tracks)
        target = mood.strip().lower()
        target_norm = target.replace("-", "")
        matches: list[MusicTrack] = []
        for track in self.tracks:
            for tag in track.mood_tags:
                tag_lower = tag.lower()
                if target == tag_lower or target_norm == tag_lower.replace("-", ""):
                    matches.append(track)
                    break
        return matches

    @classmethod
    def from_items(
        cls,
        items: list[dict[str, Any]],
        base_dir: Path | None = None,
    ) -> MusicCatalog:
        """Constrói o catálogo a partir de dicionários de manifesto."""
        parsed_tracks: list[MusicTrack] = []
        for item in items:
            track_id = str(item.get("id") or item.get("openverse_id") or Path(item.get("file", "track")).stem)
            title = str(item.get("title", ""))
            creator = str(item.get("creator", ""))
            license_val = str(item.get("license", "cc0"))
            file_rel = item.get("file_path") or item.get("file", "")
            if base_dir and not Path(file_rel).is_absolute():
                file_path = str(Path(base_dir) / file_rel)
            else:
                file_path = str(file_rel)

            if "duration_s" in item:
                duration_s = float(item["duration_s"])
            elif "duration_ms" in item:
                duration_s = float(item["duration_ms"]) / 1000.0
            else:
                duration_s = 0.0

            sha256 = str(item.get("sha256", ""))

            if "mood_tags" in item and item["mood_tags"] is not None:
                mood_tags = tuple(str(x) for x in item["mood_tags"])
            else:
                note = str(item.get("note", ""))
                mood_tags = infer_mood_tags(title, note)

            parsed_tracks.append(
                MusicTrack(
                    id=track_id,
                    title=title,
                    creator=creator,
                    license=license_val,
                    file_path=file_path,
                    duration_s=duration_s,
                    sha256=sha256,
                    mood_tags=mood_tags,
                )
            )
        return cls(tracks=tuple(parsed_tracks))

    @classmethod
    def load_from_manifest(
        cls,
        manifest_path: Path,
        storage_root: Path | None = None,
    ) -> MusicCatalog:
        """Carrega e valida o catálogo a partir de um arquivo manifest.json."""
        text = Path(manifest_path).read_text(encoding="utf-8")
        items = json.loads(text)
        base_dir = storage_root if storage_root is not None else Path(manifest_path).parent
        return cls.from_items(items, base_dir=base_dir)
