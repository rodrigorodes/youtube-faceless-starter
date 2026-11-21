"""Repositório Postgres do Render Plan versionado e do índice de cache (RP-027/RP-029).

Duas identidades, duas famílias de tabela:

- **lógica** — ``render_plans`` (o documento por ``plan_id`` + ``revision``) e
  ``render_cache_entries`` (o nó por ``(plan_id, node_kind, node_key)``, com o fingerprint do
  conteúdo que produziu o artefato);
- **física** — ``plan_artifacts`` (hash do conteúdo + codec + localização), independente da
  revisão que a referenciou.

A gravação do plano é idempotente por ``(plan_id, revision)``: regravar a mesma revisão
substitui o documento e não duplica nada. ``entries`` devolve o artefato mais recente por nó —
é o que ``PlanRegeneration`` usa para decidir um acerto de cache.
"""
from collections.abc import Callable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...domain.render_cache import CacheEntry, NodeId, PlanArtifact
from ...domain.render_plan import RenderPlan
from .editorial_repo import _Base
from .repo import _translated

_PLAN_COLUMNS = "plan_id, revision, project_id, video_id, document"
_ENTRY_COLUMNS = "plan_id, node_kind, node_key, fingerprint, artifact_sha256, artifact_uri, revision"


def _artifact(reference) -> PlanArtifact:
    codec = reference.metadata.get("codec") if reference.metadata else None
    return PlanArtifact(
        content_sha256=reference.content_sha256,
        location=reference.uri,
        codec=codec,
        media_type=reference.media_type,
    )


class PostgresRenderPlanRepository(_Base):
    def save_plan(self, plan: RenderPlan) -> None:
        with _translated(), self._connect() as conn:
            conn.execute(
                "INSERT INTO studio.render_plans(plan_id, revision, schema_version, project_id, video_id, document) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (plan_id, revision) DO UPDATE SET schema_version = EXCLUDED.schema_version, "
                "project_id = EXCLUDED.project_id, video_id = EXCLUDED.video_id, document = EXCLUDED.document",
                (plan.plan_id, plan.revision, plan.schema_version, plan.project_id, plan.video_id,
                 Jsonb(plan.model_dump(mode="json"))),
            )
            for reference in plan.asset_manifest:
                artifact = _artifact(reference)
                conn.execute(
                    "INSERT INTO studio.plan_artifacts(content_sha256, location, codec, media_type) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (content_sha256, location) DO UPDATE SET "
                    "codec = EXCLUDED.codec, media_type = EXCLUDED.media_type",
                    (artifact.content_sha256, artifact.location, artifact.codec, artifact.media_type),
                )

    def get_plan(self, plan_id: str, revision: int) -> RenderPlan | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_PLAN_COLUMNS} FROM studio.render_plans WHERE plan_id = %s AND revision = %s",
                        (plan_id, revision))
            row = cur.fetchone()
            return RenderPlan.model_validate(row["document"]) if row else None

    def latest_plan(self, plan_id: str) -> RenderPlan | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_PLAN_COLUMNS} FROM studio.render_plans WHERE plan_id = %s "
                        "ORDER BY revision DESC LIMIT 1", (plan_id,))
            row = cur.fetchone()
            return RenderPlan.model_validate(row["document"]) if row else None

    def revisions(self, plan_id: str) -> list[int]:
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT revision FROM studio.render_plans WHERE plan_id = %s ORDER BY revision", (plan_id,))
            return [row[0] for row in cur.fetchall()]

    def record_entry(self, entry: CacheEntry) -> None:
        with _translated(), self._connect() as conn:
            conn.execute(
                "INSERT INTO studio.render_cache_entries(plan_id, revision, node_kind, node_key, fingerprint, "
                "artifact_sha256, artifact_uri) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (plan_id, node_kind, node_key, fingerprint) DO UPDATE SET revision = EXCLUDED.revision, "
                "artifact_sha256 = EXCLUDED.artifact_sha256, artifact_uri = EXCLUDED.artifact_uri",
                (entry.plan_id, entry.revision, entry.node.kind, entry.node.key, entry.fingerprint,
                 entry.artifact_sha256, entry.artifact_uri),
            )

    def record_entries(self, entries) -> None:
        """Grava o índice de cache de uma revisão inteira numa transação só (RP-06b)."""
        items = list(entries)
        if not items:
            return
        with _translated(), self._connect() as conn:
            for entry in items:
                conn.execute(
                    "INSERT INTO studio.render_cache_entries(plan_id, revision, node_kind, node_key, fingerprint, "
                    "artifact_sha256, artifact_uri) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (plan_id, node_kind, node_key, fingerprint) DO UPDATE SET revision = EXCLUDED.revision, "
                    "artifact_sha256 = EXCLUDED.artifact_sha256, artifact_uri = EXCLUDED.artifact_uri",
                    (entry.plan_id, entry.revision, entry.node.kind, entry.node.key, entry.fingerprint,
                     entry.artifact_sha256, entry.artifact_uri),
                )

    def record_artifacts(self, artifacts) -> None:
        """Grava os artefatos físicos (hash/codec/localização) produzidos, numa transação só (RP-06b)."""
        items = list(artifacts)
        if not items:
            return
        with _translated(), self._connect() as conn:
            for artifact in items:
                conn.execute(
                    "INSERT INTO studio.plan_artifacts(content_sha256, location, codec, media_type, byte_size) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (content_sha256, location) DO UPDATE SET "
                    "codec = EXCLUDED.codec, media_type = EXCLUDED.media_type, byte_size = EXCLUDED.byte_size",
                    (artifact.content_sha256, artifact.location, artifact.codec, artifact.media_type,
                     artifact.byte_size),
                )

    def entries(self, plan_id: str) -> dict[NodeId, CacheEntry]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT DISTINCT ON (node_kind, node_key) {_ENTRY_COLUMNS} FROM studio.render_cache_entries "
                "WHERE plan_id = %s ORDER BY node_kind, node_key, revision DESC, created_at DESC", (plan_id,))
            return {NodeId(row["node_kind"], row["node_key"]): _entry(row) for row in cur.fetchall()}

    def artifact(self, content_sha256: str, location: str) -> PlanArtifact | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT content_sha256, location, codec, media_type, byte_size FROM studio.plan_artifacts "
                        "WHERE content_sha256 = %s AND location = %s", (content_sha256, location))
            row = cur.fetchone()
            return PlanArtifact(**row) if row else None


def _entry(row: dict) -> CacheEntry:
    return CacheEntry(
        plan_id=row["plan_id"],
        node=NodeId(row["node_kind"], row["node_key"]),
        fingerprint=row["fingerprint"],
        artifact_sha256=row["artifact_sha256"],
        artifact_uri=row["artifact_uri"],
        revision=row["revision"],
    )
