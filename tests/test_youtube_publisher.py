"""F8-03/04: upload resumable idempotente contra o YouTube (HTTP fake, sem rede real)."""
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.youtube_publisher import GoogleYouTubeUploader  # noqa: E402
from app.studio.application.ports import UploadOutcome, UploadRequest  # noqa: E402

URI = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=AbC123"
INIT = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
ACCESS = "ya29.SYNTHETIC_access_value_only_for_tests"
BODY = {"snippet": {"title": "Teste", "description": "d", "categoryId": "24"}, "status": {"privacyStatus": "private"}}


@pytest.fixture()
def video(tmp_path):
    path = tmp_path / "synthetic.mp4"
    path.write_bytes(b"synthetic-mp4-bytes" * 40)
    return path


def request(video, **kw):
    base = dict(idempotency_key="pub-" + "a" * 32 + "-" + "b" * 32 + "-" + "c" * 64,
                file_path=video, file_size=video.stat().st_size, content_type="video/mp4",
                youtube_body=BODY, upload_uri=None, offset=0)
    return UploadRequest(**{**base, **kw})


def uploader(handler):
    calls = []

    def wrapped(req):
        calls.append(req)
        return handler(req)

    return GoogleYouTubeUploader(transport=httpx.MockTransport(wrapped)), calls


def test_new_session_then_upload_success_sends_the_full_file(video):
    def handler(req):
        if req.method == "POST" and str(req.url) == INIT:
            assert req.headers["authorization"] == f"Bearer {ACCESS}"
            assert req.headers["x-upload-content-type"] == "video/mp4"
            assert req.headers["x-upload-content-length"] == str(video.stat().st_size)
            assert json.loads(req.content) == BODY
            return httpx.Response(200, headers={"Location": URI})
        assert req.method == "PUT" and str(req.url) == URI
        assert req.headers["content-range"] == f"bytes 0-{video.stat().st_size - 1}/{video.stat().st_size}"
        assert req.read() == video.read_bytes()
        return httpx.Response(200, json={"id": "oNQ2KN37sfQ", "status": {"uploadStatus": "processed"}})

    app, calls = uploader(handler)
    result = app.upload(request(video), ACCESS)
    assert result.outcome is UploadOutcome.UPLOADED and result.youtube_video_id == "oNQ2KN37sfQ"
    assert result.upload_uri == URI and len(calls) == 2


def test_existing_session_is_probed_and_resumed_from_the_acknowledged_offset(video):
    def handler(req):
        if req.method == "PUT" and req.headers["content-range"] == f"bytes */{video.stat().st_size}":
            return httpx.Response(308, headers={"Range": "bytes=0-199"})
        assert req.headers["content-range"] == f"bytes 200-{video.stat().st_size - 1}/{video.stat().st_size}"
        assert req.read() == video.read_bytes()[200:]
        return httpx.Response(201, json={"id": "oNQ2KN37sfQ"})

    app, calls = uploader(handler)
    result = app.upload(request(video, upload_uri=URI), ACCESS)
    assert result.outcome is UploadOutcome.UPLOADED and result.youtube_video_id == "oNQ2KN37sfQ"
    assert len(calls) == 2


def test_completed_session_without_a_lost_response_is_not_uploaded_again(video):
    app, calls = uploader(lambda req: httpx.Response(200, json={"id": "oNQ2KN37sfQ"}))
    result = app.upload(request(video, upload_uri=URI), ACCESS)
    assert result.outcome is UploadOutcome.UPLOADED and len(calls) == 1


def test_incomplete_without_range_reports_the_same_offset(video):
    app, _ = uploader(lambda req: httpx.Response(308, headers={}))
    result = app.upload(request(video, upload_uri=URI), ACCESS)
    assert result.outcome is UploadOutcome.INCOMPLETE and result.offset == 0 and result.upload_uri == URI


def test_a_full_session_ack_without_id_is_ambiguous_not_success(video):
    app, _ = uploader(lambda req: httpx.Response(308, headers={"Range": f"bytes=0-{video.stat().st_size - 1}"}))
    result = app.upload(request(video, upload_uri=URI), ACCESS)
    assert result.outcome is UploadOutcome.AMBIGUOUS and result.youtube_video_id is None


@pytest.mark.parametrize("status", [404, 410])
def test_expired_session_is_ambiguous_and_preserves_no_false_success(video, status):
    app, _ = uploader(lambda req: httpx.Response(status))
    result = app.upload(request(video, upload_uri=URI), ACCESS)
    assert result.outcome is UploadOutcome.AMBIGUOUS and result.youtube_video_id is None
    assert result.upload_uri == URI


def test_invalid_session_location_is_refused_before_any_token_is_sent(video):
    app, calls = uploader(lambda req: httpx.Response(200, headers={"Location": "https://evil.example/upload?upload_id=x"}))
    result = app.upload(request(video), ACCESS)
    assert result.outcome is UploadOutcome.PERMANENT and len(calls) == 1
    assert "Location" not in (result.error or "")


