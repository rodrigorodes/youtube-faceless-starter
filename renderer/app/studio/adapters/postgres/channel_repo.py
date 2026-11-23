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
    CREATABLE_FIELDS,
    ChannelFieldInvalid,
    ChannelLockTimeout,
    ChannelProfile,
    ChannelProjectNotFound,
    ChannelStyleNotFound,
    ChannelVersionConflict,
    ChannelYouTubeTargetNotFound,
    DuplicateChannelProfile,
    UPDATABLE_FIELDS,
    validate_version,
)
from ...domain.contracts import ProductionMode, VideoFormat
from ...domain.ids import check_id
from ...domain.visual_style import StylePatch
from .editorial_repo import _Base
from .repo import _translated, normalize_style_patch

_COLS = ("id, project_id, name, strategy, language, audience, pillars, narrative, target_duration_s, "
         "visual_identity, voice, audio, thumbnail, cta, style_id, style_patch, style_patch_revision, "
         "youtube_channel_id, default_mode, default_format, version, archived, created_at, updated_at")


def _profile(row: dict) -> ChannelProfile:
    row = dict(row)
    row["pillars"] = tuple(row["pillars"]) if row.get("pillars") is not None else ()
    if "default_mode" in row and row["default_mode"] is not None:
        row["default_mode"] = ProductionMode(row["default_mode"])
    if "default_format" in row and row["default_format"] is not None:
        row["default_format"] = VideoFormat(row["default_format"])
    return ChannelProfile(**row)


def _snapshot(profile: ChannelProfile) -> dict:
    snapshot: dict[str, object] = {}
    for field in dataclasses.fields(profile):
        value = getattr(profile, field.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, tuple):
            value = list(value)
        elif isinstance(value, StylePatch):
            value = value.to_mapping()
        elif isinstance(value, (ProductionMode, VideoFormat)):
            value = value.value
        snapshot[field.name] = value
    return snapshot


def _patch_revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ChannelFieldInvalid("style patch revision must be an integer >= 0")
    return value


