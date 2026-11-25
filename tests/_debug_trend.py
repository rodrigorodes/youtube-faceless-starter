import base64
import json
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}


def test_debug(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Visual", niche="Música", language="pt-BR")
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app)

    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)
    cat_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO studio.project_categories (id, project_id, name, queries) VALUES (%s, %s, %s, %s)",
        (cat_id, project.id, "Tecnologia", ["IA", "ChatGPT"]),
    )
    conn.execute(
        """
        INSERT INTO studio.trend_topics (
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, metric_name, metric_value, evidence
        ) VALUES (%s, %s, 'Novidades de IA em 2026', 'novidades de ia em 2026',
            'YouTube Data API', 'https://www.googleapis.com/youtube/v3/search',
            %s, %s, %s, 'views', 500000,
            %s::jsonb)
        """,
        (uuid.uuid4().hex, project.id, now, past, now,
         json.dumps([{"title": "IA Revoluciona Produção", "channel": "Tech Today", "url": "https://youtube.com/watch?v=2", "views": 500000}])),
    )
    conn.commit()

    uc = studio.use_cases()
    view = uc.panel.execute(days=7, project_id=project.id)
    print("CATEGORIES", view.categories)
    for t in view.trends:
        print("TREND", t.topic, "query=", getattr(t, "query", "NOQUERY"), "cat=", t.category_id, t.category_name)
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    print("STATUS", r.status_code)
    for needle in ["+ Novo pilar", 'id="btn-novo-pilar"', "Pilar: Tecnologia", "Tecnologia", f'data-pilar="{cat_id}"', "Busca", "Não informada", "Região não informada"]:
        print("NEEDLE", needle, needle in r.text)
    for m in re.finditer(r'<article class="card cartao-tendencia".*?</article>', r.text, re.S):
        print("CARD", re.sub(r"\s+", " ", m.group(0))[:1500])
