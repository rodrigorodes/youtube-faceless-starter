"""Repositório Postgres da associação de canal YouTube (F10-06). Só metadados: nunca tokens."""
from __future__ import annotations

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...application.errors import ProjectNotFound
from ...domain.ids import check_id
from ...domain.youtube_channel import OAuthStatus, YouTubeChannel
from .editorial_repo import _Base
from .repo import _translated

_COLS = "project_id, channel_id, title, scopes, oauth_status, token_expires_at, updated_at"


def _channel(row: dict) -> YouTubeChannel:
    return YouTubeChannel(
        project_id=row["project_id"],
        channel_id=row["channel_id"],
        title=row["title"],
        scopes=tuple(row["scopes"] or ()),
        oauth_status=OAuthStatus(row["oauth_status"]),
        token_expires_at=row["token_expires_at"],
        updated_at=row["updated_at"],
    )


class PostgresYouTubeChannelRepository(_Base):
    def get(self, project_id: str) -> YouTubeChannel | None:
        p_id = check_id(project_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLS} FROM studio.channel_youtube_channels WHERE project_id = %s", (p_id,))
            row = cur.fetchone()
            return _channel(row) if row else None

    def upsert(self, channel: YouTubeChannel) -> YouTubeChannel:
        if not isinstance(channel, YouTubeChannel):
            raise ValueError("channel must be a YouTubeChannel")
        try:
            with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""INSERT INTO studio.channel_youtube_channels (
                        project_id, channel_id, title, scopes, oauth_status, token_expires_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (project_id) DO UPDATE SET
                        channel_id = EXCLUDED.channel_id,
                        title = EXCLUDED.title,
                        scopes = EXCLUDED.scopes,
                        oauth_status = EXCLUDED.oauth_status,
                        token_expires_at = EXCLUDED.token_expires_at,
                        updated_at = now()
                    RETURNING {_COLS}""",
                    (channel.project_id, channel.channel_id, channel.title, Jsonb(list(channel.scopes)),
                     channel.oauth_status.value, channel.token_expires_at),
                )
                return _channel(cur.fetchone())
        except psycopg.errors.ForeignKeyViolation as exc:
            raise ProjectNotFound(channel.project_id) from exc

    def delete(self, project_id: str) -> bool:
        p_id = check_id(project_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM studio.channel_youtube_channels WHERE project_id = %s", (p_id,))
            return cur.rowcount > 0