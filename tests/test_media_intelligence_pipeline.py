"""Testes de integração do pipeline de inteligência de mídia (Onda 2 - Task 6).

Cobre:
1. MultiProviderMediaSearch: agregação resiliente de candidatos de múltiplos provedores.
2. ListSceneCandidates: aplicação de MediaRanker com visual_intent e target_format.
3. Settings: leitura e parsing de PIXABAY_API_KEY.
4. Catálogo de provedores: registro de pixabay como provedor SEARCH.
5. docker-compose.yml: declaração da variável PIXABAY_API_KEY.
6. Wiring da composição: instanciação de MultiProviderMediaSearch quando múltiplas chaves existem.
"""
from decimal import Decimal
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.media_multi import MultiProviderMediaFetcher, MultiProviderMediaSearch
from app.studio.adapters.media_pexels import PexelsMediaFetcher
from app.studio.adapters.media_pixabay import PixabayMediaFetcher, trusted_pixabay_url
from app.studio.application.media import ListSceneCandidates, SceneCandidates, SwapSceneMedia
from app.studio.application.ports import ImageResult, MediaCandidate, MediaFetcher, MediaSearch, ModelUnavailable
from app.studio.composition import Settings, _provider_implementations
from app.studio.domain.contracts import Asset, AssetKind, Scene, Script, Video, VideoFormat, VideoStatus
from app.studio.domain.provider import CostKind, ProviderKind


class FakeSearchProvider:
    def __init__(self, name: str, candidates: list[MediaCandidate] | None = None, fail: bool = False):
        self.name = name
        self.candidates = candidates if candidates is not None else []
        self.fail = fail
        self.calls: list[tuple[str, str, str, int]] = []

    def search(self, query: str, *, media_type: str = "image", orientation: str = "landscape",
               per_page: int = 10) -> list[MediaCandidate]:
        self.calls.append((query, media_type, orientation, per_page))
        if self.fail:
            raise ModelUnavailable(f"Provider {self.name} failed")
        return list(self.candidates)


def _sample_candidate(
    media_id: str,
    *,
    media_type: str = "image",
    width: int = 1920,
    height: int = 1080,
    tags: tuple[str, ...] = (),
    url: str = "",
    source_url: str = "",
) -> MediaCandidate:
    return MediaCandidate(
        license="Test License",
        source_url=source_url or f"https://example.com/source/{media_id}",
        url=url or f"https://images.example.com/{media_id}.jpg",
        attribution=f"Photo {media_id}",
        media_id=media_id,
        media_type=media_type,
        width=width,
        height=height,
        cost_usd=Decimal("0"),
        duration_s=10.0 if media_type == "video" else None,
        tags=tags,
    )


# ---------------------------------------------------------------------------
# 1. MultiProviderMediaSearch
# ---------------------------------------------------------------------------


def test_multi_provider_satisfies_media_search_protocol():
    multi = MultiProviderMediaSearch([])
    assert isinstance(multi, MediaSearch)
    assert multi.name == "multi"


def test_multi_provider_aggregates_candidates_from_all_providers():
    cand1 = _sample_candidate("p1-1", tags=("cyberpunk",))
    cand2 = _sample_candidate("p2-1", tags=("neon",))
    p1 = FakeSearchProvider("provider1", [cand1])
    p2 = FakeSearchProvider("provider2", [cand2])

    multi = MultiProviderMediaSearch([p1, p2])
    results = multi.search("tokyo night", media_type="image", orientation="portrait", per_page=5)

    assert len(results) == 2
    assert results[0].media_id == "p1-1"
    assert results[1].media_id == "p2-1"
    assert p1.calls == [("tokyo night", "image", "portrait", 5)]
    assert p2.calls == [("tokyo night", "image", "portrait", 5)]


def test_multi_provider_handles_failing_provider_gracefully():
    cand2 = _sample_candidate("p2-1", tags=("nature",))
    failing = FakeSearchProvider("broken", fail=True)
    working = FakeSearchProvider("working", [cand2])

    multi = MultiProviderMediaSearch([failing, working])
    results = multi.search("forest", media_type="image", orientation="landscape", per_page=10)

    assert len(results) == 1
    assert results[0].media_id == "p2-1"


def test_multi_provider_all_failing_returns_empty_list():
    p1 = FakeSearchProvider("p1", fail=True)
    p2 = FakeSearchProvider("p2", fail=True)

    multi = MultiProviderMediaSearch([p1, p2])
    assert multi.search("ocean") == []


def test_multi_provider_empty_query_returns_empty_without_calling_providers():
    p1 = FakeSearchProvider("p1", [_sample_candidate("1")])
    multi = MultiProviderMediaSearch([p1])

    assert multi.search("") == []
    assert multi.search("   ") == []
    assert len(p1.calls) == 0


