"""Repositórios Postgres da identidade de publicação do YouTube (YT-01b).

Quatro agregados da fatia YT-01 persistidos em tabelas próprias (migração 0035):
`google_accounts` → `oauth_grants` → `channel_authorizations` ← `youtube_channels`.

Estes repositórios guardam **só metadados**: os tokens vivem no vault (escopo
`oauth_grant:{id}`). Nenhuma coluna aqui carrega access/refresh token, e nenhum método
devolve segredo. As FKs violadas viram erros de domínio nomeados (conta/grant/canal
inexistente) para a aplicação responder com o motivo certo, nunca "erro genérico".

Nomes distintos do modelo antigo (`PostgresYouTubeChannelRepository`, em
`youtube_channel_repo.py`), que continua de pé até a fatia que religa a publicação.
"""
from __future__ import annotations

from collections.abc import Callable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...domain.ids import check_id
from ...domain.youtube_channel import OAuthStatus
from ...domain.youtube_identity import (
    STATUSES,
    ChannelAuthorization,
    ChannelAuthorizationInvalid,
    GoogleAccount,
    OAuthGrant,
    OAuthGrantInvalid,
    YouTubeChannelIdentity,
    validate_email,
    validate_youtube_channel_id,
)
from .editorial_repo import _Base
from .repo import _translated

_ACCOUNT_COLS = "id, email, display_name, created_at, updated_at"
_GRANT_COLS = "id, account_id, scopes, status, token_expires_at, created_at, updated_at"
_CHANNEL_COLS = "youtube_channel_id, title, created_at, updated_at"
_AUTHORIZATION_COLS = "grant_id, youtube_channel_id, status, validated_at, created_at"

# Sentinela: distingue "não informe o vencimento" de "limpe o vencimento" (None).
_UNSET = object()


def _account(row: dict) -> GoogleAccount:
    return GoogleAccount(**dict(row))


def _grant(row: dict) -> OAuthGrant:
    row = dict(row)
    row["scopes"] = tuple(row["scopes"] or ())
    row["status"] = OAuthStatus(row["status"])
    return OAuthGrant(**row)


def _channel(row: dict) -> YouTubeChannelIdentity:
    return YouTubeChannelIdentity(**dict(row))


def _authorization(row: dict) -> ChannelAuthorization:
    row = dict(row)
    row["status"] = OAuthStatus(row["status"])
    return ChannelAuthorization(**row)


def _stored_status(status: object) -> str:
    """Valida o status **armazenável**: DISCONNECTED é derivado, nunca persistido (CHECK da 0035)."""
    if isinstance(status, OAuthStatus):
        value = status.value
    elif isinstance(status, str):
        value = status
    else:
        raise OAuthGrantInvalid(f"status must be one of {sorted(STATUSES)}")
    if value not in STATUSES:
        raise OAuthGrantInvalid(f"status must be one of {sorted(STATUSES)}")
    return value


class PostgresGoogleAccountRepository(_Base):
    """Conta Google: uma por e-mail (sem distinguir caixa); reconectar atualiza, não duplica."""

    def upsert(self, account: GoogleAccount) -> GoogleAccount:
        if not isinstance(account, GoogleAccount):
            raise ValueError("account must be a GoogleAccount")
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""INSERT INTO studio.google_accounts (id, email, display_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT ((lower(btrim(email)))) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        updated_at = now()
                    RETURNING {_ACCOUNT_COLS}""",
                (account.id, account.email, account.display_name),
            )
            return _account(cur.fetchone())

    def get(self, account_id: str) -> GoogleAccount | None:
        aid = check_id(account_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_ACCOUNT_COLS} FROM studio.google_accounts WHERE id = %s", (aid,))
            row = cur.fetchone()
            return _account(row) if row else None

    def get_by_email(self, email: str) -> GoogleAccount | None:
        cleaned = validate_email(email)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {_ACCOUNT_COLS} FROM studio.google_accounts WHERE lower(btrim(email)) = lower(%s)",
                (cleaned,),
            )
            row = cur.fetchone()
            return _account(row) if row else None

    def list(self) -> list[GoogleAccount]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_ACCOUNT_COLS} FROM studio.google_accounts ORDER BY lower(email) ASC, id ASC")
            return [_account(row) for row in cur.fetchall()]


class PostgresOAuthGrantRepository(_Base):
    """Autorização independente da conta: escopos, status e vencimento próprios. Sem token."""

    def create(self, grant: OAuthGrant) -> OAuthGrant:
        if not isinstance(grant, OAuthGrant):
            raise ValueError("grant must be an OAuthGrant")
        try:
            with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""INSERT INTO studio.oauth_grants (id, account_id, scopes, status, token_expires_at)
                        VALUES (%s, %s, %s, %s, %s) RETURNING {_GRANT_COLS}""",
                    (grant.id, grant.account_id, Jsonb(list(grant.scopes)), grant.status.value, grant.token_expires_at),
                )
                return _grant(cur.fetchone())
        except psycopg.errors.ForeignKeyViolation as exc:
            raise OAuthGrantInvalid(f"google account {grant.account_id!r} does not exist") from exc

    def get(self, grant_id: str) -> OAuthGrant | None:
        gid = check_id(grant_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_GRANT_COLS} FROM studio.oauth_grants WHERE id = %s", (gid,))
            row = cur.fetchone()
            return _grant(row) if row else None

    def list_for_account(self, account_id: str) -> list[OAuthGrant]:
        aid = check_id(account_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {_GRANT_COLS} FROM studio.oauth_grants WHERE account_id = %s ORDER BY created_at ASC, id ASC",
                (aid,),
            )
            return [_grant(row) for row in cur.fetchall()]

    def update_status(self, grant_id: str, status: OAuthStatus, *,
                      token_expires_at: object = _UNSET) -> OAuthGrant | None:
        """Atualiza o estado declarado; `token_expires_at` só muda se informado (None limpa)."""
        gid = check_id(grant_id)
        stored = _stored_status(status)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            if token_expires_at is _UNSET:
                cur.execute(
                    f"UPDATE studio.oauth_grants SET status = %s, updated_at = now() WHERE id = %s "
                    f"RETURNING {_GRANT_COLS}",
                    (stored, gid),
                )
            else:
                cur.execute(
                    f"UPDATE studio.oauth_grants SET status = %s, token_expires_at = %s, updated_at = now() "
                    f"WHERE id = %s RETURNING {_GRANT_COLS}",
                    (stored, token_expires_at, gid),
                )
            row = cur.fetchone()
            return _grant(row) if row else None


