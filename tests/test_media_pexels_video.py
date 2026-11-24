"""Testes para busca de vídeos stock no Pexels (Task 4 de Onda 2)."""
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.media_pexels import PexelsMediaSearch  # noqa: E402
from app.studio.application.ports import ModelUnavailable  # noqa: E402

SAMPLE_VIDEO = {
    "id": 99999,
    "width": 1920,
    "height": 1080,
    "url": "https://www.pexels.com/video/99999/",
    "duration": 18,
    "user": {
        "id": 123,
        "name": "Videomaker Teste",
        "url": "https://www.pexels.com/@videomaker",
    },
    "video_files": [
        {
            "id": 1,
            "quality": "hd",
            "file_type": "video/mp4",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "link": "https://video-files.pexels.com/videos/99999/99999-hd_1920_1080.mp4",
        },
        {
            "id": 2,
            "quality": "sd",
            "file_type": "video/mp4",
            "width": 960,
            "height": 540,
            "fps": 30.0,
            "link": "https://video-files.pexels.com/videos/99999/99999-sd_960_540.mp4",
        },
    ],
}


def _video_adapter(handler, key="TEST_KEY", **kwargs):
    return PexelsMediaSearch(
        "pexels-model",
        key,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _video_response(videos):
    return httpx.Response(200, json={"videos": videos, "total_results": len(videos)})


def test_video_search_returns_valid_candidate_with_metadata():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["auth"] = request.headers.get("authorization")
        return _video_response([SAMPLE_VIDEO])

    adapter = _video_adapter(handler)
    candidates = adapter.search("natureza", media_type="video", orientation="landscape", per_page=10)

    assert len(candidates) == 1
    c = candidates[0]
    assert c.media_type == "video"
    assert c.duration_s == 18.0
    assert c.author == "Videomaker Teste"
    assert c.attribution == "Vídeo de Videomaker Teste no Pexels"
    assert c.url == "https://video-files.pexels.com/videos/99999/99999-hd_1920_1080.mp4"
    assert c.source_url == "https://www.pexels.com/video/99999/"
    assert c.license == "Pexels License"
    assert c.cost_usd == Decimal("0")
    assert c.width == 1920
    assert c.height == 1080
    assert seen["path"] == "/videos/search"
    assert seen["params"]["query"] == "natureza"
    assert seen["params"]["orientation"] == "landscape"
    assert seen["params"]["per_page"] == "10"
    assert seen["auth"] == "TEST_KEY"


def test_video_search_photographer_field_and_fallback_attribution():
    def handler_photographer(request):
        video = {**SAMPLE_VIDEO, "user": {}, "photographer": "Diretor Foto"}
        return _video_response([video])

    c1 = _video_adapter(handler_photographer).search("teste", media_type="video")[0]
    assert c1.attribution == "Vídeo de Diretor Foto no Pexels"
    assert c1.author == "Diretor Foto"

    def handler_empty(request):
        video = {**SAMPLE_VIDEO, "user": {}, "photographer": ""}
        return _video_response([video])

    c2 = _video_adapter(handler_empty).search("teste", media_type="video")[0]
    assert c2.attribution == "Vídeo do Pexels"
    assert c2.author == ""


def test_video_search_selects_best_file_matching_orientation():
    multi_file_video = {
        **SAMPLE_VIDEO,
        "video_files": [
            {
                "id": 10,
                "quality": "hd",
                "file_type": "video/mp4",
                "width": 1920,
                "height": 1080,
                "link": "https://video-files.pexels.com/videos/99999/landscape_hd.mp4",
            },
            {
                "id": 20,
                "quality": "hd",
                "file_type": "video/mp4",
                "width": 1080,
                "height": 1920,
                "link": "https://video-files.pexels.com/videos/99999/portrait_hd.mp4",
            },
        ],
    }

    def handler(request):
        return _video_response([multi_file_video])

    adapter = _video_adapter(handler)

    portrait_candidates = adapter.search("teste", media_type="video", orientation="portrait")
    assert len(portrait_candidates) == 1
    assert portrait_candidates[0].url == "https://video-files.pexels.com/videos/99999/portrait_hd.mp4"
    assert portrait_candidates[0].width == 1080
    assert portrait_candidates[0].height == 1920

    landscape_candidates = adapter.search("teste", media_type="video", orientation="landscape")
    assert len(landscape_candidates) == 1
    assert landscape_candidates[0].url == "https://video-files.pexels.com/videos/99999/landscape_hd.mp4"
    assert landscape_candidates[0].width == 1920
    assert landscape_candidates[0].height == 1080


def test_video_search_supports_vimeo_player_cdn():
    vimeo_video = {
        **SAMPLE_VIDEO,
        "video_files": [
            {
                "id": 1,
                "quality": "hd",
                "file_type": "video/mp4",
                "width": 1920,
                "height": 1080,
                "link": "https://player.vimeo.com/external/99999.hd.mp4",
            }
        ],
    }

    def handler(request):
        return _video_response([vimeo_video])

    c = _video_adapter(handler).search("teste", media_type="video")[0]
    assert c.url == "https://player.vimeo.com/external/99999.hd.mp4"


def test_video_search_rejects_untrusted_cdn():
    untrusted_video = {
        **SAMPLE_VIDEO,
        "video_files": [
            {
                "id": 1,
                "quality": "hd",
                "file_type": "video/mp4",
                "width": 1920,
                "height": 1080,
                "link": "https://evil.example.com/video.mp4",
            }
        ],
    }

    def handler(request):
        return _video_response([untrusted_video])

    assert _video_adapter(handler).search("teste", media_type="video") == []


def test_video_search_rejects_missing_or_invalid_url():
    broken = {**SAMPLE_VIDEO, "url": "http://insecure.test/video/1"}

    def handler(request):
        return _video_response([broken])

    assert _video_adapter(handler).search("teste", media_type="video") == []


def test_video_search_rejects_missing_or_empty_video_files():
    broken_empty = {**SAMPLE_VIDEO, "video_files": []}
    broken_none = {**SAMPLE_VIDEO, "video_files": None}

    def handler(request):
        return _video_response([broken_empty, broken_none])

    assert _video_adapter(handler).search("teste", media_type="video") == []


def test_video_search_orientation_and_per_page_validation():
    def handler(request):
        return _video_response([SAMPLE_VIDEO])

    adapter = _video_adapter(handler)

    with pytest.raises(ModelUnavailable, match="orientation"):
        adapter.search("teste", media_type="video", orientation="diagonal")

    with pytest.raises(ModelUnavailable, match="per_page"):
        adapter.search("teste", media_type="video", per_page=0)

    with pytest.raises(ModelUnavailable, match="per_page"):
        adapter.search("teste", media_type="video", per_page=81)


def test_video_search_unsupported_media_type():
    def handler(request):
        raise AssertionError("HTTP não deveria ser chamado")

    adapter = _video_adapter(handler)
    with pytest.raises(ModelUnavailable):
        adapter.search("teste", media_type="audio")


def test_video_search_handles_http_errors_safely():
    def handler(request):
        return httpx.Response(500, json={"error": "server error"})

    with pytest.raises(ModelUnavailable) as excinfo:
        _video_adapter(handler, key="TOP_SECRET_KEY").search("teste", media_type="video")
    assert "TOP_SECRET_KEY" not in str(excinfo.value)


def test_video_search_empty_query_returns_empty_list():
    def handler(request):
        raise AssertionError("HTTP não deveria ser chamado")

    assert _video_adapter(handler).search("", media_type="video") == []
    assert _video_adapter(handler).search("   ", media_type="video") == []


def test_video_search_duration_handling():
    def handler(request):
        video1 = {**SAMPLE_VIDEO, "id": 1, "duration": "24.5"}
        video2 = {**SAMPLE_VIDEO, "id": 2, "duration": 0}
        video3 = {**SAMPLE_VIDEO, "id": 3, "duration": None}
        return _video_response([video1, video2, video3])

    candidates = _video_adapter(handler).search("teste", media_type="video")
    assert len(candidates) == 3
    assert candidates[0].duration_s == 24.5
    assert candidates[1].duration_s is None
    assert candidates[2].duration_s is None


def test_video_search_per_page_limits():
    def handler(request):
        assert request.url.params["per_page"] in ("1", "80")
        return _video_response([SAMPLE_VIDEO])

    adapter = _video_adapter(handler)
    assert len(adapter.search("teste", media_type="video", per_page=1)) == 1
    assert len(adapter.search("teste", media_type="video", per_page=80)) == 1