# ---------------------------------------------------------------------------
# 2. ListSceneCandidates com MediaRanker
# ---------------------------------------------------------------------------


class FakeVideoRepo:
    def __init__(self, video: Video):
        self._video = video

    def get_video(self, video_id: str) -> Video | None:
        if self._video.id == video_id:
            return self._video
        return None


class FakeScriptRepo:
    def __init__(self, scenes: list[Scene]):
        self._scenes = scenes

    def scenes(self, video_id: str) -> list[Scene]:
        return self._scenes


def test_list_scene_candidates_ranks_by_format_and_visual_intent():
    # Vídeo em formato vertical (9:16 / short)
    video = Video(
        id="vid-1",
        project_id="proj-1",
        topic="Tokyo Cyberpunk",
        format=VideoFormat.short,
        status=VideoStatus.STORYBOARDED,
    )
    # Cena com visual_intent e search_queries opcionais
    scene = Scene(
        id="sc-1",
        video_id="vid-1",
        idx=0,
        narration="As luzes de neon iluminam a noite de Tokyo em alta velocidade.",
        caption="Tokyo a noite",
        image_prompt="rua futurista iluminada por luzes de neon cinematografica",
    )
    # Anexar visual_intent dinamicamente como produzido pelo diretor criativo
    object.__setattr__(scene, "visual_intent", "neon cyberpunk night city aesthetic")

    # Candidato horizontal genérico (sem match de formato vertical nem tags)
    cand_horiz = _sample_candidate("cand-horiz", width=1920, height=1080, tags=("nature", "tree"))
    # Candidato vertical relevante (match de formato 9:16 e tags de neon/cyberpunk)
    cand_vert = _sample_candidate("cand-vert", width=1080, height=1920, tags=("neon", "cyberpunk", "city"))

    search = FakeSearchProvider("mock", [cand_horiz, cand_vert])
    use_case = ListSceneCandidates(FakeVideoRepo(video), FakeScriptRepo([scene]), search)

    result = use_case.execute("vid-1", "sc-1", per_page=10)
    assert isinstance(result, SceneCandidates)
    assert len(result.candidates) == 2
    # cand_vert deve vir em primeiro lugar devido ao ranking (orientação vertical + tags)
    assert result.candidates[0].media_id == "cand-vert"
    assert result.candidates[1].media_id == "cand-horiz"


def test_list_scene_candidates_ranks_horizontal_first_for_long_format():
    # Vídeo em formato horizontal (16:9 / long)
    video = Video(
        id="vid-2",
        project_id="proj-2",
        topic="Documentary",
        format=VideoFormat.long,
        status=VideoStatus.STORYBOARDED,
    )
    scene = Scene(
        id="sc-2",
        video_id="vid-2",
        idx=0,
        narration="Documentario historico sobre grandes cidades.",
        caption="Cidades históricas",
        image_prompt="rua antiga com arquitetura classica",
    )
    cand_horiz = _sample_candidate("cand-horiz", width=1920, height=1080, tags=("cidade", "arquitetura"))
    cand_vert = _sample_candidate("cand-vert", width=1080, height=1920, tags=("cidade", "arquitetura"))

    search = FakeSearchProvider("mock", [cand_vert, cand_horiz])
    use_case = ListSceneCandidates(FakeVideoRepo(video), FakeScriptRepo([scene]), search)

    result = use_case.execute("vid-2", "sc-2", per_page=10)
    assert len(result.candidates) == 2
    # No formato 16:9, o horizontal deve pontuar mais
    assert result.candidates[0].media_id == "cand-horiz"
    assert result.candidates[1].media_id == "cand-vert"


def test_list_scene_candidates_empty_search_returns_empty_tuple():
    video = Video(
        id="vid-3",
        project_id="proj-3",
        topic="Empty test",
        format=VideoFormat.short,
        status=VideoStatus.STORYBOARDED,
    )
    scene = Scene(
        id="sc-3",
        video_id="vid-3",
        idx=0,
        narration="Sem nenhum candidato encontrado no banco.",
        caption="Vazio",
        image_prompt="cena de teste vazia",
    )
    search = FakeSearchProvider("mock", [])
    use_case = ListSceneCandidates(FakeVideoRepo(video), FakeScriptRepo([scene]), search)

    result = use_case.execute("vid-3", "sc-3")
    assert result.candidates == ()


# ---------------------------------------------------------------------------
# 3. Settings: parsing de PIXABAY_API_KEY
# ---------------------------------------------------------------------------


