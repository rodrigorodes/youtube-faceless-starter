import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.publish_repo import PostgresApprovalRepository, PostgresPublicationRepository  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.render_repo import PostgresRenderJobRepository  # noqa: E402
from app.studio.application.publishing import PublicationConflict  # noqa: E402
from app.studio.domain.contracts import Asset, AssetKind, PublicationStatus, VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.qa_report import QaCoverage, QaFinding, QaReport  # noqa: E402

S = VideoStatus
URI = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=AbC123"
AT = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def qa_report(passed=True, failures=()):
    findings = tuple(QaFinding(finding_id=f"f{i}", check_id="render.media_metrics", category="technical",
                               severity="blocking", evidence=failure, suggested_action="Revisar o render.")
                     for i, failure in enumerate(failures))
    return QaReport(render_id="9" * 32, checksum="8" * 64, generated_at=AT,
                    coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics",), findings=findings)


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("canal").id
    outputs = {}

    def make(status="AWAITING_APPROVAL", topic="ADE 2026"):
        video = videos.create_video(project, topic, VideoFormat.short)
        conn.execute("UPDATE studio.videos SET status=%s WHERE id=%s", (status, video.id))
        outputs[video.id] = insert_output(conn, video.id, 1)
        if status == "APPROVED":
            conn.execute("INSERT INTO studio.approvals(video_id, decision, output_asset_id) VALUES (%s, 'approved', %s)", (video.id, outputs[video.id]))
        conn.commit()
        return video.id

    return {"make": make, "videos": videos, "approvals": PostgresApprovalRepository(connect), "pubs": PostgresPublicationRepository(connect), "conn": conn, "connect": connect, "outputs": outputs}


def status(env, vid):
    env["conn"].commit()
    return env["conn"].execute("SELECT status FROM studio.videos WHERE id=%s", (vid,)).fetchone()[0]


def approve(env, vid, expected=S.AWAITING_APPROVAL, **kw):
    base = dict(title="T", description="D", tags=["a"], publish_at=None, reason="", qa_override=False, output_asset_id=env["outputs"][vid])
    return env["approvals"].decide(vid, expected, "approved", **{**base, **kw})


def insert_output(conn, vid, attempt):
    asset, job = uuid.uuid4().hex, uuid.uuid4().hex
    conn.execute("INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) VALUES (%s, 'video', %s, 'file.mp4', 'test', 'test', 'ok')",
                 (asset, uuid.uuid4().hex * 2))
    conn.execute("INSERT INTO studio.render_jobs(id, video_id, status, attempt, output_asset_id, finished_at) "
                 "VALUES (%s, %s, 'SUCCEEDED', %s, %s, clock_timestamp())", (job, vid, attempt, asset))
    return asset


def test_approval_cas_rechecks_output_after_waiting_for_video_lock(env):
    vid = env["make"]("RENDERED")
    first = env["outputs"][vid]
    locker = env["connect"]()
    locker.execute("SELECT id FROM studio.videos WHERE id=%s FOR UPDATE", (vid,))
    results, errors = [], []
    def decide():
        try:
            results.append(approve(env, vid, S.RENDERED, output_asset_id=first, reason="reviewed", qa_override=True))
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=decide)
    thread.start()
    second = insert_output(locker, vid, 2)
    locker.commit()
    locker.close()
    thread.join(timeout=10)
    assert not errors and not thread.is_alive() and results == [False]
    assert status(env, vid) == "RENDERED"
    assert approve(env, vid, S.RENDERED, output_asset_id=second, reason="reviewed", qa_override=True)
    assert env["approvals"].get(vid).output_asset_id == second


def test_approval_races_render_completion_without_approving_unreviewed_output(env):
    vid = env["make"]("RENDERED")
    first = env["outputs"][vid]
    asset_id, job_id, key = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex * 2
    env["conn"].execute("INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) VALUES (%s, 'video', %s, 'new.mp4', 'test', 'test', 'ok')", (asset_id, key))
    env["conn"].execute("INSERT INTO studio.render_jobs(id, video_id, status, attempt) VALUES (%s, %s, 'RUNNING', 2)", (job_id, vid))
    env["conn"].commit()
    asset = Asset(id=asset_id, kind=AssetKind.video, cache_key=key, path="new.mp4", provider="test", model="test", license="ok")
    jobs = PostgresRenderJobRepository(env["connect"])
    barrier = threading.Barrier(2)
    results, errors = {}, []
    def run(name, action):
        try:
            barrier.wait(timeout=5)
            results[name] = action()
        except Exception as exc:
            errors.append(exc)
    threads = [
        threading.Thread(target=run, args=("approval", lambda: approve(env, vid, S.RENDERED, output_asset_id=first, reason="reviewed", qa_override=True))),
        threading.Thread(target=run, args=("render", lambda: jobs.complete(job_id, asset, qa_report(False, ["test"])))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors and all(not thread.is_alive() for thread in threads)
    assert results["approval"] != results["render"]
    if results["approval"]:
        assert env["approvals"].get(vid).output_asset_id == first
        assert jobs.approved_output(vid).id == first
    else:
        assert status(env, vid) == "RENDERED"
        assert jobs.latest_output(vid).id == asset_id


def test_early_abort_cannot_remove_claim_with_external_session(env):
    vid = env["make"]("APPROVED")
    pub = env["pubs"].claim(60, 5)
    assert env["pubs"].set_upload_uri(pub.id, pub.attempt, URI, False)
    assert not env["pubs"].abort_before_delivery(pub.id, pub.attempt)
    assert env["pubs"].get(vid).upload_uri == URI


def test_unexposed_expired_preparation_can_be_cancelled_without_consuming_claim(env):
    vid = env["make"]("APPROVED")
    pub = env["pubs"].claim(60, 5)
    assert not env["pubs"].abort_before_delivery(pub.id, 2)
    assert env["pubs"].abort_before_delivery(pub.id, 1)
    assert env["pubs"].get(vid) is None
    assert env["pubs"].claim(60, 5).video_id == vid


def test_approval_rejects_legacy_render_without_completion_timestamp(env):
    vid = env["make"]()
    env["conn"].execute("UPDATE studio.render_jobs SET finished_at=NULL WHERE video_id=%s", (vid,))
    env["conn"].commit()
    assert not approve(env, vid)
    assert status(env, vid) == "AWAITING_APPROVAL"


def test_claim_and_lookup_use_approved_output_not_a_later_render(env):
    vid = env["make"]()
    first = env["outputs"][vid]
    assert approve(env, vid)
    second = insert_output(env["conn"], vid, 2)
    env["conn"].commit()
    jobs = PostgresRenderJobRepository(env["connect"])
    assert jobs.latest_output(vid).id == second
    assert jobs.approved_output(vid).id == first
    assert env["pubs"].claim(60, 5).video_id == vid


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
    env["conn"].execute("UPDATE studio.approvals SET publish_at=%s WHERE video_id=%s", (when, vid))
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
