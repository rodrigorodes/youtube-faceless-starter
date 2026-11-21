"""Contrato HTTP de F8: publicação nativa, reconciliação, OAuth e confirmação pública."""
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.studio.api.routes import make_router  # noqa: E402
from app.studio.application.publication_execution import PublicationResult, PublicationRun  # noqa: E402
from app.studio.application.youtube_oauth import ConsentStateInvalid  # noqa: E402
from app.studio.domain.contracts import Publication, PublicationStatus, VideoStatus  # noqa: E402
from app.studio.domain.publication_policy import PublicConfirmationRequired  # noqa: E402
from app.studio.domain.youtube_oauth import OAuthReconnectRequired, OAuthTransientError  # noqa: E402

V, PUB = "a" * 32, "b" * 32
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
URI = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=AbC123"


class Approve:
    def __init__(self):
        self.calls = []
        self.error = None

    def execute(self, video_id, **kw):
        self.calls.append((video_id, kw))
        if self.error:
            raise self.error
        from app.studio.domain.contracts import Video, VideoFormat
        return Video(id=video_id, project_id="c" * 32, topic="ADE 2026", format=VideoFormat.short,
                     status=VideoStatus.APPROVED, title=kw.get("title") or "T"), True


class Publish:
    def __init__(self, result=PublicationResult.UPLOADED):
        self.result = result
        self.calls = []

    def execute(self, lease_seconds, max_attempts, video_id=None):
        self.calls.append((lease_seconds, max_attempts, video_id))
        return PublicationRun(result=self.result, publication=Publication(
            id=PUB, video_id=V, status=PublicationStatus.UPLOADED, upload_uri=URI),
            youtube_video_id="oNQ2KN37sfQ", detail="d")


class Reconcile(Publish):
    def execute(self, publication_id):
        self.calls.append(publication_id)
        return PublicationRun(result=PublicationResult.RECONCILE, publication=Publication(
            id=publication_id, video_id=V, status=PublicationStatus.PENDING, upload_uri=URI), detail="unknown")


class OAuthCase:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def execute(self, project_id, *args):
        self.calls.append((project_id, *args))
        if self.error:
            raise self.error
        return {"project_id": project_id, "channel_id": "UC1", "title": "Canal", "scopes": ["s"],
                "oauth_status": "CONNECTED", "connected": True, "token_expires_at": NOW.isoformat(),
                "updated_at": None}


class Authorize(OAuthCase):
    def execute(self, project_id):
        self.calls.append(project_id)
        if self.error:
            raise self.error
        return {"project_id": project_id, "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?x=1",
                "state": "state-abcdefghijklmnop", "expires_at": NOW}


def client(*, approve=None, publish=None, reconcile=None, begin=None, complete=None, refresh=None, revoke=None):
    from app.studio.application.publishing import Publishing
    publishing = Publishing(approve=approve or Approve(), reject=None, claim=None, set_uri=None, uploaded=None,
                            failed=None, thumbnail_set=None, retry=None, get=None, thumbnail=None, preview=None,
                            publish=publish, reconcile=reconcile)
    use_cases = SimpleNamespace(publishing=publishing, begin_youtube_oauth=begin, complete_youtube_oauth=complete,
                                refresh_youtube_channel=refresh, revoke_youtube_channel=revoke)
    app = FastAPI()
    app.include_router(make_router(lambda: use_cases, lambda: True))
    return TestClient(app, headers={"Authorization": "Bearer test-worker-token"})


def test_approve_passes_visibility_and_public_confirmation():
    approve = Approve()
    response = client(approve=approve).post(f"/studio/videos/{V}/approve",
                                            json={"output_asset_id": "d" * 32, "visibility": "public",
                                                  "confirm_publication": True})
    assert response.status_code == 200
    assert approve.calls[0][1]["visibility"] == "public" and approve.calls[0][1]["confirm_public"] is True


def test_public_without_confirmation_is_422_and_does_not_decide():
    approve = Approve()
    approve.error = PublicConfirmationRequired("publishing publicly requires explicit confirmation")
    response = client(approve=approve).post(f"/studio/videos/{V}/approve",
                                            json={"output_asset_id": "d" * 32, "visibility": "public"})
    assert response.status_code == 422 and "confirmation" in response.json()["detail"]


def test_publish_endpoint_returns_truthful_result_and_never_exposes_the_session_url():
    publish = Publish()
    response = client(publish=publish).post(f"/studio/videos/{V}/publication/publish",
                                            json={"lease_seconds": 60, "max_attempts": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "UPLOADED" and body["youtube_video_id"] == "oNQ2KN37sfQ"
    assert publish.calls == [(60, 3, V)]
    assert "upload_uri" not in body["publication"] and URI not in response.text


@pytest.mark.parametrize("result", [PublicationResult.RETRY, PublicationResult.RECONCILE,
                                    PublicationResult.DEAD_LETTER, PublicationResult.BLOCKED])
def test_publish_endpoint_never_reports_success_for_incomplete_outcomes(result):
    response = client(publish=Publish(result)).post(f"/studio/videos/{V}/publication/publish")
    assert response.status_code == 200 and response.json()["result"] == result.value


def test_publish_without_executor_is_503():
    assert client().post(f"/studio/videos/{V}/publication/publish").status_code == 503


def test_reconcile_endpoint_and_404_for_unknown_publication():
    reconcile = Reconcile()
    response = client(reconcile=reconcile).post(f"/studio/publications/{PUB}/reconcile")
    assert response.status_code == 200 and reconcile.calls == [PUB]
    assert response.json()["result"] == "RECONCILE" and "upload_uri" not in response.text


def test_oauth_authorize_callback_refresh_and_revoke_are_wired():
    begin, case = Authorize(), OAuthCase()
    c = client(begin=begin, complete=case, refresh=case, revoke=case)
    assert c.post(f"/studio/projects/{'d' * 32}/youtube-oauth/authorize").json()["state"] == "state-abcdefghijklmnop"
    assert c.post(f"/studio/projects/{'d' * 32}/youtube-oauth/callback",
                  json={"code": "code-123", "state": "state-abcdefghijklmnop"}).status_code == 200
    assert c.post(f"/studio/projects/{'d' * 32}/youtube-oauth/refresh").status_code == 200
    assert c.post(f"/studio/projects/{'d' * 32}/youtube-oauth/revoke").status_code == 200
    assert case.calls[-3][1:] == ("code-123", "state-abcdefghijklmnop")


def test_oauth_without_configuration_is_503():
    assert client().post(f"/studio/projects/{'d' * 32}/youtube-oauth/authorize").status_code == 503


@pytest.mark.parametrize("error,status", [
    (ConsentStateInvalid("state expired"), 409),
    (OAuthReconnectRequired("invalid_grant"), 409),
    (OAuthTransientError("backendError"), 502),
])
def test_oauth_errors_are_mapped_without_stack_trace(error, status):
    response = client(begin=Authorize(), complete=OAuthCase(error=error)).post(
        f"/studio/projects/{'d' * 32}/youtube-oauth/callback",
        json={"code": "code-123", "state": "state-abcdefghijklmnop"})
    assert response.status_code == status and "Traceback" not in response.text