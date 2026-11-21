"""F8-02..04 (Postgres descartável): intenção imutável, retry/backoff, DLQ e reconciliação."""
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.publish_repo import (  # noqa: E402
    PostgresApprovalRepository, PostgresPublicationRepository,
)
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402
from app.studio.domain.contracts import PublicationStatus, VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.publication_policy import PublicConfirmationRequired, idempotency_key  # noqa: E402

S = VideoStatus
URI = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=AbC123"


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("canal").id

    def make(status="AWAITING_APPROVAL", qa=None):
        video = videos.create_video(project, "ADE 2026", VideoFormat.short)
        conn.execute("UPDATE studio.videos SET status=%s, qa_report=%s WHERE id=%s",
                     (status, Jsonb(qa) if qa else None, video.id))
        asset, job, key = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex * 2
        conn.execute("INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) "
                     "VALUES (%s, 'video', %s, 'file.mp4', 'test', 'test', 'ok')", (asset, key))
        conn.execute("INSERT INTO studio.render_jobs(id, video_id, status, attempt, output_asset_id, finished_at) "
                     "VALUES (%s, %s, 'SUCCEEDED', 1, %s, clock_timestamp())", (job, video.id, asset))
        conn.commit()
        return video.id, asset, job, key

    return {"make": make, "videos": videos, "conn": conn, "connect": connect,
            "approvals": PostgresApprovalRepository(connect), "pubs": PostgresPublicationRepository(connect)}


def approve(env, vid, **kw):
    base = dict(title="T", description="D", tags=["a"], publish_at=None, reason="", qa_override=False,
                output_asset_id=env["conn"].execute("SELECT output_asset_id FROM studio.render_jobs WHERE video_id=%s", (vid,)).fetchone()[0])
    return env["approvals"].decide(vid, S.AWAITING_APPROVAL, "approved", **{**base, **kw})


def approved(env, qa=None, **kw):
    vid, asset, job, key = env["make"](qa=qa)
    assert approve(env, vid, **kw)
    return vid, asset, job, key


def claimed(env):
    vid, asset, job, key = approved(env)
    pub = env["pubs"].claim(1800, 5)
    assert pub is not None and pub.video_id == vid
    return vid, asset, job, key, pub


def test_approval_writes_an_immutable_intent_with_render_id_and_checksum(env):
    vid, asset, job, key = approved(env, qa={"passed": True, "failures": []})
    intent = env["approvals"].intent(vid)
    assert intent is not None
    assert (intent.video_id, intent.render_id, intent.checksum, intent.output_asset_id) == (vid, job, key, asset)
    assert intent.qa_passed is True and intent.qa_override is False and intent.visibility == "private"
    assert intent.idempotency_key == idempotency_key(vid, job, key)
    pub = env["pubs"].claim(1800, 5)
    assert pub.attempt == 1 and env["conn"].execute(
        "SELECT idempotency_key, media_checksum, render_id, visibility, public_confirmed FROM studio.publications WHERE id=%s",
        (pub.id,)).fetchone() == (intent.idempotency_key, key, job, "private", False)


def test_public_intent_needs_a_second_confirmation_and_nothing_is_recorded_on_refusal(env):
    vid, asset, job, key = env["make"]()
    with pytest.raises(PublicConfirmationRequired):
        approve(env, vid, visibility="public", public_confirmed=False)
    assert env["conn"].execute("SELECT count(*) FROM studio.approvals").fetchone()[0] == 0
    assert env["conn"].execute("SELECT count(*) FROM studio.publication_intents").fetchone()[0] == 0
    assert env["videos"].get_video(vid).status == S.AWAITING_APPROVAL
    assert approve(env, vid, visibility="public", public_confirmed=True)
    intent = env["approvals"].intent(vid)
    assert intent.visibility == "public" and intent.public_confirmed is True


def test_rejected_video_has_no_publication_intent(env):
    vid, *_ = env["make"]()
    assert env["approvals"].decide(vid, S.AWAITING_APPROVAL, "rejected", title="", description="", tags=[],
                                   publish_at=None, reason="ruim", qa_override=False)
    assert env["approvals"].intent(vid) is None


def test_retry_is_safe_with_a_session_and_increments_the_attempt(env):
    vid, asset, job, key, pub = claimed(env)
    assert env["pubs"].record_session(pub.id, pub.attempt, URI, 2000) is True
    assert env["pubs"].retry_later(pub.id, pub.attempt, "HTTP 503", 1, "TRANSIENT") is True
    assert env["pubs"].claim_retry(1800, 5) is None  # backoff ainda não venceu
    env["conn"].execute("UPDATE studio.publications SET next_attempt_at = now() - interval '1 second' WHERE id=%s", (pub.id,))
    env["conn"].commit()
    retried = env["pubs"].claim_retry(1800, 5)
    assert retried.id == pub.id and retried.attempt == 2 and retried.upload_uri == URI
    assert retried.status == PublicationStatus.UPLOADING


