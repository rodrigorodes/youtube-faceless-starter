import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.editorial_repo import PostgresScriptRepository  # noqa: E402
from app.studio.adapters.postgres.media_repo import PostgresAssetRepository  # noqa: E402
from app.studio.adapters.postgres.render_repo import PostgresRenderJobRepository  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.application.ports import SceneDraft  # noqa: E402
from app.studio.domain.contracts import Asset, AssetKind, JobStatus, QaReport, VideoFormat, VideoStatus  # noqa: E402

S = VideoStatus


def video_asset(key="d" * 64):
    return Asset(id="9" * 32, kind=AssetKind.video, cache_key=key, path="projects/p/videos/v/final.mp4", provider="ffmpeg", model="ffmpeg", license="gerado")


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("canal").id, "ADE 2026", VideoFormat.short)
    PostgresScriptRepository(connect).save_and_advance(video.id, "t", [SceneDraft("Narração válida.", "", "", "wide stage with colorful lights", ["c"])], ["c"], S.IDEA, S.SCRIPTED)
    for old, new in [(S.SCRIPTED, S.FACT_CHECKED), (S.FACT_CHECKED, S.STORYBOARDED), (S.STORYBOARDED, S.ASSETS_READY)]:
        assert videos.transition_video(video.id, old, new)
    return {"jobs": PostgresRenderJobRepository(connect), "videos": videos, "assets": PostgresAssetRepository(connect), "video": video, "conn": conn}


def status(env):
    env["conn"].commit()
    return env["conn"].execute("SELECT status FROM studio.videos WHERE id=%s", (env["video"].id,)).fetchone()[0]


def test_enqueue_is_unique_per_active_job_and_attempts_increase(env):
    v = env["video"].id
    a, created = env["jobs"].enqueue(v, "h" * 64)
    b, created2 = env["jobs"].enqueue(v, "h" * 64)
    assert created and not created2 and a.id == b.id and a.status == JobStatus.QUEUED and a.attempt == 1
    assert env["jobs"].start(a.id) is True and env["jobs"].start(a.id) is False
    assert env["jobs"].enqueue(v, "h" * 64)[1] is False  # RUNNING também conta como ativo
    env["jobs"].fail(a.id, "x" * 900)
    again, created3 = env["jobs"].enqueue(v, "i" * 64)
    assert created3 and again.attempt == 2 and env["jobs"].latest(v).id == again.id
    assert len(env["jobs"].get(a.id).error) <= 500 and env["jobs"].get(a.id).status == JobStatus.FAILED


def test_fail_only_touches_active_jobs_and_fail_interrupted_clears_them(env):
    v = env["video"].id
    job, _ = env["jobs"].enqueue(v, "h" * 64)
    env["jobs"].start(job.id)
    assert env["jobs"].fail_interrupted() == 1
    assert env["jobs"].get(job.id).status == JobStatus.FAILED and "interrupted" in env["jobs"].get(job.id).error
    env["jobs"].fail(job.id, "outra causa")  # já FAILED: não sobrescreve
    assert "interrupted" in env["jobs"].get(job.id).error and env["jobs"].fail_interrupted() == 0


def test_complete_with_passing_qa_moves_to_awaiting_approval_and_stores_the_report(env):
    v = env["video"].id
    job, _ = env["jobs"].enqueue(v, "h" * 64)
    env["jobs"].start(job.id)
    asset = env["assets"].add(video_asset())
    qa = QaReport(passed=True, metrics={"duration_s": 12.0, "integrated_lufs": -16.0})
    assert env["jobs"].complete(job.id, asset, qa) is True
    done = env["jobs"].get(job.id)
    assert done.status == JobStatus.SUCCEEDED and done.output_asset_id == asset.id and status(env) == "AWAITING_APPROVAL"
    assert env["videos"].get_video(v).qa_report == qa


