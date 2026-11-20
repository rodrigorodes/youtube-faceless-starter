import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.trends import Evidence, TrendItem, TrendRefused, validate_trends


def _item(topic="ADE Lineup 2026", source_url="https://www.googleapis.com/youtube/v3/search", **kw):
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    base = {
        "topic": topic,
        "source_name": "YouTube Data API",
        "source_url": source_url,
        "observed_at": now,
        "window_start": now - timedelta(days=7),
        "window_end": now,
        "metric_name": "views",
        "metric_value": 1200000.0,
        "evidence": [Evidence(title="Lineup ADE", url="https://youtube.com/watch?v=1", views=1200000)],
    }
    base.update(kw)
    return TrendItem(**base)


def test_valid_trends_pass():
    items = [_item()]
    validate_trends(items, allowed_hosts=("www.googleapis.com",))


def test_http_source_url_is_refused():
    with pytest.raises(Exception):
        _item(source_url="http://www.googleapis.com/youtube/v3/search")


def test_unauthorized_host_is_refused():
    items = [_item(source_url="https://evil.com/fake-trends")]
    with pytest.raises(TrendRefused, match="host not allowed"):
        validate_trends(items, allowed_hosts=("www.googleapis.com",))


def test_observed_at_without_tz_or_in_future_is_refused():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    # naive tz
    items = [_item(observed_at=datetime(2026, 11, 20, 10, 0))]
    with pytest.raises(TrendRefused, match="timezone required"):
        validate_trends(items, allowed_hosts=("www.googleapis.com",), clock=lambda: now)

    # future
    future_items = [_item(observed_at=now + timedelta(hours=1))]
    with pytest.raises(TrendRefused, match="future"):
        validate_trends(future_items, allowed_hosts=("www.googleapis.com",), clock=lambda: now)


def test_inverted_or_excessive_window_is_refused():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    # inverted
    items = [_item(window_start=now, window_end=now - timedelta(days=1))]
    with pytest.raises(TrendRefused, match="window"):
        validate_trends(items, allowed_hosts=("www.googleapis.com",), clock=lambda: now)

    # > 31 days
    too_long = [_item(window_start=now - timedelta(days=35), window_end=now)]
    with pytest.raises(TrendRefused, match="window"):
        validate_trends(too_long, allowed_hosts=("www.googleapis.com",), clock=lambda: now)


def test_one_invalid_item_refuses_the_entire_batch():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    good = _item("Tema Valido")
    bad = _item("Tema Invalido", source_url="https://evil.com/trends")
    with pytest.raises(TrendRefused):
        validate_trends([good, bad], allowed_hosts=("www.googleapis.com",), clock=lambda: now)
