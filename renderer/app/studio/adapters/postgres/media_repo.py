"""Repositório Postgres de assets. `add` é idempotente por cache_key: em corrida, vence o primeiro e todos recebem o mesmo asset."""
import contextlib
from collections.abc import Callable, Iterator

import psycopg
from psycopg.rows import dict_row

from ...domain.contracts import Asset
from ...domain.ids import check_cache_key, check_id
from ...domain.asset_tags import (
    AssetAccessDenied,
    AssetNotFound,
    AssetTagInvalid,
    MAX_TAGS_PER_ASSET,
    escape_like,
    normalize_tag,
)
from .editorial_repo import _Base
from .repo import _translated

_COLUMNS = "id, kind, cache_key, path, provider, model, license, attribution, source_url, cost_usd"
_UNSET = object()


def _asset(row: dict, tags: list[str] | None = None) -> Asset:
    row = dict(row)
    row["cost_usd"] = float(row["cost_usd"])
    if tags is not None:
        row["tags"] = list(tags)
    elif "tags" not in row:
        row["tags"] = []
    if not row.get("origin"):
        row["origin"] = row.get("source_url") or row.get("provider") or ""
    if not row.get("provenance"):
        row["provenance"] = f"{row.get('provider', '')}:{row.get('model', '')}" if row.get("provider") else ""
    return Asset.model_validate(row)


