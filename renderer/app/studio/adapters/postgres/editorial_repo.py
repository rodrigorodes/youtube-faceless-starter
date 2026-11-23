"""Repositórios Postgres do fluxo editorial. O bloqueio da linha do vídeo (FOR UPDATE) serializa
gerações e checagens concorrentes do mesmo vídeo: quem perde enxerga o estado novo e recebe None/False."""
import hashlib
import uuid
from collections.abc import Callable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...application.errors import ScriptEditIdempotencyConflict, ScriptRevisionUnavailable
from ...application.ports import (FactCheckRecord, SceneDraft, SceneRevision, ScriptEditOutcome, ScriptEditRecord,
                                  ScriptRecord, ScriptRevisionSummary)
from ...domain.contracts import FactCheckReport, Scene, Script, SourceSnapshot, UsageEntry, VideoStatus
from ...domain.ids import check_id
from ...domain.longform import ScriptApproval, ScriptPlan
from ...domain.states import assert_transition
from .repo import _translated

_SNAPSHOT = "id, video_id, url, content_sha256, text, fetched_at"
_SCENE = "id, video_id, idx, narration, caption, label, image_prompt, claim_ids, asset_id, duration_s"
_REVISION = ("scene_id, idx, narration, caption, label, image_prompt, claim_ids, asset_id, "
             "media_review_required, duration_s")


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

    def find_edit(self, video_id: str, idempotency_key: str) -> ScriptEditRecord | None:
        """Leitura rápida do replay: devolve o resultado gravado para a chave, sem tocar no vídeo."""
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT payload_sha256, result_json FROM studio.script_edit_requests "
                        "WHERE video_id = %s AND idempotency_key = %s",
                        (check_id(video_id), idempotency_key))
            row = cur.fetchone()
            if row is None:
                return None
            return ScriptEditRecord(payload_sha256=row["payload_sha256"],
                                    outcome=_outcome_from_json(row["result_json"]))

    def save_edit(self, video_id: str, idempotency_key: str, payload_sha256: str, expected_version: int,
                  text: str, drafts: list[SceneDraft], claim_ids: list[str], plan: ScriptPlan | None,
                  content_hash: str | None, expected: VideoStatus, new: VideoStatus) -> ScriptEditOutcome | None:
        """CAS + escrita da versão + registro idempotente na mesma transação.

        O bloqueio da linha do vídeo serializa duas abas: a segunda com a mesma versão recebe None
        (CAS) e a mesma chave+hash recebe o resultado já gravado. Chave com hash diferente é conflito.
        """
        with _translated(), self._connect() as conn:
            row = conn.execute("SELECT status FROM studio.videos WHERE id = %s FOR UPDATE",
                               (check_id(video_id),)).fetchone()
            if row is None:
                return None
            existing = conn.execute("SELECT payload_sha256, result_json FROM studio.script_edit_requests "
                                    "WHERE video_id = %s AND idempotency_key = %s",
                                    (video_id, idempotency_key)).fetchone()
            if existing is not None:
                if existing[0] != payload_sha256:
                    raise ScriptEditIdempotencyConflict(
                        "idempotency key already used with a different payload")
                return _outcome_from_json(existing[1])
            if row[0] != expected.value:
                return None
            newest = conn.execute("SELECT COALESCE(MAX(version), 0) FROM studio.scripts "
                                  "WHERE video_id = %s", (video_id,)).fetchone()[0]
            if newest != expected_version:
                return None
            script = self._write_script(conn, video_id, text, drafts, claim_ids)
            if plan is not None:  # roteiro curto (gerado pelas fontes) não tem plano de capítulos nem hash de plano
                conn.execute("INSERT INTO studio.script_plans(video_id, version, structure, content_hash, words_per_minute, target_seconds) "
                             "VALUES (%s, %s, %s, %s, %s, %s)",
                             (video_id, script.version, Jsonb(plan.model_dump(mode="json")), content_hash,
                              plan.words_per_minute, plan.target_seconds))
            if expected != new:
                assert_transition(expected, new)
            conn.execute("UPDATE studio.videos SET status = %s, updated_at = now() WHERE id = %s",
                         (new.value, video_id))
            outcome = ScriptEditOutcome(script=script, scenes=tuple(_read_scenes(conn, video_id)))
            conn.execute("INSERT INTO studio.script_edit_requests(video_id, idempotency_key, payload_sha256, result_json) "
                         "VALUES (%s, %s, %s, %s)",
                         (video_id, idempotency_key, payload_sha256, Jsonb(_outcome_to_json(outcome))))
            return outcome

    def _lock_and_move(self, conn, video_id: str, expected: VideoStatus, new: VideoStatus) -> bool:
        row = conn.execute("SELECT status FROM studio.videos WHERE id = %s FOR UPDATE", (check_id(video_id),)).fetchone()
        if row is None or row[0] != expected.value:
            return False
        if expected != new:
            assert_transition(expected, new)
        conn.execute("UPDATE studio.videos SET status = %s, updated_at = now() WHERE id = %s", (new.value, video_id))
        return True

    def _write_script(self, conn, video_id: str, text: str, drafts: list[SceneDraft], claim_ids: list[str]) -> Script:
        # W4.5: a versão que deixa de ser a corrente é congelada com a mídia/duração que recebeu
        # depois de nascer; a versão nova nasce com o próprio snapshot. Nada é apagado.
        self._refresh_current_revision(conn, video_id)
        version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM studio.scripts WHERE video_id = %s", (video_id,)).fetchone()[0]
        script_id = uuid.uuid4().hex
        conn.execute("INSERT INTO studio.scripts(id, video_id, version, text, claim_ids) VALUES (%s, %s, %s, %s, %s)",
                     (script_id, video_id, version, text, Jsonb(claim_ids)))
        self._persist_scenes(conn, video_id, drafts)
        self._capture_revision(conn, video_id, version)
        return Script(id=script_id, video_id=video_id, version=version, text=text, claim_ids=claim_ids)

    def _persist_scenes(self, conn, video_id: str, drafts: list[SceneDraft]) -> None:
        """Mantém o id da cena entre versões; `idx` é só a ordem.

        Casa primeiro por conteúdo (narração + intenção visual): a cena que só mudou de posição
        mantém id e mídia. Depois casa o que sobrou pela posição: a cena editada no lugar mantém o
        id, mas o vínculo de mídia é limpo e a cena é marcada para revisão (a mídia antiga pode
        ficar incompatível com a fala nova). Cena nova recebe id novo. A posição é aplicada por
        último, com deslocamento temporário, para não colidir com `UNIQUE (video_id, idx)`.
        """
        existing = conn.execute(
            "SELECT id, idx, narration, image_prompt FROM studio.scenes WHERE video_id = %s ORDER BY idx",
            (video_id,),
        ).fetchall()
        used: set[int] = set()
        kept: list[tuple[int, SceneDraft, str, bool, bool]] = []
        assigned: set[int] = set()

        for position, draft in enumerate(drafts):
            for i, row in enumerate(existing):
                if i not in used and row[2] == draft.narration and row[3] == draft.image_prompt:
                    used.add(i)
                    kept.append((position, draft, row[0], False, row[2] != draft.narration))
                    assigned.add(position)
                    break

        for position, draft in enumerate(drafts):
            if position in assigned:
                continue
            for i, row in enumerate(existing):
                if i not in used and row[1] == position:
                    used.add(i)
                    kept.append((position, draft, row[0], True, row[2] != draft.narration))
                    assigned.add(position)
                    break

        removed = [row[0] for i, row in enumerate(existing) if i not in used]
        if removed:
            conn.execute("DELETE FROM studio.scenes WHERE video_id = %s AND id = ANY(%s)", (video_id, removed))

        if kept:
            max_idx = max(row[1] for row in existing)
            # O deslocamento precisa ficar acima de QUALQUER posição final para que a troca de
            # ordem não colida com UNIQUE (video_id, idx) no meio do caminho.
            offset = max(max_idx, len(drafts)) + 1
            conn.execute("UPDATE studio.scenes SET idx = idx + %s WHERE video_id = %s", (offset, video_id))

        for position, draft, scene_id, affected, narration_changed in kept:
            if affected:
                conn.execute(
                    "UPDATE studio.scenes SET idx = %s, narration = %s, caption = %s, label = %s, "
                    "image_prompt = %s, claim_ids = %s, asset_id = NULL, media_review_required = true, "
                    "duration_s = CASE WHEN %s THEN NULL ELSE duration_s END WHERE id = %s",
                    (position, draft.narration, draft.caption, draft.label, draft.image_prompt,
                     Jsonb(draft.claim_ids), narration_changed, scene_id),
                )
            else:
                conn.execute("UPDATE studio.scenes SET idx = %s, caption = %s, label = %s, claim_ids = %s WHERE id = %s",
                             (position, draft.caption, draft.label, Jsonb(draft.claim_ids), scene_id))

        for position, draft in enumerate(drafts):
            if position in assigned:
                continue
            conn.execute("INSERT INTO studio.scenes(id, video_id, idx, narration, caption, label, image_prompt, claim_ids) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                         (uuid.uuid4().hex, video_id, position, draft.narration, draft.caption, draft.label,
                          draft.image_prompt, Jsonb(draft.claim_ids)))

    def _capture_revision(self, conn, video_id: str, version: int) -> None:
        """Grava (upsert) o snapshot de `version` a partir das cenas correntes.

        Só é chamado para a versão que está sendo escrita (a corrente) e para a que acabou de
        deixar de ser corrente. Uma vez congelada, a revisão antiga nunca é reescrita.
        """
        rows = conn.execute(
            "SELECT id, idx, narration, caption, label, image_prompt, claim_ids, asset_id, "
            "media_review_required, duration_s FROM studio.scenes WHERE video_id = %s ORDER BY idx",
            (video_id,),
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT INTO studio.scene_revisions(video_id, version, scene_id, idx, narration, caption, "
                "label, image_prompt, claim_ids, asset_id, media_review_required, duration_s) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (video_id, version, scene_id) DO UPDATE SET idx = EXCLUDED.idx, "
                "narration = EXCLUDED.narration, caption = EXCLUDED.caption, label = EXCLUDED.label, "
                "image_prompt = EXCLUDED.image_prompt, claim_ids = EXCLUDED.claim_ids, "
                "asset_id = EXCLUDED.asset_id, media_review_required = EXCLUDED.media_review_required, "
                "duration_s = EXCLUDED.duration_s",
                (video_id, version, row[0], row[1], row[2], row[3], row[4], row[5], Jsonb(row[6]),
                 row[7], row[8], row[9]),
            )
        scene_ids = [row[0] for row in rows]
        if scene_ids:
            conn.execute(
                "DELETE FROM studio.scene_revisions WHERE video_id = %s AND version = %s AND scene_id <> ALL(%s)",
                (video_id, version, scene_ids),
            )
        else:
            conn.execute("DELETE FROM studio.scene_revisions WHERE video_id = %s AND version = %s",
                         (video_id, version))

    def _refresh_current_revision(self, conn, video_id: str) -> None:
        """Congela a versão corrente antes de outra nascer, com a mídia/duração que ela recebeu."""
        newest = conn.execute("SELECT COALESCE(MAX(version), 0) FROM studio.scripts WHERE video_id = %s",
                              (video_id,)).fetchone()[0]
        if newest:
            self._capture_revision(conn, video_id, int(newest))

    def revision_scenes(self, video_id: str, version: int) -> list[SceneRevision]:
        """Snapshot da revisão (ordem por `idx`); a corrente vem das cenas vivas, não do snapshot."""
        with _translated(), self._connect() as conn:
            current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM studio.scripts WHERE video_id = %s",
                                   (check_id(video_id),)).fetchone()[0]
            if version == current:
                rows = conn.execute(
                    "SELECT id, idx, narration, caption, label, image_prompt, claim_ids, asset_id, "
                    "media_review_required, duration_s FROM studio.scenes WHERE video_id = %s ORDER BY idx",
                    (video_id,),
                ).fetchall()
            else:
                rows = self._read_revision_rows(conn, video_id, version)
            return [_scene_revision_from_row(row) for row in rows]

    def revision_summaries(self, video_id: str) -> list[ScriptRevisionSummary]:
        """Revisões com snapshot, com contagem de cenas e pendências; a corrente é medida ao vivo."""
        with _translated(), self._connect() as conn:
            rows = conn.execute(
                "SELECT version, COUNT(*) AS scene_count, "
                "COUNT(*) FILTER (WHERE media_review_required) AS media_pending, "
                "MIN(captured_at) AS captured_at "
                "FROM studio.scene_revisions WHERE video_id = %s GROUP BY version ORDER BY version",
                (check_id(video_id),),
            ).fetchall()
            summaries = {int(row[0]): ScriptRevisionSummary(version=int(row[0]), scene_count=int(row[1]),
                                                            media_pending=int(row[2]), captured_at=row[3])
                         for row in rows}
            current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM studio.scripts WHERE video_id = %s",
                                   (check_id(video_id),)).fetchone()[0]
            if current:
                live = conn.execute(
                    "SELECT COUNT(*), COUNT(*) FILTER (WHERE media_review_required) FROM studio.scenes "
                    "WHERE video_id = %s", (video_id,)).fetchone()
                previous = summaries.get(int(current))
                summaries[int(current)] = ScriptRevisionSummary(
                    version=int(current), scene_count=int(live[0]), media_pending=int(live[1]),
                    captured_at=previous.captured_at if previous is not None else None)
            return [summaries[version] for version in sorted(summaries)]

    def save_restore(self, video_id: str, idempotency_key: str, payload_sha256: str, expected_version: int,
                     source_version: int, text: str, claim_ids: list[str], plan: ScriptPlan,
                     content_hash: str, expected: VideoStatus, new: VideoStatus) -> ScriptEditOutcome | None:
        """Restaura a revisão `source_version` como versão +1, com CAS/idempotência (W4.5/EDIT-04)."""
        with _translated(), self._connect() as conn:
            row = conn.execute("SELECT status FROM studio.videos WHERE id = %s FOR UPDATE",
                               (check_id(video_id),)).fetchone()
            if row is None:
                return None
            existing = conn.execute("SELECT payload_sha256, result_json FROM studio.script_edit_requests "
                                    "WHERE video_id = %s AND idempotency_key = %s",
                                    (video_id, idempotency_key)).fetchone()
            if existing is not None:
                if existing[0] != payload_sha256:
                    raise ScriptEditIdempotencyConflict(
                        "idempotency key already used with a different payload")
                return _outcome_from_json(existing[1])
            if row[0] != expected.value:
                return None
            newest = conn.execute("SELECT COALESCE(MAX(version), 0) FROM studio.scripts "
                                  "WHERE video_id = %s", (video_id,)).fetchone()[0]
            if newest != expected_version:
                return None
            # A revisão escolhida pode ser a corrente: congela o estado vivo antes de lê-lo.
            self._refresh_current_revision(conn, video_id)
            revisions = self._read_revision_rows(conn, video_id, source_version)
            if not revisions:
                raise ScriptRevisionUnavailable(
                    f"revision {source_version} has no recoverable scene snapshot")
            version = int(newest) + 1
            script_id = uuid.uuid4().hex
            conn.execute("INSERT INTO studio.scripts(id, video_id, version, text, claim_ids) "
                         "VALUES (%s, %s, %s, %s, %s)",
                         (script_id, video_id, version, text, Jsonb(claim_ids)))
            conn.execute("INSERT INTO studio.script_plans(video_id, version, structure, content_hash, "
                         "words_per_minute, target_seconds) VALUES (%s, %s, %s, %s, %s, %s)",
                         (video_id, version, Jsonb(plan.model_dump(mode="json")), content_hash,
                          plan.words_per_minute, plan.target_seconds))
            self._restore_scenes(conn, video_id, revisions)
            if expected != new:
                assert_transition(expected, new)
            conn.execute("UPDATE studio.videos SET status = %s, updated_at = now() WHERE id = %s",
                         (new.value, video_id))
            self._capture_revision(conn, video_id, version)
            outcome = ScriptEditOutcome(
                script=Script(id=script_id, video_id=video_id, version=version, text=text, claim_ids=claim_ids),
                scenes=tuple(_read_scenes(conn, video_id)))
            conn.execute("INSERT INTO studio.script_edit_requests(video_id, idempotency_key, payload_sha256, "
                         "result_json) VALUES (%s, %s, %s, %s)",
                         (video_id, idempotency_key, payload_sha256, Jsonb(_outcome_to_json(outcome))))
            return outcome

    def _read_revision_rows(self, conn, video_id: str, version: int) -> list[tuple]:
        return conn.execute(
            f"SELECT {_REVISION} FROM studio.scene_revisions WHERE video_id = %s AND version = %s ORDER BY idx",
            (video_id, version),
        ).fetchall()

    def _restore_scenes(self, conn, video_id: str, revisions: list[tuple]) -> None:
        """Reconcilia a projeção corrente com a revisão escolhida, preservando o `id` de cada cena.

        O vínculo de mídia vem da revisão (não do estado atual); asset inexistente vira
        `media_review_required` com `asset_id = NULL`. Cena fora da revisão sai da projeção, mas o
        snapshot continua guardando o histórico.
        """
        existing = conn.execute("SELECT id, idx FROM studio.scenes WHERE video_id = %s ORDER BY idx",
                                (video_id,)).fetchall()
        existing_ids = {row[0] for row in existing}
        asset_ids = sorted({row[7] for row in revisions if row[7]})
        available: set[str] = set()
        if asset_ids:
            available = {row[0] for row in conn.execute(
                "SELECT id FROM studio.assets WHERE id = ANY(%s)", (asset_ids,)).fetchall()}
        if existing:
            offset = max(max(row[1] for row in existing), len(revisions)) + 1
            conn.execute("UPDATE studio.scenes SET idx = idx + %s WHERE video_id = %s", (offset, video_id))
        for position, revision in enumerate(revisions):
            (scene_id, _idx, narration, caption, label, image_prompt, claim_ids, asset_id,
             review_required, duration_s) = revision
            kept_asset = asset_id if asset_id in available else None
            needs_review = bool(review_required) or (asset_id is not None and kept_asset is None)
            if scene_id in existing_ids:
                conn.execute(
                    "UPDATE studio.scenes SET idx = %s, narration = %s, caption = %s, label = %s, "
                    "image_prompt = %s, claim_ids = %s, asset_id = %s, media_review_required = %s, "
                    "duration_s = %s WHERE id = %s AND video_id = %s",
                    (position, narration, caption, label, image_prompt, Jsonb(claim_ids), kept_asset,
                     needs_review, duration_s, scene_id, video_id),
                )
            else:
                conn.execute(
                    "INSERT INTO studio.scenes(id, video_id, idx, narration, caption, label, image_prompt, "
                    "claim_ids, asset_id, media_review_required, duration_s) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (scene_id, video_id, position, narration, caption, label, image_prompt,
                     Jsonb(claim_ids), kept_asset, needs_review, duration_s),
                )
        if existing_ids:
            conn.execute("DELETE FROM studio.scenes WHERE video_id = %s AND id <> ALL(%s)",
                         (video_id, [row[0] for row in revisions]))

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


def _read_scenes(conn, video_id: str) -> list[Scene]:
    """Cenas persistidas na transação corrente (visão do próprio escritor, sem commit intermediário)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_SCENE} FROM studio.scenes WHERE video_id = %s ORDER BY idx", (check_id(video_id),))
        return [Scene.model_validate(row) for row in cur.fetchall()]


def _scene_revision_from_row(row: tuple) -> SceneRevision:
    """Linha de `studio.scenes` (colunas `id...`) ou de `studio.scene_revisions` (`scene_id...`)."""
    return SceneRevision(scene_id=row[0], idx=row[1], narration=row[2], caption=row[3], label=row[4],
                         image_prompt=row[5], claim_ids=list(row[6]), asset_id=row[7],
                         media_review_required=bool(row[8]), duration_s=row[9])


def _outcome_to_json(outcome: ScriptEditOutcome) -> dict:
    return {
        "script": outcome.script.model_dump(mode="json"),
        "scenes": [scene.model_dump(mode="json") for scene in outcome.scenes],
    }


def _outcome_from_json(data: dict) -> ScriptEditOutcome:
    return ScriptEditOutcome(
        script=Script.model_validate(data["script"]),
        scenes=tuple(Scene.model_validate(scene) for scene in data["scenes"]),
    )
