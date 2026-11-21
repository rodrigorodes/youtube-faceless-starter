import base64
import re
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
    csp = r.headers["Content-Security-Policy"]
    assert "nonce-" in csp
    assert "https://i.ytimg.com" in csp
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
    assert "Desconhecido" in r.text
    assert "US$ 0,00" not in r.text


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
    assert "Sem custo" in r.text
    assert "US$ 0,00" not in r.text
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

    # IA-01: a lista de tendências vive na tela Tendências (/studio/panel/tendencias).
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
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
    # IA-01: o botão «Criar Vídeo deste Tema» vive na tela Tendências; o formulário para onde ele
    # leva (com o tema pré-preenchido) vive no Início — o destino real é coberto em
    # test_panel_ia01_trend_create_link_prefills_the_home_topic.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "btn-create-from-trend" in r.text
    home = client.get("/studio/panel", headers=AUTH_HEADER)
    assert home.status_code == 200
    assert 'id="create-video-form"' in home.text and 'id="topic"' in home.text


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

    # IA-01: pílulas de filtro e gestão de pilares vivem na tela Tendências.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
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

    # IA-01: os pilares (e o rótulo da categoria) aparecem na tela Tendências.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "<script>alert('cat')</script>" not in r.text
    assert "&lt;script&gt;alert(&#x27;cat&#x27;)&lt;/script&gt;" in r.text or "&lt;script&gt;alert('cat')&lt;/script&gt;" in r.text
    assert "<img src=x" not in r.text
    assert "innerHTML" not in r.text


def test_panel_page_empty_trends_still_shows_category_actions(client_env):
    client = client_env["client"]
    # IA-01: as ações de coleta e pilares (mesmo sem tendências) ficam na tela Tendências.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
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

    # 2. Legacy trend with unknown region
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

    # IA-01: os cartões de tendência vivem na tela Tendências.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r.status_code == 200

    # Attributes on trend items
    assert 'data-region="BR"' in r.text
    assert 'data-region="UNKNOWN"' in r.text

    # Badges de regiao
    assert "🇧🇷 Em Alta Brasil" in r.text
    assert "Origem desconhecida" in r.text
    assert "Em Alta Mundo" not in r.text

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

    # IA-01: metadados de tendência são renderizados na tela Tendências.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
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

    # Insert a legacy trend with unknown region
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

    # IA-01: filtros de região/pilar, spinner e «Criar Vídeo deste Tema» ficam na tela Tendências.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r.status_code == 200

    # 1. Pill Filters order & attributes
    assert 'data-filter-type="all"' in r.text
    assert '🔥 Todas (2)' in r.text
    assert 'data-filter-type="region" data-region-code="BR"' in r.text
    assert '🇧🇷 Em Alta Brasil (1)' in r.text
    assert 'data-filter-type="region" data-region-code="UNKNOWN"' in r.text
    assert 'Origem desconhecida (1)' in r.text
    assert 'Em Alta Mundo' not in r.text
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


def test_panel_uses_dark_mockup_palette_and_preview_stays_dark(client_env):
    # Paleta única (tokens aprovados do mockup, G1) para o painel e para a prévia:
    # a casca compartilhada é a fonte de verdade do CSS.
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "color-scheme: dark" in r.text
    assert "--bg-canvas: #101827" in r.text
    assert "--surface: #131b2d" in r.text
    assert "--accent: #7c3aed" in r.text
    assert "prefers-color-scheme" not in r.text
    assert "#0b111e" not in r.text  # no navy blue tint
    assert "#0b0f17" not in r.text

    # A prévia não tem paleta própria: usa a mesma casca escura do painel.
    import app.studio.api.preview as preview
    assert not hasattr(preview, "CSS"), "a prévia não deve manter CSS/paleta próprios"
    v = client_env["videos"].create_video(client_env["project_id"], "Preview Palette Video", VideoFormat.short)
    preview_page = client.get(f"/studio/videos/{v.id}/preview", headers=AUTH_HEADER).text
    assert "--bg-canvas: #101827" in preview_page
    assert "--surface: #131b2d" in preview_page
    assert "--bg: #0f0f0f" not in preview_page
    assert "--surface: #181818" not in preview_page


