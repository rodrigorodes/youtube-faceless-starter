"""OAuth 2.0 do YouTube/Google — regras puras (F8-05).

Nada aqui toca rede ou SDK: só valida escopos, monta a URL de consentimento, deriva a expiração
dos tokens e classifica erros. Tokens são valores sensíveis: `OAuthTokenSet` mascara o próprio
`repr`/`str` para que um log acidental não vaze access/refresh token.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
DEFAULT_SCOPES = (YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE)
EMAIL_SCOPE = "https://www.googleapis.com/auth/userinfo.email"
# Conexões por conta: além do YouTube, o e-mail identifica a conta Google (a API do YouTube não o expõe).
ACCOUNT_SCOPES = DEFAULT_SCOPES + (EMAIL_SCOPE,)
# Ao conceder `userinfo.email`, o Google devolve na resposta do token também estes nomes curtos (OIDC).
OPENID_SCOPES = frozenset({"openid", "email", "profile"})
TOKEN_SKEW = timedelta(seconds=120)  # nunca usar um token que vence durante a requisição
_STATE_MIN, _STATE_MAX = 16, 256
_VERIFIER_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


class OAuthError(RuntimeError):
    """Erro de OAuth; a mensagem nunca contém tokens nem o client secret."""


class OAuthConfigurationError(OAuthError):
    """Configuração do app OAuth inválida (client/escopo). Exige correção de configuração."""


class OAuthReconnectRequired(OAuthError):
    """O consentimento não vale mais (invalid_grant, revogado, escopo retirado): reconectar."""


class OAuthScopeMissing(OAuthConfigurationError):
    """O consentimento não inclui o escopo de upload do YouTube."""


class OAuthTransientError(OAuthError):
    """Falha transitória do provedor (rede, 429, 5xx): pode repetir."""


def mask(value: str | None) -> str:
    """Forma segura de citar um valor sensível: só 3 primeiros e 4 últimos caracteres."""
    if not value or len(value) <= 8:
        return "***"
    return f"{value[:3]}…{value[-4:]}"


def _token_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_scopes(scopes: Sequence[str]) -> tuple[str, ...]:
    """Escopos válidos, sem duplicata, e obrigatoriamente com `youtube.upload`."""
    cleaned: list[str] = []
    for scope in scopes:
        if not isinstance(scope, str) or not scope.strip():
            raise OAuthScopeMissing("every OAuth scope must be a non-empty string")
        scope = scope.strip()
        if scope in OPENID_SCOPES:
            if scope not in cleaned:
                cleaned.append(scope)
            continue
        if not scope.startswith("https://") or " " in scope:
            raise OAuthScopeMissing("OAuth scopes must be https URLs")
        if scope not in cleaned:
            cleaned.append(scope)
    if YOUTUBE_UPLOAD_SCOPE not in cleaned:
        raise OAuthScopeMissing("the YouTube upload scope is required to publish")
    return tuple(cleaned)


def pkce_pair(verifier: str | None = None) -> tuple[str, str]:
    """PKCE S256: `(verifier, challenge)`. Sem `verifier`, gera um aleatório de 64 caracteres."""
    if verifier is None:
        verifier = secrets.token_urlsafe(48)
    if not 43 <= len(verifier) <= 128 or any(ch not in _VERIFIER_CHARS for ch in verifier):
        raise ValueError("the PKCE verifier must be 43..128 URL-safe characters")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _allowed_redirect(uri: str, allowed: Sequence[str] | None) -> bool:
    if not isinstance(uri, str) or uri != uri.strip() or not uri:
        return False
    try:
        parts = urlsplit(uri)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.fragment:
        return False
    if parts.scheme == "http" and parts.hostname not in ("localhost", "127.0.0.1", "::1"):
        return False
    if allowed is not None and uri not in allowed:
        return False
    return port is None or 0 < port < 65536


def authorization_url(*, client_id: str, redirect_uri: str, scopes: Sequence[str], state: str,
                      code_challenge: str, allowed_redirect_uris: Sequence[str] | None = None,
                      auth_endpoint: str = AUTH_ENDPOINT) -> str:
    """URL de consentimento: `offline` (refresh token), `consent` (reemite) e PKCE S256."""
    if not isinstance(client_id, str) or not client_id.strip() or " " in client_id.strip():
        raise ValueError("client_id is required")
    if not isinstance(state, str) or not _STATE_MIN <= len(state) <= _STATE_MAX or not state.strip():
        raise ValueError("state is required")
    if not isinstance(code_challenge, str) or not code_challenge or code_challenge != code_challenge.strip():
        raise ValueError("code_challenge is required")
    if not _allowed_redirect(redirect_uri, allowed_redirect_uris):
        raise ValueError("redirect_uri is not an allowed OAuth callback")
    endpoint = urlsplit(auth_endpoint)
    if endpoint.scheme != "https" or endpoint.hostname != "accounts.google.com":
        raise ValueError("the authorization endpoint must be Google's HTTPS endpoint")
    query = urlencode({
        "response_type": "code",
        "client_id": client_id.strip(),
        "redirect_uri": redirect_uri,
        "scope": " ".join(validate_scopes(scopes)),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    })
    return f"{auth_endpoint}?{query}"


@dataclass(frozen=True)
class OAuthTokenResponse:
    """Resposta crua do endpoint de token (adaptador converte para `OAuthTokenSet`)."""

    access_token: str
    refresh_token: str | None
    expires_in: int
    scopes: tuple[str, ...]
    token_type: str = "Bearer"


@dataclass(frozen=True)
class OAuthIdentity:
    """Identidade do canal autorizado, obtida com o access token (nunca do formulário).

    `email` é a identidade da **conta** quando o consentimento a expõe (escopos com e-mail do
    Google); fica vazia quando o provedor não a revela — a conta nunca é inventada a partir do
    canal. O consentimento antigo, por projeto, ignora este campo.
    """

    channel_id: str
    title: str = ""
    email: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.channel_id, str) or not self.channel_id.strip():
            raise ValueError("a YouTube channel id is required")
        if not isinstance(self.email, str):
            raise ValueError("the account email must be a string")


@dataclass(frozen=True)
class OAuthTokenSet:
    """Tokens já normalizados com expiração absoluta. `repr`/`str` nunca revelam os valores."""

    access_token: str = field(repr=False)
    expires_at: datetime
    refresh_token: str | None = field(default=None, repr=False)
    scopes: tuple[str, ...] = ()
    token_type: str = "Bearer"

    def __post_init__(self) -> None:
        if not self.access_token or not self.access_token.strip():
            raise ValueError("an access token is required")
        if self.refresh_token is not None and not self.refresh_token.strip():
            raise ValueError("a refresh token, when present, must be non-empty")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at needs a time zone")

    def is_expired(self, now: datetime, *, skew: timedelta = TOKEN_SKEW) -> bool:
        if now.tzinfo is None:
            raise ValueError("now needs a time zone")
        return self.expires_at <= now + skew

    def __repr__(self) -> str:
        refresh = mask(self.refresh_token) if self.refresh_token else "absent"
        return (f"OAuthTokenSet(access_token={mask(self.access_token)}, refresh_token={refresh}, "
                f"expires_at={self.expires_at.isoformat()}, scopes={len(self.scopes)})")

    __str__ = __repr__


def token_set_from_response(response: OAuthTokenResponse, *, now: datetime) -> OAuthTokenSet:
    if now.tzinfo is None:
        raise ValueError("now needs a time zone")
    access = _token_value(response.access_token)
    if not access:
        raise ValueError("the token response has no access token")
    if not isinstance(response.expires_in, int) or isinstance(response.expires_in, bool) or response.expires_in <= 0:
        raise ValueError("the token response has an invalid expires_in")
    refresh = _token_value(response.refresh_token) or None
    return OAuthTokenSet(access_token=access, refresh_token=refresh,
                         expires_at=now + timedelta(seconds=response.expires_in),
                         scopes=validate_scopes(response.scopes), token_type=response.token_type or "Bearer")


def classify_token_error(status: int | None, error_code: str | None) -> type[OAuthError]:
    """Classificação explícita: nunca transformar `invalid_grant` em retry silencioso."""
    code = (error_code or "").strip().lower()
    if status is None or status == 429 or 500 <= int(status) < 600:
        return OAuthTransientError
    if status == 401 or code in ("invalid_client", "invalid_scope", "unauthorized_client"):
        return OAuthConfigurationError
    return OAuthReconnectRequired


def derive_channel_status(*, has_credentials: bool, revoked: bool, expires_at: datetime | None,
                          now: datetime, stored: str = "CONNECTED") -> str:
    """Status real do canal: credencial presente + token não vencido. Nunca de campo digitado."""
    if not has_credentials and not revoked:
        return "DISCONNECTED"
    if revoked:
        return "REVOKED"
    if expires_at is not None and expires_at <= now:
        return "EXPIRED"
    return stored if stored in ("CONNECTED", "ERROR", "REVOKED", "EXPIRED") else "ERROR"