class PostgresChannelProfileRepository(_Base):
    def create(self, project_id: str, name: str, **options: object) -> ChannelProfile:
        p_id = check_id(project_id)
        unknown = set(options) - set(CREATABLE_FIELDS)
        if unknown:
            raise ValueError(f"unknown channel profile fields: {sorted(unknown)}")
        profile = ChannelProfile(id=uuid.uuid4().hex, project_id=p_id, name=name, **options)
        with _translated(), self._connect() as conn:
            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    row = self._insert(cur, profile)
                    self._insert_revision(cur, _profile(row))
                    return _profile(row)
            except psycopg.errors.LockNotAvailable as exc:
                raise ChannelLockTimeout(f"timed out acquiring the channel profile lock for project '{p_id}'") from exc
            except psycopg.errors.UniqueViolation as exc:
                raise DuplicateChannelProfile(f"channel profile already exists for project '{p_id}'") from exc
            except psycopg.errors.ForeignKeyViolation as exc:
                # A violação pode ser do projeto (canal órfão), do estilo (VS-02) ou do canal do
                # YouTube (YT-02): a mensagem tem de dizer qual, senão "projeto não existe" mente.
                constraint = getattr(exc.diag, "constraint_name", "") or ""
                if "youtube_channel_id" in constraint:
                    raise ChannelYouTubeTargetNotFound(
                        f"youtube channel {profile.youtube_channel_id!r} does not exist") from exc
                if "style_id" in constraint:
                    raise ChannelStyleNotFound(f"visual style {profile.style_id!r} does not exist") from exc
                raise ChannelProjectNotFound(f"project '{p_id}' does not exist") from exc

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
        if not isinstance(include_archived, bool):
            raise ChannelFieldInvalid("include_archived must be a boolean")
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
            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(f"SELECT {_COLS} FROM studio.channel_profiles WHERE id = %s FOR UPDATE", (pid,))
                    row = cur.fetchone()
                    if row is None:
                        return None
                    current = _profile(row)
                    if current.version != version:
                        raise ChannelVersionConflict(f"expected version {version}, found {current.version}")
                    updated = dataclasses.replace(current, version=current.version + 1, **changes)
                    try:
                        cur.execute(
                            f"""UPDATE studio.channel_profiles SET
                                name = %s, strategy = %s, language = %s, audience = %s, pillars = %s, narrative = %s,
                                target_duration_s = %s, visual_identity = %s, voice = %s, audio = %s, thumbnail = %s,
                                cta = %s, style_id = %s, youtube_channel_id = %s, default_mode = %s, default_format = %s,
                                version = %s, archived = %s,
                                updated_at = now()
                                WHERE id = %s RETURNING {_COLS}""",
                            (updated.name, updated.strategy, updated.language, updated.audience, list(updated.pillars),
                             updated.narrative, updated.target_duration_s, updated.visual_identity, updated.voice,
                             updated.audio, updated.thumbnail, updated.cta, updated.style_id,
                             updated.youtube_channel_id, updated.default_mode.value, updated.default_format.value,
                             updated.version, updated.archived, pid),
                        )
                        new_row = cur.fetchone()
                    except psycopg.errors.ForeignKeyViolation as exc:
                        # VS-02/YT-02: apontar para um estilo ou canal do YouTube inexistente é
                        # recusado com o motivo certo (não como conflito de versão nem erro genérico).
                        constraint = getattr(exc.diag, "constraint_name", "") or ""
                        if "youtube_channel_id" in constraint:
                            raise ChannelYouTubeTargetNotFound(
                                f"youtube channel {updated.youtube_channel_id!r} does not exist") from exc
                        raise ChannelStyleNotFound(f"visual style {updated.style_id!r} does not exist") from exc
                    self._insert_revision(cur, _profile(new_row))
                    return _profile(new_row)
            except psycopg.errors.LockNotAvailable as exc:
                raise ChannelLockTimeout(f"timed out acquiring the channel profile lock for '{pid}'") from exc

    def set_style_patch(self, profile_id: str, expected_revision: int, patch: object) -> ChannelProfile | None:
        """Grava o override de estilo do canal, de forma otimista e escopada (F05.T02).

        - O patch é normalizado por `StylePatch` **antes** do UPDATE (a allowlist vale no banco,
          não só na API); patch vazio/reset vira NULL — o canal volta a herdar, nunca `{}`.
        - `expected_revision` é a `style_patch_revision` que o cliente leu: se divergiu, outra
          escrita venceu a corrida e `ChannelVersionConflict` sobe **sem gravar**.
        - Só as colunas do patch mudam: a `version` editorial e o resto do perfil ficam intactos
          (personalizar estilo não é editar o perfil). Devolve o perfil como ficou no banco.
        """
        pid = check_id(profile_id)
        revision = _patch_revision(expected_revision)
        stored = normalize_style_patch(patch)  # falha alto (StylePatchInvalid) antes de qualquer SQL
        with _translated(), self._connect() as conn:
            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(f"SELECT {_COLS} FROM studio.channel_profiles WHERE id = %s FOR UPDATE", (pid,))
                    row = cur.fetchone()
                    if row is None:
                        return None
                    current = _profile(row)
                    if current.style_patch_revision != revision:
                        raise ChannelVersionConflict(
                            f"expected style patch revision {revision}, "
                            f"found {current.style_patch_revision}")
                    cur.execute(
                        f"""UPDATE studio.channel_profiles SET style_patch = %s,
                            style_patch_revision = style_patch_revision + 1, updated_at = now()
                            WHERE id = %s RETURNING {_COLS}""",
                        (Jsonb(stored) if stored is not None else None, pid),
                    )
                    return _profile(cur.fetchone())
            except psycopg.errors.LockNotAvailable as exc:
                raise ChannelLockTimeout(
                    f"timed out acquiring the channel profile lock for '{pid}'") from exc

    @staticmethod
    def _insert(cur, profile: ChannelProfile) -> dict:
        cur.execute(
            """INSERT INTO studio.channel_profiles (
                id, project_id, name, strategy, language, audience, pillars, narrative, target_duration_s,
                visual_identity, voice, audio, thumbnail, cta, style_id, youtube_channel_id,
                default_mode, default_format, version, archived
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING """ + _COLS,
            (profile.id, profile.project_id, profile.name, profile.strategy, profile.language, profile.audience,
             list(profile.pillars), profile.narrative, profile.target_duration_s, profile.visual_identity, profile.voice,
             profile.audio, profile.thumbnail, profile.cta, profile.style_id, profile.youtube_channel_id,
             profile.default_mode.value, profile.default_format.value,
             profile.version, profile.archived),
        )
        return cur.fetchone()

    @staticmethod
    def _insert_revision(cur, profile: ChannelProfile) -> None:
        cur.execute(
            "INSERT INTO studio.channel_profile_revisions (profile_id, version, snapshot) VALUES (%s, %s, %s)",
            (profile.id, profile.version, Jsonb(_snapshot(profile))),
        )