def test_settings_parses_pixabay_api_key():
    s = Settings.from_env({"PIXABAY_API_KEY": "px-test-token-123"})
    assert s.pixabay_key == "px-test-token-123"

    s_empty = Settings.from_env({})
    assert s_empty.pixabay_key == ""

    s_strip = Settings.from_env({"PIXABAY_API_KEY": "   token-with-spaces   "})
    assert s_strip.pixabay_key == "token-with-spaces"


# ---------------------------------------------------------------------------
# 4. Providers: inclusão de Pixabay no catálogo
# ---------------------------------------------------------------------------


def test_providers_catalog_includes_pixabay_search():
    implementations = _provider_implementations(Settings(pixabay_key="key-pixabay"))
    pixabay_impls = [i for i in implementations if i.kind is ProviderKind.SEARCH and i.name == "pixabay"]
    assert len(pixabay_impls) == 1
    impl = pixabay_impls[0]
    assert impl.capabilities == ("search.media",)
    assert impl.cost.kind is CostKind.FREE
    assert impl.validated is True
    assert impl.reason is None


def test_providers_catalog_marks_pixabay_unavailable_without_key():
    implementations = _provider_implementations(Settings(pixabay_key=""))
    pixabay_impls = [i for i in implementations if i.kind is ProviderKind.SEARCH and i.name == "pixabay"]
    assert len(pixabay_impls) == 1
    impl = pixabay_impls[0]
    assert impl.validated is False
    assert impl.reason == "PIXABAY_API_KEY ausente"


# ---------------------------------------------------------------------------
# 5. docker-compose.yml declara PIXABAY_API_KEY
# ---------------------------------------------------------------------------


def test_docker_compose_declares_pixabay_api_key():
    compose_path = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    assert compose_path.exists()
    content = compose_path.read_text(encoding="utf-8")
    assert "PIXABAY_API_KEY: ${PIXABAY_API_KEY:-}" in content


# ---------------------------------------------------------------------------
# 6. Deduplicação com used_media_ids e queries complementares
# ---------------------------------------------------------------------------


def test_list_scene_candidates_applies_repetition_penalty_for_used_media_ids():
    video = Video(
        id="vid-dedup",
        project_id="proj-1",
        topic="Dedup test",
        format=VideoFormat.long,
        status=VideoStatus.STORYBOARDED,
    )
    # Cena 0 já usa 'cand-1' como asset_id
    scene0 = Scene(
        id="sc-0",
        video_id="vid-dedup",
        idx=0,
        narration="Primeira cena com asset vinculado.",
        image_prompt="cena de teste 1",
        asset_id="cand-1",
    )
    # Cena 1 sendo avaliada
    scene1 = Scene(
        id="sc-1",
        video_id="vid-dedup",
        idx=1,
        narration="Segunda cena buscando candidatos.",
        image_prompt="cena de teste 2",
    )
    cand1 = _sample_candidate("cand-1", width=1920, height=1080)
    cand2 = _sample_candidate("cand-2", width=1920, height=1080)

    # Fake provider devolve cand1 primeiro, depois cand2
    search = FakeSearchProvider("mock", [cand1, cand2])
    use_case = ListSceneCandidates(FakeVideoRepo(video), FakeScriptRepo([scene0, scene1]), search)

    result = use_case.execute("vid-dedup", "sc-1", per_page=10)
    # cand-1 deve receber penalidade de repetição (-50 pts), então cand-2 deve vir em 1º lugar!
    assert len(result.candidates) == 2
    assert result.candidates[0].media_id == "cand-2"
    assert result.candidates[1].media_id == "cand-1"


def test_list_scene_candidates_aggregates_scene_search_queries_and_limits_per_page():
    video = Video(
        id="vid-multi-q",
        project_id="proj-1",
        topic="Multi queries",
        format=VideoFormat.short,
        status=VideoStatus.STORYBOARDED,
    )
    scene = Scene(
        id="sc-multi-q",
        video_id="vid-multi-q",
        idx=0,
        narration="Cena com termos de busca múltiplos.",
        image_prompt="prompt principal longo sem estilo",
        search_queries=["termo extra 1", "termo extra 2"],
    )

    class QuerySpecificSearch:
        name = "query-specific"

        def search(self, query: str, *, media_type: str = "image", orientation: str = "landscape",
                   per_page: int = 10) -> list[MediaCandidate]:
            if "prompt principal" in query:
                return [_sample_candidate(f"main-{i}", width=1080, height=1920) for i in range(3)]
            if "termo extra 1" in query:
                return [_sample_candidate(f"extra1-{i}", width=1080, height=1920) for i in range(3)]
            if "termo extra 2" in query:
                return [_sample_candidate(f"extra2-{i}", width=1080, height=1920) for i in range(3)]
            return []

    use_case = ListSceneCandidates(FakeVideoRepo(video), FakeScriptRepo([scene]), QuerySpecificSearch())

    # Limitado a 5 por página (mesmo tendo 9 candidatos agregados no total)
    result = use_case.execute("vid-multi-q", "sc-multi-q", per_page=5)
    assert len(result.candidates) == 5
    # Todos os candidatos retornados pertencem ao conjunto agregado
    cand_ids = {c.media_id for c in result.candidates}
    assert any("main" in cid for cid in cand_ids)
    assert any("extra" in cid for cid in cand_ids)