class PostgresYouTubeChannelIdentityRepository(_Base):
    """Identidade oficial do canal (`UC...`): global e independente da conta."""

    def upsert(self, channel: YouTubeChannelIdentity) -> YouTubeChannelIdentity:
        if not isinstance(channel, YouTubeChannelIdentity):
            raise ValueError("channel must be a YouTubeChannelIdentity")
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""INSERT INTO studio.youtube_channels (youtube_channel_id, title)
                    VALUES (%s, %s)
                    ON CONFLICT (youtube_channel_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        updated_at = now()
                    RETURNING {_CHANNEL_COLS}""",
                (channel.youtube_channel_id, channel.title),
            )
            return _channel(cur.fetchone())

    def get(self, youtube_channel_id: str) -> YouTubeChannelIdentity | None:
        cid = validate_youtube_channel_id(youtube_channel_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {_CHANNEL_COLS} FROM studio.youtube_channels WHERE youtube_channel_id = %s",
                (cid,),
            )
            row = cur.fetchone()
            return _channel(row) if row else None

    def list(self) -> list[YouTubeChannelIdentity]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {_CHANNEL_COLS} FROM studio.youtube_channels "
                "ORDER BY lower(title) ASC, youtube_channel_id ASC"
            )
            return [_channel(row) for row in cur.fetchall()]


class PostgresChannelAuthorizationRepository(_Base):
    """Vínculo **validado** entre autorização e canal. Existir já afirma que houve conferência."""

    def link(self, authorization: ChannelAuthorization) -> ChannelAuthorization:
        if not isinstance(authorization, ChannelAuthorization):
            raise ValueError("authorization must be a ChannelAuthorization")
        try:
            with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""INSERT INTO studio.channel_authorizations (
                        grant_id, youtube_channel_id, status, validated_at
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (grant_id, youtube_channel_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        validated_at = EXCLUDED.validated_at
                    RETURNING {_AUTHORIZATION_COLS}""",
                    (authorization.grant_id, authorization.youtube_channel_id,
                     authorization.status.value, authorization.validated_at),
                )
                return _authorization(cur.fetchone())
        except psycopg.errors.ForeignKeyViolation as exc:
            # A violação pode ser do grant ou do canal: a mensagem diz qual, senão "não existe" mente.
            constraint = (getattr(exc.diag, "constraint_name", "") or "")
            if "grant_id" in constraint:
                raise ChannelAuthorizationInvalid(
                    f"oauth grant {authorization.grant_id!r} does not exist") from exc
            raise ChannelAuthorizationInvalid(
                f"youtube channel {authorization.youtube_channel_id!r} does not exist") from exc

    def get(self, grant_id: str, youtube_channel_id: str) -> ChannelAuthorization | None:
        gid = check_id(grant_id)
        cid = validate_youtube_channel_id(youtube_channel_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {_AUTHORIZATION_COLS} FROM studio.channel_authorizations "
                "WHERE grant_id = %s AND youtube_channel_id = %s",
                (gid, cid),
            )
            row = cur.fetchone()
            return _authorization(row) if row else None

    def authorizations_for_channel(self, youtube_channel_id: str) -> list[ChannelAuthorization]:
        cid = validate_youtube_channel_id(youtube_channel_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {_AUTHORIZATION_COLS} FROM studio.channel_authorizations "
                "WHERE youtube_channel_id = %s ORDER BY created_at ASC, grant_id ASC",
                (cid,),
            )
            return [_authorization(row) for row in cur.fetchall()]

    def revoke(self, grant_id: str, youtube_channel_id: str) -> bool:
        """Marca o vínculo como REVOKED. Não apaga a linha nem o `validated_at` da conferência."""
        gid = check_id(grant_id)
        cid = validate_youtube_channel_id(youtube_channel_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE studio.channel_authorizations SET status = %s "
                "WHERE grant_id = %s AND youtube_channel_id = %s",
                (OAuthStatus.REVOKED.value, gid, cid),
            )
            return cur.rowcount > 0