def test_panel_has_project_selector_and_create_project_modal(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    p_id_1 = client_env["project_id"]
    p2 = videos.create_project("Canal Secundário", niche="Curiosidades", language="en-US")
    p_id_2 = p2.id

    # 1. Default request selects first project
    r1 = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r1.status_code == 200
    assert 'id="global-project-select"' in r1.text
    assert 'id="btn-open-project-modal"' in r1.text
    assert 'id="project-modal"' in r1.text
    assert 'role="dialog"' in r1.text
    assert 'aria-modal="true"' in r1.text
    assert 'aria-labelledby="modal-project-title"' in r1.text
    assert 'id="btn-save-project"' in r1.text
    assert 'id="project-form-feedback"' in r1.text
    assert 'value="pt-BR"' in r1.text
    assert 'value="en-US"' in r1.text
    assert 'value="es-ES"' in r1.text

    # Default project (p_id_1) is selected
    assert f'<option value="{p_id_1}" selected>' in r1.text

    # 2. Specifying project_id selects project 2
    r2 = client.get(f"/studio/panel?project_id={p_id_2}", headers=AUTH_HEADER)
    assert r2.status_code == 200
    assert f'<option value="{p_id_2}" selected>' in r2.text

    # Both global selector and new-video-project have selected attribute
    assert r2.text.count(f'value="{p_id_2}" selected') >= 2


def test_panel_renders_workflow_funnel_and_modern_video_cards(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Workflow Modern Cards Video", VideoFormat.short)
    # IA-01: o funil de produção vive na tela Produção (/studio/panel/producao)...
    r_prod = client.get("/studio/panel/producao", headers=AUTH_HEADER)
    assert r_prod.status_code == 200

    # Funnel cards with colored borders
    assert '<div class="grid-summary">' in r_prod.text
    assert "border-left: 4px solid var(--info)" in r_prod.text or "border-left: 4px solid #38bdf8" in r_prod.text
    assert "border-left: 4px solid var(--warn)" in r_prod.text or "border-left: 4px solid #fbbf24" in r_prod.text
    assert "border-left: 4px solid var(--ok)" in r_prod.text or "border-left: 4px solid #4ade80" in r_prod.text
    assert "border-left: 4px solid var(--accent)" in r_prod.text
    assert "Jobs de render/áudio ativos" in r_prod.text
    assert "Exigem revisão humana" in r_prod.text
    assert "Concluídos / Publicados" in r_prod.text or "CONCLUÍDOS / PUBLICADOS" in r_prod.text

    # ...e os cartões modernos de vídeo continuam no Início, no bloco Vídeos.
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "video-sample-card" in r.text
    assert "video-thumb-sample" in r.text
    assert "Workflow Modern Cards Video" in r.text
    assert "Short" in r.text
    assert "Ver Progresso" in r.text


def test_preview_page_has_unified_sidebar_layout(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Preview Sidebar Video", VideoFormat.short)
    conn.execute(
        "UPDATE studio.videos SET status = 'AWAITING_APPROVAL' WHERE id = %s",
        (v.id,),
    )
    conn.commit()

    r = client.get(f"/studio/videos/{v.id}/preview", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert '<aside class="sidebar" aria-label="Barra lateral">' in r.text
    assert '<div class="app-layout">' in r.text
    assert '<main class="main-content">' in r.text
    assert "Faceless Studio V2" in r.text and "YouTube Automation" in r.text

    # A navegação renderizada na prévia é a mesma casca das outras telas do painel.
    items = _nav_items(r.text)
    labels = [" ".join(re.sub(r"<[^>]+>", " ", item).split()) for item in items]
    for expected in ("Início", "Produção", "Tendências", "Vídeos", "Canais", "Analytics", "Estilos", "Equipe"):
        assert any(expected in label for label in labels), expected
    active = [item for item in items if 'aria-current="page"' in item]
    assert len(active) == 1 and "Vídeos" in " ".join(re.sub(r"<[^>]+>", " ", active[0]).split())
    # IA-01: "Vídeos" aponta para a rota real (302 → bloco #videos do Início).
    assert 'href="/studio/panel/videos"' in r.text
    assert 'href="/docs"' in r.text
    assert 'href="http://localhost:5678"' in r.text

    # Conteúdo da prévia intacto.
    assert "Painel / Prévia do Vídeo" in r.text
    assert "Voltar ao Painel" in r.text

    # O template antigo (marca, navegação e CTA) não pode voltar.
    for stale in ("FACELESS STUDIO", "Pipeline de Vídeos", "Temas em Alta", "+ Novo Vídeo"):
        assert stale not in r.text, stale


def test_panel_trends_has_compact_expansion_toggle(client_env):
    client = client_env["client"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)

    # Insert 8 trends (more than 6)
    for i in range(8):
        conn.execute(
            """
            INSERT INTO studio.trend_topics (
                id, project_id, topic, topic_key, source_name, source_url,
                observed_at, window_start, window_end, metric_name, metric_value, evidence
            ) VALUES (
                %s, %s, %s, %s,
                'YouTube Brasil (Em Alta)', 'https://www.youtube.com/feed/trending',
                %s, %s, %s, 'views', %s, '[]'::jsonb
            )
            """,
            (uuid.uuid4().hex, p_id, f"Trend Topic {i}", f"trend topic {i}", now, past, now, 100000 - i * 1000),
        )
    conn.commit()

    # IA-01: o comportamento de expansão compacta pertence à tela Tendências.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r.status_code == 200

    # Toggle button and expansion bar presence
    assert 'id="btn-toggle-more-trends"' in r.text
    assert 'data-expanded="false"' in r.text
    assert 'data-total="8"' in r.text
    assert "Ver Mais Tendências (+2)" in r.text
    assert "trends-expansion-bar" in r.text

    # Compact initial display: first 6 visible, last 2 with extra class and display: none
    assert "trend-item-extra" in r.text
    assert r.text.count('class="trend-item trend-item-extra"') == 2
    assert 'class="trend-item trend-item-extra" style="display: none;"' in r.text

    # Client-side script includes toggle logic
    assert "btn-toggle-more-trends" in r.text
    assert "Recolher Tendências" in r.text
    assert "scrollIntoView" in r.text
    assert "innerHTML" not in r.text

    # Verify that when <= 6 trends exist, toggle button is not rendered and all items are visible
    conn.execute("DELETE FROM studio.trend_topics WHERE project_id = %s", (p_id,))
    for i in range(4):
        conn.execute(
            """
            INSERT INTO studio.trend_topics (
                id, project_id, topic, topic_key, source_name, source_url,
                observed_at, window_start, window_end, metric_name, metric_value, evidence
            ) VALUES (
                %s, %s, %s, %s,
                'YouTube Brasil (Em Alta)', 'https://www.youtube.com/feed/trending',
                %s, %s, %s, 'views', %s, '[]'::jsonb
            )
            """,
            (uuid.uuid4().hex, p_id, f"Few Trend {i}", f"few trend {i}", now, past, now, 50000),
        )
    conn.commit()

    r_few = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r_few.status_code == 200
    assert 'id="btn-toggle-more-trends"' not in r_few.text
    assert 'class="trend-item trend-item-extra"' not in r_few.text











def _nav_items(html: str):
    match = re.search(r'<nav class="nav" aria-label="Principal">(.*?)</nav>', html, re.S)
    assert match is not None, "navegação principal ausente"
    return re.findall(r"<li>(.*?)</li>", match.group(1), re.S)


def _page_text(html: str) -> str:
    without_regions = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", without_regions).split())


def test_panel_shell_sidebar_marks_one_active_item_and_has_no_unavailable_ones(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    items = _nav_items(r.text)
    labels = [" ".join(re.sub(r"<[^>]+>", " ", item).split()) for item in items]

    for expected in ("Início", "Produção", "Tendências", "Vídeos", "Canais", "Analytics", "Estilos", "Equipe"):
        assert any(expected in label for label in labels), expected

    active = [item for item in items if 'aria-current="page"' in item]
    assert len(active) == 1 and "Início" in " ".join(re.sub(r"<[^>]+>", " ", active[0]).split())
    assert r.text.count('aria-current="page"') == 1

    # Estilos virou destino real (biblioteca compartilhada); nenhum item indisponível na casca.
    assert not any('aria-disabled="true"' in item for item in items)
    estilos = next(item for item in items if "Estilos" in " ".join(re.sub(r"<[^>]+>", " ", item).split()))
    assert 'href="/studio/panel/estilos"' in estilos
    assert not estilos.lstrip().startswith("<span ")

    # IA-01: Início/Produção/Tendências/Vídeos são rotas de servidor reais, não âncoras de uma página.
    for label, href in (("Início", "/studio/panel"), ("Produção", "/studio/panel/producao"),
                        ("Tendências", "/studio/panel/tendencias"), ("Vídeos", "/studio/panel/videos"),
                        ("Canais", "/studio/canais"),
                        ("Analytics", "/studio/panel/analytics")):
        item = next(item for item in items if label in " ".join(re.sub(r"<[^>]+>", " ", item).split()))
        assert f'href="{href}"' in item


def test_panel_shell_does_not_invent_product_or_execution_state(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    visible = _page_text(r.text)

    for forbidden in ("Implementado", "Plano Pro", "créditos/mês", "Gerando imagens", "62%",
                      "Rodrigo Dev", "Ana Costa", "Carlos Lima", "Mariana Alves", "Administrador",
                      "Docker Local", "Saudável", "Como a OpenAI ganha dinheiro?", "1,2 mi views",
                      "890 mil views", "650 mil views", "US$ 0,07", "US$ 0,05", "run_7f3a", "vid_2b91",
                      "9f2c", "Agentes de IA na prática", "Faber"):
        assert forbidden not in visible
    assert re.search(r"\d+(?:[.,]\d+)?\s*%", visible) is None


def test_panel_empty_production_state_is_explicit_without_fake_progress(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Nenhuma execução registrada" in r.text
    assert 'role="progressbar"' not in r.text
    assert "<progress" not in r.text
    assert 'class="budget-fill"' not in r.text
    assert "0%" not in _page_text(r.text)


def test_panel_shell_preserves_sections_and_trend_filter_contract(client_env):
    client = client_env["client"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=7)

    for i in range(8):
        conn.execute(
            """
            INSERT INTO studio.trend_topics (
                id, project_id, topic, topic_key, source_name, source_url,
                observed_at, window_start, window_end, metric_name, metric_value, evidence
            ) VALUES (%s, %s, %s, %s, 'YouTube Brasil (Em Alta)',
                      'https://www.youtube.com/feed/trending', %s, %s, %s, 'views', %s, '[]'::jsonb)
            """,
            (uuid.uuid4().hex, p_id, f"Tema {i}", f"tema {i}", now, past, now, 1000 - i),
        )
    conn.commit()

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    # IA-01: o Início publica só as suas seções; Produção e Tendências viraram telas próprias.
    for section_id in ("inicio-section", "inicio-producao-section", "precisa-section",
                       "inicio-tendencias-section", "videos", "new-video-section"):
        assert f'id="{section_id}"' in r.text
    assert 'id="producao-section"' not in r.text
    assert 'id="trending-section"' not in r.text
    assert r.text.count("<h1") == 1

    # O contrato de filtro de tendências mudou de página: agora é da tela Tendências.
    r_trend = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r_trend.status_code == 200
    assert '<button type="button" class="cat-pill active" data-filter-type="all" aria-pressed="true">🔥 Todas (8)</button>' in r_trend.text
    assert 'data-filter-type="region" data-region-code="BR" aria-pressed="false"' in r_trend.text
    assert "🇧🇷 Em Alta Brasil (8)" in r_trend.text
    assert "Ver Mais Tendências (+2)" in r_trend.text
    assert "trend-item-extra" in r_trend.text
    assert "Fontes (todas as tendências):" in r_trend.text


def test_panel_shell_escapes_trend_topic_and_source(client_env):
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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'views', 1, '[]'::jsonb)
        """,
        (uuid.uuid4().hex, p_id, "<script>alert('topic')</script>", "xss source",
         "<script>alert('source')</script>", "https://example.com/?q=<script>",
         now, past, now),
    )
    conn.commit()

    # IA-01: o tema e a origem da tendência aparecem (escapados) na tela Tendências.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "<script>alert" not in r.text
    assert "&lt;script&gt;alert(&#x27;topic&#x27;)&lt;/script&gt;" in r.text
    assert "&lt;script&gt;alert(&#x27;source&#x27;)&lt;/script&gt;" in r.text
    assert "https://example.com/?q=&lt;script&gt;" in r.text


def test_panel_costs_are_labeled_and_absence_is_not_zero(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    def ledger(video_id, provider, model, cost_usd, kind):
        if kind is None:
            conn.execute(
                "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
                "VALUES (%s, 'text', %s, %s, %s)",
                (video_id, provider, model, cost_usd),
            )
        else:
            conn.execute(
                "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd, "
                "cost_confirmation_kind, cost_confirmed_amount, cost_confirmation_reference, "
                "cost_confirmed_by, cost_confirmed_at) "
                "VALUES (%s, 'text', %s, %s, %s, %s, %s, 'ref', 'tester', now())",
                (video_id, provider, model, cost_usd, kind, cost_usd),
            )

    paid = videos.create_video(p_id, "Custo Pago", VideoFormat.short)
    ledger(paid.id, "opencode", "gpt-paid", 0.5, "ACTUAL")
    estimated = videos.create_video(p_id, "Custo Estimado", VideoFormat.short)
    ledger(estimated.id, "opencode", "gpt-est", 0.25, "ESTIMATE")
    free = videos.create_video(p_id, "Custo Gratuito", VideoFormat.short)
    ledger(free.id, "opencode", "gpt:free", 0.0, "FREE")
    unknown = videos.create_video(p_id, "Custo Desconhecido", VideoFormat.short)
    ledger(unknown.id, "opencode", "gpt-4o-paid", 0.0, None)
    conn.commit()

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Real US$ 0,50" in r.text
    assert "Estimado US$ 0,25" in r.text
    assert "Sem custo" in r.text
    assert "Desconhecido" in r.text
    # Real e estimado nunca são fundidos, e gratuidade/desconhecido nunca viram zero.
    assert "US$ 0,75" not in r.text
    assert "US$ 0,00" not in r.text


def test_video_detail_page_labels_each_call_kind(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Uso por Chamada", VideoFormat.short)
    rows = [
        ("text", "opencode", "gpt-paid", 0.07, "ACTUAL"),
        ("image", "opencode", "gpt-est", 0.05, "ESTIMATE"),
        ("voice", "piper", "piper", 0.0, "FREE"),
    ]
    for step, provider, model, cost, kind in rows:
        conn.execute(
            "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd, "
            "cost_confirmation_kind, cost_confirmed_amount, cost_confirmation_reference, "
            "cost_confirmed_by, cost_confirmed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'ref', 'tester', now())",
            (v.id, step, provider, model, cost, kind, cost),
        )
    conn.execute(
        "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
        "VALUES (%s, 'render', 'opencode', 'gpt-4o-paid', 0.0)",
        (v.id,),
    )
    conn.commit()

    r = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    advanced_area = r.text.split('id="advanced-diagnostics"', 1)[1]
    assert "Real: US$ 0,07" in advanced_area
    assert "Estimado: US$ 0,05" in advanced_area
    assert "Sem custo" in advanced_area
    assert "Desconhecido" in advanced_area
    assert "US$ 0,00" not in advanced_area


def test_panel_month_rail_labels_four_cost_categories(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Rail de Custo", VideoFormat.short)
    rows = [
        ("text", "opencode", "gpt-paid", 0.07, "ACTUAL"),
        ("image", "opencode", "gpt-est", 0.05, "ESTIMATE"),
        ("voice", "piper", "piper", 0.0, "FREE"),
    ]
    for step, provider, model, cost, kind in rows:
        conn.execute(
            "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd, "
            "cost_confirmation_kind, cost_confirmed_amount, cost_confirmation_reference, "
            "cost_confirmed_by, cost_confirmed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'ref', 'tester', now())",
            (v.id, step, provider, model, cost, kind, cost),
        )
    conn.execute(
        "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
        "VALUES (%s, 'render', 'opencode', 'gpt-4o-paid', 0.0)",
        (v.id,),
    )
    conn.commit()

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    rail = r.text.split('aria-labelledby="h-custo"', 1)[1].split('aria-labelledby="h-falha"', 1)[0]
    assert "Real</span><span>US$ 0,07" in rail
    assert "Estimado</span><span>US$ 0,05" in rail
    assert "Sem custo</span><span>1 chamada(s)" in rail
    assert "Desconhecido</span><span>1 chamada(s)" in rail
    assert "US$ 0,12" not in rail  # sem número único que funda real e estimado
    assert "US$ 0,00" not in rail


def test_panel_absence_of_cost_is_not_rendered_as_zero(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    p_id = client_env["project_id"]
    videos.create_video(p_id, "Sem Uso Registrado", VideoFormat.short)

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "sem registro de uso" in r.text
    assert "US$ 0,00" not in r.text


def test_panel_has_closed_advanced_diagnostics(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    match = re.search(r'<details class="[^"]*advanced[^"]*" id="advanced-diagnostics"([^>]*)>', r.text)
    assert match is not None
    assert "open" not in match.group(1)
    assert "Avançado — diagnóstico" in r.text


def test_panel_declares_viewport_and_responsive_media_query(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert 'name="viewport"' in r.text
    assert "@media (max-width: 820px)" in r.text


def test_video_detail_hides_invalid_approval_and_keeps_diagnostics_collapsed(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Vídeo Sem Render", VideoFormat.short)
    conn.execute(
        "INSERT INTO studio.step_runs (id, video_id, step, attempt, status, input_hash, error_message) "
        "VALUES (%s, %s, 'render', 1, 'FAILED', 'hash', 'Traceback (most recent call last): boom')",
        (uuid.uuid4().hex, v.id),
    )
    conn.execute(
        "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
        "VALUES (%s, 'text', 'opencode', 'gpt-4o-paid', 0.0)",
        (v.id,),
    )
    conn.commit()

    r = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Aprovar" not in r.text
    main_area = r.text.split('id="advanced-diagnostics"', 1)[0]
    assert "Traceback" not in main_area
    assert "Passo de correção" in main_area

    match = re.search(r'<details class="[^"]*advanced[^"]*" id="advanced-diagnostics"([^>]*)>', r.text)
    assert match is not None and "open" not in match.group(1)
    advanced_area = r.text.split('id="advanced-diagnostics"', 1)[1]
    assert "Registro de Uso de Modelos" in advanced_area
    assert "Desconhecido" in advanced_area
    assert "Traceback" in advanced_area


def test_panel_page_matches_approved_mockup_shell(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200

    assert 'class="hero"' in r.text
    assert 'id="hero-heading"' in r.text
    assert 'role="tablist"' in r.text
    serie = re.search(r'<button[^>]*id="tab-serie"[^>]*>', r.text)
    assert serie is not None
    assert 'aria-disabled="true"' in serie.group(0)
    assert 'tabindex="-1"' in serie.group(0)

    for group in ("Operação", "Gestão"):
        assert group in r.text
    for rail in ("Custo do mês", "Estado das fases", "Última falha"):
        assert rail in r.text
    assert "F8 Publicação" in r.text and "F11 SaaS" in r.text

    visible = _page_text(r.text)
    for step in ("Roteiro", "Fontes", "Fact-check", "Cenas", "Voz", "Render", "QA", "Publicação"):
        assert step in visible
    assert "Não há percentual" in visible


# ---------- PROD-01: cartão de fontes e iniciar/retomar na página do vídeo ----------


def test_video_detail_page_has_sources_card_and_start_control(client_env):
    client, videos, p_id = client_env["client"], client_env["videos"], client_env["project_id"]
    v = videos.create_video(p_id, "Vídeo sem run", VideoFormat.short)
    r = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert 'id="video-fontes"' in r.text
    assert 'id="source-url"' in r.text and 'id="source-text"' in r.text
    assert 'id="btn-start-production"' in r.text
    assert 'id="btn-retry-production"' not in r.text


def test_video_detail_page_shows_the_real_failure_reason_and_retry(client_env):
    client, videos, conn = client_env["client"], client_env["videos"], client_env["conn"]
    p_id = client_env["project_id"]
    v = videos.create_video(p_id, "Vídeo com run falho", VideoFormat.short)
    run_id = "c" * 32
    conn.execute("INSERT INTO studio.production_runs(run_id, video_id, idempotency_key, state, reason) "
                 "VALUES (%s, %s, 'req-panel-failed-1', 'FAILED', 'roteiro falhou')", (run_id, v.id))
    conn.execute("INSERT INTO studio.stage_executions(run_id, stage_id, state, attempt, error) "
                 "VALUES (%s, 'script', 'FAILED', 1, %s)",
                 (run_id, "no sources with checkable claims: add sources first"))
    conn.commit()

    r = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert 'id="btn-retry-production"' in r.text
    assert 'id="btn-start-production"' not in r.text
    assert "no sources with checkable claims: add sources first" in r.text


def test_video_detail_page_lists_registered_sources(client_env):
    client, videos, p_id = client_env["client"], client_env["videos"], client_env["project_id"]
    v = videos.create_video(p_id, "Vídeo com fonte", VideoFormat.short)
    added = client.post(f"/studio/videos/{v.id}/sources",
                        json={"url": "https://amsterdam-dance-event.nl/en/about",
                              "text": "Amsterdam Dance Event reúne mais de 3.600 artistas."},
                        headers={**AUTH_HEADER, "Origin": "http://testserver"})
    assert added.status_code == 201
    r = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "amsterdam-dance-event.nl/en/about" in r.text
    assert "caractere" in r.text


# ---------- IA-01: Início, Produção e Tendências como telas separadas ----------


def test_panel_ia01_each_route_renders_only_its_own_section(client_env):
    """IA-01: três rotas de servidor reais; cada uma devolve **só** a sua tela."""
    client = client_env["client"]
    inicio = client.get("/studio/panel", headers=AUTH_HEADER)
    producao = client.get("/studio/panel/producao", headers=AUTH_HEADER)
    tendencias = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    for r in (inicio, producao, tendencias):
        assert r.status_code == 200

    # Cada tela tem a sua própria seção...
    assert 'id="inicio-section"' in inicio.text
    assert 'id="precisa-section"' in inicio.text
    assert 'id="videos"' in inicio.text
    assert 'id="producao-section"' in producao.text
    assert 'id="trending-section"' in tendencias.text

    # ...e o HTML completo de uma tela nunca aparece dentro da outra.
    assert 'id="producao-section"' not in inicio.text
    assert 'id="trending-section"' not in inicio.text
    assert '<div class="grid-summary">' not in inicio.text
    assert '<div class="card trends-card">' not in inicio.text
    assert 'id="inicio-section"' not in producao.text
    assert 'id="trending-section"' not in producao.text
    assert '<div class="card trends-card">' not in producao.text
    assert 'id="inicio-section"' not in tendencias.text
    assert 'id="producao-section"' not in tendencias.text
    assert '<div class="grid-summary">' not in tendencias.text

    # Exatamente um aria-current="page" por página, no item certo da nav.
    for r, label in ((inicio, "Início"), (producao, "Produção"), (tendencias, "Tendências")):
        assert r.text.count('aria-current="page"') == 1
        active = next(item for item in _nav_items(r.text) if 'aria-current="page"' in item)
        assert label in re.sub(r"<[^>]+>", " ", active)


def test_panel_ia01_videos_route_redirects_to_the_home_videos_block(client_env):
    """IA-01: "Vídeos" não é tela própria — a rota real redireciona para o bloco #videos do Início."""
    client = client_env["client"]
    r = client.get("/studio/panel/videos", headers=AUTH_HEADER, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/studio/panel#videos"
    # A rota é privada como as demais telas do painel.
    assert client.get("/studio/panel/videos", follow_redirects=False).status_code == 401


def test_panel_ia01_producao_and_tendencias_are_isolated_from_the_home(client_env):
    """O Início mostra resumo; o quadro completo de Produção/Tendências não vaza para ele."""
    client = client_env["client"]
    videos = client_env["videos"]
    p_id = client_env["project_id"]
    videos.create_video(p_id, "Vídeo para funil", VideoFormat.short)

    inicio = client.get("/studio/panel", headers=AUTH_HEADER)
    producao = client.get("/studio/panel/producao", headers=AUTH_HEADER)
    assert inicio.status_code == 200 and producao.status_code == 200

    # O funil completo (grid-summary + status por fase) fica só em Produção...
    assert '<div class="grid-summary">' in producao.text
    assert "Status por fase" in producao.text
    assert '<div class="grid-summary">' not in inicio.text
    # ...e o Início traz o resumo de produção, com link para a tela cheia.
    assert 'href="/studio/panel/producao"' in inicio.text
    assert "Ver Produção" in inicio.text


def test_panel_ia01_trend_create_link_prefills_the_home_topic(client_env):
    """O «Criar Vídeo deste Tema» (Tendências) leva o tema pré-preenchido para o Início."""
    import html as html_module

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
        ) VALUES (%s, %s, %s, %s, 'YouTube Brasil (Em Alta)',
                  'https://www.youtube.com/feed/trending', %s, %s, %s, 'views', 1000, '[]'::jsonb)
        """,
        (uuid.uuid4().hex, p_id, "Tema com Acento & Cia", "tema com acento", now, past, now),
    )
    conn.commit()

    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r.status_code == 200
    match = re.search(
        r'class="btn btn-primary btn-create-from-trend"[^>]*href="([^"]+)"', r.text
    )
    assert match is not None, "botão «Criar Vídeo deste Tema» sem destino real"
    href = html_module.unescape(match.group(1))
    assert href.startswith("/studio/panel?topic=")
    assert "project_id=" in href and "days=7" in href

    # O Início trata o parâmetro: o tema chega pré-preenchido (e escapado) no formulário.
    home = client.get(href, headers=AUTH_HEADER)
    assert home.status_code == 200
    assert 'value="Tema com Acento &amp; Cia"' in home.text
