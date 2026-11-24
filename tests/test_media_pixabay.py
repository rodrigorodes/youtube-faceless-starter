"""Testes para o adaptador Pixabay de imagens e vídeos (Task 5 de Onda 2)."""
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.media_pixabay import PixabayMediaSearch  # noqa: E402
from app.studio.application.config import ProviderNotFound  # noqa: E402
from app.studio.application.ports import MediaCandidate, MediaSearch, ModelUnavailable  # noqa: E402

SAMPLE_IMAGE_HIT = {
    "id": 195893,
    "pageURL": "https://pixabay.com/photos/blossom-bloom-flower-195893/",
    "type": "photo",
    "tags": "blossom, bloom, flower",
    "previewURL": "https://cdn.pixabay.com/photo/preview.jpg",
    "webformatURL": "https://pixabay.com/photo/webformat.jpg",
    "largeImageURL": "https://pixabay.com/photo/large.jpg",
    "imageWidth": 4000,
    "imageHeight": 2250,
    "user": "FlowerPhotographer",
}

SAMPLE_VIDEO_HIT = {
    "id": 12345,
    "pageURL": "https://pixabay.com/videos/forest-drone-12345/",
    "type": "film",
    "tags": "forest, drone, 4k",
    "duration": 18,
    "videos": {
        "large": {
            "url": "https://cdn.pixabay.com/video/large.mp4",
            "width": 1920,
            "height": 1080,
            "size": 12345678,
        },
        "medium": {
            "url": "https://cdn.pixabay.com/video/medium.mp4",
            "width": 1280,
            "height": 720,
            "size": 6543210,
        },
        "small": {
            "url": "https://cdn.pixabay.com/video/small.mp4",
            "width": 960,
            "height": 540,
            "size": 3210987,
        },
    },
    "user": "DronePilot",
}


def _pixabay_adapter(handler, key="TEST_KEY", **kwargs):
    return PixabayMediaSearch(
        api_key=key,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_init_requires_key_and_license():
    with pytest.raises(ProviderNotFound, match="PIXABAY_API_KEY"):
        PixabayMediaSearch(api_key="")

    with pytest.raises(ProviderNotFound, match="PIXABAY_API_KEY"):
        PixabayMediaSearch(api_key="   ")

    with pytest.raises(ProviderNotFound, match="known license"):
        PixabayMediaSearch(api_key="valid_key", license_text="")

    adapter = PixabayMediaSearch(api_key="valid_key")
    assert adapter.name == "pixabay"


def test_image_search_returns_candidates_with_tags_and_attribution():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 1, "totalHits": 1, "hits": [SAMPLE_IMAGE_HIT]})

    adapter = _pixabay_adapter(handler)
    candidates = adapter.search("flores", media_type="image", orientation="landscape", per_page=10)

    assert len(candidates) == 1
    c = candidates[0]
    assert c.media_type == "image"
    assert c.url == "https://pixabay.com/photo/large.jpg"
    assert c.source_url == "https://pixabay.com/photos/blossom-bloom-flower-195893/"
    assert c.tags == ("blossom", "bloom", "flower")
    assert c.author == "FlowerPhotographer"
    assert c.attribution == "Foto de FlowerPhotographer no Pixabay"
    assert c.width == 4000
    assert c.height == 2250
    assert c.cost_usd == Decimal("0")
    assert c.license == "Pixabay Content License"
    assert c.media_id == "195893"

    assert seen["params"]["key"] == "TEST_KEY"
    assert seen["params"]["q"] == "flores"
    assert seen["params"]["image_type"] == "photo"
    assert seen["params"]["orientation"] == "horizontal"
    assert seen["params"]["per_page"] == "10"
    assert seen["params"]["safesearch"] == "true"


def test_image_search_fallback_to_webformat():
    def handler(request: httpx.Request) -> httpx.Response:
        hit = dict(SAMPLE_IMAGE_HIT)
        hit.pop("largeImageURL", None)
        return httpx.Response(200, json={"total": 1, "totalHits": 1, "hits": [hit]})

    adapter = _pixabay_adapter(handler)
    candidates = adapter.search("flores", media_type="image")
    assert len(candidates) == 1
    assert candidates[0].url == "https://pixabay.com/photo/webformat.jpg"


def test_video_search_returns_candidates_with_duration_renditions_and_attribution():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 1, "totalHits": 1, "hits": [SAMPLE_VIDEO_HIT]})

    adapter = _pixabay_adapter(handler)
    candidates = adapter.search("floresta", media_type="video", orientation="portrait", per_page=5)

    assert len(candidates) == 1
    c = candidates[0]
    assert c.media_type == "video"
    assert c.url == "https://cdn.pixabay.com/video/large.mp4"
    assert c.source_url == "https://pixabay.com/videos/forest-drone-12345/"
    assert c.duration_s == 18.0
    assert c.tags == ("forest", "drone", "4k")
    assert c.author == "DronePilot"
    assert c.attribution == "Vídeo de DronePilot no Pixabay"
    assert c.width == 1920
    assert c.height == 1080
    assert c.cost_usd == Decimal("0")
    assert c.license == "Pixabay Content License"
    assert c.media_id == "12345"

    assert seen["params"]["key"] == "TEST_KEY"
    assert seen["params"]["q"] == "floresta"
    assert seen["params"]["video_type"] == "all"
    assert seen["params"]["orientation"] == "vertical"
    assert seen["params"]["per_page"] == "5"
    assert seen["params"]["safesearch"] == "true"


