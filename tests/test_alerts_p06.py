import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.image_opencode import OpenCodeImage
from app.studio.adapters.text_opencode import OpenCodeText
from app.studio.application import observability
from app.studio.application.ports import ModelUnavailable


def test_bridge_connection_failure_is_passively_reported_without_sensitive_details(caplog):
    alerts = observability.BridgeAlerts()
    def offline(request):
        raise httpx.ConnectError("sensitive-error-content", request=request)

    model = OpenCodeText("model", "fake-secret", "http://local.invalid",
                         transport=httpx.MockTransport(offline), alerts=alerts)
    assert alerts.status() == "unknown"
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ModelUnavailable):
            model.complete("sensitive-prompt")
    assert alerts.status() == "unreachable"
    assert "bridge_unreachable" in caplog.text
    assert all(value not in caplog.text for value in ("fake-secret", "sensitive-prompt", "sensitive-error-content", "local.invalid"))


def test_http_response_clears_unreachable_but_does_not_claim_authentication_or_service_health():
    alerts = observability.BridgeAlerts()
    def offline(request):
        raise httpx.ConnectError("offline", request=request)
    offline_model = OpenCodeText("m", "fake", transport=httpx.MockTransport(offline), alerts=alerts)
    with pytest.raises(ModelUnavailable):
        offline_model.complete("p")
    model = OpenCodeText("m", "fake", transport=httpx.MockTransport(lambda r: httpx.Response(401)), alerts=alerts)
    with pytest.raises(ModelUnavailable):
        model.complete("p")
    assert alerts.status() == "reachable"


def test_image_health_transport_failure_reports_bridge_unreachable():
    alerts = observability.BridgeAlerts()
    def offline(request):
        raise httpx.ConnectError("offline", request=request)
    model = OpenCodeImage("model:free", "fake", transport=httpx.MockTransport(offline), alerts=alerts)
    with pytest.raises(ModelUnavailable):
        model.generate("p")
    assert alerts.status() == "unreachable"


def test_read_timeout_does_not_claim_the_bridge_is_unreachable():
    alerts = observability.BridgeAlerts()
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)
    model = OpenCodeText("m", "fake", transport=httpx.MockTransport(timeout), alerts=alerts)
    with pytest.raises(ModelUnavailable):
        model.complete("p")
    assert alerts.status() == "unknown"


def test_bridge_observation_expires_and_fresh_failure_alerts_again(caplog):
    clock = [0.0]
    alerts = observability.BridgeAlerts(clock=lambda: clock[0], max_age=10)
    with caplog.at_level(logging.WARNING, logger="studio.alerts"):
        alerts.observe(False)
        alerts.observe(False)
        clock[0] = 10.0
        assert alerts.status() == "unknown"
        alerts.observe(False)
    assert caplog.text.count("bridge_unreachable") == 2


def test_each_studio_wires_its_own_bridge_observations():
    from app.studio.composition import Settings, Studio

    first = Studio(Settings(bridge_token="fake1"))
    second = Studio(Settings(bridge_token="fake2"))
    try:
        model = first._build_provider("text", "opencode:model")
        model._transport = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("offline", request=r)))
        with pytest.raises(ModelUnavailable):
            model.complete("p")
        assert first.bridge_alerts.status() == "unreachable"
        assert second.bridge_alerts.status() == "unknown"
    finally:
        first.shutdown()
        second.shutdown()


def test_oauth_expiry_warning_contains_no_metadata(caplog):
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    with caplog.at_level(logging.WARNING, logger="studio.alerts"):
        assert observability.check_oauth_expiry(now + timedelta(days=1), now=now) == "expiring"
        assert observability.check_oauth_expiry(None, now=now) == "unknown"
    assert "oauth_expiring" in caplog.text
    assert "2030" not in caplog.text


@pytest.mark.parametrize(("expires", "expected"), [
    (None, "unknown"),
    (datetime(2030, 1, 1, tzinfo=timezone.utc), "expired"),
    (datetime(2030, 1, 2, tzinfo=timezone.utc), "expiring"),
    (datetime(2030, 1, 10, tzinfo=timezone.utc), "not_expiring"),
    (datetime(2030, 1, 2), "unknown"),
])
def test_oauth_expiry_requires_trusted_timezone_aware_metadata(expires, expected):
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert observability.oauth_expiry_status(expires, now=now, warning_window=timedelta(days=3)) == expected
