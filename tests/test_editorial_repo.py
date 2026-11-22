import shutil
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


def _drafts(count):
    return [SceneDraft(f"Narração {i} válida para o teste.", "", "", f"prompt de imagem {i} válido", [])
            for i in range(count)]


def _assign_assets(env, scene_ids):
    """Cria um asset por cena e o vincula diretamente: o teste é do repositório, não do fluxo de mídia."""
    asset_ids = []
    for i, scene_id in enumerate(scene_ids):
        asset_id = f"{i + 1:032x}"
        env["conn"].execute(
            "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) "
            "VALUES (%s, 'image', %s, %s, 'p', 'm', 'CC0')",
            (asset_id, f"{i + 1:064x}", f"cache/{i}.png"),
        )
        env["conn"].execute("UPDATE studio.scenes SET asset_id = %s WHERE id = %s", (asset_id, scene_id))
        asset_ids.append(asset_id)
    env["conn"].commit()
    return asset_ids


def _review_flags(env, video_id):
    env["conn"].commit()
    return env["conn"].execute(
        "SELECT id, media_review_required FROM studio.scenes WHERE video_id = %s ORDER BY idx", (video_id,)
    ).fetchall()


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


def test_scene_ids_survive_a_read_round_trip_and_new_versions(env):
    v = env["video"].id
    env["scripts"].save_and_advance(v, "t1", DRAFTS, [], S.IDEA, S.SCRIPTED)
    first = [s.id for s in env["scripts"].scenes(v)]
    assert [s.id for s in env["scripts"].scenes(v)] == first  # leitura repetida não muda a identidade
    env["scripts"].save_and_advance(v, "t2", DRAFTS, [], S.SCRIPTED, S.SCRIPTED)
    assert [s.id for s in env["scripts"].scenes(v)] == first  # versão nova sem mudança não recria cenas


def test_editing_one_scene_keeps_other_ids_and_assets_and_flags_its_media(env):
    v = env["video"].id
    drafts = _drafts(4)
    env["scripts"].save_and_advance(v, "t1", drafts, [], S.IDEA, S.SCRIPTED)
    first = env["scripts"].scenes(v)
    assets = _assign_assets(env, [s.id for s in first])
    env["conn"].execute("UPDATE studio.scenes SET duration_s = 2.5 WHERE id = %s", (first[2].id,))
    env["conn"].commit()

    edited = list(drafts)
    edited[2] = SceneDraft("Narração 2 reescrita e diferente.", "", "", "prompt de imagem 2 válido", [])
    env["scripts"].save_and_advance(v, "t2", edited, [], S.SCRIPTED, S.SCRIPTED)

    second = env["scripts"].scenes(v)
    assert [s.id for s in second] == [s.id for s in first]  # inclusive a cena editada no lugar
    assert [s.asset_id for s in second] == [assets[0], assets[1], None, assets[3]]
    assert second[2].duration_s is None  # timing medido fica stale quando a narração muda
    assert _review_flags(env, v) == [(first[0].id, False), (first[1].id, False), (first[2].id, True),
                                     (first[3].id, False)]


def test_reordering_scenes_keeps_ids_and_assets_with_the_content(env):
    v = env["video"].id
    drafts = _drafts(3)
    env["scripts"].save_and_advance(v, "t1", drafts, [], S.IDEA, S.SCRIPTED)
    first = env["scripts"].scenes(v)
    assets = _assign_assets(env, [s.id for s in first])

    reordered = [drafts[2], drafts[0], drafts[1]]
    env["scripts"].save_and_advance(v, "t2", reordered, [], S.SCRIPTED, S.SCRIPTED)

    second = env["scripts"].scenes(v)
    assert [s.narration for s in second] == [d.narration for d in reordered]
    assert [s.idx for s in second] == [0, 1, 2]
    assert [s.id for s in second] == [first[2].id, first[0].id, first[1].id]
    assert [s.asset_id for s in second] == [assets[2], assets[0], assets[1]]
    assert all(flag is False for _, flag in _review_flags(env, v))


def test_reordering_with_new_scenes_does_not_collide_on_position(env):
    v = env["video"].id
    drafts = _drafts(2)
    env["scripts"].save_and_advance(v, "t1", drafts, [], S.IDEA, S.SCRIPTED)
    first = env["scripts"].scenes(v)

    inserted = SceneDraft("Cena nova no fim da lista.", "", "", "prompt de imagem novo e válido", [])
    changed = [drafts[1], drafts[0], inserted]
    env["scripts"].save_and_advance(v, "t2", changed, [], S.SCRIPTED, S.SCRIPTED)

    scenes = env["scripts"].scenes(v)
    assert [s.narration for s in scenes] == [d.narration for d in changed]
    assert [s.idx for s in scenes] == [0, 1, 2]
    assert scenes[0].id == first[1].id and scenes[1].id == first[0].id
    assert scenes[2].id not in {first[0].id, first[1].id}


def test_inserting_and_removing_scenes_keeps_unaffected_ids(env):
    v = env["video"].id
    drafts = _drafts(3)
    env["scripts"].save_and_advance(v, "t1", drafts, [], S.IDEA, S.SCRIPTED)
    first = env["scripts"].scenes(v)

    inserted = SceneDraft("Cena nova inserida no meio.", "", "", "prompt de imagem novo e válido", [])
    with_insert = [drafts[0], inserted, drafts[1], drafts[2]]
    env["scripts"].save_and_advance(v, "t2", with_insert, [], S.SCRIPTED, S.SCRIPTED)

    second = env["scripts"].scenes(v)
    assert [s.narration for s in second] == [d.narration for d in with_insert]
    assert [s.id for s in second] == [first[0].id, second[1].id, first[1].id, first[2].id]
    assert second[1].id not in {s.id for s in first} and second[1].asset_id is None

    without_removed = [drafts[0], inserted, drafts[2]]  # a cena 1 sai
    env["scripts"].save_and_advance(v, "t3", without_removed, [], S.SCRIPTED, S.SCRIPTED)
    third = env["scripts"].scenes(v)
    assert [s.narration for s in third] == [d.narration for d in without_removed]
    assert [s.id for s in third] == [first[0].id, second[1].id, first[2].id]
    assert first[1].id not in {s.id for s in third}