def test_video_search_rendition_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        hit = {
            **SAMPLE_VIDEO_HIT,
            "videos": {
                "small": {
                    "url": "https://cdn.pixabay.com/video/small.mp4",
                    "width": 960,
                    "height": 540,
                }
            },
        }
        return httpx.Response(200, json={"total": 1, "totalHits": 1, "hits": [hit]})

    adapter = _pixabay_adapter(handler)
    candidates = adapter.search("floresta", media_type="video")
    assert len(candidates) == 1
    assert candidates[0].url == "https://cdn.pixabay.com/video/small.mp4"
    assert candidates[0].width == 960
    assert candidates[0].height == 540


def test_orientation_mapping_and_validation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"total": 0, "hits": []})

    adapter = _pixabay_adapter(handler)

    with pytest.raises(ModelUnavailable, match="orientation"):
        adapter.search("teste", orientation="square")

    with pytest.raises(ModelUnavailable, match="orientation"):
        adapter.search("teste", orientation="diagonal")


def test_invalid_media_type():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP não deveria ser chamado")

    adapter = _pixabay_adapter(handler)

    with pytest.raises(ModelUnavailable, match="supports 'image' and 'video' only"):
        adapter.search("teste", media_type="audio")


def test_per_page_validation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"total": 0, "hits": []})

    adapter = _pixabay_adapter(handler)

    with pytest.raises(ModelUnavailable, match="per_page"):
        adapter.search("teste", per_page=0)

    with pytest.raises(ModelUnavailable, match="per_page"):
        adapter.search("teste", per_page=81)

    with pytest.raises(ModelUnavailable, match="per_page"):
        adapter.search("teste", per_page=True)


def test_empty_query_returns_empty_list():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP não deveria ser chamado")

    adapter = _pixabay_adapter(handler)
    assert adapter.search("") == []
    assert adapter.search("   ") == []


def test_http_error_does_not_leak_key():
    secret_key = "MY_VERY_SECRET_PIXABAY_KEY_12345"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    adapter = _pixabay_adapter(handler, key=secret_key)
    with pytest.raises(ModelUnavailable) as exc_info:
        adapter.search("teste")

    assert secret_key not in str(exc_info.value)
    assert "Pixabay media search failed" in str(exc_info.value)


def test_rejects_insecure_http_urls():
    def handler(request: httpx.Request) -> httpx.Response:
        insecure_hit = {
            **SAMPLE_IMAGE_HIT,
            "largeImageURL": "http://insecure.pixabay.com/photo/large.jpg",
            "pageURL": "https://pixabay.com/photos/123",
        }
        insecure_source = {
            **SAMPLE_IMAGE_HIT,
            "largeImageURL": "https://pixabay.com/photo/large.jpg",
            "pageURL": "http://insecure.pixabay.com/photos/123",
        }
        return httpx.Response(200, json={"total": 2, "hits": [insecure_hit, insecure_source]})

    adapter = _pixabay_adapter(handler)
    candidates = adapter.search("teste", media_type="image")
    assert candidates == []


def test_attribution_and_author_fallback_when_user_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        img_hit = {**SAMPLE_IMAGE_HIT, "user": ""}
        vid_hit = {**SAMPLE_VIDEO_HIT, "user": ""}
        return httpx.Response(200, json={"total": 1, "hits": [img_hit if "api/videos" not in str(request.url) else vid_hit]})

    adapter = _pixabay_adapter(handler)
    c_img = adapter.search("teste", media_type="image")[0]
    assert c_img.attribution == "Foto do Pixabay"
    assert c_img.author == ""

    c_vid = adapter.search("teste", media_type="video")[0]
    assert c_vid.attribution == "Vídeo do Pixabay"
    assert c_vid.author == ""


def test_satisfies_media_search_protocol():
    adapter = PixabayMediaSearch(api_key="valid_key")
    assert isinstance(adapter, MediaSearch)


def test_video_duration_variations():
    def handler(request: httpx.Request) -> httpx.Response:
        v1 = {**SAMPLE_VIDEO_HIT, "id": 1, "duration": 12.3}
        v2 = {**SAMPLE_VIDEO_HIT, "id": 2, "duration": 0}
        v3 = {**SAMPLE_VIDEO_HIT, "id": 3, "duration": -5}
        v4 = {**SAMPLE_VIDEO_HIT, "id": 4, "duration": "invalid"}
        v5 = {**SAMPLE_VIDEO_HIT, "id": 5, "duration": None}
        return httpx.Response(200, json={"total": 5, "hits": [v1, v2, v3, v4, v5]})

    adapter = _pixabay_adapter(handler)
    candidates = adapter.search("teste", media_type="video")
    assert len(candidates) == 5
    assert candidates[0].duration_s == 12.3
    assert candidates[1].duration_s is None
    assert candidates[2].duration_s is None
    assert candidates[3].duration_s is None
    assert candidates[4].duration_s is None


def test_malformed_hits_ignored():
    def handler(request: httpx.Request) -> httpx.Response:
        hits = [
            "not a dict",
            None,
            {},
            {"videos": "not a dict"},
            {"videos": {}},
            {"videos": {"large": "not a dict"}},
            {"videos": {"large": {"url": "not an https url"}}},
            SAMPLE_VIDEO_HIT,
        ]
        return httpx.Response(200, json={"total": len(hits), "hits": hits})

    adapter = _pixabay_adapter(handler)
    candidates = adapter.search("teste", media_type="video")
    assert len(candidates) == 1
    assert candidates[0].media_id == "12345"