@pytest.mark.parametrize("status,outcome", [
    (429, UploadOutcome.RETRYABLE), (500, UploadOutcome.RETRYABLE), (503, UploadOutcome.RETRYABLE),
    (400, UploadOutcome.PERMANENT), (401, UploadOutcome.PERMANENT), (403, UploadOutcome.PERMANENT),
])
def test_upload_failures_are_classified_and_the_session_is_preserved(video, status, outcome):
    def handler(req):
        if req.headers.get("content-range", "").startswith("bytes */"):
            return httpx.Response(308, headers={"Range": "bytes=0-9"})
        return httpx.Response(status, json={"error": {"message": f"{ACCESS} quota or bad request"}})

    app, _ = uploader(handler)
    result = app.upload(request(video, upload_uri=URI), ACCESS)
    assert result.outcome is outcome
    if outcome is UploadOutcome.RETRYABLE:
        assert result.upload_uri == URI
    assert ACCESS not in (result.error or "")


def test_init_network_timeout_is_retryable_without_a_session_or_token_leak(video):
    def handler(req):
        raise httpx.ConnectTimeout("timeout", request=req)

    app, _ = uploader(handler)
    result = app.upload(request(video), ACCESS)
    assert result.outcome is UploadOutcome.RETRYABLE and result.upload_uri is None
    assert "Timeout" in (result.error or "") and ACCESS not in (result.error or "")


def test_upload_network_timeout_keeps_the_same_session(video):
    def handler(req):
        if req.headers.get("content-range", "").startswith("bytes */"):
            return httpx.Response(308, headers={"Range": "bytes=0-9"})
        raise httpx.ReadTimeout("timeout", request=req)

    app, _ = uploader(handler)
    result = app.upload(request(video, upload_uri=URI), ACCESS)
    assert result.outcome is UploadOutcome.RETRYABLE and result.upload_uri == URI


def test_init_server_error_is_retryable(video):
    app, _ = uploader(lambda req: httpx.Response(503))
    result = app.upload(request(video), ACCESS)
    assert result.outcome is UploadOutcome.RETRYABLE and result.upload_uri is None


@pytest.mark.parametrize("status,outcome", [
    (200, UploadOutcome.UPLOADED), (308, UploadOutcome.INCOMPLETE), (404, UploadOutcome.AMBIGUOUS),
    (410, UploadOutcome.AMBIGUOUS), (503, UploadOutcome.AMBIGUOUS),
])
def test_reconcile_never_invents_success(video, status, outcome):
    def handler(req):
        if status == 200:
            return httpx.Response(200, json={"id": "oNQ2KN37sfQ"})
        return httpx.Response(status, headers={"Range": "bytes=0-99"} if status == 308 else {})

    app, _ = uploader(handler)
    result = app.reconcile(request(video, upload_uri=URI), ACCESS)
    assert result.outcome is outcome
    if status == 308:
        assert result.offset == 100 and result.upload_uri == URI


def test_reconcile_without_a_session_is_safe_to_start_over(video):
    app, _ = uploader(lambda req: pytest.fail("no HTTP call should happen without a session"))
    result = app.reconcile(request(video), ACCESS)
    assert result.outcome is UploadOutcome.RETRYABLE and result.upload_uri is None


def test_uploader_repr_has_no_secret():
    app = GoogleYouTubeUploader(transport=httpx.MockTransport(lambda req: httpx.Response(500)))
    assert "Bearer" not in repr(app) and ACCESS not in repr(app)

def test_lookup_and_delete_are_idempotent_and_use_the_bearer_token():
    seen = []

    def handler(req):
        seen.append(req)
        assert req.headers["authorization"] == f"Bearer {ACCESS}"
        if req.method == "GET":
            return httpx.Response(200, json={"items": [{"id": "oNQ2KN37sfQ"}]})
        return httpx.Response(204)

    app = GoogleYouTubeUploader(transport=httpx.MockTransport(handler))
    assert app.lookup("oNQ2KN37sfQ", ACCESS) is True
    assert app.delete("oNQ2KN37sfQ", ACCESS) is True
    assert [r.method for r in seen] == ["GET", "DELETE"]
    assert "videoId" not in str(seen[-1].url) and "id=oNQ2KN37sfQ" in str(seen[-1].url)


def test_delete_treats_404_as_already_gone_and_403_as_reconnect():
    from app.studio.domain.youtube_oauth import OAuthReconnectRequired
    app = GoogleYouTubeUploader(transport=httpx.MockTransport(lambda req: httpx.Response(404)))
    assert app.delete("oNQ2KN37sfQ", ACCESS) is True
    app = GoogleYouTubeUploader(transport=httpx.MockTransport(lambda req: httpx.Response(403)))
    with pytest.raises(OAuthReconnectRequired):
        app.delete("oNQ2KN37sfQ", ACCESS)


def test_lookup_absent_returns_false():
    app = GoogleYouTubeUploader(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"items": []})))
    assert app.lookup("oNQ2KN37sfQ", ACCESS) is False
