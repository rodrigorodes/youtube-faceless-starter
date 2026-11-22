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
from app.studio.domain.channel import ChannelProfile  # noqa: E402
from app.studio.domain.ids import InvalidId  # noqa: E402
from app.studio.domain.youtube_channel import OAuthStatus  # noqa: E402
from app.studio.domain.youtube_identity import ChannelAuthorization  # noqa: E402
from app.studio.domain.publication_policy import (  # noqa: E402
    PublicationIntentEvidence,
    idempotency_key,
    metadata_fingerprint,
)
from app.studio.domain.youtube_oauth import OAuthReconnectRequired, OAuthTransientError  # noqa: E402

V, P, R = "a" * 32, "b" * 32, "c" * 32
OUT, PUB = "d" * 32, "e" * 32
CK = "f" * 64
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
YT = "oNQ2KN37sfQ"
TARGET = "UCtarget123"   # destino configurado do canal do estúdio (YT-02)
OTHER = "UCother123"     # canal a que um token divergente pertence (YT-03)


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


class Channels:
    """Repositório de canal: o projeto → destino do YouTube.

    ``exists=False`` simula um projeto **sem perfil de canal** (o repositório devolve ``None``);
    ``invalid=True`` simula um ``project_id`` que o repositório rejeita (``InvalidId``); com
    ``exists=True`` o canal existe e ``target=None`` significa **canal sem destino** (fail-closed
    depois do W0B.2).
    """

    def __init__(self, target=None, exists=True, invalid=False):
        self.target, self.exists, self.invalid = target, exists, invalid

    def get_by_project(self, project_id):
        if self.invalid:
            raise InvalidId("invalid id")
        if not self.exists:
            return None
        return ChannelProfile(id="c" * 32, project_id=project_id, name="Canal", youtube_channel_id=self.target)


class Authorizations:
    def __init__(self, *values):
        self.values = list(values)

    def authorizations_for_channel(self, youtube_channel_id):
        return list(self.values)


def authorization(channel_id=TARGET, status=OAuthStatus.CONNECTED):
    return ChannelAuthorization(grant_id="1" * 32, youtube_channel_id=channel_id, status=status)


def use(tmp_path, *, videos=None, intents=None, approvals=None, pubs=None, uploads=None, tokens=None, retry=None,
        exists=True, policy=None, channels=None, authorizations=None, enabled=True):
    videos = videos or Videos()
    intents = intents if intents is not None else Intents()
    approvals = approvals or Approvals()
    pubs = pubs or Pubs()
    uploads = uploads or Uploads()
    tokens = tokens or Tokens()
    run = RunPublication(videos, Scripts(), Assets(), Jobs(), Snaps(), approvals, intents, pubs, Files(tmp_path, exists),
                         uploads, tokens, clock=lambda: NOW, retry_policy=policy,
                         channels=channels, authorizations=authorizations, enabled=enabled)
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


# -- YT-03: gate de identidade (destino do canal × canal do token) -----------------------------


def test_a_configured_target_with_a_matching_token_uploads(tmp_path):
    run, pubs, uploads, _ = use(tmp_path, channels=Channels(TARGET), authorizations=Authorizations(authorization()),
                                tokens=Tokens(channel_id=TARGET))
    result = run.execute()
    assert result.result is PublicationResult.UPLOADED
    assert len(uploads.uploads) == 1 and pubs.uploaded == YT


def test_a_token_from_another_channel_is_blocked_before_any_upload(tmp_path):
    run, pubs, uploads, _ = use(tmp_path, channels=Channels(TARGET), authorizations=Authorizations(authorization()),
                                tokens=Tokens(channel_id=OTHER))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED
    assert OTHER in result.detail and TARGET in result.detail
    assert pubs.calls[-1][:3] == ("dead_letter", 1, "PERMANENT") and uploads.uploads == []  # uploader nunca chamado


