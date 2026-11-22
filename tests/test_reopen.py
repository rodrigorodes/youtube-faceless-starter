"""W4.2 / ADR-002: reabrir vídeo aprovado e não publicado para edição.

Cobre a transição, a guarda de publicação, a invalidação da intenção pendente, a preservação
do histórico e a concorrência de dois reopen simultâneos.
"""
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb  # noqa: E402

from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.publish_repo import (  # noqa: E402
    PostgresApprovalRepository,
    PostgresPublicationRepository,
    PostgresReopenRepository,
)
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.application.editorial import StateConflict  # noqa: E402
from app.studio.application.reopen import (  # noqa: E402
    PublicationAlreadyCompleted,
    PublicationInFlight,
    PublicationLease,
    ReopenConflict,
    ReopenForEditing,
    ReopenRefusal,
    publication_guard,
)
from app.studio.domain.contracts import PublicationStatus, VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.publication_policy import metadata_fingerprint  # noqa: E402
from app.studio.domain.qa_report import QaCoverage, QaFinding, QaReport  # noqa: E402

S = VideoStatus
AT = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def qa_report(passed=True):
    findings = tuple(
        QaFinding(finding_id=f"f{i}", check_id="render.media_metrics", category="technical",
                  severity="blocking", evidence="failure", suggested_action="Revisar.")
        for i in range(0 if passed else 1)
    )
    return QaReport(render_id="9" * 32, checksum="8" * 64, generated_at=AT,
                    coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics",), findings=findings)


def insert_output(conn, vid, attempt=1):
    asset = uuid.uuid4().hex
    job = uuid.uuid4().hex
    conn.execute("INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) "
                 "VALUES (%s, 'video', %s, 'file.mp4', 'test', 'test', 'ok')",
                 (asset, uuid.uuid4().hex * 2))
    conn.execute("INSERT INTO studio.render_jobs(id, video_id, status, attempt, output_asset_id, finished_at) "
                 "VALUES (%s, %s, 'SUCCEEDED', %s, %s, clock_timestamp())", (job, vid, attempt, asset))
    conn.commit()
    return asset, job


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("canal").id
    approvals = PostgresApprovalRepository(connect)
    pubs = PostgresPublicationRepository(connect)
    reopen = PostgresReopenRepository(connect)
    outputs = {}

    def make(status="AWAITING_APPROVAL", qa=None):
        video = videos.create_video(project, "ADE 2026", VideoFormat.short)
        conn.execute("UPDATE studio.videos SET status=%s, qa_report=%s WHERE id=%s",
                     (status, Jsonb(qa.model_dump(mode="json")) if qa else None, video.id))
        conn.commit()
        outputs[video.id] = insert_output(conn, video.id)
        return video.id

    def approve(vid, **changes):
        asset, _ = outputs[vid]
        base = dict(title="T", description="D", tags=[], publish_at=None, reason="",
                    qa_override=False, output_asset_id=asset)
        return approvals.decide(vid, S.AWAITING_APPROVAL, "approved", **{**base, **changes})

    return {"make": make, "approve": approve, "videos": videos, "approvals": approvals,
            "pubs": pubs, "reopen": reopen, "conn": conn, "connect": connect, "outputs": outputs}


def status(env, vid):
    env["conn"].commit()
    return env["conn"].execute("SELECT status FROM studio.videos WHERE id=%s", (vid,)).fetchone()[0]


def approved_video(env, qa=None):
    vid = env["make"]("AWAITING_APPROVAL", qa=qa or qa_report())
    assert env["approve"](vid) is True
    return vid


# -- guarda pura -----------------------------------------------------------------

def test_guard_refuses_uploaded_and_active_lease():
    now = datetime.now(timezone.utc)
    assert publication_guard(None, now) is None
    uploaded = PublicationLease(publication_id="a" * 32, status=PublicationStatus.UPLOADED,
                                lease_until=None, upload_uri=None, youtube_video_id="AbCdEfGhIjK")
    assert publication_guard(uploaded, now) is ReopenRefusal.PUBLISHED
    active = PublicationLease(publication_id="a" * 32, status=PublicationStatus.UPLOADING,
                              lease_until=now + timedelta(seconds=60), upload_uri=None, youtube_video_id=None)
    assert publication_guard(active, now) is ReopenRefusal.IN_FLIGHT
    expired = PublicationLease(publication_id="a" * 32, status=PublicationStatus.UPLOADING,
                               lease_until=now - timedelta(seconds=1), upload_uri=None, youtube_video_id=None)
    assert publication_guard(expired, now) is None
    pending = PublicationLease(publication_id="a" * 32, status=PublicationStatus.PENDING,
                               lease_until=None, upload_uri=None, youtube_video_id=None)
    assert publication_guard(pending, now) is None


# -- transição e efeitos na mesma transação --------------------------------------

def test_reopen_moves_approved_video_to_scripted_and_archives_approval(env):
    vid = approved_video(env)
    outcome = ReopenForEditing(env["reopen"]).execute(vid)
    assert outcome.reopened is True and outcome.approval_archived is True
    assert status(env, vid) == S.SCRIPTED.value
    assert env["conn"].execute("SELECT count(*) FROM studio.approvals WHERE video_id=%s", (vid,)).fetchone()[0] == 0
    assert env["conn"].execute("SELECT count(*) FROM studio.publication_intents WHERE video_id=%s", (vid,)).fetchone()[0] == 0
    row = env["conn"].execute("SELECT previous_status, decision, render_id, media_checksum, qa_report "
                              "FROM studio.approval_history WHERE video_id=%s", (vid,)).fetchone()
    assert row[0] == "APPROVED" and row[1] == "approved" and row[2] and row[3] and row[4]
    assert env["conn"].execute("SELECT qa_report FROM studio.videos WHERE id=%s", (vid,)).fetchone()[0] is None


def test_reopen_refuses_upload_in_flight(env):
    vid = approved_video(env)
    pub = env["pubs"].claim(1800, 5, vid)
    assert pub is not None and pub.status is PublicationStatus.UPLOADING
    with pytest.raises(PublicationInFlight):
        ReopenForEditing(env["reopen"]).execute(vid)
    assert status(env, vid) == S.APPROVED.value
    assert env["approvals"].get(vid) is not None
    assert env["conn"].execute("SELECT count(*) FROM studio.publications WHERE video_id=%s AND invalidated_at IS NULL",
                               (vid,)).fetchone()[0] == 1


def test_reopen_refuses_completed_publication(env):
    vid = approved_video(env)
    pub = env["pubs"].claim(1800, 5, vid)
    env["pubs"].mark_uploaded(pub.id, "AbCdEfGhIjK")
    assert status(env, vid) == S.PUBLISHED.value
    with pytest.raises(PublicationAlreadyCompleted):
        ReopenForEditing(env["reopen"]).execute(vid)
    assert status(env, vid) == S.PUBLISHED.value
    row = env["conn"].execute("SELECT status, youtube_video_id, attempt FROM studio.publications WHERE id=%s",
                              (pub.id,)).fetchone()
    assert row == (PublicationStatus.UPLOADED.value, "AbCdEfGhIjK", 1)
    assert env["approvals"].get(vid) is not None


def test_old_approval_does_not_authorize_new_version(env):
    vid = approved_video(env)
    ReopenForEditing(env["reopen"]).execute(vid)
    # o caminho atual não encontra o vídeo aprovado: nada a publicar
    assert env["pubs"].claim(1800, 5, vid) is None
    # mesmo forçando o status de volta, a aprovação antiga não está mais no caminho de publicação
    env["conn"].execute("UPDATE studio.videos SET status='APPROVED' WHERE id=%s", (vid,))
    env["conn"].commit()
    with pytest.raises(StateConflict):
        env["pubs"].claim(1800, 5, vid)


def test_pending_intent_is_invalidated_in_the_same_transaction(env):
    vid = approved_video(env)
    pub = env["pubs"].claim(1800, 5, vid)
    env["conn"].execute("UPDATE studio.publications SET status='PENDING', lease_until=NULL WHERE id=%s", (pub.id,))
    env["conn"].commit()
    outcome = ReopenForEditing(env["reopen"]).execute(vid)
    assert outcome.publication_invalidated is True
    assert status(env, vid) == S.SCRIPTED.value
    row = env["conn"].execute("SELECT invalidated_at, invalidation_reason, attempt FROM studio.publications WHERE id=%s",
                              (pub.id,)).fetchone()
    assert row[0] is not None and row[1] == "reopen_for_editing" and row[2] == pub.attempt
    assert env["conn"].execute("SELECT count(*) FROM studio.publication_intents WHERE video_id=%s", (vid,)).fetchone()[0] == 0


def test_history_is_preserved_and_publication_row_is_not_deleted(env):
    vid = approved_video(env)
    pub = env["pubs"].claim(1800, 5, vid)
    env["conn"].execute("UPDATE studio.publications SET status='PENDING', lease_until=NULL WHERE id=%s", (pub.id,))
    env["conn"].commit()
    before = env["conn"].execute("SELECT count(*) FROM studio.publications WHERE video_id=%s", (vid,)).fetchone()[0]
    ReopenForEditing(env["reopen"]).execute(vid)
    after = env["conn"].execute("SELECT count(*) FROM studio.publications WHERE video_id=%s", (vid,)).fetchone()[0]
    assert before == after == 1
    assert env["conn"].execute("SELECT count(*) FROM studio.approval_history WHERE video_id=%s", (vid,)).fetchone()[0] == 1


def test_two_concurrent_reopens_one_wins_the_other_conflicts(env):
    vid = approved_video(env)
    barrier = threading.Barrier(2)
    results = []

    def run():
        barrier.wait()
        try:
            results.append(("ok", ReopenForEditing(env["reopen"]).execute(vid)))
        except ReopenConflict as exc:
            results.append(("conflict", exc))
        except Exception as exc:  # pragma: no cover - diagnóstico
            results.append(("error", exc))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    kinds = sorted(kind for kind, _ in results)
    assert kinds == ["conflict", "ok"], results
    assert status(env, vid) == S.SCRIPTED.value
    assert env["conn"].execute("SELECT count(*) FROM studio.approval_history WHERE video_id=%s", (vid,)).fetchone()[0] == 1


def test_intent_remembers_the_metadata_and_reopen_archives_it(env):
    """W5.1/PUB-01: a intenção grava os metadados confirmados e o arquivo de reabertura os preserva."""
    vid = approved_video(env)
    stored = env["conn"].execute(
        "SELECT metadata_fingerprint, youtube_channel_id FROM studio.publication_intents WHERE video_id=%s",
        (vid,)).fetchone()
    assert stored[0] == metadata_fingerprint("T", "D", [], "private")
    assert stored[1] is None  # sem perfil de canal neste ambiente
    ReopenForEditing(env["reopen"]).execute(vid)
    archived = env["conn"].execute(
        "SELECT metadata_fingerprint FROM studio.approval_history WHERE video_id=%s", (vid,)).fetchone()[0]
    assert archived == stored[0]
