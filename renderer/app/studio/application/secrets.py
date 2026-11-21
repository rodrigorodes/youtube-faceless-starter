"""Configuração pública do projeto (F10-07): só portas de provider, nunca segredos."""
from __future__ import annotations

from ..domain.ids import check_id
from ..domain.secrets import sanitize_project_config
from .errors import ProjectNotFound
from .ports import VideoRepository


class GetPublicProjectConfig:
    """Lê o `Project.config` e devolve a lista branca que pode ir ao browser."""

    def __init__(self, videos: VideoRepository):
        self.videos = videos

    def execute(self, project_id: str) -> dict[str, object]:
        p_id = check_id(project_id)
        project = self.videos.get_project(p_id)
        if project is None:
            raise ProjectNotFound(p_id)
        return {"project_id": p_id, "config": sanitize_project_config(project.config)}