def test_scene_identity_migration_is_additive_and_keeps_existing_rows(conn, tmp_path):
    migrations = Path(__file__).resolve().parents[1] / "renderer/app/studio/adapters/postgres/migrations"
    for path in sorted(migrations.glob("*.sql")):
        if path.name <= "0041":
            shutil.copy(path, tmp_path / path.name)
    migrate(conn, tmp_path)

    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, %s)", ("a" * 32, "canal"))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, %s, %s)",
                 ("b" * 32, "a" * 32, "tema do vídeo", "short"))
    conn.execute("INSERT INTO studio.scenes(id, video_id, idx, narration, image_prompt) VALUES (%s, %s, 0, %s, %s)",
                 ("c" * 32, "b" * 32, "narração já existente", "prompt de imagem já existente"))
    conn.commit()

    shutil.copy(migrations / "0042_scene_stable_identity.sql", tmp_path / "0042_scene_stable_identity.sql")
    assert migrate(conn, tmp_path) == ["0042_scene_stable_identity"]
    row = conn.execute("SELECT id, idx, narration, media_review_required FROM studio.scenes WHERE id = %s",
                       ("c" * 32,)).fetchone()
    assert row == ("c" * 32, 0, "narração já existente", False)
    assert conn.execute("SELECT count(*) FROM studio.scenes").fetchone()[0] == 1


def test_script_edit_requests_migration_is_additive_and_cascades(conn, tmp_path):
    migrations = Path(__file__).resolve().parents[1] / "renderer/app/studio/adapters/postgres/migrations"
    target = "0044_script_edit_requests.sql"
    for path in sorted(migrations.glob("*.sql")):
        if path.name != target:
            shutil.copy(path, tmp_path / path.name)
    migrate(conn, tmp_path)

    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, %s)", ("a" * 32, "canal"))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, %s, %s)",
                 ("b" * 32, "a" * 32, "tema do vídeo", "short"))
    conn.commit()

    shutil.copy(migrations / target, tmp_path / target)
    assert migrate(conn, tmp_path) == ["0044_script_edit_requests"]
    assert conn.execute("SELECT count(*) FROM studio.script_edit_requests").fetchone()[0] == 0

    conn.execute("INSERT INTO studio.script_edit_requests(video_id, idempotency_key, payload_sha256, result_json) "
                 "VALUES (%s, %s, %s, %s::jsonb)", ("b" * 32, "key-1", "a" * 64, '{"script": {}}'))
    conn.commit()

    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO studio.script_edit_requests(video_id, idempotency_key, payload_sha256, result_json) "
                     "VALUES (%s, %s, %s, %s::jsonb)", ("b" * 32, "key-1", "b" * 64, "{}"))
    conn.rollback()

    conn.execute("DELETE FROM studio.videos WHERE id = %s", ("b" * 32,))
    conn.commit()
    assert conn.execute("SELECT count(*) FROM studio.script_edit_requests").fetchone()[0] == 0


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
    assert env["checks"].save(v, REPORT_OK, advance=True, script_version=1) is False  # ainda IDEA: nada gravado
    assert env["conn"].execute("SELECT count(*) FROM studio.fact_checks").fetchone()[0] == 0
    env["scripts"].save_and_advance(v, "t", DRAFTS, [], S.IDEA, S.SCRIPTED)
    assert env["checks"].save(v, REPORT_BAD, advance=False, script_version=1) is True and status(env) == "SCRIPTED"
    assert env["checks"].save(v, REPORT_OK, advance=True, script_version=1) is True and status(env) == "FACT_CHECKED"
    env["conn"].commit()
    assert env["conn"].execute("SELECT count(*) FROM studio.fact_checks WHERE video_id=%s", (v,)).fetchone()[0] == 2


def test_fact_check_override_is_persisted_with_reason(env):
    v = env["video"].id
    env["scripts"].save_and_advance(v, "t", DRAFTS, [], S.IDEA, S.SCRIPTED)
    report = FactCheckReport(passed=True, overridden=True, override_reason="conferido na fonte impressa", scenes=REPORT_BAD.scenes)
    assert env["checks"].save(v, report, advance=True, script_version=1) is True
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


def test_fact_check_refuses_when_the_script_changed_after_it_was_read(env):
    v = env["video"].id
    env["scripts"].save_and_advance(v, "t1", DRAFTS, [], S.IDEA, S.SCRIPTED)
    env["scripts"].save_and_advance(v, "t2", DRAFTS, [], S.SCRIPTED, S.SCRIPTED)  # v2 chegou depois da leitura da v1
    assert env["checks"].save(v, REPORT_OK, advance=True, script_version=1) is False
    assert status(env) == "SCRIPTED"
    env["conn"].commit()
    assert env["conn"].execute("SELECT count(*) FROM studio.fact_checks").fetchone()[0] == 0
    assert env["checks"].save(v, REPORT_OK, advance=True, script_version=2) is True
    env["conn"].commit()
    assert env["conn"].execute("SELECT script_version FROM studio.fact_checks WHERE video_id=%s", (v,)).fetchone()[0] == 2
