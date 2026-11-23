"""Casos de uso para pilares de conteúdo (categorias) e atualização de tendências."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..domain.categories import ProjectCategory, clean_queries
from ..domain.ids import check_id
from ..domain.trend_cards import SEARCH_SOURCE
from ..domain.trends import TrendItem
from ..domain.youtube_categories import youtube_category_for
from .errors import ProjectNotFound
from .ports import CategoryRepository, VideoRepository
from .trends import IngestTrends

# Cota da YouTube Data API (10.000 unidades/dia, compartilhadas com o upload de vídeo):
#   search.list = 100 unidades POR TERMO; videos.list (Em Alta e estatísticas) = 1 unidade por chamada.
MAX_SEARCH_TERMS_PER_REFRESH = 6          # teto de 600 unidades por "Buscar agora"
SEARCH_COOLDOWN = timedelta(hours=6)      # termo buscado há menos que isso não gasta cota de novo
MAX_POPULAR_CATEGORIES = 3                # categorias de Em Alta por coleta (1 unidade por categoria e região)
POPULAR_REGIONS = ("BR", "US")
POPULAR_PER_CALL = 10
_INGEST_BATCH = 50                        # `validate_trends` aceita até 50 itens por lote


class RefreshError(RuntimeError):
    """Erro base para atualização de tendências."""


class MissingApiKey(RefreshError):
    """Chave da YouTube Data API não configurada."""


class YouTubeApiError(RefreshError):
    """Falha de comunicação ou recusa da YouTube Data API."""


class NoSearchTerms(RefreshError):
    """Sem pilar com termos e sem nicho no canal: não há o que buscar (e não se inventa um assunto)."""


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
        popular_fetcher: Callable[..., list[TrendItem]] | None = None,
        environ: Mapping[str, str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.repo = repo
        self.ingest = ingest
        self.token_env_path = token_env_path or Path("credentials/token.env")
        self.worker_token = worker_token
        self.videos_repo = videos_repo
        self.fetcher = fetcher
        self.popular_fetcher = popular_fetcher
        self.environ = environ
        self.clock = clock or (lambda: datetime.now(timezone.utc))

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
        project = self.videos_repo.get_project(p_id) if self.videos_repo is not None else None
        if self.videos_repo is not None and project is None:
            raise ProjectNotFound(p_id)

        if custom_queries:
            queries = clean_queries(custom_queries)
            key = self._get_api_key()
            items = self.fetcher(key, queries)
            if not items:
                raise YouTubeApiError("No trend topics returned by YouTube Data API for queries")
            return self._ingest(p_id, items)

        categories = self.repo.list(p_id)
        niche = (getattr(project, "niche", "") or "").strip()
        terms, term_pillar = self._terms(categories, niche)
        popular_plan = self._popular_plan(categories, niche)
        if not terms and not popular_plan:
            raise NoSearchTerms(
                "Sem termos para buscar: cadastre um pilar com termos ou defina o nicho do canal.")

        key = self._get_api_key()
        all_items: list[TrendItem] = []
        searched = self._not_searched_recently(p_id, terms)
        if searched:
            for item in self.fetcher(key, searched):
                all_items.append(item.model_copy(update={"category_id": term_pillar.get(item.topic.casefold())}))

        if self.popular_fetcher:
            seen_urls: set[tuple[str, str]] = set()
            for pillar_id, yt_category in popular_plan:
                for region in POPULAR_REGIONS:
                    try:
                        found = self.popular_fetcher(key, region, POPULAR_PER_CALL, category_id=yt_category)
                    except Exception:
                        continue  # o Em Alta é complemento: falha parcial não derruba a coleta
                    for item in found or []:
                        # o mesmo vídeo em duas categorias do mesmo país entra uma vez; BR e US são fontes distintas
                        url = (region, item.evidence[0].url if item.evidence else item.topic)
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        all_items.append(item.model_copy(update={"category_id": pillar_id}))

        if not all_items:
            if terms and not searched:
                return 0  # todos os termos foram buscados há pouco: nada novo a pagar em cota
            raise YouTubeApiError("No trend topics returned by YouTube Data API for queries")
        return self._ingest(p_id, all_items)

    def _ingest(self, project_id: str, items: list[TrendItem]) -> int:
        stored = 0
        for start in range(0, len(items), _INGEST_BATCH):
            stored += self.ingest.execute(project_id, items[start:start + _INGEST_BATCH])
        return stored

    @staticmethod
    def _terms(categories: list[ProjectCategory], niche: str) -> tuple[list[str], dict[str, str | None]]:
        """Termos da coleta, no máximo `MAX_SEARCH_TERMS_PER_REFRESH`, intercalando os pilares (o 1º termo de
        cada pilar antes do 2º de qualquer um) para que todos os pilares entrem. Sem pilar, o nicho do canal."""
        terms: list[str] = []
        owner: dict[str, str | None] = {}
        depth = max((len(c.queries) for c in categories), default=0)
        for level in range(depth):
            for cat in categories:
                if level < len(cat.queries) and cat.queries[level].casefold() not in owner:
                    owner[cat.queries[level].casefold()] = cat.id
                    terms.append(cat.queries[level])
        if not terms and niche:
            terms, owner = [niche], {niche.casefold(): None}
        return terms[:MAX_SEARCH_TERMS_PER_REFRESH], owner

    @staticmethod
    def _popular_plan(categories: list[ProjectCategory], niche: str) -> list[tuple[str | None, str]]:
        """(pilar, categoria do YouTube) do Em Alta. Sem categoria identificável não há Em Alta: o Em Alta da
        plataforma inteira não é ideia do nicho do canal."""
        plan: list[tuple[str | None, str]] = []
        seen: set[str] = set()
        for cat in categories:
            yt = youtube_category_for(cat.name, *cat.queries)
            if yt and yt not in seen:
                seen.add(yt)
                plan.append((cat.id, yt))
        if not plan:
            yt = youtube_category_for(niche)
            if yt:
                plan.append((None, yt))
        return plan[:MAX_POPULAR_CATEGORIES]

    def _not_searched_recently(self, project_id: str, terms: list[str]) -> list[str]:
        """Remove os termos já buscados dentro do intervalo mínimo: repetir o clique não repete a conta de cota."""
        repo = getattr(self.ingest, "trends_repo", None)
        if not terms or repo is None:
            return list(terms)
        since = self.clock() - SEARCH_COOLDOWN
        fresh = {rec.topic.casefold() for rec in repo.list(project_id, since=since)
                 if rec.source_name == SEARCH_SOURCE and rec.observed_at >= since}
        return [term for term in terms if term.casefold() not in fresh]
