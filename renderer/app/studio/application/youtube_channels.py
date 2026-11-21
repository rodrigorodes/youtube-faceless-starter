"""Associação de canal YouTube e status OAuth (F10-06) com segredos fora do banco (F10-07).

Os metadados (canal, escopos, status, expiração) ficam no Postgres; access/refresh tokens ficam no
`SecretStore` (vault). Nenhuma resposta montada aqui devolve token: `public()` só traz metadados.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from ..domain.ids import check_id
from ..domain.youtube_channel import YouTubeChannel, YouTubeChannelInvalid
from .errors import ServiceUnavailable
from .ports import SecretStore, YouTubeChannelRepository

ACCESS_TOKEN = "access_token"
REFRESH_TOKEN = "refresh_token"
_KEYS = (ACCESS_TOKEN, REFRESH_TOKEN)


def youtube_scope(project_id: str) -> str:
    return f"youtube:{check_id(project_id)}"


def _safe(operation):
    try:
        return operation()
    except Exception as exc:  # cofre indisponível vira 503, nunca 500 cru
        raise ServiceUnavailable("secret store unavailable") from exc


def _has_credentials(store: SecretStore, scope: str) -> bool:
    names = set(_safe(lambda: store.names(scope)))
    return bool(names & set(_KEYS))


class AssociateYouTubeChannel:
    def __init__(self, repo: YouTubeChannelRepository, secrets: SecretStore):
        self.repo = repo
        self.secrets = secrets

    def execute(self, project_id: str, *, channel_id: str, title: str = "",
                scopes: Sequence[str] = (), access_token: str | None = None,
                refresh_token: str | None = None,
                token_expires_at: datetime | None = None) -> dict[str, object]:
        p_id = check_id(project_id)
        if not (refresh_token and refresh_token.strip()) and not (access_token and access_token.strip()):
            raise YouTubeChannelInvalid("a YouTube access_token or refresh_token is required")
        channel = YouTubeChannel(project_id=p_id, channel_id=channel_id, title=title,
                                 scopes=tuple(scopes), token_expires_at=token_expires_at)
        scope = youtube_scope(p_id)
        written: list[str] = []
        try:
            for key, value in ((ACCESS_TOKEN, access_token), (REFRESH_TOKEN, refresh_token)):
                if value and value.strip():
                    _safe(lambda k=key, v=value: self.secrets.set(scope, k, v))
                    written.append(key)
            saved = self.repo.upsert(channel)
        except BaseException:
            # não deixa token órfão se o vínculo com o canal não foi persistido
            for key in written:
                _safe(lambda k=key: self.secrets.delete(scope, k))
            raise
        return saved.public(has_credentials=True)


class GetYouTubeChannel:
    def __init__(self, repo: YouTubeChannelRepository, secrets: SecretStore,
                 now=lambda: datetime.now(timezone.utc)):
        self.repo = repo
        self.secrets = secrets
        self.now = now

    def execute(self, project_id: str) -> dict[str, object]:
        p_id = check_id(project_id)
        channel = self.repo.get(p_id)
        if channel is None:
            return {"project_id": p_id, "channel_id": None, "title": "", "scopes": [],
                    "oauth_status": "DISCONNECTED", "connected": False,
                    "token_expires_at": None, "updated_at": None}
        return channel.public(has_credentials=_has_credentials(self.secrets, youtube_scope(p_id)),
                              now=self.now())


class DisconnectYouTubeChannel:
    def __init__(self, repo: YouTubeChannelRepository, secrets: SecretStore):
        self.repo = repo
        self.secrets = secrets

    def execute(self, project_id: str) -> bool:
        p_id = check_id(project_id)
        scope = youtube_scope(p_id)
        removed = self.repo.delete(p_id)
        for key in _KEYS:
            _safe(lambda k=key: self.secrets.delete(scope, k))
        for key in _safe(lambda: self.secrets.names(scope)):  # limpa qualquer chave extra do escopo
            _safe(lambda k=key: self.secrets.delete(scope, k))
        return removed