class PostgresAssetRepository(_Base):
    def find(self, cache_key: str) -> Asset | None:
        key = check_cache_key(cache_key)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM studio.assets WHERE cache_key = %s", (key,))
            row = cur.fetchone()
            if not row:
                return None
            return _asset(row)

    def get(self, asset_id: str, *, project_id: str | None = None) -> Asset | None:
        aid = check_id(asset_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM studio.assets WHERE id = %s", (aid,))
            row = cur.fetchone()
            if not row:
                return None
            tags: list[str] = []
            pid = check_id(project_id) if project_id else None
            if not pid:
                cur.execute(
                    "SELECT v.project_id FROM studio.scenes s JOIN studio.videos v ON v.id = s.video_id WHERE s.asset_id = %s "
                    "UNION SELECT v.project_id FROM studio.scene_assets sa JOIN studio.scenes s ON s.id = sa.scene_id JOIN studio.videos v ON v.id = s.video_id WHERE sa.asset_id = %s",
                    (aid, aid),
                )
                p_rows = cur.fetchall()
                if len(p_rows) == 1:
                    pid = p_rows[0]["project_id"]
            if pid:
                cur.execute("SELECT tag FROM studio.asset_tags WHERE project_id = %s AND asset_id = %s ORDER BY tag ASC", (pid, aid))
                tags = [r["tag"] for r in cur.fetchall()]
            return _asset(row, tags=tags)

    def add(self, asset: Asset) -> Asset:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license, attribution, source_url, cost_usd) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (cache_key) DO NOTHING",
                        (check_id(asset.id), asset.kind.value, check_cache_key(asset.cache_key), asset.path, asset.provider, asset.model,
                         asset.license, asset.attribution, asset.source_url, asset.cost_usd))
            cur.execute(f"SELECT {_COLUMNS} FROM studio.assets WHERE cache_key = %s", (asset.cache_key,))
            return _asset(cur.fetchone())

    def link_scene(self, video_id: str, idx: int, asset_id: str, image_prompt: str) -> bool:
        with _translated(), self._connect() as conn:
            cur = conn.execute("UPDATE studio.scenes s SET asset_id = %s FROM studio.videos v "
                               "WHERE s.video_id = v.id AND v.status = 'STORYBOARDED' AND s.video_id = %s AND s.idx = %s AND s.image_prompt = %s",
                               (check_id(asset_id), check_id(video_id), idx, image_prompt))
            return cur.rowcount == 1

    def swap_scene_asset(self, video_id: str, scene_id: str, asset_id: str, expected_asset_id: str | None) -> bool:
        """W4.4: troca o asset de UMA cena por id estável, com CAS no vínculo lido; o resto fica intacto."""
        with _translated(), self._connect() as conn:
            cur = conn.execute("UPDATE studio.scenes SET asset_id = %s, edit_revision = edit_revision + 1 "
                               "WHERE video_id = %s AND id = %s AND asset_id IS NOT DISTINCT FROM %s",
                               (check_id(asset_id), check_id(video_id), check_id(scene_id),
                                check_id(expected_asset_id) if expected_asset_id else None))
            return cur.rowcount == 1

    def set_scene_broll(self, video_id: str, scene_id: str, enabled: bool, note: str | None) -> bool:
        """Grava só o B-roll de UMA cena por id estável; não cria versão de roteiro nem mexe no asset."""
        with _translated(), self._connect() as conn:
            cur = conn.execute("UPDATE studio.scenes SET broll_enabled = %s, broll_note = %s "
                               "WHERE video_id = %s AND id = %s",
                               (bool(enabled), note, check_id(video_id), check_id(scene_id)))
            return cur.rowcount == 1

    def add_and_swap_scene_asset(
        self,
        asset: Asset,
        video_id: str,
        scene_id: str,
        expected_asset_id: str | None,
    ) -> tuple[Asset, bool]:
        """Insere (ou reutiliza por cache_key) e vincula à cena em UMA transação com advisory lock por cache_key.

        Se o CAS na cena falhar, faz rollback completo (não deixando linha fantasma em studio.assets).
        """
        key = check_cache_key(asset.cache_key)
        vid = check_id(video_id)
        sid = check_id(scene_id)
        exp = check_id(expected_asset_id) if expected_asset_id else None
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
            cur.execute(
                "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license, attribution, source_url, cost_usd) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (cache_key) DO NOTHING",
                (check_id(asset.id), asset.kind.value, key, asset.path, asset.provider, asset.model,
                 asset.license, asset.attribution, asset.source_url, asset.cost_usd),
            )
            cur.execute(f"SELECT {_COLUMNS} FROM studio.assets WHERE cache_key = %s", (key,))
            persisted = _asset(cur.fetchone())
            cur.execute(
                "UPDATE studio.scenes SET asset_id = %s "
                "WHERE video_id = %s AND id = %s AND asset_id IS NOT DISTINCT FROM %s",
                (check_id(persisted.id), vid, sid, exp),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return persisted, False
            return persisted, True

    def add_and_replace_scene_base_media(
        self,
        *,
        video_id: str,
        scene_id: str,
        asset: Asset | None = None,
        existing_asset_id: str | None = None,
        expected_asset_id: str | None | object = _UNSET,
        expected_edit_revision: int | None = None,
        apply_trim: bool = True,
        trim_start_s: float | None = None,
        trim_end_s: float | None = None,
    ) -> tuple[Asset | None, int, bool, str]:
        """Substitui mídia base e trim da cena em UMA única transação PostgreSQL com CAS de `edit_revision`.

        Preserva integralmente todas as camadas não-base (`role <> 'base'`) em `studio.scene_assets`.
        Usa deslocamento em duas etapas (+offset -> normalização) quando `position=0` está ocupado
        por um overlay para evitar `UniqueViolation` em `uq_scene_asset_pos`.
        """
        vid = check_id(video_id)
        sid = check_id(scene_id)
        check_exp_aid = expected_asset_id is not _UNSET
        exp_aid = check_id(expected_asset_id) if (check_exp_aid and expected_asset_id) else None
        if asset is None and not existing_asset_id:
            raise ValueError("either asset or existing_asset_id must be provided")

        class _TxAbort(Exception):
            def __init__(self, reason: str, rev: int = 0):
                self.reason = reason
                self.rev = rev

        try:
            with _translated(), self._connect() as conn:
                with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
                    # Sempre adquire o lock da cena ANTES de qualquer advisory lock por cache_key.
                    cur.execute(
                        "SELECT id, asset_id, edit_revision FROM studio.scenes "
                        "WHERE id = %s AND video_id = %s FOR UPDATE",
                        (sid, vid),
                    )
                    scene_row = cur.fetchone()
                    if scene_row is None:
                        raise _TxAbort("scene_not_found")
                    current_rev = int(scene_row["edit_revision"])
                    if expected_edit_revision is not None and current_rev != int(expected_edit_revision):
                        raise _TxAbort("edit_revision_mismatch", current_rev)
                    if check_exp_aid and (scene_row["asset_id"] or None) != exp_aid:
                        raise _TxAbort("asset_id_mismatch", current_rev)

                    if asset is not None:
                        key = check_cache_key(asset.cache_key)
                        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
                        cur.execute(
                            "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license, attribution, source_url, cost_usd) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (cache_key) DO NOTHING",
                            (check_id(asset.id), asset.kind.value, key, asset.path, asset.provider, asset.model,
                             asset.license, asset.attribution, asset.source_url, asset.cost_usd),
                        )
                        cur.execute(f"SELECT {_COLUMNS} FROM studio.assets WHERE cache_key = %s", (key,))
                        persisted = _asset(cur.fetchone())
                    else:
                        cur.execute(f"SELECT {_COLUMNS} FROM studio.assets WHERE id = %s", (check_id(existing_asset_id),))
                        found = cur.fetchone()
                        if found is None:
                            raise _TxAbort("asset_not_found", current_rev)
                        persisted = _asset(found)

                    cur.execute(
                        "UPDATE studio.scenes SET asset_id = %s, edit_revision = edit_revision + 1 "
                        "WHERE id = %s AND video_id = %s RETURNING edit_revision",
                        (check_id(persisted.id), sid, vid),
                    )
                    new_rev = int(cur.fetchone()["edit_revision"])

                    if apply_trim:
                        if trim_start_s is not None and trim_end_s is not None:
                            cur.execute(
                                "SELECT id FROM studio.scene_assets "
                                "WHERE scene_id = %s AND role = 'base' ORDER BY position LIMIT 1",
                                (sid,),
                            )
                            base_row = cur.fetchone()
                            if base_row is not None:
                                cur.execute(
                                    "UPDATE studio.scene_assets SET asset_id = %s, start_s = %s, end_s = %s "
                                    "WHERE id = %s",
                                    (check_id(persisted.id), float(trim_start_s), float(trim_end_s), base_row["id"]),
                                )
                                cur.execute(
                                    "DELETE FROM studio.scene_assets "
                                    "WHERE scene_id = %s AND role = 'base' AND id <> %s",
                                    (sid, base_row["id"]),
                                )
                            else:
                                cur.execute(
                                    "SELECT 1 FROM studio.scene_assets WHERE scene_id = %s AND position = 0 LIMIT 1",
                                    (sid,),
                                )
                                if cur.fetchone() is not None:
                                    cur.execute(
                                        "SELECT COALESCE(MAX(position), 0) + 10000 AS off "
                                        "FROM studio.scene_assets WHERE scene_id = %s",
                                        (sid,),
                                    )
                                    offset = int(cur.fetchone()["off"])
                                    cur.execute(
                                        "UPDATE studio.scene_assets SET position = position + %s "
                                        "WHERE scene_id = %s AND role <> 'base'",
                                        (offset, sid),
                                    )
                                    cur.execute(
                                        "WITH ranked AS ("
                                        "  SELECT id, ROW_NUMBER() OVER (ORDER BY position, created_at, id) AS new_pos "
                                        "  FROM studio.scene_assets WHERE scene_id = %s AND role <> 'base'"
                                        ") UPDATE studio.scene_assets sa SET position = ranked.new_pos "
                                        "FROM ranked WHERE sa.id = ranked.id",
                                        (sid,),
                                    )
                                cur.execute(
                                    "INSERT INTO studio.scene_assets "
                                    "(id, scene_id, asset_id, position, start_s, end_s, role, motion, transition_kind, transition_duration_s) "
                                    "VALUES (gen_random_uuid(), %s, %s, 0, %s, %s, 'base', 'none', 'none', 0.0)",
                                    (sid, check_id(persisted.id), float(trim_start_s), float(trim_end_s)),
                                )
                        else:
                            cur.execute(
                                "DELETE FROM studio.scene_assets WHERE scene_id = %s AND role = 'base'",
                                (sid,),
                            )
                    else:
                        cur.execute(
                            "UPDATE studio.scene_assets SET asset_id = %s "
                            "WHERE scene_id = %s AND role = 'base'",
                            (check_id(persisted.id), sid),
                        )

                    return persisted, new_rev, True, "ok"
        except _TxAbort as abort:
            return None, abort.rev, False, abort.reason

    def is_path_referenced(self, path: str) -> bool:
        """Retorna True se qualquer linha em studio.assets ainda aponta para este caminho."""
        with _translated(), self._connect() as conn:
            cur = conn.execute(
                "SELECT 1 FROM studio.assets WHERE path = %s LIMIT 1",
                (path,),
            )
            return cur.fetchone() is not None

    def belongs_to_other_project(self, asset_id: str, project_id: str) -> bool:
        """Retorna True se o asset já estiver vinculado a cenas/camadas de outro projeto."""
        aid = check_id(asset_id)
        pid = check_id(project_id)
        with _translated(), self._connect() as conn:
            cur = conn.execute(
                "SELECT 1 WHERE EXISTS ("
                "  SELECT 1 FROM studio.scenes s "
                "  JOIN studio.videos v ON v.id = s.video_id "
                "  WHERE s.asset_id = %s AND v.project_id <> %s"
                ") OR EXISTS ("
                "  SELECT 1 FROM studio.scene_assets sa "
                "  JOIN studio.scenes s ON s.id = sa.scene_id "
                "  JOIN studio.videos v ON v.id = s.video_id "
                "  WHERE sa.asset_id = %s AND v.project_id <> %s"
                ") OR EXISTS ("
                "  SELECT 1 FROM studio.render_jobs rj "
                "  JOIN studio.videos v ON v.id = rj.video_id "
                "  WHERE rj.output_asset_id = %s AND v.project_id <> %s"
                ")",
                (aid, pid, aid, pid, aid, pid),
            )
            return cur.fetchone() is not None

    def delete_if_unreferenced(self, asset_id: str) -> bool:
        """Remove um asset apenas se nenhuma cena, scene_asset ou render_job o referencia (compensação)."""
        aid = check_id(asset_id)
        with _translated(), self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM studio.assets WHERE id = %s "
                "AND NOT EXISTS (SELECT 1 FROM studio.scenes WHERE asset_id = %s) "
                "AND NOT EXISTS (SELECT 1 FROM studio.render_jobs WHERE output_asset_id = %s) "
                "AND NOT EXISTS (SELECT 1 FROM studio.scene_assets WHERE asset_id = %s)",
                (aid, aid, aid, aid),
            )
            return cur.rowcount == 1

    def belongs_to_scope(self, asset_id: str, *, video_id: str | None = None, project_id: str | None = None) -> bool:
        aid = check_id(asset_id)
        with _translated(), self._connect() as conn:
            if video_id:
                vid = check_id(video_id)
                if project_id:
                    pid = check_id(project_id)
                    cur = conn.execute(
                        "SELECT 1 FROM studio.videos WHERE id = %s AND project_id = %s",
                        (vid, pid),
                    )
                    if not cur.fetchone():
                        return False
                cur = conn.execute(
                    "SELECT 1 WHERE EXISTS ("
                    "  SELECT 1 FROM studio.scenes WHERE video_id = %s AND asset_id = %s"
                    ") OR EXISTS ("
                    "  SELECT 1 FROM studio.scene_assets sa "
                    "  JOIN studio.scenes s ON s.id = sa.scene_id "
                    "  WHERE s.video_id = %s AND sa.asset_id = %s"
                    ") OR EXISTS ("
                    "  SELECT 1 FROM studio.render_jobs rj "
                    "  WHERE rj.video_id = %s AND rj.output_asset_id = %s"
                    ")",
                    (vid, aid, vid, aid, vid, aid),
                )
                return cur.fetchone() is not None
            elif project_id:
                pid = check_id(project_id)
                cur = conn.execute(
                    "SELECT 1 WHERE EXISTS ("
                    "  SELECT 1 FROM studio.scenes s "
                    "  JOIN studio.videos v ON v.id = s.video_id "
                    "  WHERE v.project_id = %s AND s.asset_id = %s"
                    ") OR EXISTS ("
                    "  SELECT 1 FROM studio.scene_assets sa "
                    "  JOIN studio.scenes s ON s.id = sa.scene_id "
                    "  JOIN studio.videos v ON v.id = s.video_id "
                    "  WHERE v.project_id = %s AND sa.asset_id = %s"
                    ") OR EXISTS ("
                    "  SELECT 1 FROM studio.render_jobs rj "
                    "  JOIN studio.videos v ON v.id = rj.video_id "
                    "  WHERE v.project_id = %s AND rj.output_asset_id = %s"
                    ")",
                    (pid, aid, pid, aid, pid, aid),
                )
                return cur.fetchone() is not None
            return False

    def add_asset_tag(self, asset_id: str, tag: str, *, project_id: str | None = None) -> list[str]:
        """Adiciona uma tag ao asset de forma concorrente-segura e idempotente."""
        aid = check_id(asset_id)
        if not project_id:
            raise AssetAccessDenied("project_id is required for asset tags")
        pid = check_id(project_id)
        clean_tag = normalize_tag(tag)
        with _translated(), self._connect() as conn:
            cur = conn.execute("SELECT 1 FROM studio.assets WHERE id = %s FOR UPDATE", (aid,))
            if not cur.fetchone():
                raise AssetNotFound(f"asset {aid} not found")

            if not self.belongs_to_scope(aid, project_id=pid):
                if self.belongs_to_other_project(aid, pid):
                    raise AssetAccessDenied("asset belongs to another project")
                raise AssetAccessDenied("asset outside project scope")

            cur = conn.execute("SELECT count(*) FROM studio.asset_tags WHERE project_id = %s AND asset_id = %s", (pid, aid))
            count = cur.fetchone()[0]
            if count >= MAX_TAGS_PER_ASSET:
                cur = conn.execute("SELECT 1 FROM studio.asset_tags WHERE project_id = %s AND asset_id = %s AND tag = %s", (pid, aid, clean_tag))
                if not cur.fetchone():
                    raise AssetTagInvalid(f"asset tag limit reached (maximum {MAX_TAGS_PER_ASSET} tags)")

            conn.execute(
                "INSERT INTO studio.asset_tags(project_id, asset_id, tag) VALUES (%s, %s, %s) "
                "ON CONFLICT (project_id, asset_id, tag) DO NOTHING",
                (pid, aid, clean_tag),
            )
            cur = conn.execute("SELECT tag FROM studio.asset_tags WHERE project_id = %s AND asset_id = %s ORDER BY tag ASC", (pid, aid))
            return [r[0] for r in cur.fetchall()]

    def remove_asset_tag(self, asset_id: str, tag: str, *, project_id: str | None = None) -> list[str]:
        """Remove uma tag do asset de forma idempotente."""
        aid = check_id(asset_id)
        if not project_id:
            raise AssetAccessDenied("project_id is required for asset tags")
        pid = check_id(project_id)
        clean_tag = normalize_tag(tag)
        with _translated(), self._connect() as conn:
            cur = conn.execute("SELECT 1 FROM studio.assets WHERE id = %s", (aid,))
            if not cur.fetchone():
                raise AssetNotFound(f"asset {aid} not found")

            if not self.belongs_to_scope(aid, project_id=pid):
                if self.belongs_to_other_project(aid, pid):
                    raise AssetAccessDenied("asset belongs to another project")
                raise AssetAccessDenied("asset outside project scope")

            conn.execute(
                "DELETE FROM studio.asset_tags WHERE project_id = %s AND asset_id = %s AND tag = %s",
                (pid, aid, clean_tag),
            )
            cur = conn.execute("SELECT tag FROM studio.asset_tags WHERE project_id = %s AND asset_id = %s ORDER BY tag ASC", (pid, aid))
            return [r[0] for r in cur.fetchall()]

    def list_asset_tags(self, asset_id: str, *, project_id: str | None = None) -> list[str]:
        """Lista todas as tags de um asset com verificação estrita de escopo."""
        aid = check_id(asset_id)
        if not project_id:
            raise AssetAccessDenied("project_id is required for asset tags")
        pid = check_id(project_id)
        with _translated(), self._connect() as conn:
            cur = conn.execute("SELECT 1 FROM studio.assets WHERE id = %s", (aid,))
            if not cur.fetchone():
                raise AssetNotFound(f"asset {aid} not found")

            if not self.belongs_to_scope(aid, project_id=pid):
                if self.belongs_to_other_project(aid, pid):
                    raise AssetAccessDenied("asset belongs to another project")
                raise AssetAccessDenied("asset outside project scope")

            cur = conn.execute("SELECT tag FROM studio.asset_tags WHERE project_id = %s AND asset_id = %s ORDER BY tag ASC", (pid, aid))
            return [r[0] for r in cur.fetchall()]

    def search_project_assets(
        self,
        *,
        project_id: str,
        query: str | None = None,
        tag: str | None = None,
        kind: str | None = None,
        license: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Asset], int]:
        """Busca determinística e paginada de assets com isolamento estrito por projeto/canal."""
        pid = check_id(project_id)
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))

        where_clauses = [
            """(
                EXISTS (
                    SELECT 1 FROM studio.scenes s
                    JOIN studio.videos v ON v.id = s.video_id
                    WHERE v.project_id = %(project_id)s AND s.asset_id = a.id
                )
                OR EXISTS (
                    SELECT 1 FROM studio.scene_assets sa
                    JOIN studio.scenes s ON s.id = sa.scene_id
                    JOIN studio.videos v ON v.id = s.video_id
                    WHERE v.project_id = %(project_id)s AND sa.asset_id = a.id
                )
                OR EXISTS (
                    SELECT 1 FROM studio.render_jobs rj
                    JOIN studio.videos v ON v.id = rj.video_id
                    WHERE v.project_id = %(project_id)s AND rj.output_asset_id = a.id
                )
            )"""
        ]
        params: dict[str, object] = {"project_id": pid}

        if tag is not None and str(tag).strip():
            clean_tag = normalize_tag(str(tag))
            where_clauses.append(
                "EXISTS (SELECT 1 FROM studio.asset_tags at WHERE at.project_id = %(project_id)s AND at.asset_id = a.id AND at.tag = %(tag)s)"
            )
            params["tag"] = clean_tag

        if query is not None and str(query).strip():
            clean_q = str(query).strip()
            params["like_q"] = f"%{escape_like(clean_q)}%"
            where_clauses.append(
                """(
                    a.path ILIKE %(like_q)s ESCAPE '\\'
                    OR a.license ILIKE %(like_q)s ESCAPE '\\'
                    OR a.attribution ILIKE %(like_q)s ESCAPE '\\'
                    OR a.source_url ILIKE %(like_q)s ESCAPE '\\'
                    OR a.provider ILIKE %(like_q)s ESCAPE '\\'
                    OR a.model ILIKE %(like_q)s ESCAPE '\\'
                    OR EXISTS (
                        SELECT 1 FROM studio.asset_tags at
                        WHERE at.project_id = %(project_id)s AND at.asset_id = a.id AND at.tag ILIKE %(like_q)s ESCAPE '\\'
                    )
                    OR EXISTS (
                        SELECT 1 FROM studio.scenes s
                        JOIN studio.videos v ON v.id = s.video_id
                        WHERE v.project_id = %(project_id)s AND s.asset_id = a.id AND s.label ILIKE %(like_q)s ESCAPE '\\'
                    )
                )"""
            )

        if kind is not None and str(kind).strip():
            where_clauses.append("a.kind = %(kind)s")
            params["kind"] = str(kind).strip().lower()

        if license is not None and str(license).strip():
            where_clauses.append("a.license ILIKE %(license)s")
            params["license"] = str(license).strip()

        where_sql = " AND ".join(where_clauses)

        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT count(DISTINCT a.id) AS total FROM studio.assets a WHERE {where_sql}", params)
            total = int(cur.fetchone()["total"])
            if total == 0:
                return [], 0

            page_params = dict(params)
            page_params["limit"] = limit
            page_params["offset"] = offset

            cur.execute(
                f"SELECT {_COLUMNS} FROM studio.assets a WHERE {where_sql} "
                "ORDER BY a.created_at DESC, a.id ASC LIMIT %(limit)s OFFSET %(offset)s",
                page_params,
            )
            rows = cur.fetchall()

            aids = [r["id"] for r in rows]
            tags_map: dict[str, list[str]] = {aid: [] for aid in aids}
            if aids:
                cur.execute(
                    "SELECT asset_id, tag FROM studio.asset_tags WHERE project_id = %s AND asset_id = ANY(%s) ORDER BY tag ASC",
                    (pid, aids),
                )
                for tag_row in cur.fetchall():
                    tags_map[tag_row["asset_id"]].append(tag_row["tag"])

            assets = [_asset(r, tags=tags_map.get(r["id"], [])) for r in rows]
            return assets, total


class PostgresProductionLock:
    """Advisory lock de sessão por vídeo, numa conexão própria (autocommit). Não espera: sem o lock, entra com False.
    Se a conexão cair no meio, o Postgres solta o lock sozinho."""

    def __init__(self, connect_autocommit: Callable[[], psycopg.Connection]):
        self._connect = connect_autocommit

    @contextlib.contextmanager
    def hold(self, video_id: str) -> Iterator[bool]:
        with _translated():
            conn = self._connect()
        try:
            with _translated():
                got = conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", ("produce:" + check_id(video_id),)).fetchone()[0]
            yield bool(got)
        finally:
            try:
                conn.close()  # fechar a sessão solta o lock
            except psycopg.Error:
                pass
