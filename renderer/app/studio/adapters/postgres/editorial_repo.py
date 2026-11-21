"""Repositórios Postgres do fluxo editorial. O bloqueio da linha do vídeo (FOR UPDATE) serializa
gerações e checagens concorrentes do mesmo vídeo: quem perde enxerga o estado novo e recebe None/False."""
import hashlib
import uuid
from collections.abc import Callable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...application.ports import FactCheckRecord, SceneDraft, ScriptRecord
from ...domain.contracts import FactCheckReport, Scene, Script, SourceSnapshot, UsageEntry, VideoStatus
from ...domain.ids import check_id
from ...domain.longform import ScriptApproval, ScriptPlan
from ...domain.states import assert_transition
from .repo import _translated

_SNAPSHOT = "id, video_id, url, content_sha256, text, fetched_at"
_SCENE = "id, video_id, idx, narration, caption, label, image_prompt, claim_ids, asset_id, duration_s"


class _Base:
    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self._connect = connect


class PostgresSnapshotRepository(_Base):
    def add(self, video_id: str, url: str, text: str) -> SourceSnapshot:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"INSERT INTO studio.source_snapshots(id, video_id, url, content_sha256, text) VALUES (%s, %s, %s, %s, %s) "
                        f"ON CONFLICT (video_id, url, content_sha256) DO UPDATE SET url = EXCLUDED.url RETURNING {_SNAPSHOT}",
                        (uuid.uuid4().hex, check_id(video_id), url, digest, text))
            return SourceSnapshot.model_validate(cur.fetchone())

    def list(self, video_id: str) -> list[SourceSnapshot]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_SNAPSHOT} FROM studio.source_snapshots WHERE video_id = %s ORDER BY fetched_at, id", (check_id(video_id),))
            return [SourceSnapshot.model_validate(r) for r in cur.fetchall()]


class PostgresScriptRepository(_Base):
    def save_and_advance(self, video_id: str, text: str, drafts: list[SceneDraft], claim_ids: list[str],
                         expected: VideoStatus, new: VideoStatus) -> Script | None:
        with _translated(), self._connect() as conn:
            if not self._lock_and_move(conn, video_id, expected, new):
                return None
            return self._write_script(conn, video_id, text, drafts, claim_ids)

    def save_planned_version(self, video_id: str, text: str, drafts: list[SceneDraft], claim_ids: list[str],
                             plan: ScriptPlan, content_hash: str, expected: VideoStatus, new: VideoStatus) -> Script | None:
        """Grava roteiro, cenas e plano/hash na mesma transação: nunca há versão sem hash."""
        with _translated(), self._connect() as conn:
            if not self._lock_and_move(conn, video_id, expected, new):
                return None
            script = self._write_script(conn, video_id, text, drafts, claim_ids)
            conn.execute("INSERT INTO studio.script_plans(video_id, version, structure, content_hash, words_per_minute, target_seconds) "
                         "VALUES (%s, %s, %s, %s, %s, %s)",
                         (video_id, script.version, Jsonb(plan.model_dump(mode="json")), content_hash,
                          plan.words_per_minute, plan.target_seconds))
            return script

    def _lock_and_move(self, conn, video_id: str, expected: VideoStatus, new: VideoStatus) -> bool:
        row = conn.execute("SELECT status FROM studio.videos WHERE id = %s FOR UPDATE", (check_id(video_id),)).fetchone()
        if row is None or row[0] != expected.value:
            return False
        if expected != new:
            assert_transition(expected, new)
        conn.execute("UPDATE studio.videos SET status = %s, updated_at = now() WHERE id = %s", (new.value, video_id))
        return True

    def _write_script(self, conn, video_id: str, text: str, drafts: list[SceneDraft], claim_ids: list[str]) -> Script:
        version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM studio.scripts WHERE video_id = %s", (video_id,)).fetchone()[0]
        script_id = uuid.uuid4().hex
        conn.execute("INSERT INTO studio.scripts(id, video_id, version, text, claim_ids) VALUES (%s, %s, %s, %s, %s)",
                     (script_id, video_id, version, text, Jsonb(claim_ids)))
        conn.execute("DELETE FROM studio.scenes WHERE video_id = %s", (video_id,))
        for idx, d in enumerate(drafts):
            conn.execute("INSERT INTO studio.scenes(id, video_id, idx, narration, caption, label, image_prompt, claim_ids) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                         (uuid.uuid4().hex, video_id, idx, d.narration, d.caption, d.label, d.image_prompt, Jsonb(d.claim_ids)))
        return Script(id=script_id, video_id=video_id, version=version, text=text, claim_ids=claim_ids)

    def list_script_records(self, video_id: str) -> list[ScriptRecord]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT s.id, s.video_id, s.version, s.text, s.claim_ids, "
                        "p.structure, p.content_hash, "
                        "a.decision, a.reason, a.approved_by, a.approved_at, a.content_hash AS approval_hash "
                        "FROM studio.scripts s "
                        "LEFT JOIN studio.script_plans p ON p.video_id = s.video_id AND p.version = s.version "
                        "LEFT JOIN studio.script_approvals a ON a.video_id = s.video_id AND a.version = s.version "
                        "WHERE s.video_id = %s ORDER BY s.version", (check_id(video_id),))
            records: list[ScriptRecord] = []
            for row in cur.fetchall():
                script = Script(id=row["id"], video_id=row["video_id"], version=row["version"], text=row["text"],
                                claim_ids=row["claim_ids"])
                plan = ScriptPlan.model_validate(row["structure"]) if row["structure"] is not None else None
                approval = None
                if row["decision"] is not None:
                    approval = ScriptApproval(video_id=row["video_id"], script_version=row["version"],
                                              content_hash=row["approval_hash"], decision=row["decision"],
                                              reason=row["reason"] or "", approved_by=row["approved_by"],
                                              approved_at=row["approved_at"])
                records.append(ScriptRecord(script=script, plan=plan, content_hash=row["content_hash"], approval=approval))
            return records

    def approve(self, video_id: str, version: int, content_hash: str, decision: str, reason: str,
                approved_by: str, approved_at=None) -> bool:
        """Vincula a decisão à (versão, hash); False se essa versão já não é a mais recente."""
        with _translated(), self._connect() as conn:
            row = conn.execute("SELECT status FROM studio.videos WHERE id = %s FOR UPDATE", (check_id(video_id),)).fetchone()
            if row is None:
                return False
            newest = conn.execute("SELECT COALESCE(MAX(version), 0) FROM studio.scripts WHERE video_id = %s", (video_id,)).fetchone()[0]
            if newest != version:
                return False
            stored = conn.execute("SELECT content_hash FROM studio.script_plans WHERE video_id = %s AND version = %s",
                                  (video_id, version)).fetchone()
            if stored is None or stored[0] != content_hash:
                return False
            conn.execute("INSERT INTO studio.script_approvals(video_id, version, content_hash, decision, reason, approved_by, approved_at) "
                         "VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, now())) "
                         "ON CONFLICT (video_id, version) DO UPDATE SET content_hash = EXCLUDED.content_hash, "
                         "decision = EXCLUDED.decision, reason = EXCLUDED.reason, approved_by = EXCLUDED.approved_by, "
                         "approved_at = EXCLUDED.approved_at",
                         (video_id, version, content_hash, decision, reason, approved_by, approved_at))
            return True

    def scenes(self, video_id: str) -> list[Scene]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_SCENE} FROM studio.scenes WHERE video_id = %s ORDER BY idx", (check_id(video_id),))
            return [Scene.model_validate(r) for r in cur.fetchall()]

    def latest(self, video_id: str) -> Script | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, video_id, version, text, claim_ids FROM studio.scripts WHERE video_id = %s "
                        "ORDER BY version DESC LIMIT 1", (check_id(video_id),))
            row = cur.fetchone()
            return Script.model_validate(row) if row else None