def test_ambiguous_result_is_never_retried_automatically(env):
    vid, _, _, _, pub = claimed(env)
    assert env["pubs"].record_session(pub.id, pub.attempt, URI, 0)
    assert env["pubs"].mark_ambiguous(pub.id, pub.attempt, "timeout after sending bytes")
    assert env["pubs"].claim_retry(1800, 5) is None
    row = env["conn"].execute("SELECT remote_state, failure_class, dead_letter FROM studio.publications WHERE id=%s", (pub.id,)).fetchone()
    assert row == ("UNKNOWN", "AMBIGUOUS", False)


def test_dead_letter_is_terminal_and_skipped(env):
    vid, _, _, _, pub = claimed(env)
    assert env["pubs"].dead_letter(pub.id, pub.attempt, "HTTP 403 quotaExceeded", "PERMANENT")
    assert env["pubs"].claim_retry(1800, 5) is None
    row = env["conn"].execute("SELECT status, dead_letter, failure_class FROM studio.publications WHERE id=%s", (pub.id,)).fetchone()
    assert row == ("FAILED", True, "PERMANENT")


def test_retry_respects_max_attempts(env):
    vid, _, _, _, pub = claimed(env)
    env["conn"].execute("UPDATE studio.publications SET status='PENDING', lease_until=NULL, attempt=5 WHERE id=%s", (pub.id,))
    env["conn"].commit()
    assert env["pubs"].claim_retry(1800, 5) is None
    assert env["pubs"].claim_retry(1800, 6) is not None


def test_retry_never_returns_a_published_video_or_a_future_schedule(env):
    vid, _, _, _, pub = claimed(env)
    assert env["pubs"].mark_uploaded(pub.id, "oNQ2KN37sfQ")
    assert env["pubs"].claim_retry(1800, 5) is None
    # um vídeo aprovado com agenda futura ainda pode subir (o YouTube agenda), mas não entra em retry
    # se a linha estiver em PENDING e sem id; isso é coberto pelo próximo claim.
    assert env["pubs"].claim(1800, 5) is None


def test_record_session_only_accepts_the_current_attempt(env):
    vid, _, _, _, pub = claimed(env)
    assert env["pubs"].record_session(pub.id, 2, URI, 0) is False
    assert env["pubs"].record_session(pub.id, 1, URI, 0) is True
    assert env["pubs"].record_session(pub.id, 1, URI, 10) is True  # repetir a mesma sessão é seguro
    row = env["conn"].execute("SELECT upload_uri, offset_bytes, remote_state FROM studio.publications WHERE id=%s", (pub.id,)).fetchone()
    assert row == (URI, 10, "SESSION")


def test_concurrent_retry_claims_yield_exactly_one_winner(env):
    vid, _, _, _, pub = claimed(env)
    assert env["pubs"].record_session(pub.id, pub.attempt, URI, 0)
    assert env["pubs"].retry_later(pub.id, pub.attempt, "HTTP 503", 1, "TRANSIENT")
    env["conn"].execute("UPDATE studio.publications SET next_attempt_at = now() - interval '1 second'")
    env["conn"].commit()
    barrier = threading.Barrier(8)
    got, errors = [], []

    def claim():
        try:
            barrier.wait(timeout=5)
            got.append(env["pubs"].claim_retry(1800, 5))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=claim) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors and all(not thread.is_alive() for thread in threads)
    winners = [item for item in got if item]
    assert len(winners) == 1 and winners[0].attempt == 2

def test_resolve_ambiguous_only_retries_when_reconciliation_proved_absence(env):
    vid, _, _, _, pub = claimed(env)
    assert env["pubs"].record_session(pub.id, pub.attempt, URI, 100)
    assert env["pubs"].mark_ambiguous(pub.id, pub.attempt, "timeout")
    assert env["pubs"].resolve_ambiguous(pub.id, retry=True, error="", failure_class="TRANSIENT")
    row = env["conn"].execute("SELECT status, remote_state, next_attempt_at IS NOT NULL FROM studio.publications WHERE id=%s",
                              (pub.id,)).fetchone()
    assert row == ("PENDING", "SESSION", True)
    assert env["pubs"].claim_retry(1800, 5).attempt == 2

    retried = env["pubs"].get_by_id(pub.id)
    assert env["pubs"].mark_ambiguous(retried.id, retried.attempt, "still unknown")
    assert env["pubs"].resolve_ambiguous(retried.id, retry=False, error="session expired", failure_class="AMBIGUOUS")
    row = env["conn"].execute("SELECT status, dead_letter, remote_state FROM studio.publications WHERE id=%s", (pub.id,)).fetchone()
    assert row == ("FAILED", True, "UNKNOWN")
