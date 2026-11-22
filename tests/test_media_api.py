import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402

SOURCE = ("Amsterdam Dance Event celebrates 30 years with more than 3,600 artists, 1,300 events and 300 venues across the city.\n"
          "Jean-Michel Jarre opens the festival with a concert at AFAS Live on 21 October to mark 50 years of Oxygène.\n")
REF = "https://www.amsterdam-dance-event.nl/en/about"


def make_client(dsn, tmp_path, image="placeholder:gradient", **env):
    environ = {"STUDIO_TEXT": "demo:x", "STUDIO_IMAGE": image, **env}
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ=environ)
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return TestClient(app, headers={"Authorization": "Bearer test-worker-token"})


@pytest.fixture()
def client(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    return make_client(dsn, tmp_path)


def fact_checked_video(client, name="canal"):
    pid = client.post("/studio/projects", json={"name": name}).json()["id"]
    vid = client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": "short"}).json()["id"]
    client.post(f"/studio/videos/{vid}/sources", json={"url": REF, "text": SOURCE})
    client.post(f"/studio/videos/{vid}/script", json={"scene_count": 4})
    assert client.post(f"/studio/videos/{vid}/fact-check", json={}).status_code == 200
    return vid


def status(client, vid):
    return client.get(f"/studio/videos/{vid}").json()["status"]


def test_full_media_flow_with_cache_files_licenses_and_state(client, tmp_path):
    vid = fact_checked_video(client)
    assert client.post(f"/studio/videos/{vid}/storyboard").status_code == 200 and status(client, vid) == "STORYBOARDED"
    r = client.post(f"/studio/videos/{vid}/assets")
    assert r.status_code == 200 and r.json() == {"generated": 1, "reused": 3}  # o demo usa o mesmo prompt nas 4 cenas
    assert status(client, vid) == "ASSETS_READY"
    listed = client.get(f"/studio/videos/{vid}/assets").json()["scenes"]
    assert [s["idx"] for s in listed] == [0, 1, 2, 3] and len({s["asset"]["id"] for s in listed}) == 1
    asset = listed[0]["asset"]
    assert asset["license"].startswith("CC0") and asset["provider"] == "placeholder" and not asset["path"].startswith("/")
    assert Image.open(tmp_path / asset["path"]).size == (1080, 1920)


def test_second_video_with_the_same_content_generates_zero_new_images(client):
    first = fact_checked_video(client, "um")
    client.post(f"/studio/videos/{first}/storyboard")
    assert client.post(f"/studio/videos/{first}/assets").json()["generated"] == 1
    second = fact_checked_video(client, "dois")
    client.post(f"/studio/videos/{second}/storyboard")
    assert client.post(f"/studio/videos/{second}/assets").json() == {"generated": 0, "reused": 4}


def test_state_guards_and_reserved_transitions(client):
    vid = fact_checked_video(client)
    assert client.post(f"/studio/videos/{vid}/assets").status_code == 409  # ainda FACT_CHECKED
    assert client.post(f"/studio/videos/{vid}/storyboard").status_code == 200
    assert client.post(f"/studio/videos/{vid}/storyboard").status_code == 409
    for target in ("STORYBOARDED", "ASSETS_READY"):
        assert client.post(f"/studio/videos/{vid}/transition", json={"expected": "FACT_CHECKED", "new": target}).status_code == 403
    assert client.post(f"/studio/videos/{'0' * 32}/storyboard").status_code == 404
    assert client.post(f"/studio/videos/{'0' * 32}/assets").status_code == 404
    assert client.get(f"/studio/videos/{'0' * 32}/assets").status_code == 404
    assert client.post(f"/studio/videos/{'A' * 32}/assets").status_code == 422


def test_veo_is_refused_with_cap_zero_and_nothing_changes(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    client = make_client(dsn, tmp_path, image="veo:veo-3.1")
    vid = fact_checked_video(client)
    client.post(f"/studio/videos/{vid}/storyboard")
    assert client.post(f"/studio/videos/{vid}/assets").status_code == 403
    assert status(client, vid) == "STORYBOARDED"
    conn.commit()
    assert conn.execute("SELECT count(*) FROM studio.assets").fetchone()[0] == 0


@pytest.mark.parametrize("spec", ["naoexiste:x", "opencode:x", "stock:pexels"])
def test_unknown_or_unconfigured_image_provider_is_422(conn, dsn, tmp_path, spec):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    client = make_client(dsn, tmp_path, image=spec)
    vid = fact_checked_video(client)
    client.post(f"/studio/videos/{vid}/storyboard")
    assert client.post(f"/studio/videos/{vid}/assets").status_code == 422
    assert status(client, vid) == "STORYBOARDED"


def test_veo_not_implemented_when_cap_is_released_is_502(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path, max_cost_video=10.0), environ={"STUDIO_TEXT": "demo:x", "STUDIO_IMAGE": "veo:v"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})
    vid = fact_checked_video(client)
    client.post(f"/studio/videos/{vid}/storyboard")
    assert client.post(f"/studio/videos/{vid}/assets").status_code == 502


def test_image_usage_is_recorded_and_project_config_overrides_env(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    client = make_client(dsn, tmp_path, image="naoexiste:x")  # ambiente quebrado; o projeto escolhe o placeholder
    pid = client.post("/studio/projects", json={"name": "canal"}).json()["id"]
    conn.execute("UPDATE studio.projects SET config = %s::jsonb WHERE id = %s", ('{"image": "placeholder:y"}', pid))
    conn.commit()
    vid = client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": "short"}).json()["id"]
    client.post(f"/studio/videos/{vid}/sources", json={"url": REF, "text": SOURCE})
    client.post(f"/studio/videos/{vid}/script", json={"scene_count": 3})
    client.post(f"/studio/videos/{vid}/fact-check", json={})
    client.post(f"/studio/videos/{vid}/storyboard")
    assert client.post(f"/studio/videos/{vid}/assets").status_code == 200
    conn.commit()
    assert conn.execute("SELECT count(*) FROM studio.usage_ledger WHERE video_id=%s AND step='image'", (vid,)).fetchone()[0] == 1


def test_storyboard_without_scenes_is_409_not_a_model_error(client):
    pid = client.post("/studio/projects", json={"name": "vazio"}).json()["id"]
    vid = client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": "short"}).json()["id"]
    assert client.post(f"/studio/videos/{vid}/storyboard").status_code == 409  # IDEA: estado errado vem antes


def test_each_scene_gets_the_asset_of_its_own_prompt(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    client = make_client(dsn, tmp_path)
    vid = fact_checked_video(client)
    conn.execute("UPDATE studio.scenes SET image_prompt = 'prompt numero ' || idx || ' sobre palco' WHERE video_id = %s", (vid,))
    conn.commit()
    client.post(f"/studio/videos/{vid}/storyboard")
    assert client.post(f"/studio/videos/{vid}/assets").json() == {"generated": 4, "reused": 0}
    listed = client.get(f"/studio/videos/{vid}/assets").json()["scenes"]
    assert len({s["asset"]["id"] for s in listed}) == 4
    conn.commit()
    assert conn.execute("SELECT count(*) FROM studio.usage_ledger WHERE video_id=%s AND step='image'", (vid,)).fetchone()[0] == 4


def test_swap_scene_media_links_only_that_scene_and_is_idempotent(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    client = make_client(dsn, tmp_path)
    vid = fact_checked_video(client)
    conn.execute("UPDATE studio.scenes SET image_prompt = 'prompt numero ' || idx || ' sobre palco' WHERE video_id = %s", (vid,))
    conn.commit()
    client.post(f"/studio/videos/{vid}/storyboard")
    client.post(f"/studio/videos/{vid}/assets")
    before = [scene["asset"]["id"] for scene in client.get(f"/studio/videos/{vid}/assets").json()["scenes"]]
    assert len(set(before)) == 4  # cada cena tem o próprio asset
    scene_id = conn.execute("SELECT id FROM studio.scenes WHERE video_id=%s AND idx=1", (vid,)).fetchone()[0]

    response = client.post(f"/studio/videos/{vid}/scenes/{scene_id}/media", json={"asset_id": before[2]})
    assert response.status_code == 200 and response.json()["changed"] is True
    after = [scene["asset"]["id"] for scene in client.get(f"/studio/videos/{vid}/assets").json()["scenes"]]
    assert after == [before[0], before[2], before[2], before[3]]  # só a cena 1 mudou

    replay = client.post(f"/studio/videos/{vid}/scenes/{scene_id}/media", json={"asset_id": before[2]})
    assert replay.status_code == 200 and replay.json()["changed"] is False  # repetir é seguro

