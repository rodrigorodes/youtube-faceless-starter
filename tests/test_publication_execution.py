"""F8-02..06: executor nativo da publicação — gate de QA, idempotência, retry/DLQ e reconciliação."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.publication_execution import PublicationResult, RunPublication  # noqa: E402
from app.studio.application.ports import AccessToken, UploadOutcome, UploadResult  # noqa: E402
from app.studio.domain.contracts import (  # noqa: E402
    Approval, Asset, AssetKind, Publication, PublicationStatus, Scene, Script, SourceSnapshot, Video,
    VideoFormat, VideoStatus,
)
from app.studio.domain.qa_report import QaCoverage, QaFinding, QaReport  # noqa: E402
from app.studio.domain.publication_policy import PublicationIntentEvidence, idempotency_key  # noqa: E402
from app.studio.domain.youtube_oauth import OAuthReconnectRequired, OAuthTransientError  # noqa: E402

V, P, R = "a" * 32, "b" * 32, "c" * 32
OUT, PUB = "d" * 32, "e" * 32
CK = "f" * 64
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
YT = "oNQ2KN37sfQ"


def qa_report(passed=True):
    """Relatório de QA versionado (F6) para os vídeos dos fakes deste teste."""
    findings = () if passed else (QaFinding(finding_id="f0", check_id="render.audio_stream", category="technical",
                                             severity="blocking", evidence="sem áudio", suggested_action="Revisar o render."),)
    return QaReport(render_id="9" * 32, checksum="8" * 64, generated_at=NOW,
                    coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics", "render.audio_stream"),
                    findings=findings)


def intent(**changes):
    base = dict(video_id=V, render_id=R, checksum=CK, output_asset_id=OUT, qa_passed=True, qa_override=False,
                visibility="private", public_confirmed=False)
    merged = {**base, **changes}
    merged.setdefault("idempotency_key", idempotency_key(merged["video_id"], merged["render_id"], merged["checksum"]))
    return PublicationIntentEvidence(**merged)


class Videos:
    def __init__(self, qa=True, status=VideoStatus.APPROVED):
        self.video = Video(id=V, project_id=P, topic="ADE 2026", format=VideoFormat.short, status=status,
                           title="Título", description="Resumo", tags=["ade"],
                           qa_report=qa_report(qa))

    def get_video(self, video_id):
        return self.video


class Scripts:
    def latest(self, video_id):
        return Script(id="1" * 32, video_id=V, version=1, text="Texto")

    def scenes(self, video_id):
        return [Scene(id="2" * 32, video_id=V, idx=0, narration="Narração válida.", image_prompt="prompt válido", asset_id="3" * 32)]


class Assets:
    def get(self, asset_id):
        return Asset(id=asset_id, kind=AssetKind.image, cache_key="4" * 64, path="k.png", provider="stock", model="p",
                     license="Pexels License", attribution="Foto de Ana no Pexels")


class Snaps:
    def list(self, video_id):
        return [SourceSnapshot(id="5" * 32, video_id=V, url="https://example.org/x", content_sha256="6" * 64, text="t")]


class Jobs:
    def __init__(self):
        self.asset = Asset(id=OUT, kind=AssetKind.video, cache_key=CK, path="projects/p/final.mp4", provider="ffmpeg",
                           model="m", license="ok")

    def approved_output(self, video_id):
        return self.asset

    def latest(self, video_id):
        from app.studio.domain.contracts import JobStatus, RenderJob
        return RenderJob(id=R, video_id=V, status=JobStatus.SUCCEEDED, attempt=1, output_asset_id=OUT)


class Approvals:
    def __init__(self, output=OUT):
        self.output = output

    def get(self, video_id):
        return Approval(video_id=V, decision="approved", output_asset_id=self.output)


class Intents:
    def __init__(self, value="present"):
        try:
            self.value = intent() if value == "present" else value
        except Exception:
            self.value = value

    def get(self, video_id):
        return self.value


class Files:
    def __init__(self, tmp, exists=True):
        self.tmp, self.exists = tmp, exists

    def resolve(self, relative, kind):
        if not self.exists:
            return None
        path = self.tmp / "final.mp4"
        path.write_bytes(b"m" * 5000)
        return path


class Pubs:
    def __init__(self, pub=None, retry=None):
        self.pub = pub or Publication(id=PUB, video_id=V, status=PublicationStatus.UPLOADING, attempt=1, publish_at=None)
        self.retry_pub = retry
        self.calls = []
        self.uploaded = None

    def claim_retry(self, lease_seconds, max_attempts, video_id=None):
        self.calls.append(("claim_retry",))
        return self.retry_pub

    def claim(self, lease_seconds, max_attempts, video_id=None):
        self.calls.append(("claim",))
        return self.pub

    def record_session(self, publication_id, attempt, uri, offset):
        self.calls.append(("record_session", attempt, uri, offset))
        return True

    def retry_later(self, publication_id, attempt, error, delay, failure_class):
        self.calls.append(("retry_later", attempt, delay, failure_class))
        return True

    def dead_letter(self, publication_id, attempt, error, failure_class):
        self.calls.append(("dead_letter", attempt, failure_class, error))
        return True

    def mark_ambiguous(self, publication_id, attempt, error):
        self.calls.append(("mark_ambiguous", attempt, error))
        return True

    def mark_uploaded(self, publication_id, youtube_video_id):
        self.calls.append(("mark_uploaded", youtube_video_id))
        self.uploaded = youtube_video_id
        return self.pub.model_copy(update={"youtube_video_id": youtube_video_id, "status": PublicationStatus.UPLOADED})

    def resolve_ambiguous(self, publication_id, *, retry, error, failure_class):
        self.calls.append(("resolve_ambiguous", retry, failure_class))
        return True

    def get_by_id(self, publication_id):
        return self.pub


class Uploads:
    def __init__(self, result=None, reconcile_result=None, error=None):
        self.result = result or UploadResult(UploadOutcome.UPLOADED, youtube_video_id=YT, upload_uri="u")
        self.reconcile_result = reconcile_result
        self.error = error
        self.uploads, self.reconciliations = [], []

    def upload(self, request, access_token):
        self.uploads.append((request, access_token))
        if self.error:
            raise self.error
        return self.result

    def reconcile(self, request, access_token):
        self.reconciliations.append(request)
        return self.reconcile_result or UploadResult(UploadOutcome.AMBIGUOUS, error="unknown")


class Tokens:
    def __init__(self, error=None, channel_id=None):
        self.error = error
        self.channel_id = channel_id
        self.calls = 0

    def execute(self, project_id):
        self.calls += 1
        if self.error:
            raise self.error
        return AccessToken("ya29.SYNTHETIC_access", self.channel_id)


def use(tmp_path, *, videos=None, intents=None, approvals=None, pubs=None, uploads=None, tokens=None, retry=None,
        exists=True, policy=None):
    videos = videos or Videos()
    intents = intents if intents is not None else Intents()
    approvals = approvals or Approvals()
    pubs = pubs or Pubs()
    uploads = uploads or Uploads()
    tokens = tokens or Tokens()
    run = RunPublication(videos, Scripts(), Assets(), Jobs(), Snaps(), approvals, intents, pubs, Files(tmp_path, exists),
                         uploads, tokens, clock=lambda: NOW, retry_policy=policy)
    return run, pubs, uploads, tokens


def test_idle_when_there_is_nothing_to_publish(tmp_path):
    pubs = Pubs()
    pubs.retry_pub = None
    pubs.claim = lambda lease_seconds, max_attempts, video_id=None: None
    run, pubs, uploads, tokens = use(tmp_path, pubs=pubs)
    result = run.execute()
    assert result.result is PublicationResult.IDLE and uploads.uploads == [] and tokens.calls == 0


def test_happy_path_uploads_and_records_the_youtube_id(tmp_path):
    run, pubs, uploads, tokens = use(tmp_path)
    result = run.execute()
    assert result.result is PublicationResult.UPLOADED and result.youtube_video_id == YT
    assert pubs.uploaded == YT and tokens.calls == 1
    request, token = uploads.uploads[0]
    assert token == "ya29.SYNTHETIC_access" and request.idempotency_key == idempotency_key(V, R, CK)
    assert request.youtube_body["status"]["privacyStatus"] == "private"
    assert request.file_size == 5000 and request.content_type == "video/mp4"
    assert "Foto de Ana no Pexels" in request.youtube_body["snippet"]["description"]


def test_missing_intent_blocks_publication_and_never_calls_the_provider(tmp_path):
    run, pubs, uploads, tokens = use(tmp_path, intents=Intents(None))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and "intent" in result.detail
    assert ("dead_letter", 1, "PERMANENT") == pubs.calls[-1][:3] and uploads.uploads == [] and tokens.calls == 0


def test_a_stale_render_or_checksum_blocks_publication(tmp_path):
    run, pubs, uploads, _ = use(tmp_path, intents=Intents(intent(render_id="9" * 32)))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and "render" in result.detail
    assert pubs.calls[-1][0] == "dead_letter" and uploads.uploads == []


def test_failed_qa_without_override_blocks_publication(tmp_path):
    run, pubs, uploads, _ = use(tmp_path, videos=Videos(qa=False), intents=Intents(intent(qa_passed=False)))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and "QA" in result.detail
    assert uploads.uploads == []


def test_recorded_human_override_allows_publication(tmp_path):
    run, pubs, uploads, _ = use(tmp_path, videos=Videos(qa=False),
                                intents=Intents(intent(qa_passed=False, qa_override=True)))
    assert run.execute().result is PublicationResult.UPLOADED and len(uploads.uploads) == 1


@pytest.mark.parametrize("visibility,confirmed,privacy", [
    ("private", False, "private"), ("unlisted", False, "unlisted"), ("public", True, "public")])
def test_visibility_is_carried_into_the_youtube_body(tmp_path, visibility, confirmed, privacy):
    run, _, uploads, _ = use(tmp_path, intents=Intents(intent(visibility=visibility, public_confirmed=confirmed)))
    assert run.execute().result is PublicationResult.UPLOADED
    assert uploads.uploads[0][0].youtube_body["status"]["privacyStatus"] == privacy


def test_scheduled_publication_uses_private_with_publish_at(tmp_path):
    when = NOW + timedelta(days=1)
    pubs = Pubs(pub=Publication(id=PUB, video_id=V, status=PublicationStatus.UPLOADING, attempt=1, publish_at=when))
    run, _, uploads, _ = use(tmp_path, pubs=pubs, intents=Intents(intent(visibility="public", public_confirmed=True)))
    assert run.execute().result is PublicationResult.UPLOADED
    status = uploads.uploads[0][0].youtube_body["status"]
    assert status["privacyStatus"] == "private" and status["publishAt"].endswith("Z")


def test_expired_schedule_is_dead_lettered_not_uploaded(tmp_path):
    pubs = Pubs(pub=Publication(id=PUB, video_id=V, status=PublicationStatus.UPLOADING, attempt=1,
                                publish_at=NOW - timedelta(minutes=1)))
    run, pubs, uploads, _ = use(tmp_path, pubs=pubs)
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and "schedule" in result.detail
    assert pubs.calls[-1][0] == "dead_letter" and uploads.uploads == []


def test_transient_failure_releases_with_backoff_and_preserves_the_session(tmp_path):
    uploads = Uploads(UploadResult(UploadOutcome.RETRYABLE, upload_uri="https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x", error="HTTP 503"))
    run, pubs, _, _ = use(tmp_path, uploads=uploads)
    result = run.execute()
    assert result.result is PublicationResult.RETRY
    assert pubs.calls[-1] == ("retry_later", 1, 30, "TRANSIENT")


def test_incomplete_session_is_recorded_and_retried_from_the_offset(tmp_path):
    uri = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x"
    uploads = Uploads(UploadResult(UploadOutcome.INCOMPLETE, upload_uri=uri, offset=1234))
    run, pubs, _, _ = use(tmp_path, uploads=uploads)
    assert run.execute().result is PublicationResult.RETRY
    assert ("record_session", 1, uri, 1234) in pubs.calls and pubs.calls[-1] == ("retry_later", 1, 30, "TRANSIENT")


def test_permanent_failure_is_dead_lettered(tmp_path):
    uploads = Uploads(UploadResult(UploadOutcome.PERMANENT, error="HTTP 403 quotaExceeded"))
    run, pubs, _, _ = use(tmp_path, uploads=uploads)
    result = run.execute()
    assert result.result is PublicationResult.DEAD_LETTER and pubs.calls[-1][:3] == ("dead_letter", 1, "PERMANENT")


def test_retry_is_dead_lettered_after_the_attempt_cap(tmp_path):
    from app.studio.domain.publication_policy import RetryPolicy
    pubs = Pubs(pub=Publication(id=PUB, video_id=V, status=PublicationStatus.UPLOADING, attempt=5))
    uploads = Uploads(UploadResult(UploadOutcome.RETRYABLE, error="HTTP 503"))
    run, pubs, _, _ = use(tmp_path, pubs=pubs, uploads=uploads, policy=RetryPolicy(max_attempts=5))
    result = run.execute()
    assert result.result is PublicationResult.DEAD_LETTER and pubs.calls[-1][:3] == ("dead_letter", 5, "TRANSIENT")


def test_ambiguous_result_requires_reconciliation_and_is_not_retried(tmp_path):
    uploads = Uploads(UploadResult(UploadOutcome.AMBIGUOUS, upload_uri="https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x", error="timeout"))
    run, pubs, _, _ = use(tmp_path, uploads=uploads)
    result = run.execute()
    assert result.result is PublicationResult.RECONCILE and pubs.calls[-1][0] == "mark_ambiguous"
    assert not any(call[0] == "retry_later" for call in pubs.calls)


def test_missing_channel_credentials_block_before_any_upload(tmp_path):
    run, pubs, uploads, _ = use(tmp_path, tokens=Tokens(error=OAuthReconnectRequired("no refresh token")))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and "channel" in result.detail
    assert pubs.calls[-1][0] == "dead_letter" and uploads.uploads == []


def test_transient_oauth_failure_is_retried(tmp_path):
    run, pubs, uploads, _ = use(tmp_path, tokens=Tokens(error=OAuthTransientError("backendError")))
    result = run.execute()
    assert result.result is PublicationResult.RETRY and pubs.calls[-1] == ("retry_later", 1, 30, "TRANSIENT")
    assert uploads.uploads == []


def test_retry_claims_are_preferred_over_new_publications(tmp_path):
    retry_pub = Publication(id="7" * 32, video_id=V, status=PublicationStatus.UPLOADING, attempt=2,
                            upload_uri="https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x")
    pubs = Pubs(retry=retry_pub)
    run, pubs, uploads, _ = use(tmp_path, pubs=pubs)
    assert run.execute().result is PublicationResult.UPLOADED
    assert pubs.calls[0] == ("claim_retry",) and uploads.uploads[0][0].upload_uri == retry_pub.upload_uri


def _unknown_pub(upload_uri="https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x"):
    return Publication(id=PUB, video_id=V, status=PublicationStatus.PENDING, attempt=1, upload_uri=upload_uri)


def test_reconcile_marks_uploaded_only_when_the_remote_confirms(tmp_path):
    from app.studio.application.publication_execution import ReconcilePublication
    pubs = Pubs(pub=_unknown_pub())
    uploads = Uploads(reconcile_result=UploadResult(UploadOutcome.UPLOADED, youtube_video_id=YT, upload_uri="u"))
    result = ReconcilePublication(Videos(), pubs, uploads, Tokens()).execute(PUB)
    assert result.result is PublicationResult.UPLOADED and pubs.uploaded == YT


def test_reconcile_keeps_unknown_when_the_remote_cannot_tell(tmp_path):
    from app.studio.application.publication_execution import ReconcilePublication
    pubs = Pubs(pub=_unknown_pub())
    uploads = Uploads(reconcile_result=UploadResult(UploadOutcome.AMBIGUOUS, error="HTTP 503"))
    result = ReconcilePublication(Videos(), pubs, uploads, Tokens()).execute(PUB)
    assert result.result is PublicationResult.RECONCILE and pubs.calls[-1] == ("resolve_ambiguous", False, "AMBIGUOUS")


def test_reconcile_restarts_when_the_session_is_merely_incomplete(tmp_path):
    from app.studio.application.publication_execution import ReconcilePublication
    pubs = Pubs(pub=_unknown_pub())
    uploads = Uploads(reconcile_result=UploadResult(UploadOutcome.INCOMPLETE, upload_uri="u", offset=10))
    assert ReconcilePublication(Videos(), pubs, uploads, Tokens()).execute(PUB).result is PublicationResult.RETRY
    assert pubs.calls[-1] == ("resolve_ambiguous", True, "TRANSIENT")


def test_reconcile_requires_reconnect_instead_of_guessing(tmp_path):
    from app.studio.application.publication_execution import ReconcilePublication
    pubs = Pubs(pub=_unknown_pub())
    result = ReconcilePublication(Videos(), pubs, Uploads(), Tokens(error=OAuthReconnectRequired("invalid_grant"))).execute(PUB)
    assert result.result is PublicationResult.BLOCKED and pubs.calls[-1] == ("resolve_ambiguous", False, "PERMANENT")