def test_complete_with_failing_qa_stays_rendered_and_can_render_again(env):
    v = env["video"].id
    job, _ = env["jobs"].enqueue(v, "h" * 64)
    env["jobs"].start(job.id)
    asset = env["assets"].add(video_asset())
    bad = QaReport(passed=False, failures=["audio is silent"], metrics={"integrated_lufs": None})
    assert env["jobs"].complete(job.id, asset, bad) is True and status(env) == "RENDERED"
    job2, _ = env["jobs"].enqueue(v, "j" * 64)
    env["jobs"].start(job2.id)
    assert env["jobs"].complete(job2.id, asset, QaReport(passed=True)) is True and status(env) == "AWAITING_APPROVAL"


def test_complete_refuses_when_state_or_job_changed(env):
    v = env["video"].id
    job, _ = env["jobs"].enqueue(v, "h" * 64)
    env["jobs"].start(job.id)
    asset = env["assets"].add(video_asset())
    env["conn"].execute("UPDATE studio.videos SET status='FAILED' WHERE id=%s", (v,))
    env["conn"].commit()
    assert env["jobs"].complete(job.id, asset, QaReport(passed=True)) is False
    assert env["jobs"].get(job.id).status == JobStatus.RUNNING and status(env) == "FAILED"
    env["conn"].execute("UPDATE studio.videos SET status='ASSETS_READY' WHERE id=%s", (v,))
    env["jobs"].fail(job.id, "cancelado")
    env["conn"].commit()
    assert env["jobs"].complete(job.id, asset, QaReport(passed=True)) is False and status(env) == "ASSETS_READY"


def test_video_kind_is_accepted_by_the_database(env):
    assert env["assets"].add(video_asset()).kind == AssetKind.video


def test_alive_requires_running_job_and_a_renderable_video(env):
    v = env["video"].id
    job, _ = env["jobs"].enqueue(v, "h" * 64)
    assert env["jobs"].alive(job.id) is False  # QUEUED ainda não é dono de nada
    env["jobs"].start(job.id)
    assert env["jobs"].alive(job.id) is True
    env["conn"].execute("UPDATE studio.videos SET status='APPROVED' WHERE id=%s", (v,))
    env["conn"].commit()
    assert env["jobs"].alive(job.id) is False
    env["conn"].execute("UPDATE studio.videos SET status='ASSETS_READY' WHERE id=%s", (v,))
    env["jobs"].fail(job.id, "x")
    env["conn"].commit()
    assert env["jobs"].alive(job.id) is False


def test_latest_output_is_the_asset_of_the_newest_succeeded_job(env):
    v = env["video"].id
    assert env["jobs"].latest_output(v) is None
    job, _ = env["jobs"].enqueue(v, "h" * 64)
    env["jobs"].start(job.id)
    first = env["assets"].add(video_asset("1" * 64))
    env["jobs"].complete(job.id, first, QaReport(passed=False, failures=["x"]))
    assert env["jobs"].latest_output(v).id == first.id
    job2, _ = env["jobs"].enqueue(v, "i" * 64)
    env["jobs"].start(job2.id)
    assert env["jobs"].latest_output(v).id == first.id  # render em andamento não troca o arquivo servido
    second = env["assets"].add(video_asset("2" * 64).model_copy(update={"id": "8" * 32}))
    env["jobs"].complete(job2.id, second, QaReport(passed=True))
    assert env["jobs"].latest_output(v).id == second.id


def test_enqueue_reaps_a_stale_active_job_but_not_a_fresh_one(env):
    v = env["video"].id
    job, _ = env["jobs"].enqueue(v, "h" * 64)
    env["jobs"].start(job.id)
    assert env["jobs"].enqueue(v, "h" * 64) == (env["jobs"].get(job.id), False)  # recente: continua ativo
    env["conn"].execute("UPDATE studio.render_jobs SET started_at = now() - interval '3 hours' WHERE id=%s", (job.id,))
    env["conn"].commit()
    again, created = env["jobs"].enqueue(v, "h" * 64)
    assert created and again.id != job.id
    old = env["jobs"].get(job.id)
    assert old.status == JobStatus.FAILED and "stale" in old.error
