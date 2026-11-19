"""Layout de pastas em disco. Todo ID é validado antes de virar caminho."""
from pathlib import Path

from ..domain.ids import check_cache_key, check_id


def video_dir(root: Path, project_id: str, video_id: str) -> Path:
    return Path(root) / "projects" / check_id(project_id) / "videos" / check_id(video_id)


def cache_path(root: Path, cache_key: str) -> Path:
    return Path(root) / "cache" / check_cache_key(cache_key)[:2] / cache_key
