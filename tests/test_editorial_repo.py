import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.editorial_repo import (  # noqa: E402
    PostgresFactCheckRepository, PostgresScriptRepository, PostgresSnapshotRepository, PostgresUsageRepository,
)
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.application.ports import SceneDraft  # noqa: E402
from app.studio.application.use_cases import ServiceUnavailable  # noqa: E402
from app.studio.domain.contracts import FactCheckReport, SceneFactCheck, UnsupportedItem, UsageEntry, VideoFormat, VideoStatus  # noqa: E402

S = VideoStatus
DRAFTS = [SceneDraft("Primeira narração válida.", "Legenda", "QUA", "wide stage with colorful lights", ["abc"]),
          SceneDraft("Segunda narração válida.", "", "", "crowd silhouettes under neon lights", [])]


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("canal").id, "ADE 2026", VideoFormat.short)
    return {"connect": connect, "conn": conn, "video": video, "videos": videos, "snaps": PostgresSnapshotRepository(connect),
            "scripts": PostgresScriptRepository(connect), "checks": PostgresFactCheckRepository(connect), "usage": PostgresUsageRepository(connect)}


def status(env):
    env["conn"].commit()
    return env["conn"].execute("SELECT status FROM studio.videos WHERE id=%s", (env["video"].id,)).fetchone()[0]


def test_snapshot_is_deduplicated_by_content(env):
    a = env["snaps"].add(env["video"].id, "https://x.example/a", "texto da fonte")
    assert env["snaps"].add(env["video"].id, "https://x.example/a", "texto da fonte").id == a.id
    b = env["snaps"].add(env["video"].id, "https://x.example/a", "texto mudou")
    assert b.id != a.id and [s.id for s in env["snaps"].list(env["video"].id)] == [a.id, b.id]
    assert len(a.content_sha256) == 64 and a.fetched_at is not None


def test_script_saves_scenes_bumps_version_and_moves_state(env):
    v = env["video"].id
    s1 = env["scripts"].save_and_advance(v, "t1", DRAFTS, ["abc"], S.IDEA, S.SCRIPTED)
    assert s1.version == 1 and status(env) == "SCRIPTED"
    s2 = env["scripts"].save_and_advance(v, "t2", DRAFTS[:2], [], S.SCRIPTED, S.SCRIPTED)
    assert s2.version == 2 and status(env) == "SCRIPTED"
    scenes = env["scripts"].scenes(v)
    assert [x.idx for x in scenes] == [0, 1] and scenes[0].claim_ids == ["abc"] and scenes[0].label == "QUA"
    assert env["scripts"].latest(v).version == 2 and env["scripts"].latest(v).text == "t2"


def test_script_wrong_expected_state_persists_nothing(env):
    v = env["video"].id
    assert env["scripts"].save_and_advance(v, "t", DRAFTS, [], S.FACT_CHECKED, S.SCRIPTED) is None
    assert env["scripts"].latest(v) is None and env["scripts"].scenes(v) == [] and status(env) == "IDEA"


def test_concurrent_script_generation_one_wins_with_unique_version(env):
    v, results, barrier = env["video"].id, [], threading.Barrier(2)

    def attempt():
        barrier.wait()
        results.append(env["scripts"].save_and_advance(v, "t", DRAFTS, [], S.IDEA, S.SCRIPTED))

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r is None for r in results) == [False, True]


def test_concurrent_regeneration_never_collides_on_version(env):
    v = env["video"].id
    env["scripts"].save_and_advance(v, "t", DRAFTS, [], S.IDEA, S.SCRIPTED)
    results, barrier = [], threading.Barrier(4)

    def attempt():
        barrier.wait()
        results.append(env["scripts"].save_and_advance(v, "t", DRAFTS, [], S.SCRIPTED, S.SCRIPTED))

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r.version for r in results) == [2, 3, 4, 5]


REPORT_OK = FactCheckReport(passed=True)
REPORT_BAD = FactCheckReport(passed=False, scenes=[SceneFactCheck(idx=0, unsupported=[UnsupportedItem(kind="number", value="4000")])])


def test_fact_check_advances_only_from_scripted(env):
    v = env["video"].id
    assert env["checks"].save(v, REPORT_OK, advance=True) is False  # ainda IDEA: nada gravado
    assert env["conn"].execute("SELECT count(*) FROM studio.fact_checks").fetchone()[0] == 0
    env["scripts"].save_and_advance(v, "t", DRAFTS, [], S.IDEA, S.SCRIPTED)
    assert env["checks"].save(v, REPORT_BAD, advance=False) is True and status(env) == "SCRIPTED"
    assert env["checks"].save(v, REPORT_OK, advance=True) is True and status(env) == "FACT_CHECKED"
    env["conn"].commit()
    assert env["conn"].execute("SELECT count(*) FROM studio.fact_checks WHERE video_id=%s", (v,)).fetchone()[0] == 2


def test_fact_check_override_is_persisted_with_reason(env):
    v = env["video"].id
    env["scripts"].save_and_advance(v, "t", DRAFTS, [], S.IDEA, S.SCRIPTED)
    report = FactCheckReport(passed=True, overridden=True, override_reason="conferido na fonte impressa", scenes=REPORT_BAD.scenes)
    assert env["checks"].save(v, report, advance=True) is True
    env["conn"].commit()
    row = env["conn"].execute("SELECT passed, overridden, override_reason FROM studio.fact_checks WHERE video_id=%s", (v,)).fetchone()
    assert row == (True, True, "conferido na fonte impressa")


def test_usage_sums_by_video_and_month(env):
    v = env["video"].id
    env["usage"].record(v, UsageEntry(step="script", provider="p", model="m", cost_usd=0.25))
    env["usage"].record(v, UsageEntry(step="script", provider="p", model="m", cost_usd=0.5))
    env["usage"].record(None, UsageEntry(step="ideas", provider="p", model="m", cost_usd=1.0))
    assert env["usage"].spent_video(v) == pytest.approx(0.75) and env["usage"].spent_month() == pytest.approx(1.75)
    env["conn"].execute("UPDATE studio.usage_ledger SET created_at = now() - interval '70 days' WHERE cost_usd = 1.0")
    env["conn"].commit()
    assert env["usage"].spent_month() == pytest.approx(0.75)


def test_dead_connection_becomes_service_unavailable(dsn):
    closed = psycopg.connect(dsn)
    closed.close()
    with pytest.raises(ServiceUnavailable):
        PostgresUsageRepository(lambda: closed).spent_month()
