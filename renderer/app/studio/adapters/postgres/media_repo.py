"""Repositório Postgres de assets. `add` é idempotente por cache_key: em corrida, vence o primeiro e todos recebem o mesmo asset."""
import contextlib
from collections.abc import Callable, Iterator

import psycopg
from psycopg.rows import dict_row

from ...domain.contracts import Asset
from ...domain.ids import check_cache_key, check_id
from .editorial_repo import _Base
from .repo import _translated

_COLUMNS = "id, kind, cache_key, path, provider, model, license, attribution, source_url, cost_usd"


def _asset(row: dict) -> Asset:
    row = dict(row)
    row["cost_usd"] = float(row["cost_usd"])
    return Asset.model_validate(row)


class PostgresAssetRepository(_Base):
    def find(self, cache_key: str) -> Asset | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM studio.assets WHERE cache_key = %s", (check_cache_key(cache_key),))
            row = cur.fetchone()
            return _asset(row) if row else None

    def get(self, asset_id: str) -> Asset | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM studio.assets WHERE id = %s", (check_id(asset_id),))
            row = cur.fetchone()
            return _asset(row) if row else None

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
            cur = conn.execute("UPDATE studio.scenes SET asset_id = %s "
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