def test_a_target_without_a_connected_authorization_is_blocked(tmp_path):
    run, pubs, uploads, _ = use(tmp_path, channels=Channels(TARGET), authorizations=Authorizations(),
                                tokens=Tokens(channel_id=TARGET))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and TARGET in result.detail
    assert uploads.uploads == [] and pubs.calls[-1][0] == "dead_letter"


def test_a_grant_failure_blocks_the_publication_without_uploading(tmp_path):
    """F01.T01: quando o grant do destino não serve, o executor bloqueia — nunca cai no legado."""
    from app.studio.application.channel_grant import ChannelGrantMissing
    run, pubs, uploads, _ = use(tmp_path, channels=Channels(TARGET), authorizations=Authorizations(authorization()),
                                tokens=Tokens(error=ChannelGrantMissing(
                                    f"no connected authorization for the expected YouTube channel {TARGET}")))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and TARGET in result.detail
    assert "reconnected" in result.detail and uploads.uploads == []
    assert pubs.calls[-1][:3] == ("dead_letter", 1, "PERMANENT")


def test_an_unknown_token_channel_is_blocked_when_a_target_is_configured(tmp_path):
    run, _, uploads, _ = use(tmp_path, channels=Channels(TARGET), authorizations=Authorizations(authorization()),
                             tokens=Tokens(channel_id=None))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and "unknown" in result.detail and uploads.uploads == []


def test_a_channel_without_a_target_is_blocked_before_any_upload(tmp_path):
    """W0B.2 (R8): canal existente **sem destino** não publica — o gate deixou de ser fail-open."""
    run, pubs, uploads, _ = use(tmp_path, channels=Channels(None), authorizations=Authorizations(authorization()),
                                tokens=Tokens(channel_id=OTHER))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED
    assert "destination" in result.detail and "Canais" in result.detail  # mensagem acionável
    assert uploads.uploads == []  # o uploader nunca é chamado
    assert pubs.calls[-1][:3] == ("dead_letter", 1, "PERMANENT")


def test_a_project_without_a_channel_profile_is_blocked_before_any_upload(tmp_path):
    """W0B.2: com repositórios injetados, a ausência de perfil de canal bloqueia a publicação."""
    run, pubs, uploads, _ = use(tmp_path, channels=Channels(exists=False),
                                authorizations=Authorizations(authorization()), tokens=Tokens(channel_id=TARGET))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED
    assert "channel" in result.detail.lower() and uploads.uploads == []
    assert pubs.calls[-1][:3] == ("dead_letter", 1, "PERMANENT")


def test_an_invalid_project_id_is_blocked_when_repositories_are_injected(tmp_path):
    """W0B.2: ``InvalidId`` do repositório de canal não pode virar permissão silenciosa."""
    run, pubs, uploads, _ = use(tmp_path, channels=Channels(invalid=True),
                                authorizations=Authorizations(authorization()), tokens=Tokens(channel_id=TARGET))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and uploads.uploads == []
    assert pubs.calls[-1][:3] == ("dead_letter", 1, "PERMANENT")


def test_a_legacy_construction_without_repositories_preserves_the_current_behavior(tmp_path):
    """Construção legada (sem repositórios de canal/autorizações) segue o caminho antigo.

    O caminho do servidor sempre injeta os repositórios (`composition.py`), então esta forma só
    existe em testes/construções antigas; documentada como exceção no docstring do gate.
    """
    legacy, _, legacy_uploads, _ = use(tmp_path)  # sem repositórios: `channels`/`authorizations` = None
    assert legacy.execute().result is PublicationResult.UPLOADED and len(legacy_uploads.uploads) == 1


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


# --------------------------- W5.2 (PUB-02): retry idempotente, sem upload duplicado (A20)


def test_a_confirmed_publication_is_idempotent_and_never_uploads_again(tmp_path):
    """W5.2/A20: repetir a MESMA publicação com id confirmado devolve UPLOADED sem novo upload."""
    pubs = Pubs(pub=Publication(id=PUB, video_id=V, status=PublicationStatus.UPLOADED, attempt=1,
                                youtube_video_id=YT))
    run, pubs, uploads, tokens = use(tmp_path, pubs=pubs)
    result = run.execute()
    assert result.result is PublicationResult.UPLOADED and result.youtube_video_id == YT
    assert uploads.uploads == [] and tokens.calls == 0