class PostgresFactCheckRepository(_Base):
    def save(self, video_id: str, report: FactCheckReport, advance: bool, script_version: int) -> bool:
        with _translated(), self._connect() as conn:
            if advance:
                row = conn.execute("SELECT status FROM studio.videos WHERE id = %s FOR UPDATE", (check_id(video_id),)).fetchone()
                if row is None or row[0] != VideoStatus.SCRIPTED.value:
                    return False
                newest = conn.execute("SELECT MAX(version) FROM studio.scripts WHERE video_id = %s", (video_id,)).fetchone()[0]
                if newest != script_version:  # o roteiro foi regerado depois da leitura: este relatório não vale para ele
                    return False
                conn.execute("UPDATE studio.videos SET status = %s, updated_at = now() WHERE id = %s", (VideoStatus.FACT_CHECKED.value, video_id))
            conn.execute("INSERT INTO studio.fact_checks(id, video_id, passed, overridden, override_reason, report, script_version) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                         (uuid.uuid4().hex, check_id(video_id), report.passed, report.overridden, report.override_reason,
                          Jsonb(report.model_dump(mode="json")), script_version))
            return True

    def latest(self, video_id: str) -> FactCheckRecord | None:
        """Último relatório do vídeo com a versão do roteiro que cobre; None se não houver."""
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT report, script_version FROM studio.fact_checks WHERE video_id = %s "
                        "ORDER BY created_at DESC, id DESC LIMIT 1", (check_id(video_id),))
            row = cur.fetchone()
            if row is None or row["script_version"] is None:
                return None
            return FactCheckRecord(report=FactCheckReport.model_validate(row["report"]),
                                   script_version=row["script_version"])


class PostgresUsageRepository(_Base):
    def record(self, video_id: str | None, entry: UsageEntry) -> None:
        with _translated(), self._connect() as conn:
            conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, input_tokens, output_tokens, "
                         "cache_read_tokens, cache_write_tokens, cost_usd) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                         (check_id(video_id) if video_id else None, entry.step, entry.provider, entry.model, entry.input_tokens,
                          entry.output_tokens, entry.cache_read_tokens, entry.cache_write_tokens, entry.cost_usd))

    def spent_video(self, video_id: str) -> float:
        with _translated(), self._connect() as conn:
            return float(conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM studio.usage_ledger WHERE video_id = %s", (check_id(video_id),)).fetchone()[0])

    def spent_month(self) -> float:
        with _translated(), self._connect() as conn:
            return float(conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM studio.usage_ledger "
                                      "WHERE created_at >= date_trunc('month', now())").fetchone()[0])
