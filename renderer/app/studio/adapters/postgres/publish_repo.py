"""Repositórios Postgres de aprovação e publicação. Cada operação que muda estado é uma transação com verificação e ação juntas."""
import uuid
from datetime import datetime

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...application.publishing import PublicationConflict
from ...application.editorial import StateConflict
from ...domain.contracts import Approval, Publication, VideoStatus
from ...domain.ids import check_id
from ...domain.publication_policy import PublicationIntentEvidence, idempotency_key
from ...domain.states import assert_transition
from .editorial_repo import _Base
from .repo import _translated

_PUB = "id, video_id, youtube_video_id, upload_uri, status, publish_at, privacy, thumbnail_set, attempt, error"


class PostgresApprovalRepository(_Base):
    def decide(self, video_id: str, expected: VideoStatus, decision: str, *, title: str, description: str, tags: list[str],
               publish_at: datetime | None, reason: str, qa_override: bool, output_asset_id: str | None = None,
               visibility: str = "private", public_confirmed: bool = False) -> bool:
        target = VideoStatus.APPROVED if decision == "approved" else VideoStatus.REJECTED
        with _translated():
            if expected == VideoStatus.RENDERED:  # vídeo com QA reprovado: passa pela revisão e decide na mesma transação
                assert_transition(VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL)
                assert_transition(VideoStatus.AWAITING_APPROVAL, target)
            else:
                assert_transition(expected, target)
            with self._connect() as conn:
                row = conn.execute("SELECT status, qa_report FROM studio.videos WHERE id = %s FOR UPDATE",
                                   (check_id(video_id),)).fetchone()
                if row is None or row[0] != expected.value:
                    return False
                intent = None
                if decision == "approved":
                    if not output_asset_id:
                        return False
                    latest = conn.execute("SELECT j.id, j.output_asset_id, j.finished_at, a.cache_key "
                                          "FROM studio.render_jobs j JOIN studio.assets a ON a.id = j.output_asset_id "
                                          "WHERE j.video_id = %s AND j.status = 'SUCCEEDED' "
                                          "ORDER BY j.finished_at DESC, j.attempt DESC LIMIT 1", (video_id,)).fetchone()
                    if not latest or latest[2] is None or latest[1] != check_id(output_asset_id):
                        return False
                    qa = row[1] if isinstance(row[1], dict) else {}
                    intent = PublicationIntentEvidence(
                        video_id=video_id, render_id=latest[0], checksum=latest[3],
                        output_asset_id=latest[1], qa_passed=qa.get("passed") is True, qa_override=qa_override,
                        visibility=visibility, public_confirmed=public_confirmed,
                        idempotency_key=idempotency_key(video_id, latest[0], latest[3]))
                conn.execute("UPDATE studio.videos SET status = %s, title = %s, description = %s, tags = %s, updated_at = now() WHERE id = %s",
                             (target.value, title, description, Jsonb(tags), video_id))
                conn.execute("INSERT INTO studio.approvals(video_id, decision, reason, qa_override, publish_at, output_asset_id) VALUES (%s, %s, %s, %s, %s, %s)",
                             (video_id, decision, reason, qa_override, publish_at, output_asset_id if decision == "approved" else None))
                if intent is not None:
                    conn.execute("INSERT INTO studio.publication_intents(video_id, render_id, media_checksum, output_asset_id, "
                                 "qa_passed, qa_override, visibility, public_confirmed, idempotency_key) "
                                 "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                 (intent.video_id, intent.render_id, intent.checksum, intent.output_asset_id,
                                  intent.qa_passed, intent.qa_override, intent.visibility, intent.public_confirmed,
                                  intent.idempotency_key))
                return True

    def get(self, video_id: str) -> Approval | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT video_id, decision, reason, qa_override, publish_at, created_at, output_asset_id FROM studio.approvals WHERE video_id = %s", (check_id(video_id),))
            row = cur.fetchone()
            return Approval.model_validate(row) if row else None

    def intent(self, video_id: str) -> PublicationIntentEvidence | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT video_id, render_id, media_checksum, output_asset_id, qa_passed, qa_override, "
                        "visibility, public_confirmed, idempotency_key FROM studio.publication_intents WHERE video_id = %s",
                        (check_id(video_id),))
            row = cur.fetchone()
            if row is None:
                return None
            return PublicationIntentEvidence(video_id=row["video_id"], render_id=row["render_id"],
                                             checksum=row["media_checksum"], output_asset_id=row["output_asset_id"],
                                             qa_passed=row["qa_passed"], qa_override=row["qa_override"],
                                             visibility=row["visibility"], public_confirmed=row["public_confirmed"],
                                             idempotency_key=row["idempotency_key"])


