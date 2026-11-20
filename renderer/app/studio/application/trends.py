"""Caso de uso de ingestão de tópicos e métricas de tendência."""
from ..domain.trends import TrendItem, validate_trends
from .errors import ProjectNotFound
from .ports import TrendRepository, VideoRepository


class IngestTrends:
    def __init__(self, trends_repo: TrendRepository, videos_repo: VideoRepository, allowed_hosts: tuple[str, ...]):
        self.trends_repo = trends_repo
        self.videos_repo = videos_repo
        self.allowed_hosts = allowed_hosts

    def execute(self, project_id: str, items: list[TrendItem]) -> int:
        if self.videos_repo.get_project(project_id) is None:
            raise ProjectNotFound(project_id)
        validate_trends(items, self.allowed_hosts)
        return self.trends_repo.upsert(project_id, items)
