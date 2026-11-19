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
    env["assets"].link_scene(env["video"].id, 1, a.id)
    scenes = env["scripts"].scenes(env["video"].id)
    assert [s.asset_id for s in scenes] == [None, a.id]
