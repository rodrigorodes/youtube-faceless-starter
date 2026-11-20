import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.publish_repo import PostgresApprovalRepository, PostgresPublicationRepository  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.application.publishing import PublicationConflict  # noqa: E402
from app.studio.domain.contracts import PublicationStatus, VideoFormat, VideoStatus  # noqa: E402

S = VideoStatus
URI = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=AbC123"


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("canal").id

    def make(status="AWAITING_APPROVAL", topic="ADE 2026"):
        video = videos.create_video(project, topic, VideoFormat.short)
        conn.execute("UPDATE studio.videos SET status=%s WHERE id=%s", (status, video.id))
        conn.commit()
        return video.id

    return {"make": make, "videos": videos, "approvals": PostgresApprovalRepository(connect), "pubs": PostgresPublicationRepository(connect), "conn": conn, "connect": connect}


def status(env, vid):
    env["conn"].commit()
    return env["conn"].execute("SELECT status FROM studio.videos WHERE id=%s", (vid,)).fetchone()[0]


def approve(env, vid, expected=S.AWAITING_APPROVAL, **kw):
    base = dict(title="T", description="D", tags=["a"], publish_at=None, reason="", qa_override=False)
    return env["approvals"].decide(vid, expected, "approved", **{**base, **kw})


# ---------- decisão ----------
def test_approve_stores_metadata_and_audit_row_atomically(env):
    vid = env["make"]()
    when = datetime.now(timezone.utc) + timedelta(days=1)
    assert approve(env, vid, title="Meu título", description="Resumo", tags=["ade", "dança"], publish_at=when) is True
    video = env["videos"].get_video(vid)
    assert video.status == S.APPROVED and video.title == "Meu título" and video.tags == ["ade", "dança"]
    a = env["approvals"].get(vid)
    assert a.decision == "approved" and a.publish_at == when and a.qa_override is False
    assert approve(env, vid) is False  # já não está em AWAITING_APPROVAL
    assert env["conn"].execute("SELECT count(*) FROM studio.approvals WHERE video_id=%s", (vid,)).fetchone()[0] == 1


def test_approve_from_rendered_with_override_passes_through_review_in_one_step(env):
    vid = env["make"]("RENDERED")
    assert approve(env, vid, S.RENDERED, reason="vale assim", qa_override=True) is True
    assert status(env, vid) == "APPROVED" and env["approvals"].get(vid).qa_override is True


def test_override_without_reason_is_refused_by_the_database(env):
    vid = env["make"]("RENDERED")
    with pytest.raises(psycopg.errors.CheckViolation):
        approve(env, vid, S.RENDERED, reason="  ", qa_override=True)
    assert status(env, vid) == "RENDERED"  # a transação inteira voltou


def test_reject_and_wrong_expected_state(env):
    vid = env["make"]()
    assert env["approvals"].decide(vid, S.AWAITING_APPROVAL, "rejected", title="", description="", tags=[], publish_at=None, reason="ruim", qa_override=False)
    assert status(env, vid) == "REJECTED" and env["approvals"].get(vid).reason == "ruim"
    other = env["make"]("ASSETS_READY")
    assert approve(env, other, S.AWAITING_APPROVAL) is False and status(env, other) == "ASSETS_READY"
    with pytest.raises(Exception):
        approve(env, other, S.ASSETS_READY)  # transição proibida: nem toca no banco
    assert env["approvals"].get(other) is None


