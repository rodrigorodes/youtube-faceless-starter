"""Upload resumable nativo do YouTube (F8-03/F8-04). HTTP injetável; sem SDK de provedor.

Garantias que o adaptador sustenta:
- a sessão resumable é a **única** fonte de identidade do upload: repetir dentro dela nunca cria
  um segundo vídeo; uma sessão expirada (404/410) ou um ACK sem id nunca viram "sucesso";
- o corpo da resposta nunca entra na mensagem de erro (evita vazar token/eco de payload);
- o destino do upload é validado (`valid_upload_uri`) antes de o token ser enviado.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from ..application.ports import UploadOutcome, UploadRequest, UploadResult
from ..domain.publish import valid_upload_uri, valid_youtube_id

UPLOAD_INIT = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"
_CHUNK = 8 * 1024 * 1024


def _safe_error(context: str, status: int | None = None, exc: Exception | None = None) -> str:
    if exc is not None:
        return f"{context} failed ({type(exc).__name__})"
    return f"{context} failed (HTTP {status})"


class GoogleYouTubeUploader:
    """Fala com a API de upload do YouTube por `httpx`, com transporte injetável."""

    def __init__(self, *, transport: httpx.BaseTransport | None = None, timeout: float = 60.0):
        self._transport = transport
        self._timeout = timeout

    def __repr__(self) -> str:
        return "GoogleYouTubeUploader(transport=***)"

    __str__ = __repr__

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            with self._client() as http:
                return http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            from ..domain.youtube_oauth import OAuthTransientError
            raise OAuthTransientError(f"YouTube request failed ({type(exc).__name__})") from None

    def _client(self, timeout: float | None = None) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=timeout or self._timeout, follow_redirects=False)

    def _probe(self, session_uri: str, size: int, access_token: str) -> UploadResult:
        """Pergunta à sessão em que ponto ela está. Nunca devolve sucesso sem id do YouTube."""
        try:
            with self._client() as http:
                response = http.put(session_uri, content=b"",
                                    headers={"Authorization": f"Bearer {access_token}", "Content-Range": f"bytes */{size}"})
        except httpx.HTTPError as exc:
            return UploadResult(UploadOutcome.RETRYABLE, upload_uri=session_uri, error=_safe_error("session probe", exc=exc))
        status = response.status_code
        if status in (200, 201, 202):
            video_id = self._video_id(response)
            if video_id is None:
                return UploadResult(UploadOutcome.AMBIGUOUS, upload_uri=session_uri,
                                    error="the session is complete but the response has no video id")
            return UploadResult(UploadOutcome.UPLOADED, youtube_video_id=video_id, upload_uri=session_uri)
        if status == 308:
            offset = self._offset(response)
            if offset >= size:
                return UploadResult(UploadOutcome.AMBIGUOUS, upload_uri=session_uri,
                                    error="all bytes acknowledged without a video id; reconcile manually")
            return UploadResult(UploadOutcome.INCOMPLETE, upload_uri=session_uri, offset=offset)
        if status in (404, 410):
            return UploadResult(UploadOutcome.AMBIGUOUS, upload_uri=session_uri,
                                error=f"upload session unavailable (HTTP {status}); reconcile before a new upload")
        if status in (401, 403):
            return UploadResult(UploadOutcome.PERMANENT, upload_uri=session_uri, error=_safe_error("session probe", status))
        return UploadResult(UploadOutcome.RETRYABLE, upload_uri=session_uri, error=_safe_error("session probe", status))

    def _new_session(self, request: UploadRequest, access_token: str) -> UploadResult | str:
        try:
            with self._client() as http:
                response = http.post(UPLOAD_INIT, json=request.youtube_body, headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Upload-Content-Type": request.content_type,
                    "X-Upload-Content-Length": str(request.file_size)})
        except httpx.HTTPError as exc:
            return UploadResult(UploadOutcome.RETRYABLE, error=_safe_error("session creation", exc=exc))
        if response.status_code not in (200, 201):
            from ..domain.publication_policy import FailureClass, classify_http
            kind = classify_http(response.status_code)
            outcome = {FailureClass.TRANSIENT: UploadOutcome.RETRYABLE, FailureClass.PERMANENT: UploadOutcome.PERMANENT,
                       FailureClass.AMBIGUOUS: UploadOutcome.AMBIGUOUS}[kind]
            return UploadResult(outcome, error=_safe_error("session creation", response.status_code))
        location = response.headers.get("Location") or response.headers.get("location")
        if not valid_upload_uri(location):
            return UploadResult(UploadOutcome.PERMANENT, error="the session response had no valid YouTube upload URL")
        return location

    def _send_chunk(self, request: UploadRequest, session_uri: str, offset: int, access_token: str) -> UploadResult:
        size = request.file_size
        try:
            with self._client(timeout=max(self._timeout, 30 * 60)) as http, Path(request.file_path).open("rb") as handle:
                handle.seek(offset)
                response = http.put(session_uri, content=handle.read(),
                                    headers={"Authorization": f"Bearer {access_token}",
                                             "Content-Type": request.content_type,
                                             "Content-Range": f"bytes {offset}-{max(offset, size - 1)}/{size}"})
        except httpx.HTTPError as exc:  # mesma sessão: repetir não cria um segundo vídeo
            return UploadResult(UploadOutcome.RETRYABLE, upload_uri=session_uri, offset=offset, error=_safe_error("upload", exc=exc))
        status = response.status_code
        if status in (200, 201, 202):
            video_id = self._video_id(response)
            if video_id is None:
                return UploadResult(UploadOutcome.AMBIGUOUS, upload_uri=session_uri,
                                    error="the upload finished but the response has no video id")
            return UploadResult(UploadOutcome.UPLOADED, youtube_video_id=video_id, upload_uri=session_uri)
        if status == 308:
            acknowledged = self._offset(response)
            if acknowledged >= size:
                return UploadResult(UploadOutcome.AMBIGUOUS, upload_uri=session_uri,
                                    error="all bytes acknowledged without a video id; reconcile manually")
            return UploadResult(UploadOutcome.INCOMPLETE, upload_uri=session_uri, offset=acknowledged)
        if status in (404, 410):
            return UploadResult(UploadOutcome.AMBIGUOUS, upload_uri=session_uri,
                                error=f"upload session unavailable (HTTP {status}); reconcile before a new upload")
        if status in (401, 403):
            return UploadResult(UploadOutcome.PERMANENT, upload_uri=session_uri, error=_safe_error("upload", status))
        from ..domain.publication_policy import FailureClass, classify_http
        kind = classify_http(status)
        outcome = {FailureClass.TRANSIENT: UploadOutcome.RETRYABLE, FailureClass.PERMANENT: UploadOutcome.PERMANENT,
                   FailureClass.AMBIGUOUS: UploadOutcome.AMBIGUOUS}[kind]
        return UploadResult(outcome, upload_uri=session_uri, offset=offset, error=_safe_error("upload", status))

    @staticmethod
    def _video_id(response: httpx.Response) -> str | None:
        try:
            body = response.json()
        except ValueError:
            return None
        value = body.get("id") if isinstance(body, dict) else None
        return value if valid_youtube_id(value) else None

    @staticmethod
    def _offset(response: httpx.Response) -> int:
        rng = response.headers.get("Range") or response.headers.get("range") or ""
        if not rng.startswith("bytes=0-"):
            return 0
        try:
            return int(rng.split("-", 1)[1].split("/", 1)[0]) + 1
        except ValueError:
            return 0

    def upload(self, request: UploadRequest, access_token: str) -> UploadResult:
        session_uri = request.upload_uri
        offset = max(0, int(request.offset))
        if session_uri is not None:
            if not valid_upload_uri(session_uri):
                return UploadResult(UploadOutcome.PERMANENT, error="the recorded upload session is not a YouTube resumable URL")
            probed = self._probe(session_uri, request.file_size, access_token)
            if probed.outcome is not UploadOutcome.INCOMPLETE:
                return probed
            offset = probed.offset
        else:
            created = self._new_session(request, access_token)
            if isinstance(created, UploadResult):
                return created
            session_uri = created
        return self._send_chunk(request, session_uri, offset, access_token)

    def lookup(self, youtube_video_id: str, access_token: str) -> bool:
        """Confirma se o vídeo existe no canal (leitura; nunca inventa existência)."""
        if not valid_youtube_id(youtube_video_id):
            raise ValueError("invalid YouTube video id")
        response = self._request("GET", VIDEOS_API, params={"part": "status", "id": youtube_video_id},
                                 headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
        if response.status_code in (401, 403):
            from ..domain.youtube_oauth import OAuthReconnectRequired
            raise OAuthReconnectRequired("the channel cannot read the video (reconnect required)")
        if not 200 <= response.status_code < 300:
            from ..domain.youtube_oauth import OAuthTransientError
            raise OAuthTransientError(f"video lookup failed (HTTP {response.status_code})")
        try:
            return bool(response.json().get("items"))
        except (ValueError, AttributeError):
            from ..domain.youtube_oauth import OAuthTransientError
            raise OAuthTransientError("video lookup returned an invalid response") from None

    def delete(self, youtube_video_id: str, access_token: str) -> bool:
        """Apaga um vídeo de teste; 404 conta como já removido (idempotente)."""
        if not valid_youtube_id(youtube_video_id):
            raise ValueError("invalid YouTube video id")
        response = self._request("DELETE", VIDEOS_API, params={"id": youtube_video_id},
                                 headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
        if response.status_code in (200, 204, 404):
            return True
        if response.status_code in (401, 403):
            from ..domain.youtube_oauth import OAuthReconnectRequired
            raise OAuthReconnectRequired("the channel cannot delete the video (reconnect or permission required)")
        from ..domain.youtube_oauth import OAuthTransientError
        raise OAuthTransientError(f"video delete failed (HTTP {response.status_code})")

    def reconcile(self, request: UploadRequest, access_token: str) -> UploadResult:
        if request.upload_uri is None:
            # Sem sessão criada, não existe efeito externo a reconciliar: reiniciar é seguro.
            return UploadResult(UploadOutcome.RETRYABLE, error="no upload session was created; safe to start over")
        if not valid_upload_uri(request.upload_uri):
            return UploadResult(UploadOutcome.AMBIGUOUS, error="the recorded upload session is not a YouTube resumable URL")
        try:
            with self._client() as http:
                response = http.put(request.upload_uri, content="", headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Range": f"bytes */{request.file_size}"})
        except httpx.HTTPError as exc:
            return UploadResult(UploadOutcome.AMBIGUOUS, upload_uri=request.upload_uri, error=_safe_error("reconcile", exc=exc))
        if response.status_code in (200, 201, 202):
            video_id = self._video_id(response)
            if video_id is None:
                return UploadResult(UploadOutcome.AMBIGUOUS, upload_uri=request.upload_uri,
                                    error="the session is complete but the response has no video id")
            return UploadResult(UploadOutcome.UPLOADED, youtube_video_id=video_id, upload_uri=request.upload_uri)
        if response.status_code == 308:
            return UploadResult(UploadOutcome.INCOMPLETE, upload_uri=request.upload_uri, offset=self._offset(response))
        return UploadResult(UploadOutcome.AMBIGUOUS, upload_uri=request.upload_uri,
                            error=_safe_error("reconcile", response.status_code))