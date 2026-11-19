import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.studio.application.config import register  # noqa: E402
from app.studio.application.ports import FetchedPage, TextResult  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.domain.contracts import UsageEntry  # noqa: E402

SOURCE = ("Amsterdam Dance Event celebrates 30 years with more than 3,600 artists, 1,300 events and 300 venues across the city.\n"
          "Jean-Michel Jarre opens the festival with a concert at AFAS Live on 21 October to mark 50 years of Oxygène.\n")
REF = "https://www.amsterdam-dance-event.nl/en/about"


class FakeFetcher:
    def fetch(self, url):
        return FetchedPage(text=SOURCE, final_url=url)


class BadText:
    """Devolve um roteiro com número inventado, citando a primeira claim da fonte."""
    name = "fake"

    def __init__(self, model):
        self.model, self.cost = model, 0.0

    def cost_estimate(self, prompt):
        return self.cost

    def complete(self, prompt, *, json_schema=None):
        import re
        first = re.search(r"^\[([0-9a-f]{10})\]", prompt, re.M).group(1)
        scenes = [{"narration": "Eram mais de quatro mil artistas.", "image_prompt": "wide stage with colorful lights",
                   "claim_ids": [first]}] * 2
        return TextResult(json.dumps({"scenes": scenes}), UsageEntry(step="text", provider="fake", model=self.model, cost_usd=0))


class PaidText(BadText):
    name = "paid"

    def __init__(self, model):
        super().__init__(model)
        self.cost = 0.5


register("text", "fake", BadText)
register("text", "paid", PaidText)


def make_client(dsn, tmp_path, text="demo:x"):
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ={"STUDIO_TEXT": text}, fetcher=FakeFetcher())
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return TestClient(app)


@pytest.fixture()
def client(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    return make_client(dsn, tmp_path)


def new_video(client):
    pid = client.post("/studio/projects", json={"name": "canal"}).json()["id"]
    return client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": "short"}).json()["id"]


def add_text_source(client, vid, text=SOURCE):
    return client.post(f"/studio/videos/{vid}/sources", json={"url": REF, "text": text})


def status(client, vid):
    return client.get(f"/studio/videos/{vid}").json()["status"]


def test_text_source_is_stored_without_echoing_the_whole_text(client):
    vid = new_video(client)
    r = add_text_source(client, vid)
    assert r.status_code == 201 and r.json()["chars"] == len(SOURCE.strip()) and "text" not in r.json()


def test_url_source_goes_through_the_fetcher_and_allowlist(client):
    vid = new_video(client)
    assert client.post(f"/studio/videos/{vid}/sources", json={"url": REF}).status_code == 201
    assert client.post(f"/studio/videos/{vid}/sources", json={"url": "https://evil.example/x"}).status_code == 422
    assert client.post(f"/studio/videos/{vid}/sources", json={"url": "file:///etc/passwd"}).status_code == 422


def test_source_errors(client):
    vid = new_video(client)
    assert add_text_source(client, vid, "   ").status_code == 422
    assert add_text_source(client, vid, "a" * 200_001).status_code == 422
    assert client.post(f"/studio/videos/{'0' * 32}/sources", json={"url": REF, "text": "x"}).status_code == 404
    assert client.post(f"/studio/videos/{'A' * 32}/sources", json={"url": REF, "text": "x"}).status_code == 422


def test_script_needs_sources_then_generates_and_is_readable(client):
    vid = new_video(client)
    assert client.post(f"/studio/videos/{vid}/script", json={}).status_code == 422
    assert client.get(f"/studio/videos/{vid}/script").status_code == 404
    add_text_source(client, vid)
    r = client.post(f"/studio/videos/{vid}/script", json={"scene_count": 4})
    assert r.status_code == 201 and r.json()["script"]["version"] == 1 and len(r.json()["scenes"]) == 4
    assert status(client, vid) == "SCRIPTED"
    assert client.get(f"/studio/videos/{vid}/script").json()["script"]["version"] == 1
    assert client.post(f"/studio/videos/{vid}/script", json={"scene_count": 4}).json()["script"]["version"] == 2
    assert client.post(f"/studio/videos/{vid}/script", json={"scene_count": 99}).status_code == 422


def test_fact_check_passes_demo_script_and_blocks_regeneration(client):
    vid = new_video(client)
    add_text_source(client, vid)
    client.post(f"/studio/videos/{vid}/script", json={"scene_count": 4})
    r = client.post(f"/studio/videos/{vid}/fact-check", json={})
    assert r.status_code == 200 and r.json()["passed"] is True and status(client, vid) == "FACT_CHECKED"
    assert client.post(f"/studio/videos/{vid}/fact-check", json={}).status_code == 409
    assert client.post(f"/studio/videos/{vid}/script", json={}).status_code == 409


def test_fact_check_fails_on_invented_number_then_override_needs_a_reason(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    client = make_client(dsn, tmp_path, text="fake:x")
    vid = new_video(client)
    add_text_source(client, vid)
    assert client.post(f"/studio/videos/{vid}/script", json={"scene_count": 2}).status_code == 201
    r = client.post(f"/studio/videos/{vid}/fact-check", json={})
    assert r.status_code == 200 and r.json()["passed"] is False and status(client, vid) == "SCRIPTED"
    assert [(i["kind"], i["value"]) for i in r.json()["scenes"][0]["unsupported"]] == [("number", "4000")]
    for bad in ("", "   "):
        assert client.post(f"/studio/videos/{vid}/fact-check", json={"override_reason": bad}).status_code == 422
    assert status(client, vid) == "SCRIPTED"
    r = client.post(f"/studio/videos/{vid}/fact-check", json={"override_reason": "conferido na fonte impressa"})
    assert r.status_code == 200 and r.json()["passed"] and r.json()["overridden"] and status(client, vid) == "FACT_CHECKED"


def test_paid_model_is_refused_by_cost_guard_before_the_call(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    client = make_client(dsn, tmp_path, text="paid:x")
    vid = new_video(client)
    add_text_source(client, vid)
    assert client.post(f"/studio/videos/{vid}/script", json={}).status_code == 403
    assert status(client, vid) == "IDEA"


def test_unknown_or_unconfigured_provider_is_422_not_500(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    for spec in ("naoexiste:x", "opencode:x"):  # o segundo existe mas está sem OPENCODE_BRIDGE_TOKEN
        client = make_client(dsn, tmp_path, text=spec)
        vid = new_video(client)
        add_text_source(client, vid)
        assert client.post(f"/studio/videos/{vid}/script", json={}).status_code == 422, spec


def test_project_config_overrides_environment(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    client = make_client(dsn, tmp_path, text="naoexiste:x")  # o ambiente está quebrado...
    pid = client.post("/studio/projects", json={"name": "canal"}).json()["id"]
    conn.execute("UPDATE studio.projects SET config = %s::jsonb WHERE id = %s", ('{"text": "demo:y"}', pid))
    conn.commit()  # ...mas o projeto escolhe o demo
    vid = client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": "short"}).json()["id"]
    add_text_source(client, vid)
    assert client.post(f"/studio/videos/{vid}/script", json={}).status_code == 201


def test_usage_is_recorded_in_the_ledger(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    client = make_client(dsn, tmp_path)
    vid = new_video(client)
    add_text_source(client, vid)
    client.post(f"/studio/videos/{vid}/script", json={})
    conn.commit()
    assert conn.execute("SELECT count(*), max(provider) FROM studio.usage_ledger WHERE video_id=%s", (vid,)).fetchone() == (1, "demo")