def test_concurrent_approvals_decide_exactly_once(env):
    vid = env["make"]()
    results = []
    threads = [threading.Thread(target=lambda: results.append(approve(env, vid))) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [False] * 5 + [True]


# ---------- fila ----------
@pytest.mark.parametrize("state", ["expired", "released", "failed", "pending"])
def test_started_publication_is_never_reclaimed_without_reconciliation(env, state):
    vid = env["make"]("APPROVED")
    pub = env["pubs"].claim(60, 5)
    assert env["pubs"].set_upload_uri(pub.id, pub.attempt, URI, False)
    if state == "expired":
        env["conn"].execute("UPDATE studio.publications SET lease_until = now() - interval '1 second' WHERE id=%s", (pub.id,))
        env["conn"].commit()
    elif state == "released":
        assert env["pubs"].release(pub.id, pub.attempt, "timeout")
    elif state == "failed":
        assert env["pubs"].fail(pub.id, pub.attempt, "failure")
        assert env["pubs"].retry(vid) is None
    else:
        env["conn"].execute("UPDATE studio.publications SET status='PENDING', lease_until=NULL WHERE id=%s", (pub.id,))
        env["conn"].commit()
    assert env["pubs"].claim(60, 5) is None
    current = env["pubs"].get_by_id(pub.id)
    assert current.attempt == 1 and current.upload_uri == URI
    assert current.status == (PublicationStatus.FAILED if state == "failed" else PublicationStatus.PENDING if state == "pending" else PublicationStatus.UPLOADING)


def test_claim_only_takes_approved_videos_and_opens_a_lease(env):
    assert env["pubs"].claim(1800, 5) is None
    env["make"]("AWAITING_APPROVAL")
    assert env["pubs"].claim(1800, 5) is None
    vid = env["make"]("APPROVED")
    when = datetime.now(timezone.utc) + timedelta(days=2)
    env["conn"].execute("INSERT INTO studio.approvals(video_id, decision, publish_at) VALUES (%s, 'approved', %s)", (vid, when))
    env["conn"].commit()
    pub = env["pubs"].claim(1800, 5)
    assert pub.video_id == vid and pub.status == PublicationStatus.UPLOADING and pub.attempt == 1 and pub.publish_at == when and pub.privacy == "private"
    assert env["pubs"].claim(1800, 5) is None  # lease vigente: ninguém mais pega


def test_expired_lease_preserves_the_upload_session(env):
    vid = env["make"]("APPROVED")
    pub = env["pubs"].claim(1800, 5)
    assert env["pubs"].set_upload_uri(pub.id, 1, URI, False)
    env["conn"].execute("UPDATE studio.publications SET lease_until = now() - interval '1 minute' WHERE id=%s", (pub.id,))
    env["conn"].commit()
    assert env["pubs"].claim(1800, 5) is None
    assert env["pubs"].get(vid).upload_uri == URI


def test_two_workers_never_get_the_same_video(env):
    env["make"]("APPROVED")
    got = []
    threads = [threading.Thread(target=lambda: got.append(env["pubs"].claim(1800, 5))) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len([g for g in got if g]) == 1


def test_concurrent_reclaims_grant_no_new_attempt(env):
    env["make"]("APPROVED")
    first = env["pubs"].claim(1800, 5)
    env["conn"].execute("UPDATE studio.publications SET lease_until = now() - interval '1 second' WHERE id=%s", (first.id,))
    env["conn"].commit()
    barrier = threading.Barrier(8)
    got, errors = [], []

    def claim():
        try:
            barrier.wait(timeout=5)
            got.append(env["pubs"].claim(1800, 5))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=claim) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors and all(not thread.is_alive() for thread in threads)
    winners = [pub for pub in got if pub]
    assert winners == []


def test_upload_uri_only_for_the_current_attempt_and_never_replaced(env):
    env["make"]("APPROVED")
    pub = env["pubs"].claim(1800, 5)
    assert env["pubs"].set_upload_uri(pub.id, 2, URI, False) is None  # tentativa errada
    assert env["pubs"].set_upload_uri(pub.id, 1, URI, False) is not None
    other = URI.replace("AbC123", "Zzz999")
    assert env["pubs"].set_upload_uri(pub.id, 1, other, False) is None  # já tem sessão
    assert env["pubs"].set_upload_uri(pub.id, 1, other, True) is None
    assert env["pubs"].get_by_id(pub.id).upload_uri == URI


def test_mark_uploaded_publishes_atomically_and_is_idempotent(env):
    vid = env["make"]("APPROVED")
    pub = env["pubs"].claim(1800, 5)
    done = env["pubs"].mark_uploaded(pub.id, "oNQ2KN37sfQ")
    assert done.status == PublicationStatus.UPLOADED and done.youtube_video_id == "oNQ2KN37sfQ" and status(env, vid) == "PUBLISHED"
    assert env["pubs"].mark_uploaded(pub.id, "oNQ2KN37sfQ").youtube_video_id == "oNQ2KN37sfQ"  # repetir não muda nada
    with pytest.raises(PublicationConflict):
        env["pubs"].mark_uploaded(pub.id, "aaaaaaaaaaa")
    assert env["pubs"].claim(1800, 5) is None  # publicado: não volta para a fila
    assert env["pubs"].mark_uploaded("0" * 32, "oNQ2KN37sfQ") is None


def test_same_youtube_id_cannot_belong_to_two_videos(env):
    env["make"]("APPROVED"), env["make"]("APPROVED")
    a, b = env["pubs"].claim(1800, 5), env["pubs"].claim(1800, 5)
    env["pubs"].mark_uploaded(a.id, "oNQ2KN37sfQ")
    with pytest.raises(psycopg.errors.UniqueViolation):
        env["pubs"].mark_uploaded(b.id, "oNQ2KN37sfQ")


def test_release_fail_retry_and_thumbnail(env):
    vid = env["make"]("APPROVED")
    pub = env["pubs"].claim(1800, 5)
    assert env["pubs"].release(pub.id, 9, "x") is False
    assert env["pubs"].release(pub.id, 1, "HTTP 503") is True
    assert env["pubs"].claim(1800, 5) is None
    assert env["pubs"].mark_thumbnail(pub.id) is False
    assert env["pubs"].fail(pub.id, 1, "HTTP 403") is True
    assert env["pubs"].fail(pub.id, 1, "again") is False
    assert env["pubs"].retry(vid) is None
    assert env["pubs"].claim(1800, 5) is None
    env["pubs"].mark_uploaded(pub.id, "oNQ2KN37sfQ")
    assert env["pubs"].mark_thumbnail(pub.id) is True
    assert env["pubs"].get(vid).thumbnail_set is True


def test_bad_youtube_id_is_refused_by_the_database(env):
    env["make"]("APPROVED")
    pub = env["pubs"].claim(1800, 5)
    with pytest.raises(psycopg.errors.CheckViolation):
        env["pubs"].mark_uploaded(pub.id, "curto")
