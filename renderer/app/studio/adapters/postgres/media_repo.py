"""Repositório Postgres de assets. `add` é idempotente por cache_key: em corrida, vence o primeiro e todos recebem o mesmo asset."""
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

    def link_scene(self, video_id: str, idx: int, asset_id: str) -> None:
        with _translated(), self._connect() as conn:
            conn.execute("UPDATE studio.scenes SET asset_id = %s WHERE video_id = %s AND idx = %s",
                         (check_id(asset_id), check_id(video_id), idx))
