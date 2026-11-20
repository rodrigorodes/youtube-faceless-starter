import base64
import sys
import uuid
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
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}


@pytest.fixture()
def client_env(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Visual", niche="Música", language="pt-BR")

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app)
    return {"client": client, "videos": videos, "project_id": project.id, "conn": conn}


def test_panel_page_escapes_xss(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "<script>alert(1)</script>", VideoFormat.short)
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text


def test_panel_page_csp_and_cache_control_headers(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Content-Security-Policy" in r.headers
    assert "nonce-" in r.headers["Content-Security-Policy"]
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_panel_page_empty_state(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Nenhum vídeo no período" in r.text


def test_panel_page_and_detail_never_contain_upload_uri(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Tema Normal", VideoFormat.short)
    secret_uri = "https://youtube.googleapis.com/upload/SECRET_URI_RESUMABLE_PANEL_PAGE"

    conn.execute(
        "INSERT INTO studio.publications (id, video_id, status, attempt, upload_uri, error) "
        "VALUES (%s, %s, 'FAILED', 1, %s, 'Erro')",
        (uuid.uuid4().hex, v.id, secret_uri),
    )
    conn.commit()

    r_panel = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r_panel.status_code == 200
    assert secret_uri not in r_panel.text

    r_detail = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r_detail.status_code == 200
    assert secret_uri not in r_detail.text


def test_video_detail_page_escapes_error_messages(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Tema Erro", VideoFormat.short)
    conn.execute(
        "INSERT INTO studio.step_runs (id, video_id, step, attempt, status, input_hash, error_message) "
        "VALUES (%s, %s, 'script', 1, 'FAILED', 'hash', 'Falha <grave> no roteiro')",
        (uuid.uuid4().hex, v.id),
    )
    conn.commit()

    r = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Falha <grave>" not in r.text
    assert "Falha &lt;grave&gt;" in r.text


def test_video_detail_page_displays_unknown_cost_honestly(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Tema Custo Desconhecido", VideoFormat.short)
    conn.execute(
        "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
        "VALUES (%s, 'text', 'opencode', 'openai/gpt-4o-paid', 0.0)",
        (v.id,),
    )
    conn.commit()

    r = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "0.0000" not in r.text
    assert "0,0000" not in r.text
    assert "Não informado" in r.text or "sem custo informado" in r.text


def test_video_detail_page_displays_render_error(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Tema Render Error", VideoFormat.short)
    conn.execute(
        "INSERT INTO studio.render_jobs (id, video_id, status, attempt, input_hash, error) "
        "VALUES (%s, %s, 'FAILED', 1, 'h1', 'FFmpeg timeout gravíssimo')",
        (uuid.uuid4().hex, v.id),
    )
    conn.commit()

    r = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "FFmpeg timeout gravíssimo" in r.text


def test_panel_page_renders_topic_group_summary_and_cost(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    v1 = videos.create_video(p_id, "Tema Agrupado", VideoFormat.short)
    v2 = videos.create_video(p_id, "tema  agrupado!", VideoFormat.short)
    conn.execute(
        "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
        "VALUES (%s, 'text', 'opencode', 'gpt:free', 0.0)",
        (v1.id,),
    )
    conn.commit()

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Tema Agrupado" in r.text
    assert "US$ 0,00 (gratuito)" in r.text
    assert "<details" in r.text


def test_panel_page_renders_trending_topics_block(client_env):
    client = client_env["client"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)

    conn.execute(
        """
        INSERT INTO studio.trend_topics (
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, metric_name, metric_value, evidence
        ) VALUES (
            %s, %s, 'ADE Lineup 2026 Revelado', 'ade lineup 2026 revelado',
            'YouTube Data API', 'https://www.googleapis.com/youtube/v3/search',
            %s, %s, %s, 'views', 1200000,
            '[{"title": "Lineup Revelado <exclusivo>", "channel": "Cerc Music", "url": "https://youtube.com/watch?v=1", "views": 1200000}]'::jsonb
        )
        """,
        (uuid.uuid4().hex, p_id, now, past, now),
    )
    conn.commit()

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Temas em Alta" in r.text
    assert "ADE Lineup 2026 Revelado" in r.text
    assert "YouTube Data API" in r.text
    assert "Lineup Revelado &lt;exclusivo&gt;" in r.text
    assert "Lineup Revelado <exclusivo>" not in r.text




def test_panel_page_has_create_video_form_and_safe_script(client_env):
    client = client_env["client"]
    p_id = client_env["project_id"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert 'id="create-video-form"' in r.text
    assert 'maxlength="300"' in r.text
    assert p_id in r.text
    assert '<script nonce="' in r.text
    assert "innerHTML" not in r.text
    assert "eval(" not in r.text


def test_panel_page_trend_create_button_wires_to_form(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "btn-create-from-trend" in r.text or "new-video-topic" in r.text
    assert "btn-create-from-trend" in r.text


def test_panel_page_renders_category_pills_and_management_modal(client_env):
    client = client_env["client"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)

    cat_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO studio.project_categories (id, project_id, name, queries) VALUES (%s, %s, %s, %s)",
        (cat_id, p_id, "Tecnologia", ["IA", "ChatGPT"]),
    )
    conn.execute(
        """
        INSERT INTO studio.trend_topics (
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, metric_name, metric_value, evidence
        ) VALUES (
            %s, %s, 'Novidades de IA em 2026', 'novidades de ia em 2026',
            'YouTube Data API', 'https://www.googleapis.com/youtube/v3/search',
            %s, %s, %s, 'views', 500000,
            '[{"title": "IA Revoluciona Produção", "channel": "Tech Today", "url": "https://youtube.com/watch?v=2", "views": 500000}]'::jsonb
        )
        """,
        (uuid.uuid4().hex, p_id, now, past, now),
    )
    conn.commit()

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200

    # Pílulas de filtro
    assert "Todas (" in r.text
    assert "Tecnologia (" in r.text
    assert "+ Novo Pilar" in r.text or "btn-add-pillar" in r.text

    # Botões de ação do painel
    assert "Buscar Agora" in r.text
    assert "Gerenciar Categorias" in r.text

    # Modal de gerenciamento
    assert 'id="categories-modal"' in r.text
    assert 'id="form-category"' in r.text
    assert "btn-save-category" in r.text

    # Badge de categoria no item de tendência associado
    assert "Tecnologia" in r.text
    assert "data-category-id=" in r.text


def test_panel_page_category_xss_safety(client_env):
    client = client_env["client"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    cat_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO studio.project_categories (id, project_id, name, queries) VALUES (%s, %s, %s, %s)",
        (cat_id, p_id, "<script>alert('cat')</script>", ["<img src=x onerror=alert(2)>"]),
    )
    conn.commit()

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "<script>alert('cat')</script>" not in r.text
    assert "&lt;script&gt;alert(&#x27;cat&#x27;)&lt;/script&gt;" in r.text or "&lt;script&gt;alert('cat')&lt;/script&gt;" in r.text
    assert "<img src=x" not in r.text
    assert "innerHTML" not in r.text


def test_panel_page_empty_trends_still_shows_category_actions(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Buscar Agora" in r.text
    assert "Gerenciar Categorias" in r.text
    assert 'id="categories-modal"' in r.text


def test_panel_renders_youtube_themed_cards_and_video_links(client_env):
    client = client_env["client"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)

    # 1. Brasil trend with video and thumbnail
    conn.execute(
        """
        INSERT INTO studio.trend_topics (
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, metric_name, metric_value, evidence
        ) VALUES (
            %s, %s, 'Hit do Carnaval 2026', 'hit do carnaval 2026',
            'YouTube Brasil (Em Alta)', 'https://www.youtube.com/feed/trending',
            %s, %s, %s, 'views', 2500000,
            '[{"title": "Hit do Carnaval 2026", "channel": "Música BR", "url": "https://youtube.com/watch?v=br123", "views": 2500000, "published_at": "2026-11-19T12:00:00Z"}]'::jsonb
        )
        """,
        (uuid.uuid4().hex, p_id, now, past, now),
    )

    # 2. Global trend with video
    conn.execute(
        """
        INSERT INTO studio.trend_topics (
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, metric_name, metric_value, evidence
        ) VALUES (
            %s, %s, 'Global AI Breakthrough', 'global ai breakthrough',
            'YouTube Global (Em Alta)', 'https://www.youtube.com/feed/trending',
            %s, %s, %s, 'views', 10000000,
            '[{"title": "Global AI Breakthrough", "channel": "Tech World", "url": "https://youtube.com/watch?v=us456", "views": 10000000}]'::jsonb
        )
        """,
        (uuid.uuid4().hex, p_id, now, past, now),
    )

    # 3. Item without video evidence
    conn.execute(
        """
        INSERT INTO studio.trend_topics (
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, metric_name, metric_value, evidence
        ) VALUES (
            %s, %s, 'Manual Offline Topic <clean>', 'manual offline topic <clean>',
            'Curadoria Interna', 'https://example.com',
            %s, %s, %s, 'views', 5000, '[]'::jsonb
        )
        """,
        (uuid.uuid4().hex, p_id, now, past, now),
    )
    conn.commit()

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200

    # Attributes on trend items
    assert 'data-region="BR"' in r.text
    assert 'data-region="GLOBAL"' in r.text

    # Badges de regiao
    assert "🇧🇷 Em Alta Brasil" in r.text
    assert "🌍 Em Alta Mundo" in r.text

    # Thumbnails
    assert "https://i.ytimg.com/vi/br123/hqdefault.jpg" in r.text
    assert "https://i.ytimg.com/vi/us456/hqdefault.jpg" in r.text
    assert "trend-thumb" in r.text

    # Video links with target="_blank" and rel="noopener noreferrer"
    assert 'href="https://youtube.com/watch?v=br123"' in r.text
    assert 'target="_blank"' in r.text
    assert 'rel="noopener noreferrer"' in r.text

    # Channel & metadata
    assert "Música BR" in r.text
    assert "Tech World" in r.text
    assert "📺" in r.text

    # Action buttons
    assert "Assistir no YouTube" in r.text
    assert "btn-create-from-trend" in r.text

    # SVG placeholder fallback for item without video
    assert "trend-thumb-placeholder" in r.text or "<svg" in r.text

    # XSS safety
    assert "Manual Offline Topic &lt;clean&gt;" in r.text
    assert "Manual Offline Topic <clean>" not in r.text


def test_panel_youtube_card_escapes_xss_in_video_metadata(client_env):
    client = client_env["client"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)

    conn.execute(
        """
        INSERT INTO studio.trend_topics (
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, metric_name, metric_value, evidence
        ) VALUES (
            %s, %s, 'XSS Trend <script>alert(1)</script>', 'xss trend',
            'YouTube Brasil (Em Alta)', 'https://www.youtube.com/feed/trending',
            %s, %s, %s, 'views', 1000,
            '[{"title": "Video <bad>", "channel": "Bad <Channel>\\"", "url": "https://youtube.com/watch?v=test\\"onclick=\\"alert(2)", "views": 1000}]'::jsonb
        )
        """,
        (uuid.uuid4().hex, p_id, now, past, now),
    )
    conn.commit()

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    assert "Bad &lt;Channel&gt;&quot;" in r.text or "Bad &lt;Channel&gt;&#34;" in r.text
    assert 'onclick="alert(2)' not in r.text


def test_panel_page_has_loading_spinner_and_region_filters(client_env):
    client = client_env["client"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)

    # Insert a category
    cat_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO studio.project_categories (id, project_id, name, queries) VALUES (%s, %s, %s, %s)",
        (cat_id, p_id, "Inovação", ["IA"]),
    )

    # Insert a BR trend
    conn.execute(
        """
        INSERT INTO studio.trend_topics (
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, metric_name, metric_value, evidence
        ) VALUES (
            %s, %s, 'Tema Brasil Teste', 'tema brasil teste',
            'YouTube Brasil (Em Alta)', 'https://www.youtube.com/feed/trending',
            %s, %s, %s, 'views', 100000, '[]'::jsonb
        )
        """,
        (uuid.uuid4().hex, p_id, now, past, now),
    )

    # Insert a Global trend
    conn.execute(
        """
        INSERT INTO studio.trend_topics (
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, metric_name, metric_value, evidence
        ) VALUES (
            %s, %s, 'Global Topic Test', 'global topic test',
            'YouTube Global (Em Alta)', 'https://www.youtube.com/feed/trending',
            %s, %s, %s, 'views', 200000, '[]'::jsonb
        )
        """,
        (uuid.uuid4().hex, p_id, now, past, now),
    )
    conn.commit()

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200

    # 1. Pill Filters order & attributes
    assert 'data-filter-type="all"' in r.text
    assert '🔥 Todas (2)' in r.text
    assert 'data-filter-type="region" data-region-code="BR"' in r.text
    assert '🇧🇷 Em Alta Brasil (1)' in r.text
    assert 'data-filter-type="region" data-region-code="GLOBAL"' in r.text
    assert '🌍 Em Alta Mundo (1)' in r.text
    assert 'data-filter-type="category"' in r.text
    assert f'data-cat-id="{cat_id}"' in r.text
    assert '🏷️ Inovação (0)' in r.text
    assert 'id="btn-open-categories-modal"' in r.text
    assert '+ Novo Pilar' in r.text

    # 2. UX Loading Spinner on Buscar Agora
    assert '.spinner-inline' in r.text
    assert '@keyframes spin' in r.text
    assert 'Consultando YouTube...' in r.text
    assert 'btn-refresh-trends' in r.text

    # 3. Smooth Action on Criar Vídeo deste Tema
    assert 'btn-create-from-trend' in r.text
    assert 'data-topic="Tema Brasil Teste"' in r.text
    assert 'topic-pulse' in r.text
    assert '@keyframes topicPulse' in r.text

    # 4. Strict CSP & XSS safety
    assert 'innerHTML' not in r.text





