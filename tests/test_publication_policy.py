"""F8-02/04/06: política pura da publicação — idempotência, retry/DLQ, gate de QA e visibilidade."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.publication_policy import (  # noqa: E402
    FailureClass,
    PublicationGateError,
    PublicationIntentEvidence,
    PublicConfirmationRequired,
    RetryPolicy,
    classify_http,
    idempotency_key,
    next_action,
    publication_window_state,
    requires_public_confirmation,
    resolve_visibility,
    retry_delay,
    validate_visibility,
    verify_publication_gate,
)

V, R = "a" * 32, "b" * 32
C = "c" * 64
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def intent(**changes):
    base = dict(video_id=V, render_id=R, checksum=C, output_asset_id="d" * 32,
                qa_passed=True, qa_override=False, visibility="private", public_confirmed=False)
    merged = {**base, **changes}
    merged.setdefault("idempotency_key", idempotency_key(merged["video_id"], merged["render_id"], merged["checksum"]))
    return PublicationIntentEvidence(**merged)


def test_idempotency_key_is_deterministic_and_media_specific():
    first = idempotency_key(V, R, C)
    assert first == idempotency_key(V, R, C)
    assert first != idempotency_key(V, R, "9" * 64)
    assert first != idempotency_key("9" * 32, R, C)
    assert first.startswith("pub-") and len(first) <= 200
    assert all(ch.islower() or ch.isdigit() or ch in ".:_-" for ch in first)
    for bad in (("x", R, C), (V, "x", C), (V, R, "x")):
        with pytest.raises(ValueError):
            idempotency_key(*bad)


def test_visibility_defaults_private_and_public_needs_a_second_confirmation():
    assert validate_visibility("private") == "private" and validate_visibility("unlisted") == "unlisted"
    assert requires_public_confirmation("public") and not requires_public_confirmation("private")
    assert resolve_visibility("public", True) == "public"
    with pytest.raises(PublicConfirmationRequired):
        resolve_visibility("public", False)
    with pytest.raises(PublicConfirmationRequired):
        resolve_visibility("public", None)
    assert resolve_visibility("unlisted", False) == "unlisted"
    with pytest.raises(ValueError):
        validate_visibility("internal")


def test_intent_is_immutable_and_public_requires_confirmation_at_rest():
    assert intent(visibility="public", public_confirmed=True).visibility == "public"
    with pytest.raises(PublicConfirmationRequired):
        intent(visibility="public")
    with pytest.raises(ValueError):
        intent(render_id="short")
    with pytest.raises(ValueError):
        intent(checksum="x" * 32)


def test_gate_requires_the_exact_approved_render_checksum_and_qa():
    ok = intent()
    verify_publication_gate(ok, render_id=R, checksum=C, output_asset_id="d" * 32, qa_report_passed=True,
                            approval_output_asset_id="d" * 32)
    cases = (
        (dict(render_id="9" * 32), "render"),
        (dict(checksum="9" * 64), "checksum"),
        (dict(output_asset_id="9" * 32), "output"),
    )
    for changes, expected in cases:
        with pytest.raises(PublicationGateError, match=expected):
            verify_publication_gate(intent(**changes), render_id=R, checksum=C, output_asset_id="d" * 32,
                                    qa_report_passed=True, approval_output_asset_id="d" * 32)
    with pytest.raises(PublicationGateError, match="QA"):
        verify_publication_gate(intent(qa_passed=False), render_id=R, checksum=C, output_asset_id="d" * 32,
                                qa_report_passed=False, approval_output_asset_id="d" * 32)
    with pytest.raises(PublicationGateError, match="approved output"):
        verify_publication_gate(ok, render_id=R, checksum=C, output_asset_id="d" * 32, qa_report_passed=True,
                                approval_output_asset_id="9" * 32)


def test_gate_accepts_a_recorded_human_qa_override_but_not_a_silent_one():
    verify_publication_gate(intent(qa_passed=False, qa_override=True), render_id=R, checksum=C,
                            output_asset_id="d" * 32, qa_report_passed=False,
                            approval_output_asset_id="d" * 32)


@pytest.mark.parametrize("status,error,expected", [
    (None, None, FailureClass.TRANSIENT), (408, None, FailureClass.TRANSIENT), (429, None, FailureClass.TRANSIENT),
    (500, None, FailureClass.TRANSIENT), (503, "backend", FailureClass.TRANSIENT),
    (400, "invalid", FailureClass.PERMANENT), (401, None, FailureClass.PERMANENT),
    (403, "quotaExceeded", FailureClass.PERMANENT), (403, "forbidden", FailureClass.PERMANENT),
    (404, None, FailureClass.AMBIGUOUS), (410, None, FailureClass.AMBIGUOUS), (409, None, FailureClass.AMBIGUOUS),
])
def test_http_failure_classification_never_assumes_success(status, error, expected):
    assert classify_http(status, error_code=error) is expected


def test_retry_policy_is_exponential_capped_and_dead_letters_permanent_failures():
    policy = RetryPolicy(max_attempts=5, base_seconds=30, cap_seconds=600)
    assert [retry_delay(policy, attempt) for attempt in (1, 2, 3, 4, 5, 8)] == [30, 60, 120, 240, 480, 600]
    assert next_action(policy, 1, FailureClass.TRANSIENT) == "RETRY"
    assert next_action(policy, 4, FailureClass.TRANSIENT) == "RETRY"
    assert next_action(policy, 5, FailureClass.TRANSIENT) == "DEAD_LETTER"
    assert next_action(policy, 6, FailureClass.TRANSIENT) == "DEAD_LETTER"
    for failure in (FailureClass.PERMANENT, FailureClass.AMBIGUOUS):
        assert next_action(policy, 1, failure) == "DEAD_LETTER"
    for bad in (0, -1):
        with pytest.raises(ValueError):
            RetryPolicy(max_attempts=bad)


def test_publication_window_respects_schedule_and_processing_lead():
    assert publication_window_state(None, NOW) == "OPEN"
    assert publication_window_state(NOW + timedelta(days=1), NOW) == "SCHEDULED"
    assert publication_window_state(NOW + timedelta(minutes=5), NOW) == "TOO_LATE"
    assert publication_window_state(NOW, NOW) == "EXPIRED"
    assert publication_window_state(NOW - timedelta(minutes=1), NOW) == "EXPIRED"
    with pytest.raises(ValueError):
        publication_window_state(NOW + timedelta(days=1), datetime(2026, 11, 20, 12, 0))  # sem fuso

def test_youtube_body_privacy_maps_visibility_and_schedule_safely():
    from app.studio.domain.publication_policy import body_privacy_status
    assert body_privacy_status("private", None) == "private"
    assert body_privacy_status("unlisted", None) == "unlisted"
    assert body_privacy_status("public", None) == "public"
    assert body_privacy_status("private", NOW + timedelta(days=1)) == "private"
    assert body_privacy_status("public", NOW + timedelta(days=1)) == "private"  # YouTube agenda com private+publishAt
    with pytest.raises(ValueError):
        body_privacy_status("unlisted", NOW + timedelta(days=1))


def test_publication_body_reflects_the_confirmed_visibility():
    from app.studio.domain.publish import youtube_insert_body
    body = youtube_insert_body("Título", "Descrição", ["a"], None, visibility="public")
    assert body["status"]["privacyStatus"] == "public" and "publishAt" not in body["status"]
    scheduled = youtube_insert_body("Título", "Descrição", ["a"], NOW + timedelta(days=1), visibility="public")
    assert scheduled["status"]["privacyStatus"] == "private" and scheduled["status"]["publishAt"].endswith("Z")
