"""Casos de uso para pilares de conteúdo (categorias) e atualização de tendências."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from ..domain.categories import ProjectCategory, clean_queries
from ..domain.ids import check_id
from ..domain.trends import TrendItem
from .errors import ProjectNotFound
from .ports import CategoryRepository, VideoRepository
from .trends import IngestTrends

DEFAULT_REFRESH_QUERIES = [
    "Música Eletrônica 2026",
    "Alok 2026",
    "Vintage Culture 2026",
    "ADE 2026",
]


class RefreshError(RuntimeError):
    """Erro base para atualização de tendências."""


class MissingApiKey(RefreshError):
    """Chave da YouTube Data API não configurada."""


class YouTubeApiError(RefreshError):
    """Falha de comunicação ou recusa da YouTube Data API."""


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    res: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        res[k.strip()] = v.strip().strip("'\"")
    return res


class ListCategories:
    def __init__(self, repo: CategoryRepository, videos_repo: VideoRepository | None = None):
        self.repo = repo
        self.videos_repo = videos_repo

    def execute(self, project_id: str) -> list[ProjectCategory]:
        p_id = check_id(project_id)
        if self.videos_repo is not None and self.videos_repo.get_project(p_id) is None:
            raise ProjectNotFound(p_id)
        return self.repo.list(p_id)


class SaveCategory:
    def __init__(self, repo: CategoryRepository, videos_repo: VideoRepository | None = None):
        self.repo = repo
        self.videos_repo = videos_repo

    def execute(
        self,
        project_id: str,
        name: str,
        queries: list[str],
        category_id: str | None = None,
    ) -> ProjectCategory:
        p_id = check_id(project_id)
        if self.videos_repo is not None and self.videos_repo.get_project(p_id) is None:
            raise ProjectNotFound(p_id)
        return self.repo.save(p_id, name, queries, category_id)


class DeleteCategory:
    def __init__(self, repo: CategoryRepository):
        self.repo = repo

    def execute(self, category_id: str) -> bool:
        cid = check_id(category_id)
        return self.repo.delete(cid)


class RefreshTrends:
    def __init__(
        self,
        repo: CategoryRepository,
        ingest: IngestTrends,
        token_env_path: Path | None = None,
        worker_token: str | None = None,
        videos_repo: VideoRepository | None = None,
        fetcher: Callable[[str, list[str]], list[TrendItem]] | None = None,
        environ: Mapping[str, str] | None = None,
    ):
        self.repo = repo
        self.ingest = ingest
        self.token_env_path = token_env_path or Path("credentials/token.env")
        self.worker_token = worker_token
        self.videos_repo = videos_repo
        self.fetcher = fetcher
        self.environ = environ

    def _get_api_key(self) -> str:
        if self.environ is not None:
            env_key = self.environ.get("YOUTUBE_API_KEY", "").strip()
            if env_key:
                return env_key
        if self.token_env_path and self.token_env_path.is_file():
            env_dict = parse_env_file(self.token_env_path)
            file_key = env_dict.get("YOUTUBE_API_KEY", "").strip()
            if file_key:
                return file_key
        raise MissingApiKey(f"YOUTUBE_API_KEY not configured in {self.token_env_path} or environment")

    def execute(self, project_id: str, custom_queries: list[str] | None = None) -> int:
        if self.fetcher is None:
            raise YouTubeApiError("No trend fetcher configured")
        p_id = check_id(project_id)
        if self.videos_repo is not None and self.videos_repo.get_project(p_id) is None:
            raise ProjectNotFound(p_id)

        if custom_queries:
            queries = clean_queries(custom_queries)
        else:
            categories = self.repo.list(p_id)
            queries = []
            for cat in categories:
                for q in cat.queries:
                    if q not in queries:
                        queries.append(q)
            if not queries:
                queries = DEFAULT_REFRESH_QUERIES.copy()

        key = self._get_api_key()
        items = self.fetcher(key, queries)
        if not items:
            raise YouTubeApiError("No trend topics returned by YouTube Data API for queries")
        return self.ingest.execute(p_id, items)
