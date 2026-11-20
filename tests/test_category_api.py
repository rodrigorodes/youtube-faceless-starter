import base64
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.application.categories import (  # noqa: E402
    MissingApiKey,
    YouTubeApiError,
)
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.trends import Evidence, TrendItem  # noqa: E402

BASIC_HEADER = {
    "Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode(),
    "Origin": "http://testserver",
}
WORKER_HEADER = {"Authorization": "Bearer test-worker-token"}


def dummy_trend_item(topic: str) -> TrendItem:
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)
    return TrendItem(
        topic=topic,
        source_name="YouTube Data API",
        source_url="https://www.googleapis.com/youtube/v3/search",
        observed_at=now,
        window_start=past,
        window_end=now,
        metric_name="views",
        metric_value=250000.0,
        evidence=[
            Evidence(
                title=f"Video on {topic}",
                url="https://youtube.com/watch?v=mock123",
                channel="Electronic Channel",
                views=250000,
            )
        ],
    )


@pytest.fixture()
def api_env(conn, dsn, tmp_path):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Pilares", niche="Musica Eletronica", language="pt-BR")

    recorded_queries = []

    def mock_yt_fetcher(key: str, queries: list[str]) -> list[TrendItem]:
        recorded_queries.clear()
        recorded_queries.extend(queries)
        if key == "INVALID_KEY":
            raise YouTubeApiError("API key expired or invalid quota")
        return [dummy_trend_item(q) for q in queries[:5]]

    token_file = tmp_path / "token.env"
    token_file.write_text("YOUTUBE_API_KEY=test-yt-key-123\n", encoding="utf-8")

    settings = Settings(
        database_url=dsn,
        storage_root=tmp_path,
        token_env_path=token_file,
    )
    studio = Studio(settings, youtube_fetcher=mock_yt_fetcher)
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app)

    return {
        "client": client,
        "videos": videos,
        "project_id": project.id,
        "conn": conn,
        "recorded_queries": recorded_queries,
        "token_file": token_file,
        "tmp_path": tmp_path,
        "dsn": dsn,
    }