class PostgresPublicationRepository(_Base):
    def claim(self, lease_seconds: int, max_attempts: int, video_id: str | None = None) -> Publication | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT v.id FROM studio.videos v LEFT JOIN studio.publications p ON p.video_id = v.id "
                        "WHERE v.status = 'APPROVED' AND p.id IS NULL " + ("AND v.id = %s " if video_id else "") +
                        "ORDER BY v.updated_at, v.id LIMIT 1 FOR UPDATE OF v SKIP LOCKED",
                        (check_id(video_id),) if video_id else ())
            row = cur.fetchone()
            if row is None:
                return None
            video_id = row["id"]
            cur.execute("SELECT a.output_asset_id, a.publish_at, EXISTS (SELECT 1 FROM studio.render_jobs j "
                        "WHERE j.video_id = a.video_id AND j.status = 'SUCCEEDED' AND j.finished_at IS NOT NULL AND j.output_asset_id = a.output_asset_id) AS valid "
                        "FROM studio.approvals a WHERE a.video_id = %s AND a.decision = 'approved'", (video_id,))
            approval = cur.fetchone()
            if not approval or not approval["output_asset_id"] or not approval["valid"]:
                raise StateConflict("approved render is unavailable or has no trusted revision; human reconciliation required")
            if approval["publish_at"] is not None:
                cur.execute("SELECT date_trunc('second', %s::timestamptz) <= clock_timestamp() AS expired", (approval["publish_at"],))
                if cur.fetchone()["expired"]:
                    raise StateConflict("publication schedule has expired; reschedule before claiming")
            cur.execute(f"INSERT INTO studio.publications(id, video_id, status, attempt, lease_until, publish_at, visibility, public_confirmed, render_id, media_checksum, idempotency_key) "
                        f"VALUES (%s, %s, 'UPLOADING', 1, now() + %s * interval '1 second', "
                        f"(SELECT publish_at FROM studio.approvals WHERE video_id = %s), "
                        f"COALESCE((SELECT visibility FROM studio.publication_intents WHERE video_id = %s), 'private'), "
                        f"COALESCE((SELECT public_confirmed FROM studio.publication_intents WHERE video_id = %s), false), "
                        f"(SELECT render_id FROM studio.publication_intents WHERE video_id = %s), "
                        f"(SELECT media_checksum FROM studio.publication_intents WHERE video_id = %s), "
                        f"(SELECT idempotency_key FROM studio.publication_intents WHERE video_id = %s)) "
                        f"ON CONFLICT (video_id) DO NOTHING RETURNING {_PUB}",
                        (uuid.uuid4().hex, video_id, lease_seconds, video_id, video_id, video_id, video_id, video_id, video_id))
            out = cur.fetchone()
            return Publication.model_validate(out) if out else None

    def claim_retry(self, lease_seconds: int, max_attempts: int, video_id: str | None = None) -> Publication | None:
        """Reivindica uma publicação segura de repetir (F8-04).

        Nunca devolve resultado ambíguo (`remote_state='UNKNOWN'`), DLQ, vídeo com id confirmado,
        agenda ainda não vencida ou tentativa além do teto. A sessão resumable existente é
        preservada: repetir dentro dela nunca cria um segundo vídeo.
        """
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT p.id, p.attempt, p.attempt_base FROM studio.publications p "
                "WHERE p.status IN ('PENDING', 'FAILED') AND NOT p.dead_letter AND p.youtube_video_id IS NULL "
                "AND p.attempt < p.attempt_base + %s "
                "AND (p.next_attempt_at IS NULL OR p.next_attempt_at <= clock_timestamp()) "
                "AND (p.lease_until IS NULL OR p.lease_until <= clock_timestamp()) "
                "AND p.remote_state IS DISTINCT FROM 'UNKNOWN' "
                "AND (p.remote_state IS DISTINCT FROM 'SESSION' OR p.upload_uri IS NOT NULL) "
                + ("AND p.video_id = %s " if video_id else "") +
                "ORDER BY p.next_attempt_at NULLS FIRST, p.updated_at, p.id "
                "LIMIT 1 FOR UPDATE SKIP LOCKED", (max_attempts, check_id(video_id)) if video_id else (max_attempts,))
            row = cur.fetchone()
            if row is None:
                return None
            cur.execute(f"UPDATE studio.publications SET status = 'UPLOADING', attempt = attempt + 1, "
                        f"lease_until = clock_timestamp() + %s * interval '1 second', next_attempt_at = NULL, "
                        f"updated_at = now() WHERE id = %s RETURNING {_PUB}",
                        (lease_seconds, row["id"]))
            return Publication.model_validate(cur.fetchone())

    def record_session(self, publication_id: str, attempt: int, upload_uri: str, offset: int) -> bool:
        with _translated(), self._connect() as conn:
            return conn.execute(
                "UPDATE studio.publications SET upload_uri = %s, offset_bytes = %s, remote_state = 'SESSION', "
                "updated_at = now() WHERE id = %s AND attempt = %s AND status = 'UPLOADING' AND youtube_video_id IS NULL",
                (upload_uri, max(0, int(offset)), check_id(publication_id), attempt)).rowcount == 1

    def retry_later(self, publication_id: str, attempt: int, error: str, delay_seconds: int,
                    failure_class: str) -> bool:
        with _translated(), self._connect() as conn:
            return conn.execute(
                "UPDATE studio.publications SET status = 'PENDING', lease_until = NULL, "
                "next_attempt_at = clock_timestamp() + %s * interval '1 second', error = %s, "
                "failure_class = %s, updated_at = now() "
                "WHERE id = %s AND attempt = %s AND status = 'UPLOADING' AND youtube_video_id IS NULL",
                (max(1, int(delay_seconds)), error.replace("\x00", "")[:500], failure_class,
                 check_id(publication_id), attempt)).rowcount == 1

    def dead_letter(self, publication_id: str, attempt: int, error: str, failure_class: str) -> bool:
        with _translated(), self._connect() as conn:
            return conn.execute(
                "UPDATE studio.publications SET status = 'FAILED', dead_letter = true, lease_until = NULL, "
                "next_attempt_at = NULL, error = %s, failure_class = %s, updated_at = now() "
                "WHERE id = %s AND attempt = %s AND youtube_video_id IS NULL",
                (error.replace("\x00", "")[:500], failure_class, check_id(publication_id), attempt)).rowcount == 1

    def mark_ambiguous(self, publication_id: str, attempt: int, error: str) -> bool:
        with _translated(), self._connect() as conn:
            return conn.execute(
                "UPDATE studio.publications SET status = 'PENDING', lease_until = NULL, next_attempt_at = NULL, "
                "remote_state = 'UNKNOWN', failure_class = 'AMBIGUOUS', error = %s, updated_at = now() "
                "WHERE id = %s AND attempt = %s AND status = 'UPLOADING' AND youtube_video_id IS NULL",
                (error.replace("\x00", "")[:500], check_id(publication_id), attempt)).rowcount == 1

    def resolve_ambiguous(self, publication_id: str, *, retry: bool, error: str, failure_class: str) -> bool:
        """Fecha a ambiguidade: `retry=True` só quando a reconciliação provou que não há vídeo."""
        with _translated(), self._connect() as conn:
            if retry:
                return conn.execute(
                    "UPDATE studio.publications SET status = 'PENDING', lease_until = NULL, "
                    "next_attempt_at = clock_timestamp(), remote_state = CASE WHEN upload_uri IS NULL THEN 'NONE' ELSE 'SESSION' END, "
                    "failure_class = NULL, error = %s, updated_at = now() "
                    "WHERE id = %s AND remote_state = 'UNKNOWN' AND youtube_video_id IS NULL AND NOT dead_letter",
                    (error.replace("\x00", "")[:500], check_id(publication_id))).rowcount == 1
            return conn.execute(
                "UPDATE studio.publications SET status = 'FAILED', dead_letter = true, lease_until = NULL, "
                "next_attempt_at = NULL, failure_class = %s, error = %s, updated_at = now() "
                "WHERE id = %s AND youtube_video_id IS NULL AND NOT dead_letter",
                (failure_class, error.replace("\x00", "")[:500], check_id(publication_id))).rowcount == 1

    def _one(self, sql: str, params: tuple) -> Publication | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return Publication.model_validate(row) if row else None

    def get(self, video_id: str) -> Publication | None:
        return self._one(f"SELECT {_PUB} FROM studio.publications WHERE video_id = %s", (check_id(video_id),))

    def get_by_id(self, publication_id: str) -> Publication | None:
        return self._one(f"SELECT {_PUB} FROM studio.publications WHERE id = %s", (check_id(publication_id),))

    def abort_before_delivery(self, publication_id: str, attempt: int) -> bool:
        # Exclusivamente pelo preparador, antes de devolver o claim a qualquer executor.
        with _translated(), self._connect() as conn:
            return conn.execute("DELETE FROM studio.publications WHERE id = %s AND attempt = %s AND status = 'UPLOADING' "
                                "AND upload_uri IS NULL AND youtube_video_id IS NULL",
                                (check_id(publication_id), attempt)).rowcount == 1

    def set_upload_uri(self, publication_id: str, attempt: int, uri: str, replace: bool) -> Publication | None:
        return self._one(f"UPDATE studio.publications SET upload_uri = %s, updated_at = now() WHERE id = %s AND attempt = %s AND status = 'UPLOADING' "
                         f"AND upload_uri IS NULL RETURNING {_PUB}", (uri, check_id(publication_id), attempt))

    def mark_uploaded(self, publication_id: str, youtube_video_id: str) -> Publication | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_PUB} FROM studio.publications WHERE id = %s FOR UPDATE", (check_id(publication_id),))
            current = cur.fetchone()
            if current is None:
                return None
            if current["youtube_video_id"] is not None:
                if current["youtube_video_id"] != youtube_video_id:
                    raise PublicationConflict("this video already has another YouTube id recorded")
                return Publication.model_validate(current)  # repetição: no-op
            cur.execute("SELECT status FROM studio.videos WHERE id = %s FOR UPDATE", (current["video_id"],))
            status = cur.fetchone()["status"]
            if status == VideoStatus.APPROVED.value:
                assert_transition(VideoStatus.APPROVED, VideoStatus.PUBLISHED)
                cur.execute("UPDATE studio.videos SET status = 'PUBLISHED', updated_at = now() WHERE id = %s", (current["video_id"],))
            cur.execute(f"UPDATE studio.publications SET youtube_video_id = %s, status = 'UPLOADED', error = NULL, lease_until = NULL, updated_at = now() "
                        f"WHERE id = %s RETURNING {_PUB}", (youtube_video_id, publication_id))
            return Publication.model_validate(cur.fetchone())

    def mark_thumbnail(self, publication_id: str) -> bool:
        with _translated(), self._connect() as conn:
            return conn.execute("UPDATE studio.publications SET thumbnail_set = true, updated_at = now() WHERE id = %s AND status = 'UPLOADED'",
                                (check_id(publication_id),)).rowcount == 1

    def release(self, publication_id: str, attempt: int, error: str) -> bool:
        with _translated(), self._connect() as conn:
            return conn.execute("UPDATE studio.publications SET lease_until = now(), error = %s, updated_at = now() "
                                "WHERE id = %s AND attempt = %s AND status = 'UPLOADING'", (error.replace("\x00", "")[:500], check_id(publication_id), attempt)).rowcount == 1

    def fail(self, publication_id: str, attempt: int, error: str) -> bool:
        with _translated(), self._connect() as conn:
            return conn.execute("UPDATE studio.publications SET status = 'FAILED', error = %s, lease_until = NULL, updated_at = now() "
                                "WHERE id = %s AND attempt = %s AND status = 'UPLOADING'", (error.replace("\x00", "")[:500], check_id(publication_id), attempt)).rowcount == 1

    def retry(self, video_id: str) -> Publication | None:
        check_id(video_id)
        return None  # A falha não prova que o executor anterior parou ou que o YouTube não recebeu o vídeo.
