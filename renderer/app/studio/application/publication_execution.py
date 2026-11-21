"""Executor nativo da publicação (F8-02..F8-06).

O caminho real: reivindica a publicação (nova ou devida-para-retry), prova o gate de QA pelo
`render_id`/checksum aprovados, obtém um access token do canal e sobe pela porta `YouTubeUploader`.
Falha transitória volta com backoff; falha permanente e ambiguidade esgotada vão para DLQ; resultado
externo desconhecido nunca é presumido sucesso — fica `UNKNOWN` esperando reconciliação.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from ..domain.contracts import Publication, PublicationStatus, VideoStatus
from ..domain.publish import build_description, default_title, youtube_insert_body
from ..domain.publication_policy import (
    FailureClass,
    PublicationGateError,
    PublicationPolicyError,
    RetryPolicy,
    idempotency_key,
    next_action,
    publication_window_state,
    retry_delay,
    verify_publication_gate,
)
from ..domain.youtube_oauth import OAuthError, OAuthReconnectRequired, OAuthTransientError
from .youtube_oauth import ChannelNotConnected
from .editorial import StateConflict
from .ports import (
    AccessToken,
    ApprovalRepository,
    AssetRepository,
    PublicationIntentRepository,
    PublicationQueueRepository,
    RenderJobRepository,
    RenderStorage,
    ScriptRepository,
    SnapshotRepository,
    UploadOutcome,
    UploadRequest,
    VideoRepository,
    YouTubeUploader,
)
from .publishing import PublicationNotFound, credits_and_sources


class PublicationResult(str, Enum):
    IDLE = "IDLE"                  # nada pendente
    UPLOADED = "UPLOADED"          # id do YouTube confirmado e registrado
    RETRY = "RETRY"                # falha transitória: agendada com backoff
    RECONCILE = "RECONCILE"        # estado externo desconhecido: exige reconciliação humana/automática
    DEAD_LETTER = "DEAD_LETTER"    # falha permanente ou tentativas esgotadas
    BLOCKED = "BLOCKED"            # gate de QA/identidade impede qualquer upload


@dataclass(frozen=True)
class PublicationRun:
    result: PublicationResult
    publication: Publication | None = None
    youtube_video_id: str | None = None
    detail: str | None = None


class TokenProvider:
    """Porta mínima: devolve um access token válido **e o canal a que ele pertence** (YT-03).

    Devolver a identidade junto do token é o que permite ao gate de publicação comparar o canal
    real do token com o destino esperado. O token cru, sozinho, não prova canal.
    """

    def execute(self, project_id: str) -> AccessToken:  # pragma: no cover - interface
        raise NotImplementedError


class MissingTokenProvider:
    """Sem app OAuth configurado: falha fechado e explica, nunca inventa credencial."""

    def execute(self, project_id: str) -> AccessToken:
        raise ChannelNotConnected("the Google OAuth app is not configured; set the client secret file")


class FallbackTokenProvider:
    """Cofre por projeto primeiro; se o projeto ainda não tem consentimento, usa o token do ambiente.

    O fallback só vale para `ChannelNotConnected` (ausência de credencial), nunca para
    `invalid_grant`/revogação: trocar de token silenciosamente mascararia um canal errado.
    """

    def __init__(self, primary: TokenProvider, fallback: TokenProvider):
        self.primary, self.fallback = primary, fallback

    def execute(self, project_id: str) -> AccessToken:
        try:
            return self.primary.execute(project_id)
        except ChannelNotConnected:
            return self.fallback.execute(project_id)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunPublication:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository,
                 jobs: RenderJobRepository, snaps: SnapshotRepository, approvals: ApprovalRepository,
                 intents: PublicationIntentRepository, pubs: PublicationQueueRepository, files: RenderStorage,
                 uploads: YouTubeUploader, tokens: TokenProvider, *, clock: Callable[[], datetime] = _utc_now,
                 retry_policy: RetryPolicy | None = None):
        self.videos, self.scripts, self.assets, self.jobs, self.snaps = videos, scripts, assets, jobs, snaps
        self.approvals, self.intents, self.pubs, self.files = approvals, intents, pubs, files
        self.uploads, self.tokens = uploads, tokens
        self.clock = clock
        self.policy = retry_policy or RetryPolicy()

    # -- preparação --------------------------------------------------------

    def _claimed(self, lease_seconds: int, max_attempts: int, video_id: str | None = None) -> Publication | None:
        """Retry seguro tem prioridade sobre publicação nova (mesma sessão preservada)."""
        return (self.pubs.claim_retry(lease_seconds, max_attempts, video_id)
                or self.pubs.claim(lease_seconds, max_attempts, video_id))

    def _dead_letter(self, pub: Publication, error: str, failure: FailureClass) -> PublicationRun:
        self.pubs.dead_letter(pub.id, pub.attempt, error, failure.value)
        return PublicationRun(PublicationResult.DEAD_LETTER if failure is not FailureClass.AMBIGUOUS else PublicationResult.RECONCILE,
                              publication=pub, detail=error)

    def _blocked(self, pub: Publication, error: str) -> PublicationRun:
        self.pubs.dead_letter(pub.id, pub.attempt, error, FailureClass.PERMANENT.value)
        return PublicationRun(PublicationResult.BLOCKED, publication=pub, detail=error)

    def _retry(self, pub: Publication, error: str, failure: FailureClass) -> PublicationRun:
        if next_action(self.policy, pub.attempt, failure) == "DEAD_LETTER":
            return self._dead_letter(pub, error, failure)
        delay = retry_delay(self.policy, pub.attempt)
        self.pubs.retry_later(pub.id, pub.attempt, error, delay, failure.value)
        return PublicationRun(PublicationResult.RETRY, publication=pub, detail=error)

    def _body(self, pub: Publication, video, intent, output) -> dict:
        credits, sources = credits_and_sources(self.scripts, self.assets, self.snaps, video.id)
        description = build_description(video.description, credits, sources, synthetic=True)
        return youtube_insert_body(video.title or default_title(video.topic), description, video.tags,
                                   pub.publish_at, visibility=intent.visibility)

    def _prepare(self, pub: Publication) -> tuple[UploadRequest, str] | PublicationRun:
        video = self.videos.get_video(pub.video_id)
        if video is None:
            return self._blocked(pub, "the video no longer exists")
        intent = self.intents.get(video.id)
        if intent is None:
            return self._blocked(pub, "the publication intent is missing; re-approve the video with a reviewed render")
        approval = self.approvals.get(video.id)
        job = self.jobs.latest(video.id)
        output = self.jobs.approved_output(video.id)
        if job is None or output is None:
            return self._blocked(pub, "there is no successful render to publish")
        try:
            verify_publication_gate(intent, render_id=job.id, checksum=output.cache_key, output_asset_id=output.id,
                                    qa_report_passed=bool(video.qa_report and video.qa_report.is_publishable),
                                    approval_output_asset_id=approval.output_asset_id if approval else None)
        except PublicationGateError as exc:
            return self._blocked(pub, str(exc))
        window = publication_window_state(pub.publish_at, self.clock())
        if window in ("EXPIRED", "TOO_LATE"):
            return self._blocked(pub, "publication schedule has expired or is too close; reschedule before publishing")
        path = self.files.resolve(output.path, "mp4")
        if path is None:
            return self._blocked(pub, "the rendered file is missing")
        try:
            body = self._body(pub, video, intent, output)
        except PublicationPolicyError as exc:
            return self._blocked(pub, str(exc))
        return (UploadRequest(idempotency_key=intent.idempotency_key, file_path=Path(path), file_size=Path(path).stat().st_size,
                              content_type="video/mp4", youtube_body=body, upload_uri=pub.upload_uri,
                              offset=0), video.project_id)

    # -- execução ----------------------------------------------------------

    def execute(self, lease_seconds: int = 1800, max_attempts: int | None = None,
                video_id: str | None = None) -> PublicationRun:
        max_attempts = max_attempts or self.policy.max_attempts
        pub = self._claimed(lease_seconds, max_attempts, video_id)
        if pub is None:
            return PublicationRun(PublicationResult.IDLE)
        prepared = self._prepare(pub)
        if isinstance(prepared, PublicationRun):
            return prepared
        request, project_id = prepared
        try:
            access_token = self.tokens.execute(project_id)
        except OAuthReconnectRequired as exc:
            return self._blocked(pub, f"the YouTube channel needs to be reconnected ({exc})")
        except OAuthTransientError as exc:
            return self._retry(pub, f"OAuth refresh failed ({exc})", FailureClass.TRANSIENT)
        except OAuthError as exc:
            return self._blocked(pub, f"the YouTube channel credentials are unusable ({exc})")
        try:
            result = self.uploads.upload(request, access_token.token)
        except Exception as exc:  # adaptador quebrado não pode derrubar o worker nem marcar sucesso
            return self._retry(pub, f"the uploader failed ({type(exc).__name__})", FailureClass.TRANSIENT)
        return self._settle(pub, result)

    def _settle(self, pub: Publication, result) -> PublicationRun:
        error = (result.error or "")[:500] or "upload failed"
        if result.outcome is UploadOutcome.UPLOADED:
            if not result.youtube_video_id:
                return self._ambiguous(pub, "the uploader reported success without a video id")
            try:
                saved = self.pubs.mark_uploaded(pub.id, result.youtube_video_id)
            except Exception as exc:  # conflito de id: nunca sobrescreve, exige humano
                return self._blocked(pub, f"could not record the YouTube id: {type(exc).__name__}")
            if saved is None:
                return self._ambiguous(pub, "the publication disappeared while recording the YouTube id")
            return PublicationRun(PublicationResult.UPLOADED, publication=saved,
                                  youtube_video_id=result.youtube_video_id)
        if result.outcome is UploadOutcome.INCOMPLETE:
            session_uri = result.upload_uri or pub.upload_uri
            if not session_uri:
                return self._ambiguous(pub, "the uploader reported an incomplete session without a session URL")
            self.pubs.record_session(pub.id, pub.attempt, session_uri, result.offset)
            return self._retry(pub, error, FailureClass.TRANSIENT)
        if result.outcome is UploadOutcome.RETRYABLE:
            if result.upload_uri and result.upload_uri != pub.upload_uri:
                self.pubs.record_session(pub.id, pub.attempt, result.upload_uri, result.offset)
            return self._retry(pub, error, FailureClass.TRANSIENT)
        if result.outcome is UploadOutcome.PERMANENT:
            return self._dead_letter(pub, error, FailureClass.PERMANENT)
        return self._ambiguous(pub, error)

    def _ambiguous(self, pub: Publication, error: str) -> PublicationRun:
        if pub.attempt >= self.policy.max_attempts:
            return self._dead_letter(pub, error, FailureClass.AMBIGUOUS)
        self.pubs.mark_ambiguous(pub.id, pub.attempt, error)
        return PublicationRun(PublicationResult.RECONCILE, publication=pub, detail=error)


class ReconcilePublication:
    """Resolve um resultado externo desconhecido: só grava id se o YouTube confirmar.

    `INCOMPLETE`/`RETRYABLE` do reconcile provam que a sessão não gerou vídeo: libera o retry.
    `AMBIGUOUS`/`PERMANENT` mantêm a DLQ/reconciliação humana — nunca inventa sucesso.
    """

    def __init__(self, videos: VideoRepository, pubs: PublicationQueueRepository, uploads: YouTubeUploader,
                 tokens: TokenProvider, *, policy: RetryPolicy | None = None, clock: Callable[[], datetime] = _utc_now):
        self.videos, self.pubs, self.uploads, self.tokens = videos, pubs, uploads, tokens
        self.policy, self.clock = policy or RetryPolicy(), clock

    def execute(self, publication_id: str) -> PublicationRun:
        pub = self.pubs.get_by_id(publication_id)
        if pub is None:
            raise PublicationNotFound(publication_id)
        if pub.youtube_video_id:
            return PublicationRun(PublicationResult.UPLOADED, publication=pub, youtube_video_id=pub.youtube_video_id)
        video = self.videos.get_video(pub.video_id)
        if video is None:
            self.pubs.resolve_ambiguous(pub.id, retry=False, failure_class=FailureClass.PERMANENT.value,
                                        error="the video no longer exists")
            return PublicationRun(PublicationResult.BLOCKED, publication=pub, detail="the video no longer exists")
        try:
            access_token = self.tokens.execute(video.project_id)
        except OAuthReconnectRequired as exc:
            self.pubs.resolve_ambiguous(pub.id, retry=False, failure_class=FailureClass.PERMANENT.value,
                                        error=f"the YouTube channel needs to be reconnected ({exc})")
            return PublicationRun(PublicationResult.BLOCKED, publication=pub, detail="channel reconnect required")
        except OAuthError:
            return PublicationRun(PublicationResult.RECONCILE, publication=pub, detail="could not obtain a token to reconcile")
        request = UploadRequest(idempotency_key="reconcile", file_path=Path("."), file_size=0,
                                content_type="video/mp4", youtube_body={}, upload_uri=pub.upload_uri, offset=0)
        result = self.uploads.reconcile(request, access_token.token)
        if result.outcome is UploadOutcome.UPLOADED and result.youtube_video_id:
            saved = self.pubs.mark_uploaded(pub.id, result.youtube_video_id)
            return PublicationRun(PublicationResult.UPLOADED, publication=saved, youtube_video_id=result.youtube_video_id)
        if result.outcome in (UploadOutcome.INCOMPLETE, UploadOutcome.RETRYABLE):
            self.pubs.resolve_ambiguous(pub.id, retry=True, failure_class=FailureClass.TRANSIENT.value, error="")
            return PublicationRun(PublicationResult.RETRY, publication=pub, detail="session alive without a video; retry scheduled")
        if result.outcome is UploadOutcome.PERMANENT:
            self.pubs.resolve_ambiguous(pub.id, retry=False, failure_class=FailureClass.PERMANENT.value,
                                        error=(result.error or "")[:500])
            return PublicationRun(PublicationResult.DEAD_LETTER, publication=pub, detail=result.error)
        self.pubs.resolve_ambiguous(pub.id, retry=False, failure_class=FailureClass.AMBIGUOUS.value,
                                    error=(result.error or "")[:500])
        return PublicationRun(PublicationResult.RECONCILE, publication=pub, detail=result.error)