"""Repositórios Postgres de aprovação e publicação. Cada operação que muda estado é uma transação com verificação e ação juntas."""
import uuid
from datetime import datetime

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...application.publishing import PublicationConflict
from ...domain.contracts import Approval, Publication, VideoStatus
from ...domain.ids import check_id
from ...domain.states import assert_transition
from .editorial_repo import _Base
from .repo import _translated

_PUB = "id, video_id, youtube_video_id, upload_uri, status, publish_at, privacy, thumbnail_set, attempt, error"


class PostgresApprovalRepository(_Base):
    def decide(self, video_id: str, expected: VideoStatus, decision: str, *, title: str, description: str, tags: list[str],
               publish_at: datetime | None, reason: str, qa_override: bool) -> bool:
        target = VideoStatus.APPROVED if decision == "approved" else VideoStatus.REJECTED
        with _translated():
            if expected == VideoStatus.RENDERED:  # vídeo com QA reprovado: passa pela revisão e decide na mesma transação
                assert_transition(VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL)
                assert_transition(VideoStatus.AWAITING_APPROVAL, target)
            else:
                assert_transition(expected, target)
            with self._connect() as conn:
                row = conn.execute("SELECT status FROM studio.videos WHERE id = %s FOR UPDATE", (check_id(video_id),)).fetchone()
                if row is None or row[0] != expected.value:
                    return False
                conn.execute("UPDATE studio.videos SET status = %s, title = %s, description = %s, tags = %s, updated_at = now() WHERE id = %s",
                             (target.value, title, description, Jsonb(tags), video_id))
                conn.execute("INSERT INTO studio.approvals(video_id, decision, reason, qa_override, publish_at) VALUES (%s, %s, %s, %s, %s)",
                             (video_id, decision, reason, qa_override, publish_at))
                return True

    def get(self, video_id: str) -> Approval | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT video_id, decision, reason, qa_override, publish_at, created_at FROM studio.approvals WHERE video_id = %s", (check_id(video_id),))
            row = cur.fetchone()
            return Approval.model_validate(row) if row else None


class PostgresPublicationRepository(_Base):
    def claim(self, lease_seconds: int, max_attempts: int) -> Publication | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("UPDATE studio.publications SET status = 'FAILED', error = 'too many attempts', lease_until = NULL, updated_at = now() "
                        "WHERE status IN ('PENDING', 'UPLOADING') AND attempt >= %s AND (lease_until IS NULL OR lease_until < now())", (max_attempts,))
            cur.execute("SELECT v.id FROM studio.videos v LEFT JOIN studio.publications p ON p.video_id = v.id "
                        "WHERE v.status = 'APPROVED' AND (p.id IS NULL OR (p.status IN ('PENDING', 'UPLOADING') "
                        "AND (p.lease_until IS NULL OR p.lease_until < now()))) ORDER BY v.updated_at, v.id LIMIT 1 FOR UPDATE OF v SKIP LOCKED")
            row = cur.fetchone()
            if row is None:
                return None
            video_id = row["id"]
            cur.execute(f"INSERT INTO studio.publications(id, video_id, status, attempt, lease_until, publish_at) VALUES (%s, %s, 'UPLOADING', 1, "
                        f"now() + %s * interval '1 second', (SELECT publish_at FROM studio.approvals WHERE video_id = %s)) "
                        f"ON CONFLICT (video_id) DO UPDATE SET status = 'UPLOADING', attempt = studio.publications.attempt + 1, "
                        f"lease_until = EXCLUDED.lease_until, error = NULL, updated_at = now() "
                        f"WHERE studio.publications.status IN ('PENDING', 'UPLOADING') RETURNING {_PUB}",
                        (uuid.uuid4().hex, video_id, lease_seconds, video_id))
            out = cur.fetchone()
            return Publication.model_validate(out) if out else None

    def _one(self, sql: str, params: tuple) -> Publication | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return Publication.model_validate(row) if row else None

    def get(self, video_id: str) -> Publication | None:
        return self._one(f"SELECT {_PUB} FROM studio.publications WHERE video_id = %s", (check_id(video_id),))

    def get_by_id(self, publication_id: str) -> Publication | None:
        return self._one(f"SELECT {_PUB} FROM studio.publications WHERE id = %s", (check_id(publication_id),))

    def set_upload_uri(self, publication_id: str, attempt: int, uri: str, replace: bool) -> Publication | None:
        return self._one(f"UPDATE studio.publications SET upload_uri = %s, updated_at = now() WHERE id = %s AND attempt = %s AND status = 'UPLOADING' "
                         f"AND (upload_uri IS NULL OR %s) RETURNING {_PUB}", (uri, check_id(publication_id), attempt, replace))

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

    def fail(self, publication_id: str, error: str) -> bool:
        with _translated(), self._connect() as conn:
            return conn.execute("UPDATE studio.publications SET status = 'FAILED', error = %s, lease_until = NULL, updated_at = now() "
                                "WHERE id = %s AND status IN ('PENDING', 'UPLOADING')", (error.replace("\x00", "")[:500], check_id(publication_id))).rowcount == 1

    def retry(self, video_id: str) -> Publication | None:
        return self._one(f"UPDATE studio.publications p SET status = 'PENDING', attempt = 0, upload_uri = NULL, lease_until = NULL, error = NULL, updated_at = now() "
                         f"FROM studio.videos v WHERE p.video_id = %s AND v.id = p.video_id AND v.status = 'APPROVED' AND p.status = 'FAILED' "
                         f"RETURNING {', '.join('p.' + c.strip() for c in _PUB.split(','))}", (check_id(video_id),))