# ---------------------------------------------------------------------------
# 7. PixabayMediaFetcher e MultiProviderMediaFetcher
# ---------------------------------------------------------------------------


def test_pixabay_media_fetcher_downloads_image_safely():
    import httpx

    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"pixabay-image-bytes")
    )
    fetcher = PixabayMediaFetcher(transport=transport)
    candidate = _sample_candidate("pix-1", url="https://pixabay.com/get/test.jpg")

    result = fetcher.fetch(candidate)
    assert isinstance(result, ImageResult)
    assert result.data == b"pixabay-image-bytes"
    assert result.mime == "image/jpeg"
    assert result.license == "Test License"


def test_pixabay_media_fetcher_rejects_untrusted_host():
    fetcher = PixabayMediaFetcher()
    candidate = _sample_candidate("bad-1", url="https://malicious-site.com/evil.jpg")

    with pytest.raises(ModelUnavailable, match="trusted Pixabay host"):
        fetcher.fetch(candidate)


def test_multi_provider_media_fetcher_dispatches_by_domain():
    import httpx

    p_pexels = PexelsMediaFetcher(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"pexels-data")
        )
    )

    p_pixabay = PixabayMediaFetcher(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"pixabay-data")
        )
    )

    multi_fetcher = MultiProviderMediaFetcher([p_pexels, p_pixabay])

    cand_pix = _sample_candidate("pix-10", url="https://pixabay.com/get/10.jpg")
    res_pix = multi_fetcher.fetch(cand_pix)
    assert res_pix.data == b"pixabay-data"

    cand_pex = _sample_candidate("pex-20", url="https://images.pexels.com/photos/20/p.jpg", source_url="https://www.pexels.com/photo/20/")
    res_pex = multi_fetcher.fetch(cand_pex)
    assert res_pex.data == b"pexels-data"


def test_swap_scene_media_materializes_pixabay_candidate_via_multi_fetcher():
    import httpx

    class FakeAssetRepo:
        def __init__(self):
            self.by_id: dict[str, Asset] = {}
            self.by_key: dict[str, Asset] = {}
            self.links: dict[str, str] = {}

        def add(self, asset: Asset) -> Asset:
            self.by_key[asset.cache_key] = self.by_id[asset.id] = asset
            return asset

        def get(self, asset_id: str) -> Asset | None:
            return self.by_id.get(asset_id)

        def find(self, cache_key: str) -> Asset | None:
            return self.by_key.get(cache_key)

        def swap_scene_asset(self, video_id: str, scene_id: str, asset_id: str, expected_asset_id=None) -> bool:
            self.links[scene_id] = asset_id
            return True

    class FakeAssetStore:
        def put(self, key: str, data: bytes, aspect: str) -> str:
            return f"storage/{key}.jpg"

    class FakeScriptRepoForSwap:
        def __init__(self, scenes: list[Scene]):
            self._scenes = scenes

        def scenes(self, video_id: str) -> list[Scene]:
            return self._scenes

        def latest(self, video_id: str) -> Script | None:
            return Script(id="scr-1", video_id=video_id, version=1, text="roteiro")

    video = Video(id="v1", project_id="p1", topic="Swap test", format=VideoFormat.short, status=VideoStatus.STORYBOARDED)
    scene = Scene(id="s1", video_id="v1", idx=0, narration="Cena para swap de teste valida", image_prompt="prompt valido com mais de dez caracteres")

    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"swap-pixabay-data")
    )
    pix_fetcher = PixabayMediaFetcher(transport=transport)
    multi_fetcher = MultiProviderMediaFetcher([pix_fetcher])

    assets = FakeAssetRepo()
    store = FakeAssetStore()
    scripts = FakeScriptRepoForSwap([scene])

    swap_use_case = SwapSceneMedia(FakeVideoRepo(video), scripts, assets, store, fetcher=multi_fetcher)
    cand = _sample_candidate("pix-swap-1", url="https://pixabay.com/get/swap.jpg")

    result = swap_use_case.execute("v1", "s1", candidate=cand)
    assert result.changed is True
    assert result.asset is not None
    assert assets.links["s1"] == result.asset.id

