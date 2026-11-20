"""Repositório de categorias de projeto (Postgres)."""
from __future__ import annotations

import uuid

import psycopg
from psycopg.rows import dict_row

from ...domain.categories import (
    CategoryNameInvalid,
    DuplicateCategoryName,
    ProjectCategory,
    clean_queries,
    validate_category_name,
)
from ...domain.ids import check_id
from .editorial_repo import _Base
from .repo import _translated

_CATEGORY_COLS = "id, project_id, name, queries, created_at, updated_at"


def _category(row: dict) -> ProjectCategory:
    return ProjectCategory(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        queries=list(row["queries"]) if row.get("queries") is not None else [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresCategoryRepository(_Base):
    def list(self, project_id: str) -> list[ProjectCategory]:
        p_id = check_id(project_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT {_CATEGORY_COLS}
                FROM studio.project_categories
                WHERE project_id = %s
                ORDER BY name ASC, created_at ASC
                """,
                (p_id,),
            )
            return [_category(row) for row in cur.fetchall()]

    def get(self, category_id: str) -> ProjectCategory | None:
        cid = check_id(category_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT {_CATEGORY_COLS}
                FROM studio.project_categories
                WHERE id = %s
                """,
                (cid,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return _category(row)

    def save(
        self,
        project_id: str,
        name: str,
        queries: list[str],
        category_id: str | None = None,
    ) -> ProjectCategory:
        p_id = check_id(project_id)
        valid_name = validate_category_name(name)
        cleaned_q = clean_queries(queries)
        cid = check_id(category_id) if category_id is not None else uuid.uuid4().hex

        with _translated(), self._connect() as conn:
            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        f"""
                        INSERT INTO studio.project_categories (
                            id, project_id, name, queries, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, now(), now())
                        ON CONFLICT (id) DO UPDATE SET
                            project_id = EXCLUDED.project_id,
                            name = EXCLUDED.name,
                            queries = EXCLUDED.queries,
                            updated_at = now()
                        RETURNING {_CATEGORY_COLS}
                        """,
                        (cid, p_id, valid_name, cleaned_q),
                    )
                    row = cur.fetchone()
                    return _category(row)
            except psycopg.errors.UniqueViolation as exc:
                raise DuplicateCategoryName(
                    f"category '{valid_name}' already exists in project '{p_id}'"
                ) from exc
            except psycopg.errors.CheckViolation as exc:
                raise CategoryNameInvalid("invalid category name or data") from exc

    def delete(self, category_id: str) -> bool:
        cid = check_id(category_id)
        with _translated(), self._connect() as conn:
            res = conn.execute(
                "DELETE FROM studio.project_categories WHERE id = %s",
                (cid,),
            )
            return res.rowcount > 0