def test_a_second_click_finds_nothing_to_claim_and_does_not_upload_again(tmp_path):
    """W5.2/A20: duplo clique não duplica: o segundo execute não reivindica nem sobe nada."""

    class OncePubs(Pubs):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.claims = 0

        def claim_retry(self, lease_seconds, max_attempts, video_id=None):
            return None

        def claim(self, lease_seconds, max_attempts, video_id=None):
            self.claims += 1
            return self.pub if self.claims == 1 else None

    run, pubs, uploads, _ = use(tmp_path, pubs=OncePubs())
    assert run.execute().result is PublicationResult.UPLOADED
    assert run.execute().result is PublicationResult.IDLE
    assert len(uploads.uploads) == 1


def test_a_retry_reuses_the_existing_resumable_session(tmp_path):
    """W5.2/A20: o retry da MESMA publicação retoma a sessão existente; não abre uma segunda."""
    uri = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=existing"
    retry_pub = Publication(id="9" * 32, video_id=V, status=PublicationStatus.PENDING, attempt=2,
                            upload_uri=uri)
    run, pubs, uploads, _ = use(tmp_path, pubs=Pubs(retry=retry_pub))
    result = run.execute()
    assert result.result is PublicationResult.UPLOADED
    request, _ = uploads.uploads[0]
    assert request.upload_uri == uri
    assert len(uploads.uploads) == 1
    assert pubs.calls[0] == ("claim_retry",)


def test_an_uploader_exception_is_ambiguous_and_never_retried(tmp_path):
    """W5.2/A20: exceção do adaptador não prova ausência de efeito externo — reconciliação, não reenvio."""
    uploads = Uploads(error=RuntimeError("transport exploded"))
    run, pubs, uploads, _ = use(tmp_path, uploads=uploads)
    result = run.execute()
    assert result.result is PublicationResult.RECONCILE
    assert len(uploads.uploads) == 1
    assert not any(call[0] == "retry_later" for call in pubs.calls)
    assert pubs.calls[-1][0] == "mark_ambiguous"


def test_a_successful_upload_whose_id_cannot_be_recorded_is_reconciled_not_duplicated(tmp_path):
    """W5.2: o vídeo subiu mas o id não foi gravado; reconciliar — nunca subir de novo."""

    class FailingMarkPubs(Pubs):
        def mark_uploaded(self, publication_id, youtube_video_id):
            self.calls.append(("mark_uploaded", youtube_video_id))
            raise RuntimeError("database unavailable")

    run, pubs, uploads, _ = use(tmp_path, pubs=FailingMarkPubs())
    result = run.execute()
    assert result.result is PublicationResult.RECONCILE
    assert len(uploads.uploads) == 1
    assert pubs.calls[-1][0] == "mark_ambiguous"


def test_a_session_that_cannot_be_recorded_is_ambiguous_not_retried(tmp_path):
    """W5.2: sem a sessão gravada, o retry abriria uma NOVA sessão — exige reconciliação."""

    class UnrecordablePubs(Pubs):
        def record_session(self, publication_id, attempt, uri, offset):
            self.calls.append(("record_session", attempt, uri, offset))
            return False

    uri = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x"
    uploads = Uploads(UploadResult(UploadOutcome.INCOMPLETE, upload_uri=uri, offset=1234))
    run, pubs, uploads, _ = use(tmp_path, pubs=UnrecordablePubs(), uploads=uploads)
    result = run.execute()
    assert result.result is PublicationResult.RECONCILE
    assert not any(call[0] == "retry_later" for call in pubs.calls)
    assert pubs.calls[-1][0] == "mark_ambiguous"


