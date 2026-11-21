"""Repositório Postgres de estilos visuais (transacional, sem autocommit).

`create`/`update` rodam numa transação e gravam um snapshot por versão em
`visual_style_revisions`; o `SELECT ... FOR UPDATE` no update serializa atualizações
concorrentes do mesmo estilo (quem perde recebe `VisualStyleVersionConflict`). Mesmo padrão
do repositório de perfis de canal — o estilo é a identidade versionada da biblioteca.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...domain.ids import check_id
from ...domain.visual_style import (
    CREATABLE_FIELDS,
    UPDATABLE_FIELDS,
    DuplicateVisualStyle,
    VisualStyle,
    VisualStyleVersionConflict,
    validate_version,
)
from .editorial_repo import _Base
from .repo import _translated

_COLS = "id, organization_id, name, params, version, archived, created_at, updated_at"


def _style(row: dict) -> VisualStyle:
    return VisualStyle(**dict(row))


def _snapshot(style: VisualStyle) -> dict:
    snapshot: dict[str, object] = {}
    for field in dataclasses.fields(style):
        value = getattr(style, field.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        snapshot[field.name] = value
    return snapshot


class PostgresVisualStyleRepository(_Base):
    def create(self, name: str, **options: object) -> VisualStyle:
        unknown = set(options) - set(CREATABLE_FIELDS)
        if unknown:
            raise ValueError(f"unknown visual style fields: {sorted(unknown)}")
        organization_id = options.get("organization_id")
        if organization_id is not None:
            organization_id = check_id(organization_id)
        style = VisualStyle(id=uuid.uuid4().hex, name=name, organization_id=organization_id,
                            params=options.get("params") or {}, archived=bool(options.get("archived", False)))
        with _translated(), self._connect() as conn:
            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    row = self._insert(cur, style)
                    self._insert_revision(cur, _style(row))
                    return _style(row)
            except psycopg.errors.UniqueViolation as exc:
                raise DuplicateVisualStyle(f"a visual style named '{style.name}' already exists") from exc

    def get(self, style_id: str) -> VisualStyle | None:
        sid = check_id(style_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLS} FROM studio.visual_styles WHERE id = %s", (sid,))
            row = cur.fetchone()
            return _style(row) if row else None

    def list(self, include_archived: bool = False) -> list[VisualStyle]:
        if not isinstance(include_archived, bool):
            raise ValueError("include_archived must be a boolean")
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {_COLS} FROM studio.visual_styles WHERE (%s OR NOT archived) "
                "ORDER BY name ASC, id ASC",
                (include_archived,),
            )
            return [_style(row) for row in cur.fetchall()]

    def usage_counts(self) -> dict[str, int]:
        """Quantos canais usam cada estilo, medido de verdade (nunca estimado).

        Só conta canal com `style_id` preenchido; canal sem estilo não aparece no mapa. A
        contagem é o que a lista da biblioteca mostra ao lado de cada estilo.
        """
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT style_id, count(*) FROM studio.channel_profiles "
                "WHERE style_id IS NOT NULL GROUP BY style_id"
            )
            return {row[0]: int(row[1]) for row in cur.fetchall()}

    def archive(self, style_id: str) -> VisualStyle | None:
        """Arquiva (soft delete): marca `archived = true` e grava uma nova revisão.

        Não apaga linha nenhuma — o estilo some da lista padrão, mas continua rastreável e os
        canais que apontavam para ele passam a resolver o padrão do estúdio. Idempotente: um
        estilo já arquivado é devolvido como está, sem bumpar versão de novo.
        """
        sid = check_id(style_id)
        with _translated(), self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"SELECT {_COLS} FROM studio.visual_styles WHERE id = %s FOR UPDATE", (sid,))
                row = cur.fetchone()
                if row is None:
                    return None
                current = _style(row)
                if current.archived:
                    return current
                cur.execute(
                    f"""UPDATE studio.visual_styles SET archived = true, version = version + 1, updated_at = now()
                        WHERE id = %s RETURNING {_COLS}""",
                    (sid,),
                )
                new_row = cur.fetchone()
                self._insert_revision(cur, _style(new_row))
                return _style(new_row)

    def update(self, style_id: str, expected_version: int, changes: dict[str, Any]) -> VisualStyle | None:
        sid = check_id(style_id)
        version = validate_version(expected_version)
        unknown = set(changes) - set(UPDATABLE_FIELDS)
        if unknown:
            raise ValueError(f"unknown visual style fields: {sorted(unknown)}")
        with _translated(), self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"SELECT {_COLS} FROM studio.visual_styles WHERE id = %s FOR UPDATE", (sid,))
                row = cur.fetchone()
                if row is None:
                    return None
                current = _style(row)
                if current.version != version:
                    raise VisualStyleVersionConflict(f"expected version {version}, found {current.version}")
                updated = dataclasses.replace(current, version=current.version + 1, **changes)
                try:
                    cur.execute(
                        f"""UPDATE studio.visual_styles SET
                            name = %s, params = %s, version = %s, archived = %s, updated_at = now()
                            WHERE id = %s RETURNING {_COLS}""",
                        (updated.name, Jsonb(updated.params), updated.version, updated.archived, sid),
                    )
                except psycopg.errors.UniqueViolation as exc:
                    raise DuplicateVisualStyle(f"a visual style named '{updated.name}' already exists") from exc
                new_row = cur.fetchone()
                self._insert_revision(cur, _style(new_row))
                return _style(new_row)

    @staticmethod
    def _insert(cur, style: VisualStyle) -> dict:
        cur.execute(
            """INSERT INTO studio.visual_styles (id, organization_id, name, params, version, archived)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING """ + _COLS,
            (style.id, style.organization_id, style.name, Jsonb(style.params), style.version, style.archived),
        )
        return cur.fetchone()

    @staticmethod
    def _insert_revision(cur, style: VisualStyle) -> None:
        cur.execute(
            "INSERT INTO studio.visual_style_revisions (style_id, version, snapshot) VALUES (%s, %s, %s)",
            (style.id, style.version, Jsonb(_snapshot(style))),
        )
