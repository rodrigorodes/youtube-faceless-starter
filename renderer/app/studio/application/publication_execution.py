"""Executor nativo da publicação (F8-02..F8-06).

O caminho real: reivindica a publicação (nova ou devida-para-retry), prova o gate de QA pelo
`render_id`/checksum aprovados, obtém um access token do canal e sobe pela porta `YouTubeUploader`.
Falha transitória volta com backoff; falha permanente e ambiguidade esgotada vão para DLQ; resultado
externo desconhecido nunca é presumido sucesso — fica `UNKNOWN` esperando reconciliação.

W5.2 (PUB-02) — idempotência do retry: repetir a **mesma** publicação nunca cria um segundo upload.
A única identidade do efeito externo é a sessão resumable já gravada (`upload_uri`); o retry a
retoma. Quando o resultado do adaptador é desconhecido (exceção, sessão que não pôde ser gravada),
o estado externo é ambíguo e a publicação vai para `UNKNOWN`/reconciliação — **não** se reenvia
sozinho. Uma publicação já com `youtube_video_id` confirmado devolve `UPLOADED` sem tocar na rede.

W5.2 — caminho efetivo: o workflow n8n `workflows/03-publish-approved.json` está **inativo**
(`"active": false`) e só orquestra; o servidor (este executor, via `POST /studio/publications/execute`)
é o caminho de upload. Se o workflow for reativado, ele **não** carrega credencial do YouTube nem
faz PUT: continua chamando este endpoint. Ver `workflows/README-publish-approval.md`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from ..domain.contracts import Publication, PublicationStatus, VideoStatus
from ..domain.channel import verify_publication_authorization
from ..domain.ids import InvalidId
from ..domain.publish import build_description, default_title, youtube_insert_body
from ..domain.publication_policy import (
    FailureClass,
    PublicationPolicyError,
    RetryPolicy,
    idempotency_key,
    next_action,
    publication_window_state,
    retry_delay,
)
from .publication_gate import confirmed_destination, publication_block_reason
from ..domain.youtube_oauth import OAuthError, OAuthReconnectRequired, OAuthTransientError
from .youtube_oauth import ChannelNotConnected
from .editorial import StateConflict
from .ports import (
    AccessToken,
    ApprovalRepository,
    AssetRepository,
    ChannelAuthorizationRepository,
    ChannelProfileRepository,
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
from .publishing import PublicationConflict, PublicationNotFound, credits_and_sources


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


class TargetChannelTokenProvider:
    """Escolhe a origem do token pelo destino do projeto — sem fallback cruzado entre canais (F01.T01).

    Com destino configurado (`channel_profiles.youtube_channel_id`), o token vem **exclusivamente**
    de `targeted` (a autorização daquele canal, renovada pelo grant). Qualquer falha propaga e a
    publicação bloqueia: nunca se tenta `legacy` nem outro canal.

    Sem destino, permanece o caminho legado **explícito e restrito**: cofre por projeto
    (`youtube:{project_id}`) e, na ausência de consentimento por projeto, o `token.env` do operador
    (`FallbackTokenProvider`). Esse caminho só existe enquanto nenhum canal do estúdio aponta para
    um destino, e não serve de fallback para um canal com destino.

    Projeto com id inválido é tratado como sem destino — lê o mesmo ``get_by_project`` do gate de
    identidade (`RunPublication._authorization_gate`). Desde o W0B.2 esse caso **bloqueia** no gate
    (canal não resolvido): o token legado pode até ser buscado, mas a publicação para antes do upload.
    """

    def __init__(self, channels: ChannelProfileRepository, targeted: TokenProvider, legacy: TokenProvider):
        self.channels, self.targeted, self.legacy = channels, targeted, legacy

    def execute(self, project_id: str) -> AccessToken:
        try:
            channel = self.channels.get_by_project(project_id)
        except InvalidId:
            channel = None
        if channel is not None and channel.youtube_channel_id is not None:
            return self.targeted.execute(project_id)
        return self.legacy.execute(project_id)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunPublication:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository,
                 jobs: RenderJobRepository, snaps: SnapshotRepository, approvals: ApprovalRepository,
                 intents: PublicationIntentRepository, pubs: PublicationQueueRepository, files: RenderStorage,
                 uploads: YouTubeUploader, tokens: TokenProvider, *, clock: Callable[[], datetime] = _utc_now,
                 retry_policy: RetryPolicy | None = None,
                 channels: ChannelProfileRepository | None = None,
                 authorizations: ChannelAuthorizationRepository | None = None,
                 enabled: bool = True):
        self.videos, self.scripts, self.assets, self.jobs, self.snaps = videos, scripts, assets, jobs, snaps
        self.approvals, self.intents, self.pubs, self.files = approvals, intents, pubs, files
        self.uploads, self.tokens = uploads, tokens
        # YT-03/W0B.2: com destino configurado, a publicação exige a autorização do canal. Sem estes
        # repositórios (default None, ex.: construção antiga/testes) o gate não consulta o canal e a
        # publicação segue sem bloqueio — o caminho do servidor sempre os injeta (`composition.py`).
        # Ver `_authorization_gate`.
        self.channels, self.authorizations = channels, authorizations
        self.clock = clock
        self.policy = retry_policy or RetryPolicy()
        # F01.T04: desligar a publicação é a contingência explícita — nunca reativa caminho inseguro.
        self.enabled = bool(enabled)

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

    def _confirmed_destination(self, video, intent) -> str | None:
        """Destino confirmado da intenção — delega ao gate único (`publication_gate`)."""
        return confirmed_destination(video, intent, self.channels)

    def _prepare(self, pub: Publication) -> tuple[UploadRequest, str] | PublicationRun:
        video = self.videos.get_video(pub.video_id)
        if video is None:
            return self._blocked(pub, "the video no longer exists")
        # A19/A37 + W5.1: o gate é o mesmo do claim (`application/publication_gate.py`).
        blocked = publication_block_reason(video, intents=self.intents, approvals=self.approvals,
                                           jobs=self.jobs, channels=self.channels)
        if blocked is not None:
            return self._blocked(pub, blocked)
        intent = self.intents.get(video.id)
        output = self.jobs.approved_output(video.id)
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

    def _authorization_gate(self, pub: Publication, project_id: str,
                            token_channel_id: str | None) -> PublicationRun | None:
        """YT-03: verifica que a autorização resolve para o canal esperado — antes de qualquer upload.

        W0B.2 (R8): o gate **falha fechado**. Com os repositórios injetados — o que o caminho do
        servidor sempre faz (`composition.py` passa ``channels``/``authorizations``) — a publicação
        só prossegue quando o canal do projeto tem destino **e** há uma autorização ``CONNECTED``
        que resolva para esse destino, com o token pertencendo ao mesmo canal. Sem perfil de canal,
        com ``project_id`` inválido (``InvalidId``), com canal **sem destino**, sem autorização
        vigente ou com token de outro canal, bloqueia via `_blocked` (DLQ ``PERMANENT``) — nenhum
        `uploads.upload` acontece nesse caminho.

        Única exceção, documentada de propósito: quando o ``RunPublication`` é construído **sem**
        os repositórios de canal/autorizações (``channels is None`` ou ``authorizations is None``).
        Essa é uma construção legada (testes) que o caminho do servidor **não** produz; sem os
        repositórios não há como consultar o canal, então a publicação segue o caminho antigo sem
        gate para não quebrar quem monta o executor assim.
        """
        if self.channels is None or self.authorizations is None:
            return None
        try:
            channel = self.channels.get_by_project(project_id)
        except InvalidId:
            return self._blocked(
                pub, "invalid project identifier; the channel destination cannot be checked — "
                     "re-create the channel in Canais → Conexão")
        if channel is None:
            return self._blocked(
                pub, "no channel profile is configured for this project; the YouTube destination "
                     "cannot be checked — connect the channel in Canais → Conexão")
        authorizations = (self.authorizations.authorizations_for_channel(channel.youtube_channel_id)
                          if channel.youtube_channel_id is not None else ())
        verdict = verify_publication_authorization(channel, authorizations, token_channel_id=token_channel_id)
        if verdict.allowed:
            return None
        return self._blocked(pub, verdict.reason)

    def execute(self, lease_seconds: int = 1800, max_attempts: int | None = None,
                video_id: str | None = None) -> PublicationRun:
        if not self.enabled:
            return PublicationRun(PublicationResult.BLOCKED,
                                  detail="publication is disabled by configuration (STUDIO_PUBLICATION_ENABLED=0)")
        max_attempts = max_attempts or self.policy.max_attempts
        pub = self._claimed(lease_seconds, max_attempts, video_id)
        if pub is None:
            return PublicationRun(PublicationResult.IDLE)
        # W5.2: idempotência dura. Se a MESMA publicação já tem id confirmado, não há o que subir:
        # devolver UPLOADED sem tocar na rede. `claim`/`claim_retry` já filtram esse caso; a guarda
        # existe para que nem um repositório mais permissivo consiga reenviar um vídeo já publicado.
        if pub.youtube_video_id:
            return PublicationRun(PublicationResult.UPLOADED, publication=pub, youtube_video_id=pub.youtube_video_id)
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
        blocked = self._authorization_gate(pub, project_id, access_token.youtube_channel_id)
        if blocked is not None:
            return blocked
        try:
            result = self.uploads.upload(request, access_token.token)
        except Exception as exc:
            # W5.2: uma exceção do adaptador **não prova** que o YouTube não recebeu o vídeo. Sem
            # resultado e sem poder descartar um efeito externo, o estado é ambíguo: reenviar poderia
            # duplicar o upload. Vai para `UNKNOWN`/reconciliação, nunca para retry automático.
            return self._ambiguous(pub, f"the uploader raised ({type(exc).__name__}); the remote state is unknown")
        return self._settle(pub, result)

    def _settle(self, pub: Publication, result) -> PublicationRun:
        error = (result.error or "")[:500] or "upload failed"
        if result.outcome is UploadOutcome.UPLOADED:
            if not result.youtube_video_id:
                return self._ambiguous(pub, "the uploader reported success without a video id")
            try:
                saved = self.pubs.mark_uploaded(pub.id, result.youtube_video_id)
            except PublicationConflict:
                # Outro id já gravado para o vídeo: conflito real, não sobrescreve — exige humano.
                return self._blocked(pub, "the video already has another YouTube id recorded")
            except Exception as exc:
                # O vídeo existe no YouTube, mas não conseguimos gravar o id. Reconciliação resolve
                # (o id é recuperável); DLQ esconderia um sucesso real.
                return self._ambiguous(pub, f"the YouTube id could not be recorded ({type(exc).__name__})")
            if saved is None:
                return self._ambiguous(pub, "the publication disappeared while recording the YouTube id")
            return PublicationRun(PublicationResult.UPLOADED, publication=saved,
                                  youtube_video_id=result.youtube_video_id)
        if result.outcome is UploadOutcome.INCOMPLETE:
            session_uri = result.upload_uri or pub.upload_uri
            if not session_uri:
                return self._ambiguous(pub, "the uploader reported an incomplete session without a session URL")
            if not self.pubs.record_session(pub.id, pub.attempt, session_uri, result.offset):
                # Sem a sessão gravada, o retry abriria uma NOVA sessão: risco de segundo upload.
                return self._ambiguous(pub, "the upload session could not be recorded; reconcile before retrying")
            return self._retry(pub, error, FailureClass.TRANSIENT)
        if result.outcome is UploadOutcome.RETRYABLE:
            if result.upload_uri and result.upload_uri != pub.upload_uri:
                if not self.pubs.record_session(pub.id, pub.attempt, result.upload_uri, result.offset):
                    return self._ambiguous(pub, "the upload session could not be recorded; reconcile before retrying")
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