def test_reconcile_never_uploads_and_marks_the_confirmed_id(tmp_path):
    """W5.2: a reconciliação só sonda a sessão; nunca faz um novo upload."""
    from app.studio.application.publication_execution import ReconcilePublication
    pubs = Pubs(pub=_unknown_pub())
    uploads = Uploads(reconcile_result=UploadResult(UploadOutcome.UPLOADED, youtube_video_id=YT, upload_uri="u"))
    result = ReconcilePublication(Videos(), pubs, uploads, Tokens()).execute(PUB)
    assert result.result is PublicationResult.UPLOADED and pubs.uploaded == YT
    assert uploads.uploads == [] and len(uploads.reconciliations) == 1


# ------------------------------- F01.T04: contingência explícita da publicação


def test_disabled_publication_blocks_before_claim_and_never_uploads(tmp_path):
    """Desligar por configuração é a contingência: bloqueia antes do claim, sem token nem upload."""
    run, pubs, uploads, tokens = use(tmp_path, enabled=False)
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED
    assert "STUDIO_PUBLICATION_ENABLED" in (result.detail or "")
    assert pubs.calls == [] and uploads.uploads == [] and tokens.calls == 0


def test_disabled_publication_does_not_mark_anything_as_sent(tmp_path):
    """O bloqueio não deixa rastro de sucesso: nada vira UPLOADED e nada é reconciliado."""
    run, pubs, uploads, _ = use(tmp_path, enabled=False)
    run.execute(video_id=V)
    assert pubs.uploaded is None and uploads.reconciliations == []


def test_enabled_by_default_preserves_the_existing_behavior(tmp_path):
    run, pubs, uploads, tokens = use(tmp_path)
    assert run.enabled is True
    assert run.execute().result is PublicationResult.UPLOADED
    assert len(uploads.uploads) == 1 and tokens.calls == 1


def test_publication_flag_is_read_from_the_environment():
    from app.studio.composition import Settings
    assert Settings.from_env({}).publication_enabled is True
    assert Settings.from_env({"STUDIO_PUBLICATION_ENABLED": "1"}).publication_enabled is True
    assert Settings.from_env({"STUDIO_PUBLICATION_ENABLED": "0"}).publication_enabled is False
    assert Settings.from_env({"STUDIO_PUBLICATION_ENABLED": "false"}).publication_enabled is False


# -- W5.1 (PUB-01 / A19 / A37): destino ou metadados mudados tornam a intenção obsoleta ---------


def _confirmed_intent():
    return intent(youtube_channel_id=TARGET,
                  metadata_fingerprint=metadata_fingerprint("Título", "Resumo", ["ade"], "private"))


def test_a_changed_destination_blocks_the_stale_intent(tmp_path):
    run, pubs, uploads, _ = use(
        tmp_path, intents=Intents(_confirmed_intent()),
        channels=Channels("UCnewdestination"),
        authorizations=Authorizations(authorization("UCnewdestination")),
        tokens=Tokens(channel_id="UCnewdestination"))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and "destination" in result.detail
    assert uploads.uploads == []  # a intenção antiga não autoriza upload para outro canal
    assert pubs.calls[-1][:3] == ("dead_letter", 1, "PERMANENT")


def test_changed_metadata_blocks_the_stale_intent(tmp_path):
    videos = Videos()
    videos.video = videos.video.model_copy(update={"title": "Título editado"})
    run, pubs, uploads, _ = use(tmp_path, videos=videos,
                                intents=Intents(intent(metadata_fingerprint=metadata_fingerprint(
                                    "Título", "Resumo", ["ade"], "private"))))
    result = run.execute()
    assert result.result is PublicationResult.BLOCKED and "metadata" in result.detail
    assert uploads.uploads == [] and pubs.calls[-1][:3] == ("dead_letter", 1, "PERMANENT")


def test_unchanged_destination_and_metadata_still_upload(tmp_path):
    run, _, uploads, _ = use(tmp_path, intents=Intents(_confirmed_intent()),
                             channels=Channels(TARGET), authorizations=Authorizations(authorization()),
                             tokens=Tokens(channel_id=TARGET))
    assert run.execute().result is PublicationResult.UPLOADED and len(uploads.uploads) == 1
