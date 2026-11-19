import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.editorial_repo import PostgresScriptRepository  # noqa: E402
from app.studio.adapters.postgres.media_repo import PostgresAssetRepository  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.application.ports import SceneDraft  # noqa: E402
from app.studio.domain.contracts import Asset, AssetKind, VideoFormat, VideoStatus  # noqa: E402


def asset(id_="1" * 32, key="a" * 64, **kw):
    base = dict(id=id_, kind=AssetKind.image, cache_key=key, path=f"cache/aa/{key}.png", provider="p", model="m", license="CC0",
                attribution="Foto de Fulano", source_url="https://x.example", cost_usd=0.0)
    return Asset(**{**base, **kw})


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("canal").id, "ADE 2026", VideoFormat.short)
    scripts = PostgresScriptRepository(connect)
    scripts.save_and_advance(video.id, "t", [SceneDraft("Primeira narração válida.", "", "", "wide stage with colorful lights", ["c"]),
                                             SceneDraft("Segunda narração válida.", "", "", "crowd under neon lights", ["c"])],
                             ["c"], VideoStatus.IDEA, VideoStatus.SCRIPTED)
    return {"assets": PostgresAssetRepository(connect), "scripts": scripts, "video": video, "conn": conn}


def test_add_find_get_roundtrip_keeps_credits(env):
    saved = env["assets"].add(asset())
    assert env["assets"].find("a" * 64) == saved == env["assets"].get("1" * 32)
    assert saved.attribution == "Foto de Fulano" and saved.source_url == "https://x.example" and saved.license == "CC0"
    assert env["assets"].find("b" * 64) is None and env["assets"].get("9" * 32) is None


def test_add_with_existing_cache_key_returns_the_existing_asset(env):
    first = env["assets"].add(asset("1" * 32))
    second = env["assets"].add(asset("2" * 32))  # outra execução gerou a mesma chave
    assert second.id == first.id == "1" * 32
    env["conn"].commit()
    assert env["conn"].execute("SELECT count(*) FROM studio.assets").fetchone()[0] == 1


def test_link_scene_is_visible_through_scenes(env):
    a = env["assets"].add(asset())
    env["scripts"].scenes(env["video"].id)
    env["conn"].execute("UPDATE studio.videos SET status='STORYBOARDED' WHERE id=%s", (env["video"].id,))
    env["conn"].commit()
    assert env["assets"].link_scene(env["video"].id, 1, a.id, "crowd under neon lights") is True
    scenes = env["scripts"].scenes(env["video"].id)
    assert [s.asset_id for s in scenes] == [None, a.id]


def test_link_scene_refuses_wrong_prompt_wrong_state_or_missing_scene(env):
    a, v = env["assets"].add(asset()), env["video"].id
    assert env["assets"].link_scene(v, 1, a.id, "crowd under neon lights") is False  # vídeo ainda SCRIPTED
    env["conn"].execute("UPDATE studio.videos SET status='STORYBOARDED' WHERE id=%s", (v,))
    env["conn"].commit()
    assert env["assets"].link_scene(v, 1, a.id, "outro prompt") is False
    assert env["assets"].link_scene(v, 9, a.id, "crowd under neon lights") is False
    assert [s.asset_id for s in env["scripts"].scenes(v)] == [None, None]
    assert env["assets"].link_scene(v, 0, a.id, "wide stage with colorful lights") is True


def test_production_lock_is_exclusive_per_video_and_released(env, dsn):
    from app.studio.adapters.postgres.media_repo import PostgresProductionLock
    lock = PostgresProductionLock(lambda: psycopg.connect(dsn, autocommit=True))
    v, other = env["video"].id, "f" * 32
    with lock.hold(v) as got:
        assert got is True
        with lock.hold(v) as again:
            assert again is False
        with lock.hold(other) as parallel:
            assert parallel is True
    with lock.hold(v) as after:
        assert after is True


def test_blank_license_with_tabs_or_newlines_is_refused_by_the_database(env):
    ins = "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) VALUES (%s, 'image', %s, 'x', 'p', 'm', %s)"
    for lic in ("\t", "\n", " \t\n "):
        with pytest.raises(psycopg.errors.CheckViolation):
            env["conn"].execute(ins, ("3" * 32, "c" * 64, lic))
        env["conn"].rollback()
        migrate(env["conn"])
