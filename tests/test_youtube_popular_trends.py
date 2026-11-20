import io
import json
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.youtube_trends import fetch_popular_trends
from app.studio.application.categories import YouTubeApiError
from app.studio.domain.trends import TrendItem, validate_trends


def _mock_response(payload: dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def test_fetch_popular_trends_brazil_returns_items(monkeypatch):
    sample_payload = {
        "items": [
            {
                "id": "vid123",
                "snippet": {
                    "title": "Clipe Oficial de Sucesso",
                    "channelTitle": "Canal Musical",
                    "publishedAt": "2026-11-19T14:30:00Z",
                },
                "statistics": {
                    "viewCount": "1500000",
                },
            },
            {
                "id": "vid456",
                "snippet": {
                    "title": "Gols da Rodada do Brasileirão",
                    "channelTitle": "Futebol Total",
                    "publishedAt": "2026-11-20T01:00:00Z",
                },
                "statistics": {
                    "viewCount": "820000",
                },
            },
        ]
    }

    mock_urlopen = MagicMock(return_value=_mock_response(sample_payload))
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    items = fetch_popular_trends("fake-key", "BR", max_results=2)

    assert len(items) == 2
    assert all(isinstance(it, TrendItem) for it in items)
    assert items[0].source_name == "YouTube Brasil (Em Alta)"
    assert items[0].source_url == "https://www.youtube.com/feed/trending"
    assert items[0].topic == "Clipe Oficial de Sucesso"
    assert items[0].metric_name == "views"
    assert items[0].metric_value == 1500000.0
    assert len(items[0].evidence) == 1
    ev = items[0].evidence[0]
    assert ev.url == "https://youtube.com/watch?v=vid123"
    assert ev.title == "Clipe Oficial de Sucesso"
    assert ev.channel == "Canal Musical"
    assert ev.views == 1500000
    assert ev.published_at == datetime(2026, 11, 19, 14, 30, 0, tzinfo=timezone.utc)

    # Check request url
    req = mock_urlopen.call_args[0][0]
    req_url = req.full_url if hasattr(req, "full_url") else str(req)
    assert "regionCode=BR" in req_url
    assert "chart=mostPopular" in req_url
    assert "maxResults=2" in req_url
    assert "key=fake-key" in req_url

    # Check domain validation
    validate_trends(items, allowed_hosts=("www.youtube.com",))


def test_fetch_popular_trends_global_returns_items(monkeypatch):
    sample_payload = {
        "items": [
            {
                "id": "global_vid",
                "snippet": {
                    "title": "World News Live",
                    "channelTitle": "Global News",
                    "publishedAt": "2026-11-20T08:00:00Z",
                },
                "statistics": {
                    "viewCount": "3400000",
                },
            }
        ]
    }

    mock_urlopen = MagicMock(return_value=_mock_response(sample_payload))
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    items = fetch_popular_trends("fake-key", "US", max_results=1)

    assert len(items) == 1
    assert items[0].source_name == "YouTube Global (Em Alta)"
    assert items[0].source_url == "https://www.youtube.com/feed/trending"


def test_fetch_popular_trends_http_error_raises_youtube_api_error(monkeypatch):
    error = urllib.error.HTTPError(
        url="https://www.googleapis.com",
        code=403,
        msg="Quota Exceeded",
        hdrs={},
        fp=io.BytesIO(b"{}"),
    )
    monkeypatch.setattr("urllib.request.urlopen", MagicMock(side_effect=error))

    with pytest.raises(YouTubeApiError, match="YouTube popular trends error"):
        fetch_popular_trends("fake-key", "BR")


def test_fetch_popular_trends_network_error_raises_youtube_api_error(monkeypatch):
    error = urllib.error.URLError("DNS resolution failed")
    monkeypatch.setattr("urllib.request.urlopen", MagicMock(side_effect=error))

    with pytest.raises(YouTubeApiError, match="YouTube popular trends request failed"):
        fetch_popular_trends("fake-key", "BR")


def test_fetch_popular_trends_handles_empty_or_missing_fields(monkeypatch):
    sample_payload = {
        "items": [
            {
                "id": "vid_sparse",
                "snippet": {},
                "statistics": {},
            }
        ]
    }
    mock_urlopen = MagicMock(return_value=_mock_response(sample_payload))
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    items = fetch_popular_trends("fake-key", "BR")
    assert len(items) == 1
    assert len(items[0].topic) >= 3
    assert items[0].metric_value == 0.0
    assert items[0].evidence[0].views == 0
    assert items[0].evidence[0].published_at is None
