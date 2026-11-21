"""Cliente OAuth do Google/YouTube (F8-05). HTTP injetável; nenhum SDK de provedor no núcleo.

O adaptador só transporta: a classificação de erro e a política de escopos ficam em
`domain/youtube_oauth.py`. Mensagens de erro citam apenas o código OAuth (`invalid_grant` etc.),
nunca o corpo da resposta, o client secret ou tokens.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..application.ports import OAuthClient
from ..domain.youtube_oauth import (
    AUTH_ENDPOINT,
    DEFAULT_SCOPES,
    REVOKE_ENDPOINT,
    TOKEN_ENDPOINT,
    OAuthConfigurationError,
    OAuthError,
    OAuthIdentity,
    OAuthReconnectRequired,
    OAuthTokenResponse,
    OAuthTransientError,
    authorization_url,
    classify_token_error,
)

CHANNELS_ENDPOINT = "https://www.googleapis.com/youtube/v3/channels"
_SAFE_CODE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_code(value: object) -> str:
    return _SAFE_CODE.sub("", str(value))[:40] if value is not None else ""


def _error_code(body: object) -> str:
    """Extrai só o código do erro (Google devolve `error` string ou objeto com `code`)."""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, str):
            return error
        if isinstance(error, dict):
            return _safe_code(error.get("status") or error.get("code") or "")
        return _safe_code(body.get("error_code") or "")
    return ""


class GoogleOAuthClient(OAuthClient):
    """`authorization code → token → refresh → revoke` com endpoints fixos do Google."""

    def __init__(self, client_id: str, secret: str, *, transport: httpx.BaseTransport | None = None,
                 redirect_uri: str | None = None, timeout: float = 10.0,
                 token_endpoint: str = TOKEN_ENDPOINT, revoke_endpoint: str = REVOKE_ENDPOINT,
                 channels_endpoint: str = CHANNELS_ENDPOINT,
                 clock=lambda: datetime.now(timezone.utc)):
        if not isinstance(client_id, str) or not client_id.strip():
            raise OAuthConfigurationError("the OAuth client_id is missing")
        if not isinstance(secret, str) or not secret.strip():
            raise OAuthConfigurationError("the OAuth client secret is missing")
        for endpoint in (token_endpoint, revoke_endpoint, channels_endpoint):
            if not endpoint.startswith("https://") or any(ch in endpoint for ch in " \t\r\n"):
                raise OAuthConfigurationError("OAuth endpoints must be fixed HTTPS URLs")
        self._client_id = client_id.strip()
        self._secret = secret.strip()
        self._redirect_uri = redirect_uri
        self._transport = transport
        self._timeout = timeout
        self._token_endpoint = token_endpoint
        self._revoke_endpoint = revoke_endpoint
        self._channels_endpoint = channels_endpoint
        self._clock = clock

    def __repr__(self) -> str:
        # client_secret nunca entra no repr: logs e tracebacks são superfície de vazamento.
        redirect = self._redirect_uri or "unset"
        return f"GoogleOAuthClient(client_id={self._client_id!r}, redirect_uri={redirect!r}, secret=***)"

    __str__ = __repr__

    def _http(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=self._timeout, follow_redirects=False)

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            with self._http() as http:
                return http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise OAuthTransientError(f"OAuth request failed ({type(exc).__name__})") from None

    def _form(self, **values) -> dict:
        form = dict(values)
        form["client_secret"] = self._secret
        return form

    def _token_request(self, form: dict) -> OAuthTokenResponse:
        response = self._request("POST", self._token_endpoint, data=form,
                                 headers={"Accept": "application/json"})
        if not 200 <= response.status_code < 300:
            try:
                body = response.json()
            except ValueError:
                body = {}
            code = _error_code(body)
            error = classify_token_error(response.status_code, code)
            raise error(f"the OAuth token endpoint refused the request ({code or 'HTTP ' + str(response.status_code)})")
        try:
            body = response.json()
        except ValueError:
            raise OAuthTransientError("the OAuth token endpoint returned a non-JSON response") from None
        access = body.get("access_token")
        if not isinstance(access, str) or not access.strip():
            raise OAuthTransientError("the OAuth token endpoint returned no access token")
        refresh = body.get("refresh_token")
        expires_in = body.get("expires_in")
        try:
            expires_in = int(expires_in)
        except (TypeError, ValueError):
            raise OAuthTransientError("the OAuth token endpoint returned an invalid expires_in") from None
        scope = body.get("scope")
        scopes = tuple(str(scope).split()) if isinstance(scope, str) and scope.strip() else DEFAULT_SCOPES
        return OAuthTokenResponse(access_token=access.strip(), refresh_token=refresh if isinstance(refresh, str) and refresh.strip() else None,
                                  expires_in=expires_in, scopes=scopes, token_type=str(body.get("token_type") or "Bearer"))

    def authorization_url(self, redirect_uri: str, scopes, state: str, code_challenge: str) -> str:
        if self._redirect_uri is not None and redirect_uri != self._redirect_uri:
            raise ValueError("redirect_uri does not match the configured OAuth callback")
        allowed = (self._redirect_uri,) if self._redirect_uri is not None else None
        return authorization_url(client_id=self._client_id, redirect_uri=redirect_uri, scopes=scopes,
                                 state=state, code_challenge=code_challenge,
                                 allowed_redirect_uris=allowed, auth_endpoint=AUTH_ENDPOINT)

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> OAuthTokenResponse:
        if not all(isinstance(value, str) and value.strip() for value in (code, redirect_uri, code_verifier)):
            raise OAuthConfigurationError("code, redirect_uri and code_verifier are required")
        return self._token_request(self._form(
            grant_type="authorization_code", code=code.strip(), redirect_uri=redirect_uri,
            code_verifier=code_verifier, client_id=self._client_id))

    def refresh(self, token: str) -> OAuthTokenResponse:
        if not isinstance(token, str) or not token.strip():
            raise OAuthReconnectRequired("there is no refresh token to use; reconnect the channel")
        return self._token_request(self._form(grant_type="refresh_token", refresh_token=token.strip(),
                                              client_id=self._client_id))

    def revoke(self, token: str) -> None:
        if not isinstance(token, str) or not token.strip():
            return
        response = self._request("POST", self._revoke_endpoint, data={"token": token.strip()})
        if 200 <= response.status_code < 300 or response.status_code == 404:
            return
        try:
            code = _error_code(response.json())
        except ValueError:
            code = ""
        if response.status_code == 400 and code == "invalid_token":
            return  # revogar duas vezes é idempotente, não falha
        error = classify_token_error(response.status_code, code)
        raise error(f"the OAuth revoke endpoint refused the request ({code or 'HTTP ' + str(response.status_code)})")

    def identity(self, access_token: str) -> OAuthIdentity:
        if not isinstance(access_token, str) or not access_token.strip():
            raise OAuthReconnectRequired("there is no access token to identify the channel")
        response = self._request("GET", self._channels_endpoint, params={"part": "snippet", "mine": "true"},
                                 headers={"Authorization": f"Bearer {access_token.strip()}", "Accept": "application/json"})
        if not 200 <= response.status_code < 300:
            try:
                code = _error_code(response.json())
            except ValueError:
                code = ""
            if response.status_code in (401, 403) or code in ("invalid_grant", "unauthorized"):
                raise OAuthReconnectRequired(f"the authorized account cannot read its YouTube channel ({code or 'HTTP ' + str(response.status_code)})")
            raise classify_token_error(response.status_code, code)(
                f"the YouTube identity request failed ({code or 'HTTP ' + str(response.status_code)})")
        try:
            items = response.json().get("items") or []
        except (ValueError, AttributeError):
            raise OAuthTransientError("the YouTube identity endpoint returned an invalid response") from None
        if not items or not isinstance(items[0], dict) or not str(items[0].get("id") or "").strip():
            raise OAuthReconnectRequired("the authorized account has no YouTube channel")
        title = items[0].get("snippet", {}).get("title", "") if isinstance(items[0].get("snippet"), dict) else ""
        return OAuthIdentity(channel_id=str(items[0]["id"]).strip(), title=str(title).strip()[:200])


def google_oauth_from_client_secret(path: Path | str, *, redirect_uri: str | None = None,
                                    transport: httpx.BaseTransport | None = None) -> GoogleOAuthClient:
    """Lê o JSON de client secret **do caminho original** (somente leitura) e monta o cliente.

    O arquivo nunca é copiado para a worktree; o conteúdo só existe em memória e não entra em
    `repr`/mensagens. O redirect, quando informado, precisa constar em `redirect_uris` do app.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise OAuthConfigurationError("the OAuth client secret file is unavailable or invalid") from None
    section = data.get("web") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        raise OAuthConfigurationError("the OAuth client secret file has no 'web' app section")
    client_id, client_secret = section.get("client_id"), section.get("client_secret")
    if not isinstance(client_id, str) or not isinstance(client_secret, str) or not client_id.strip() or not client_secret.strip():
        raise OAuthConfigurationError("the OAuth client secret file is missing client_id/client_secret")
    if redirect_uri is not None:
        registered = [str(item) for item in (section.get("redirect_uris") or []) if isinstance(item, str)]
        # `redirect_uris` vazio: o app não declarou a lista; a validação de forma (https/loopback)
        # continua no domínio, mas não inventamos uma allowlist que o arquivo não tem.
        if registered and redirect_uri not in registered:
            raise OAuthConfigurationError("the OAuth redirect is not registered in the client secret app")
    return GoogleOAuthClient(client_id, client_secret, transport=transport, redirect_uri=redirect_uri,
                             token_endpoint=str(section.get("token_uri") or TOKEN_ENDPOINT),
                             channels_endpoint=CHANNELS_ENDPOINT)