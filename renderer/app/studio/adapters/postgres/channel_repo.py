"""Repositório Postgres de perfis de canal (transacional, sem autocommit).

`create`/`update` rodam numa transação e gravam um snapshot por versão em
`channel_profile_revisions`; o `SELECT ... FOR UPDATE` no update serializa atualizações
concorrentes do mesmo perfil (quem perde recebe `ChannelVersionConflict`).
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...domain.channel import (
    ChannelProfile,
    ChannelVersionConflict,
    DuplicateChannelProfile,
    UPDATABLE_FIELDS,
    validate_version,
)
from ...domain.ids import check_id
from .editorial_repo import _Base
from .repo import _translated

_COLS = ("id, project_id, name, strategy, language, audience, pillars, narrative, target_duration_s, "
         "visual_identity, voice, audio, thumbnail, cta, version, archived, created_at, updated_at")

_CREATE_OPTIONS = (
    "strategy", "language", "audience", "pillars", "narrative", "target_duration_s",
    "visual_identity", "voice", "audio", "thumbnail", "cta", "archived",
)


def _profile(row: dict) -> ChannelProfile:
    row = dict(row)
    row["pillars"] = list(row["pillars"]) if row.get("pillars") is not None else []
    return ChannelProfile(**row)


def _snapshot(profile: ChannelProfile) -> dict:
    snapshot: dict[str, object] = {}
    for field in dataclasses.fields(profile):
        value = getattr(profile, field.name)
        snapshot[field.name] = value.isoformat() if isinstance(value, datetime) else value
    return snapshot


class PostgresChannelProfileRepository(_Base):
    def create(self, project_id: str, name: str, **options: object) -> ChannelProfile:
        p_id = check_id(project_id)
        unknown = set(options) - set(_CREATE_OPTIONS)
        if unknown:
            raise ValueError(f"unknown channel profile fields: {sorted(unknown)}")
        profile = ChannelProfile(id=uuid.uuid4().hex, project_id=p_id, name=name, **options)
        with _translated(), self._connect() as conn:
            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    row = self._insert(cur, profile)
                    self._insert_revision(cur, _profile(row))
                    return _profile(row)
            except psycopg.errors.UniqueViolation as exc:
                raise DuplicateChannelProfile(f"channel profile already exists for project '{p_id}'") from exc

    def get(self, profile_id: str) -> ChannelProfile | None:
        pid = check_id(profile_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLS} FROM studio.channel_profiles WHERE id = %s", (pid,))
            row = cur.fetchone()
            return _profile(row) if row else None

    def get_by_project(self, project_id: str) -> ChannelProfile | None:
        p_id = check_id(project_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLS} FROM studio.channel_profiles WHERE project_id = %s", (p_id,))
            row = cur.fetchone()
            return _profile(row) if row else None

    def list(self, include_archived: bool = False) -> list[ChannelProfile]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {_COLS} FROM studio.channel_profiles WHERE (%s OR NOT archived) ORDER BY name ASC, id ASC",
                (include_archived,),
            )
            return [_profile(row) for row in cur.fetchall()]

    def update(self, profile_id: str, expected_version: int, changes: dict[str, object]) -> ChannelProfile | None:
        pid = check_id(profile_id)
        version = validate_version(expected_version)
        unknown = set(changes) - set(UPDATABLE_FIELDS)
        if unknown:
            raise ValueError(f"unknown channel profile fields: {sorted(unknown)}")
        with _translated(), self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"SELECT {_COLS} FROM studio.channel_profiles WHERE id = %s FOR UPDATE", (pid,))
                row = cur.fetchone()
                if row is None:
                    return None
                current = _profile(row)
                if current.version != version:
                    raise ChannelVersionConflict(f"expected version {version}, found {current.version}")
                updated = dataclasses.replace(current, version=current.version + 1, **changes)
                cur.execute(
                    f"""UPDATE studio.channel_profiles SET
                        name = %s, strategy = %s, language = %s, audience = %s, pillars = %s, narrative = %s,
                        target_duration_s = %s, visual_identity = %s, voice = %s, audio = %s, thumbnail = %s,
                        cta = %s, version = %s, archived = %s, updated_at = now()
                        WHERE id = %s RETURNING {_COLS}""",
                    (updated.name, updated.strategy, updated.language, updated.audience, updated.pillars,
                     updated.narrative, updated.target_duration_s, updated.visual_identity, updated.voice,
                     updated.audio, updated.thumbnail, updated.cta, updated.version, updated.archived, pid),
                )
                new_row = cur.fetchone()
                self._insert_revision(cur, _profile(new_row))
                return _profile(new_row)

    @staticmethod
    def _insert(cur, profile: ChannelProfile) -> dict:
        cur.execute(
            """INSERT INTO studio.channel_profiles (
                id, project_id, name, strategy, language, audience, pillars, narrative, target_duration_s,
                visual_identity, voice, audio, thumbnail, cta, version, archived
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING """ + _COLS,
            (profile.id, profile.project_id, profile.name, profile.strategy, profile.language, profile.audience,
             profile.pillars, profile.narrative, profile.target_duration_s, profile.visual_identity, profile.voice,
             profile.audio, profile.thumbnail, profile.cta, profile.version, profile.archived),
        )
        return cur.fetchone()

    @staticmethod
    def _insert_revision(cur, profile: ChannelProfile) -> None:
        cur.execute(
            "INSERT INTO studio.channel_profile_revisions (profile_id, version, snapshot) VALUES (%s, %s, %s)",
            (profile.id, profile.version, Jsonb(_snapshot(profile))),
        )