def test_categories_endpoint_requires_auth(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    # Without auth -> 401
    r = client.get(f"/studio/projects/{p_id}/categories")
    assert r.status_code == 401


def test_categories_endpoint_host_guard(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    r = client.get(
        f"/studio/projects/{p_id}/categories",
        headers={**WORKER_HEADER, "Host": "malicious.com"},
    )
    assert r.status_code == 403


def test_list_categories_empty_for_new_project(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    r = client.get(f"/studio/projects/{p_id}/categories", headers=WORKER_HEADER)
    assert r.status_code == 200
    assert r.json() == []


def test_list_categories_project_not_found(api_env):
    client = api_env["client"]
    r = client.get(f"/studio/projects/{'0' * 32}/categories", headers=WORKER_HEADER)
    assert r.status_code == 404


def test_create_category_success_with_worker_and_basic(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    # Create via Worker Header
    payload = {"name": "Afro House", "queries": ["Afro House 2026", "Keinemusik"]}
    r = client.post(f"/studio/projects/{p_id}/categories", json=payload, headers=WORKER_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert len(data["id"]) == 32
    assert data["project_id"] == p_id
    assert data["name"] == "Afro House"
    assert data["queries"] == ["Afro House 2026", "Keinemusik"]
    assert "created_at" in data
    assert "updated_at" in data

    # Create another via Basic Header (browser)
    payload2 = {"name": "Melodic Techno", "queries": ["Anyma", "Afterlife"]}
    r2 = client.post(f"/studio/projects/{p_id}/categories", json=payload2, headers=BASIC_HEADER)
    assert r2.status_code == 201
    data2 = r2.json()
    assert data2["name"] == "Melodic Techno"

    # List categories returns both
    r_list = client.get(f"/studio/projects/{p_id}/categories", headers=WORKER_HEADER)
    assert r_list.status_code == 200
    items = r_list.json()
    assert len(items) == 2
    assert [item["name"] for item in items] == ["Afro House", "Melodic Techno"]


def test_create_category_duplicate_name_returns_409(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    payload = {"name": "Techno", "queries": ["Drumcode"]}
    r1 = client.post(f"/studio/projects/{p_id}/categories", json=payload, headers=WORKER_HEADER)
    assert r1.status_code == 201

    # Attempt same name in same project -> 409
    r2 = client.post(f"/studio/projects/{p_id}/categories", json=payload, headers=WORKER_HEADER)
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"].lower()


def test_create_category_invalid_name_returns_422(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    for invalid_name in ["", "   ", "x" * 101]:
        r = client.post(
            f"/studio/projects/{p_id}/categories",
            json={"name": invalid_name, "queries": ["q"]},
            headers=WORKER_HEADER,
        )
        assert r.status_code == 422


def test_update_category(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    r1 = client.post(
        f"/studio/projects/{p_id}/categories",
        json={"name": "Pilar Antigo", "queries": ["q1"]},
        headers=WORKER_HEADER,
    )
    assert r1.status_code == 201
    cat_id = r1.json()["id"]

    # Update using same id
    r2 = client.post(
        f"/studio/projects/{p_id}/categories",
        json={"id": cat_id, "name": "Pilar Atualizado", "queries": ["q1_new", "q2_new"]},
        headers=WORKER_HEADER,
    )
    assert r2.status_code == 201
    data = r2.json()
    assert data["id"] == cat_id
    assert data["name"] == "Pilar Atualizado"
    assert data["queries"] == ["q1_new", "q2_new"]


def test_delete_category_success_and_404(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    r1 = client.post(
        f"/studio/projects/{p_id}/categories",
        json={"name": "Para Deletar", "queries": ["q"]},
        headers=WORKER_HEADER,
    )
    assert r1.status_code == 201
    cat_id = r1.json()["id"]

    # Delete existing
    r_del = client.delete(
        f"/studio/projects/{p_id}/categories/{cat_id}",
        headers=WORKER_HEADER,
    )
    assert r_del.status_code == 200
    assert r_del.json() == {"deleted": True}

    # Delete again -> 404
    r_del_again = client.delete(
        f"/studio/projects/{p_id}/categories/{cat_id}",
        headers=WORKER_HEADER,
    )
    assert r_del_again.status_code == 404

    # Delete non-existent ID -> 404
    r_non_existent = client.delete(
        f"/studio/projects/{p_id}/categories/{'f' * 32}",
        headers=WORKER_HEADER,
    )
    assert r_non_existent.status_code == 404


def test_refresh_trends_uses_project_category_queries(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]
    recorded = api_env["recorded_queries"]

    # Create 2 categories
    client.post(
        f"/studio/projects/{p_id}/categories",
        json={"name": "Bass House", "queries": ["Bass House 2026", "Tchami"]},
        headers=WORKER_HEADER,
    )
    client.post(
        f"/studio/projects/{p_id}/categories",
        json={"name": "EDM", "queries": ["Tomorrowland 2026"]},
        headers=WORKER_HEADER,
    )

    r_refresh = client.post(f"/studio/projects/{p_id}/trends/refresh", json={}, headers=WORKER_HEADER)
    assert r_refresh.status_code == 200
    assert r_refresh.json() == {"stored": 3}
    assert recorded == ["Bass House 2026", "Tchami", "Tomorrowland 2026"]


def test_refresh_trends_fallback_when_no_categories(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]
    recorded = api_env["recorded_queries"]

    r_refresh = client.post(f"/studio/projects/{p_id}/trends/refresh", headers=WORKER_HEADER)
    assert r_refresh.status_code == 200
    data = r_refresh.json()
    assert data["stored"] > 0
    assert len(recorded) > 0  # Fallback default queries were used


def test_refresh_trends_custom_queries_override(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]
    recorded = api_env["recorded_queries"]

    client.post(
        f"/studio/projects/{p_id}/categories",
        json={"name": "Trance", "queries": ["ASOT 2026"]},
        headers=WORKER_HEADER,
    )

    r_refresh = client.post(
        f"/studio/projects/{p_id}/trends/refresh",
        json={"queries": ["Custom Query 1", "Custom Query 2"]},
        headers=WORKER_HEADER,
    )
    assert r_refresh.status_code == 200
    assert r_refresh.json() == {"stored": 2}
    assert recorded == ["Custom Query 1", "Custom Query 2"]


def test_refresh_trends_missing_api_key_returns_400(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]
    token_file = api_env["token_file"]

    # Remove API key from token file
    token_file.write_text("OTHER_VAR=abc\n", encoding="utf-8")

    r_refresh = client.post(f"/studio/projects/{p_id}/trends/refresh", headers=WORKER_HEADER)
    assert r_refresh.status_code == 400
    assert "YOUTUBE_API_KEY" in r_refresh.json()["detail"]


def test_refresh_trends_youtube_api_error_returns_502(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]
    token_file = api_env["token_file"]

    # Set key that triggers error in mock fetcher
    token_file.write_text("YOUTUBE_API_KEY=INVALID_KEY\n", encoding="utf-8")

    r_refresh = client.post(f"/studio/projects/{p_id}/trends/refresh", headers=WORKER_HEADER)
    assert r_refresh.status_code == 502
    assert "quota" in r_refresh.json()["detail"] or "invalid" in r_refresh.json()["detail"]


def test_create_category_project_not_found(api_env):
    client = api_env["client"]
    r = client.post(
        f"/studio/projects/{'0' * 32}/categories",
        json={"name": "Tech", "queries": ["AI"]},
        headers=WORKER_HEADER,
    )
    assert r.status_code == 404


def test_update_category_conflict_name_returns_409(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    client.post(
        f"/studio/projects/{p_id}/categories",
        json={"name": "Pilar A", "queries": ["q1"]},
        headers=WORKER_HEADER,
    )
    r2 = client.post(
        f"/studio/projects/{p_id}/categories",
        json={"name": "Pilar B", "queries": ["q2"]},
        headers=WORKER_HEADER,
    )
    cat2_id = r2.json()["id"]

    # Attempt to rename Pilar B to Pilar A
    r3 = client.post(
        f"/studio/projects/{p_id}/categories",
        json={"id": cat2_id, "name": "Pilar A", "queries": ["q2"]},
        headers=WORKER_HEADER,
    )
    assert r3.status_code == 409


def test_delete_category_invalid_id_returns_422(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    r = client.delete(
        f"/studio/projects/{p_id}/categories/invalid-id-xyz",
        headers=WORKER_HEADER,
    )
    assert r.status_code == 422


def test_delete_category_cross_project_isolation(api_env):
    client = api_env["client"]
    videos = api_env["videos"]
    p_id = api_env["project_id"]
    other_project = videos.create_project("Canal Secundario", niche="Outro", language="pt-BR")

    r = client.post(
        f"/studio/projects/{p_id}/categories",
        json={"name": "Isolado", "queries": ["q"]},
        headers=WORKER_HEADER,
    )
    cat_id = r.json()["id"]

    # Attempt to delete this category via other_project's endpoint -> 404
    r_del = client.delete(
        f"/studio/projects/{other_project.id}/categories/{cat_id}",
        headers=WORKER_HEADER,
    )
    assert r_del.status_code == 404

    # The category still exists in original project
    r_check = client.get(f"/studio/projects/{p_id}/categories", headers=WORKER_HEADER)
    assert len(r_check.json()) == 1


def test_fetch_youtube_trends_handles_http_error(monkeypatch):
    from app.studio.adapters.youtube_trends import fetch_youtube_trends
    import urllib.request
    import urllib.error

    def mock_urlopen(req, timeout=15):
        raise urllib.error.HTTPError(
            url="https://youtube.googleapis.com",
            code=403,
            msg="Quota exceeded",
            hdrs={},
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    with pytest.raises(YouTubeApiError) as exc_info:
        fetch_youtube_trends("fake-key", ["query1"])
    assert "403" in str(exc_info.value) or "Quota exceeded" in str(exc_info.value)


def test_refresh_trends_calls_popular_fetcher_on_default_refresh():
    import uuid
    from app.studio.application.categories import RefreshTrends
    from app.studio.domain.categories import ProjectCategory

    p_id = uuid.uuid4().hex

    c_id = uuid.uuid4().hex

    class FakeCatRepo:
        def list(self, project_id):
            return [ProjectCategory(c_id, project_id, "Tech", ["AI 2026"])]

    class FakeIngest:
        def __init__(self):
            self.ingested_items = []

        def execute(self, project_id, items):
            self.ingested_items.extend(items)
            return len(items)

    pillar_called = []
    popular_called = []

    def mock_fetcher(key, queries):
        pillar_called.append((key, queries))
        return [dummy_trend_item(q) for q in queries]

    def mock_popular(key, region, max_results):
        popular_called.append((key, region, max_results))
        return [dummy_trend_item(f"Popular in {region}")]

    ingest = FakeIngest()
    refresh = RefreshTrends(
        repo=FakeCatRepo(),
        ingest=ingest,
        fetcher=mock_fetcher,
        popular_fetcher=mock_popular,
        environ={"YOUTUBE_API_KEY": "fake-key"},
    )

    count = refresh.execute(p_id)
    assert count == 3  # 1 pillar + 1 BR + 1 US
    assert len(pillar_called) == 1
    assert pillar_called[0] == ("fake-key", ["AI 2026"])
    assert popular_called == [
        ("fake-key", "BR", 10),
        ("fake-key", "US", 10),
    ]


def test_refresh_trends_bypasses_popular_fetcher_on_custom_queries():
    import uuid
    from app.studio.application.categories import RefreshTrends

    p_id = uuid.uuid4().hex

    class FakeCatRepo:
        def list(self, project_id):
            return []

    class FakeIngest:
        def execute(self, project_id, items):
            return len(items)

    popular_called = []

    def mock_fetcher(key, queries):
        return [dummy_trend_item(q) for q in queries]

    def mock_popular(key, region, max_results):
        popular_called.append((key, region, max_results))
        return [dummy_trend_item("pop")]

    refresh = RefreshTrends(
        repo=FakeCatRepo(),
        ingest=FakeIngest(),
        fetcher=mock_fetcher,
        popular_fetcher=mock_popular,
        environ={"YOUTUBE_API_KEY": "fake-key"},
    )

    count = refresh.execute(p_id, custom_queries=["Custom Query"])
    assert count == 1
    assert popular_called == []


def test_refresh_trends_popular_fetcher_resilience():
    import uuid
    from app.studio.application.categories import RefreshTrends

    p_id = uuid.uuid4().hex

    class FakeCatRepo:
        def list(self, project_id):
            return []

    class FakeIngest:
        def execute(self, project_id, items):
            return len(items)

    def mock_fetcher(key, queries):
        return [dummy_trend_item(queries[0])]

    def failing_popular(key, region, max_results):
        raise RuntimeError("Network timeout connecting to YouTube")

    refresh = RefreshTrends(
        repo=FakeCatRepo(),
        ingest=FakeIngest(),
        fetcher=mock_fetcher,
        popular_fetcher=failing_popular,
        environ={"YOUTUBE_API_KEY": "fake-key"},
    )

    # Should not raise RuntimeError, should return count from pillar items
    count = refresh.execute(p_id)
    assert count == 1


def test_refresh_trends_endpoint_includes_popular_trends(conn, dsn, tmp_path):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Pop", niche="Geral", language="pt-BR")

    popular_regions = []

    def mock_yt_fetcher(key: str, queries: list[str]) -> list[TrendItem]:
        return [dummy_trend_item(queries[0])]

    def mock_pop_fetcher(key: str, region: str, max_results: int) -> list[TrendItem]:
        popular_regions.append(region)
        return [dummy_trend_item(f"Popular {region}")]

    token_file = tmp_path / "token.env"
    token_file.write_text("YOUTUBE_API_KEY=test-yt-key-123\n", encoding="utf-8")

    settings = Settings(database_url=dsn, storage_root=tmp_path, token_env_path=token_file)
    studio = Studio(settings, youtube_fetcher=mock_yt_fetcher, youtube_popular_fetcher=mock_pop_fetcher)
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app)

    r = client.post(f"/studio/projects/{project.id}/trends/refresh", headers=WORKER_HEADER)
    assert r.status_code == 200
    assert r.json() == {"stored": 3}  # 1 default pillar + 1 BR + 1 US
    assert popular_regions == ["BR", "US"]



