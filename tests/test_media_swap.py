"""W4.4 (EDIT-03/VE-06) — troca de mídia de UMA cena com candidatos.

Prova o contrato do caso de uso sem banco: listar candidatos da cena, aplicar um candidato
(materializado pelo fetcher) ou um asset existente, recusar candidato sem licença e manter a
mídia atual quando não há escolha. A troca não pode tocar nas outras cenas.

A invalidação seletiva (só a cena trocada + final) é provada em ``test_render_regeneration.py``
e ``test_render_cache.py``, porque é uma propriedade do grafo do Render Plan, não da persistência.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import StateConflict, VideoNotFound  # noqa: E402
from app.studio.application.media import (  # noqa: E402
    AssetRefused, ListSceneCandidates, SceneMediaRefused, SceneNotFound, SwapSceneMedia,
)
from app.studio.application.ports import ImageResult, MediaCandidate  # noqa: E402
from app.studio.domain.contracts import Asset, Scene, Script, UsageEntry, Video, VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.media import IMAGE_STYLE  # noqa: E402

V, P = "v" * 32, "p" * 32
PROMPTS = ("wide stage with colorful lights", "crowd silhouettes under neon lights", "aerial city canals at night")


def scene_id(idx: int) -> str:
    return f"{idx:032x}"


class Videos:
    def __init__(self, status=VideoStatus.ASSETS_READY, fmt=VideoFormat.short):
        self.status, self.fmt, self.exists = status, fmt, True

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic="ADE 2026", format=self.fmt, status=self.status) if self.exists else None

    def transition_video(self, video_id, expected, new):
        if self.status != expected:
            return False
        self.status = new
        return True


class Assets:
    def __init__(self):
        self.by_id, self.by_key = {}, {}
        self.links = {}
        self.swap_calls, self.refuse_swap = [], False

    def find(self, cache_key):
        return self.by_key.get(cache_key)

    def add(self, asset):
        existing = self.by_key.get(asset.cache_key)
        if existing:
            return existing
        self.by_key[asset.cache_key] = self.by_id[asset.id] = asset
        return asset

    def get(self, asset_id):
        return self.by_id.get(asset_id)

    def swap_scene_asset(self, video_id, scene_id, asset_id, expected_asset_id):
        self.swap_calls.append((scene_id, asset_id, expected_asset_id))
        if self.refuse_swap:
            return False
        idx = int(scene_id, 16)
        if self.links.get(idx) != expected_asset_id:
            return False
        self.links[idx] = asset_id
        return True


class Scripts:
    def __init__(self, assets, prompts=PROMPTS, version=1):
        self.assets, self.prompts, self.version = assets, list(prompts), version

    def scenes(self, video_id):
        return [Scene(id=scene_id(i), video_id=V, idx=i, narration=f"Narração {i} válida", image_prompt=p,
                      claim_ids=["c"], asset_id=self.assets.links.get(i)) for i, p in enumerate(self.prompts)]

    def latest(self, video_id):
        return Script(id="s" * 32, video_id=V, version=self.version, text="texto") if self.version else None


class Store:
    def __init__(self):
        self.puts = []

    def put(self, cache_key, data, aspect):
        self.puts.append((cache_key, aspect))
        return f"cache/{cache_key[:2]}/{cache_key}.png"


class Search:
    name = "fake-search"

    def __init__(self, candidates=()):
        self.candidates, self.queries = list(candidates), []

    def search(self, query, *, media_type="image", orientation="landscape", per_page=10):
        self.queries.append((query, media_type, orientation, per_page))
        return list(self.candidates)


class Fetcher:
    name = "fake-search"

    def __init__(self, license="CC0", mime="image/png"):
        self.license, self.mime, self.calls = license, mime, 0

    def fetch(self, candidate):
        self.calls += 1
        return ImageResult(data=b"candidate", mime=self.mime,
                           usage=UsageEntry(step="image", provider="fake", model="m", cost_usd=0.0),
                           license=self.license, attribution=candidate.attribution, source_url=candidate.source_url)


def candidate(**kw):
    base = dict(license="CC0", source_url="https://www.pexels.com/photo/9/",
                url="https://images.pexels.com/photos/9/p.jpg", attribution="Foto de Alguém no Pexels", media_id="9")
    base.update(kw)
    return MediaCandidate(**base)


def asset(asset_id: str, **kw):
    base = dict(id=asset_id, kind="image", cache_key=f"key-{asset_id}", path=f"cache/{asset_id}.png",
                provider="fake", model="m", license="CC0", attribution="", source_url="https://x.example/a")
    base.update(kw)
    return Asset(**base)


def world(**kw):
    assets = Assets()
    return {"videos": Videos(**kw), "assets": assets, "scripts": Scripts(assets), "store": Store()}


def seed(w, count=3):
    """Cada cena já vinculada a um asset próprio; devolve a lista de ids por índice."""
    ids = []
    for idx in range(count):
        item = asset(f"{idx + 1:032x}")
        w["assets"].add(item)
        w["assets"].links[idx] = item.id
        ids.append(item.id)
    return ids


# ---------- listar candidatos ----------
def test_list_candidates_uses_the_scene_prompt_and_short_orientation():
    w = world()
    found = Search([candidate()])
    result = ListSceneCandidates(w["videos"], w["scripts"], found).execute(V, scene_id(1))
    assert result.scene_id == scene_id(1) and result.candidates == (candidate(),)
    query, media_type, orientation, _ = found.queries[0]
    assert query == PROMPTS[1] and not query.endswith(IMAGE_STYLE["9:16"])
    assert (media_type, orientation) == ("image", "portrait")  # short = 9:16


def test_list_candidates_uses_landscape_for_long_form():
    w = world(fmt=VideoFormat.long)
    found = Search([])
    ListSceneCandidates(w["videos"], w["scripts"], found).execute(V, scene_id(0))
    assert found.queries[0][2] == "landscape"


def test_list_candidates_empty_is_the_fallback_signal():
    w = world()
    result = ListSceneCandidates(w["videos"], w["scripts"], Search([])).execute(V, scene_id(0))
    assert result.candidates == ()  # sem candidato: a cena mantém a mídia atual


def test_list_candidates_unknown_scene_and_video():
    w = world()
    with pytest.raises(SceneNotFound):
        ListSceneCandidates(w["videos"], w["scripts"], Search()).execute(V, scene_id(9))
    w["videos"].exists = False
    with pytest.raises(VideoNotFound):
        ListSceneCandidates(w["videos"], w["scripts"], Search()).execute(V, scene_id(0))


# ---------- trocar mídia ----------
def test_swap_to_an_existing_asset_touches_only_the_target_scene():
    w = world()
    seeded = seed(w)
    replacement = asset("f" * 32)
    w["assets"].add(replacement)
    result = SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"]).execute(
        V, scene_id(1), asset_id=replacement.id)
    assert result.changed is True and result.asset.id == replacement.id
    assert w["assets"].links == {0: seeded[0], 1: replacement.id, 2: seeded[2]}  # demais cenas intactas
    assert w["assets"].swap_calls == [(scene_id(1), replacement.id, seeded[1])]


def test_swap_with_a_candidate_materializes_the_asset_and_links_the_scene():
    w = world()
    seeded = seed(w)
    fetcher = Fetcher()
    chosen = candidate()
    result = SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"], fetcher=fetcher).execute(
        V, scene_id(1), candidate=chosen)
    assert fetcher.calls == 1 and len(w["store"].puts) == 1
    assert result.asset.license == "CC0" and result.asset.source_url == chosen.source_url
    assert result.asset.provider == "fake-search" and result.asset.kind.value == "image"
    assert w["assets"].links == {0: seeded[0], 1: result.asset.id, 2: seeded[2]}


@pytest.mark.parametrize("license", ["", "   "])
def test_candidate_without_license_is_refused_and_nothing_changes(license):
    w = world()
    seeded = seed(w)
    with pytest.raises(AssetRefused, match="license"):
        SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"], fetcher=Fetcher(license=license)).execute(
            V, scene_id(1), candidate=candidate())
    assert w["store"].puts == [] and w["assets"].swap_calls == []
    assert w["assets"].links == {0: seeded[0], 1: seeded[1], 2: seeded[2]}


def test_swap_without_a_choice_keeps_the_current_media():
    w = world()
    seeded = seed(w)
    result = SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"]).execute(V, scene_id(1))
    assert result.changed is False and result.reason == "no_candidate"
    assert result.asset.id == seeded[1]
    assert w["assets"].swap_calls == [] and w["assets"].links[1] == seeded[1]


def test_swap_is_idempotent_for_the_same_asset():
    w = world()
    seed(w)
    replacement = asset("f" * 32)
    w["assets"].add(replacement)
    swap = SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"])
    first = swap.execute(V, scene_id(1), asset_id=replacement.id)
    second = swap.execute(V, scene_id(1), asset_id=replacement.id)
    assert first.changed is True and second.changed is False and second.reason == "already-linked"
    assert len(w["assets"].swap_calls) == 1  # repetir não regrava


def test_swap_refuses_when_the_link_changed_underneath():
    w = world()
    seed(w)
    replacement = asset("f" * 32)
    w["assets"].add(replacement)
    w["assets"].refuse_swap = True
    with pytest.raises(StateConflict, match="changed"):
        SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"]).execute(
            V, scene_id(1), asset_id=replacement.id)


def test_swap_refuses_candidate_and_asset_together():
    w = world()
    seed(w)
    with pytest.raises(SceneMediaRefused):
        SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"]).execute(
            V, scene_id(1), asset_id="f" * 32, candidate=candidate())


def test_swap_refuses_a_candidate_without_a_fetcher():
    w = world()
    seed(w)
    with pytest.raises(SceneMediaRefused):
        SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"]).execute(
            V, scene_id(1), candidate=candidate())


def test_swap_unknown_scene_and_unknown_asset():
    w = world()
    seed(w)
    with pytest.raises(SceneNotFound):
        SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"]).execute(V, scene_id(9), asset_id="f" * 32)
    with pytest.raises(SceneMediaRefused):
        SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"]).execute(V, scene_id(0), asset_id="f" * 32)


def test_swap_refuses_a_stale_script_version():
    w = world()
    seed(w)
    w["scripts"].version = 2
    replacement = asset("f" * 32)
    w["assets"].add(replacement)
    with pytest.raises(StateConflict, match="script version"):
        SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"]).execute(
            V, scene_id(1), asset_id=replacement.id, expected_version=1)
    assert w["assets"].swap_calls == []  # nada gravado


def test_swap_accepts_the_current_script_version():
    w = world()
    seed(w)
    replacement = asset("f" * 32)
    w["assets"].add(replacement)
    result = SwapSceneMedia(w["videos"], w["scripts"], w["assets"], w["store"]).execute(
        V, scene_id(1), asset_id=replacement.id, expected_version=1)
    assert result.changed is True and w["assets"].links[1] == replacement.id

