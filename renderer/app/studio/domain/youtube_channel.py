"""Associação de canal YouTube e status OAuth (F10-06). Puro: nunca carrega tokens.

O status efetivo é derivado no momento da leitura: sem credenciais no vault, o canal é DISCONNECTED
mesmo que exista linha no banco; token vencido vira EXPIRED. `public()` devolve só metadados.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .ids import check_id

MAX_CHANNEL_ID = 128
MAX_TITLE = 200
_CHANNEL_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class YouTubeChannelError(Exception):
    """Erro base da associação de canal YouTube."""


class YouTubeChannelInvalid(YouTubeChannelError, ValueError):
    """Identidade de canal, título ou credenciais inválidos."""


class OAuthStatus(str, Enum):
    CONNECTED = "CONNECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    ERROR = "ERROR"
    DISCONNECTED = "DISCONNECTED"  # derivado: sem credenciais no vault


@dataclass(frozen=True)
class YouTubeChannel:
    project_id: str
    channel_id: str
    title: str = ""
    scopes: tuple[str, ...] = ()
    oauth_status: OAuthStatus = OAuthStatus.CONNECTED
    token_expires_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", check_id(self.project_id))
        if not isinstance(self.channel_id, str) or not self.channel_id.strip():
            raise YouTubeChannelInvalid("youtube channel_id is required")
        cleaned = self.channel_id.strip()
        if len(cleaned) > MAX_CHANNEL_ID or not _CHANNEL_ID_RE.match(cleaned):
            raise YouTubeChannelInvalid("youtube channel_id has an invalid format")
        object.__setattr__(self, "channel_id", cleaned)
        if not isinstance(self.title, str) or len(self.title.strip()) > MAX_TITLE:
            raise YouTubeChannelInvalid(f"title must be at most {MAX_TITLE} characters")
        object.__setattr__(self, "title", self.title.strip())
        scopes = tuple(self.scopes)
        for scope in scopes:
            if not isinstance(scope, str) or not scope.strip():
                raise YouTubeChannelInvalid("scopes must be non-empty strings")
        object.__setattr__(self, "scopes", scopes)
        if not isinstance(self.oauth_status, OAuthStatus):
            object.__setattr__(self, "oauth_status", OAuthStatus(self.oauth_status))
        if self.token_expires_at is not None and not isinstance(self.token_expires_at, datetime):
            raise YouTubeChannelInvalid("token_expires_at must be a datetime")

    def effective_status(self, *, has_credentials: bool, now: datetime | None = None) -> OAuthStatus:
        if not has_credentials:
            return OAuthStatus.DISCONNECTED
        if self.token_expires_at is not None and now is not None and self.token_expires_at <= now:
            return OAuthStatus.EXPIRED
        return self.oauth_status

    def public(self, *, has_credentials: bool, now: datetime | None = None) -> dict[str, object]:
        status = self.effective_status(has_credentials=has_credentials, now=now)
        return {
            "project_id": self.project_id,
            "channel_id": self.channel_id,
            "title": self.title,
            "scopes": list(self.scopes),
            "oauth_status": status.value,
            "connected": status is OAuthStatus.CONNECTED,
            "token_expires_at": self.token_expires_at.isoformat() if self.token_expires_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
