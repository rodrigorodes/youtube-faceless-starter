"""Identidade de publicação do YouTube: conta → autorizações → canais (YT-01). Puro.

Separa o que a associação antiga (`channel_youtube_channels`, por projeto) confundia:

- `GoogleAccount` — a identidade (e-mail). **Não** é dona da autorização.
- `OAuthGrant` — a autorização independente: escopos, status, expiração (tokens no vault).
- `YouTubeChannelIdentity` — a identidade oficial do canal (`UC...`), distinta da conta.
- `ChannelAuthorization` — o vínculo **validado** entre uma autorização e um canal.

Princípio: **cada canal publicado tem uma autorização validada para ele**; nunca se presume
que uma autorização seja intercambiável entre canais. Se um dia se provar o contrário, o
modelo absorve (um grant com várias autorizações) sem migração estrutural.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .ids import check_id
from .youtube_channel import OAuthStatus
from .youtube_oauth import derive_channel_status

MAX_EMAIL = 320
MAX_DISPLAY_NAME = 200
MAX_CHANNEL_ID = 128
MAX_TITLE = 200
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CHANNEL_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
STATUSES = frozenset({"CONNECTED", "EXPIRED", "REVOKED", "ERROR"})


class YouTubeIdentityError(Exception):
    """Erro base da identidade de publicação."""


class GoogleAccountInvalid(YouTubeIdentityError, ValueError):
    """E-mail, nome de exibição ou id inválidos."""


class OAuthGrantInvalid(YouTubeIdentityError, ValueError):
    """Escopos, status ou conta da autorização inválidos."""


class YouTubeChannelIdentityInvalid(YouTubeIdentityError, ValueError):
    """Identidade de canal inválida (id vazio/malformado ou título longo)."""


class ChannelAuthorizationInvalid(YouTubeIdentityError, ValueError):
    """Vínculo autorização↔canal inválido (ids, status ou data de validação)."""


def _status(value: object) -> OAuthStatus:
    if isinstance(value, OAuthStatus):
        return value
    if not isinstance(value, str) or value not in STATUSES:
        raise OAuthGrantInvalid(f"status must be one of {sorted(STATUSES)}")
    return OAuthStatus(value)


def validate_email(email: object) -> str:
    if not isinstance(email, str):
        raise GoogleAccountInvalid("email must be a string")
    cleaned = email.strip()
    if not (3 <= len(cleaned) <= MAX_EMAIL) or not _EMAIL_RE.match(cleaned):
        raise GoogleAccountInvalid("email must be a valid address")
    return cleaned


def validate_youtube_channel_id(channel_id: object) -> str:
    if not isinstance(channel_id, str):
        raise YouTubeChannelIdentityInvalid("youtube_channel_id must be a string")
    cleaned = channel_id.strip()
    if not (1 <= len(cleaned) <= MAX_CHANNEL_ID) or not _CHANNEL_ID_RE.match(cleaned):
        raise YouTubeChannelIdentityInvalid("youtube_channel_id has an invalid format")
    return cleaned


@dataclass(frozen=True)
class GoogleAccount:
    """A identidade de uma Conta Google (pode administrar vários canais)."""

    id: str
    email: str
    display_name: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        check_id(self.id)
        object.__setattr__(self, "email", validate_email(self.email))
        if not isinstance(self.display_name, str) or len(self.display_name.strip()) > MAX_DISPLAY_NAME:
            raise GoogleAccountInvalid(f"display_name must be at most {MAX_DISPLAY_NAME} characters")
        object.__setattr__(self, "display_name", self.display_name.strip())


@dataclass(frozen=True)
class OAuthGrant:
    """Uma autorização independente: escopos, status e ciclo de vida próprios.

    Os tokens vivem no vault (escopo `oauth_grant:{id}`); esta entidade nunca os carrega.
    """

    id: str
    account_id: str
    scopes: tuple[str, ...] = ()
    status: OAuthStatus = OAuthStatus.CONNECTED
    token_expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        check_id(self.id)
        check_id(self.account_id)
        cleaned: list[str] = []
        for scope in tuple(self.scopes):
            if not isinstance(scope, str) or not scope.strip():
                raise OAuthGrantInvalid("every scope must be a non-empty string")
            if scope.strip() not in cleaned:
                cleaned.append(scope.strip())
        object.__setattr__(self, "scopes", tuple(cleaned))
        object.__setattr__(self, "status", _status(self.status))
        if self.token_expires_at is not None and not isinstance(self.token_expires_at, datetime):
            raise OAuthGrantInvalid("token_expires_at must be a datetime")

    def effective_status(self, *, has_credentials: bool, now: datetime,
                         revoked: bool = False) -> OAuthStatus:
        """Estado real da autorização — derivado de credencial/revogação/expiração, nunca presumido."""
        return OAuthStatus(derive_channel_status(has_credentials=has_credentials, revoked=revoked,
                                                 expires_at=self.token_expires_at, now=now,
                                                 stored=self.status.value))


@dataclass(frozen=True)
class YouTubeChannelIdentity:
    """A identidade oficial do canal (`UC...`). Um canal, não uma conta."""

    youtube_channel_id: str
    title: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "youtube_channel_id", validate_youtube_channel_id(self.youtube_channel_id))
        if not isinstance(self.title, str) or len(self.title.strip()) > MAX_TITLE:
            raise YouTubeChannelIdentityInvalid(f"title must be at most {MAX_TITLE} characters")
        object.__setattr__(self, "title", self.title.strip())


@dataclass(frozen=True)
class ChannelAuthorization:
    """O vínculo **validado** entre uma autorização e um canal.

    Existir a linha já é a afirmação de que a conferência foi feita; `validated_at` é quando.
    Não se presume o vínculo: quem grava é o resultado de uma verificação (`channels.list`).
    """

    grant_id: str
    youtube_channel_id: str
    status: OAuthStatus = OAuthStatus.CONNECTED
    validated_at: datetime | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        check_id(self.grant_id)
        object.__setattr__(self, "youtube_channel_id", validate_youtube_channel_id(self.youtube_channel_id))
        object.__setattr__(self, "status", _status(self.status))
        if self.validated_at is not None and not isinstance(self.validated_at, datetime):
            raise ChannelAuthorizationInvalid("validated_at must be a datetime")
