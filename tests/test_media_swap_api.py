"""W4.4 — rotas HTTP de mídia por cena (listar candidatos e aplicar a escolha).

Testa o contrato da rota com casos de uso falsos: o mapeamento HTTP não depende de banco nem
de provedor. A recusa por licença e o conflito de vínculo chegam como erro de negócio, nunca 500.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.studio.api.routes import make_router  # noqa: E402
from app.studio.application.media import (  # noqa: E402
    AssetRefused, SceneCandidates, SceneMediaRefused, SceneMediaResult, SceneNotFound,
)
from app.studio.application.ports import MediaCandidate  # noqa: E402
from app.studio.domain.contracts import Asset  # noqa: E402

V = "a" * 32
SCENE = "b" * 32
ASSET_ID = "c" * 32


def candidate(**kw):
    base = dict(license="Pexels License", source_url="https://www.pexels.com/photo/9/",
                url="https://images.pexels.com/photos/9/p.jpg", attribution="Foto de Alguém no Pexels", media_id="9")
    base.update(kw)
    return MediaCandidate(**base)


def asset():
    return Asset(id=ASSET_ID, kind="image", cache_key="k", path="cache/k.png", provider="fake", model="m",
                 license="CC0", attribution="", source_url="https://x.example/a")


class _ListCandidates:
    def __init__(self, result):
        self.result, self.calls = result, []

    def execute(self, video_id, scene_id):
        self.calls.append((video_id, scene_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Swap:
    def __init__(self, result):
        self.result, self.calls = result, []

    def execute(self, video_id, scene_id, *, asset_id=None, candidate=None, expected_asset_id=None,
                expected_version=None):
        self.calls.append((video_id, scene_id, asset_id, candidate, expected_asset_id, expected_version))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Media:
    def __init__(self, list_candidates=None, swap=None):
        self.list_candidates, self.swap = list_candidates, swap


class _UseCases:
    def __init__(self, media):
        self.media = media


def client(media):
    app = FastAPI()
    app.include_router(make_router(lambda: _UseCases(media), lambda: True))
    return TestClient(app, headers={"Authorization": "Bearer test-worker-token"})


def test_list_candidates_returns_the_search_payload():
    found = SceneCandidates(scene_id=SCENE, query="wide stage", candidates=(candidate(),))
    listing = _ListCandidates(found)
    response = client(_Media(list_candidates=listing)).get(f"/studio/videos/{V}/scenes/{SCENE}/media/candidates")
    assert response.status_code == 200
    body = response.json()
    assert body["scene_id"] == SCENE and body["query"] == "wide stage"
    assert body["candidates"][0]["license"] == "Pexels License"
    assert body["candidates"][0]["url"] == "https://images.pexels.com/photos/9/p.jpg"
    assert listing.calls == [(V, SCENE)]


def test_list_candidates_without_search_provider_is_503():
    response = client(_Media(list_candidates=None)).get(f"/studio/videos/{V}/scenes/{SCENE}/media/candidates")
    assert response.status_code == 503


def test_swap_accepts_a_candidate_and_returns_the_new_asset():
    swap = _Swap(SceneMediaResult(scene_id=SCENE, asset=asset(), changed=True, reason="swapped"))
    response = client(_Media(swap=swap)).post(
        f"/studio/videos/{V}/scenes/{SCENE}/media",
        json={"candidate": {"license": "Pexels License", "source_url": "https://www.pexels.com/photo/9/",
                            "url": "https://images.pexels.com/photos/9/p.jpg",
                            "attribution": "Foto de Alguém no Pexels", "media_id": "9"}})
    assert response.status_code == 200
    body = response.json()
    assert body["changed"] is True and body["asset"]["id"] == ASSET_ID
    video_id, scene_id, asset_id, chosen, _, _ = swap.calls[0]
    assert (video_id, scene_id, asset_id) == (V, SCENE, None)
    assert isinstance(chosen, MediaCandidate) and chosen.license == "Pexels License"


def test_swap_accepts_an_existing_asset():
    swap = _Swap(SceneMediaResult(scene_id=SCENE, asset=asset(), changed=True))
    response = client(_Media(swap=swap)).post(
        f"/studio/videos/{V}/scenes/{SCENE}/media", json={"asset_id": ASSET_ID})
    assert response.status_code == 200
    assert swap.calls[0][2] == ASSET_ID


def test_swap_without_choice_keeps_the_current_media():
    swap = _Swap(SceneMediaResult(scene_id=SCENE, asset=asset(), changed=False, reason="no_candidate"))
    response = client(_Media(swap=swap)).post(f"/studio/videos/{V}/scenes/{SCENE}/media", json={})
    assert response.status_code == 200 and response.json()["changed"] is False


def test_swap_with_a_license_less_candidate_is_422_not_500():
    swap = _Swap(SceneMediaResult(scene_id=SCENE, asset=asset(), changed=True))
    response = client(_Media(swap=swap)).post(
        f"/studio/videos/{V}/scenes/{SCENE}/media",
        json={"candidate": {"license": "", "source_url": "https://www.pexels.com/photo/9/",
                            "url": "https://images.pexels.com/photos/9/p.jpg",
                            "attribution": "Foto de Alguém no Pexels"}})
    assert response.status_code == 422
    assert swap.calls == []  # o candidato inválido nem chega ao caso de uso


@pytest.mark.parametrize("error,status", [
    (SceneNotFound(SCENE), 404),
    (SceneMediaRefused("choose either a candidate or an asset"), 422),
    (AssetRefused("candidate without a registered license"), 502),
])
def test_swap_business_errors_never_become_500(error, status):
    response = client(_Media(swap=_Swap(error))).post(
        f"/studio/videos/{V}/scenes/{SCENE}/media", json={"asset_id": ASSET_ID})
    assert response.status_code == status


def test_swap_invalid_id_is_422():
    response = client(_Media(swap=_Swap(SceneMediaResult(scene_id=SCENE, asset=asset(), changed=True)))).post(
        "/studio/videos/not-an-id/scenes/" + SCENE + "/media", json={"asset_id": ASSET_ID})
    assert response.status_code == 422
