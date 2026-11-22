import base64
import json
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
    # UX V3: o vazio do Início diz o próximo passo em vez de só constatar a ausência.
    assert "Nenhum vídeo ainda" in r.text
    assert "Descreva um tema acima para criar o primeiro" in r.text


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


def test_video_pages_show_the_owner_channel(client_env):
    """W1.2 (R6): as páginas do vídeo mostram o **canal dono** em leitura, não a casca vazia.

    Trocar de canal ativo não move o vídeo (`active_channel.py`), então a página do vídeo precisa
    dizer de quem ele é — antes a casca ia com `projects=[]` e exibia "Nenhum canal cadastrado".
    """
    client, videos = client_env["client"], client_env["videos"]
    other = videos.create_project("Canal B", niche="História")
    video = videos.create_video(other.id, "Tema do canal B", VideoFormat.short)
    for path in (f"/studio/panel/videos/{video.id}",
                 f"/studio/videos/{video.id}/roteiro",
                 f"/studio/videos/{video.id}/preview"):
        response = client.get(path, headers=AUTH_HEADER)
        assert response.status_code == 200, path
        assert "Canal B" in response.text, path
        assert 'id="sem-canal"' not in response.text, path


def test_video_area_routes_are_real_and_old_routes_still_work(client_env):
    """W1.4 (UX-03): cada área do vídeo é uma rota de servidor; as rotas antigas seguem válidas.

    A navegação é por **links** com `aria-current="page"` exato na área ativa (sem SPA nem JS de
    abas) e cada área é uma leitura sobre o que o core já tem.
    """
    client, videos = client_env["client"], client_env["videos"]
    project = videos.create_project("Canal Áreas", niche="História")
    video = videos.create_video(project.id, "Tema das áreas", VideoFormat.short)

    for area in ("visao-geral", "fontes", "narracao", "cenas", "composicao", "qualidade",
                 "publicacao", "producao"):
        response = client.get(f"/studio/panel/videos/{video.id}/{area}", headers=AUTH_HEADER)
        assert response.status_code == 200, area
        assert '<nav class="abas-video" aria-label="Áreas do vídeo">' in response.text, area
        assert f'href="/studio/panel/videos/{video.id}/{area}" aria-current="page"' in response.text, area

    # As rotas antigas continuam existindo e funcionando.
    for path in (f"/studio/panel/videos/{video.id}",
                 f"/studio/videos/{video.id}/roteiro",
                 f"/studio/videos/{video.id}/preview",
                 f"/studio/panel/videos/{video.id}/production-runs"):
        assert client.get(path, headers=AUTH_HEADER).status_code == 200, path

    # Área desconhecida não quebra: cai na Visão geral (a nav marca a área padrão).
    unknown = client.get(f"/studio/panel/videos/{video.id}/nao-existe", headers=AUTH_HEADER)
    assert unknown.status_code == 200
    assert f'href="/studio/panel/videos/{video.id}/visao-geral" aria-current="page"' in unknown.text


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
    # UX V3: o título da tela é "Tendências" e o cartão mostra a origem real da coleta.
    assert "Tendências</h1>" in r.text
    assert "ADE Lineup 2026 Revelado" in r.text
    assert "YouTube Data API" in r.text
    assert "Não informada" in r.text  # ausência de região é dita, não inventada




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

    # Pílulas de filtro (UX V3: `chip-filtro` + `data-filtro`).
    assert "Todas (" in r.text
    assert "Tecnologia (" in r.text
    assert f'data-filtro="pilar:{cat_id}"' in r.text
    assert "+ Novo pilar" in r.text or 'id="btn-novo-pilar"' in r.text

    # Botões de ação do painel
    assert "Buscar agora" in r.text
    assert "Gerenciar pilares" in r.text

    # Diálogo de gerenciamento
    assert 'id="dialog-pilares"' in r.text
    assert 'id="form-pilar"' in r.text
    assert "btn-salvar-pilar" in r.text

    # Badge de pilar no cartão de tendência associado
    assert "Pilar: Tecnologia" in r.text
    assert f'data-pilar="{cat_id}"' in r.text


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
    assert "Buscar agora" in r.text
    assert "Gerenciar pilares" in r.text
    assert 'id="dialog-pilares"' in r.text


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

    # Attributes on trend items (UX V3: `data-regiao`).
    assert 'data-regiao="BR"' in r.text
    assert 'data-regiao="UNKNOWN"' in r.text

    # Região é dita em texto; origem global não vira "Em Alta Mundo" inventado.
    assert "Brasil" in r.text
    assert "Origem desconhecida" in r.text
    assert "Em Alta Mundo" not in r.text

    # Vídeo base com link real e seguro (sem thumbnail próprio na V3).
    assert 'href="https://youtube.com/watch?v=br123"' in r.text
    assert 'href="https://youtube.com/watch?v=us456"' in r.text
    assert 'target="_blank"' in r.text
    assert 'rel="noopener noreferrer"' in r.text

    # Canal e metadados reais da evidência
    assert "Música BR" in r.text
    assert "Tech World" in r.text

    # Ação real de criar vídeo a partir do tema
    assert "Criar vídeo deste tema" in r.text
    assert 'data-usar-tendencia="Hit do Carnaval 2026"' in r.text

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

    # 1. Pílulas de filtro (UX V3: `chip-filtro` + `data-filtro`)
    assert 'data-filtro="todas"' in r.text
    assert 'Todas (2)' in r.text
    assert 'data-filtro="regiao:BR"' in r.text
    assert 'Em Alta Brasil (1)' in r.text
    assert 'data-filtro="regiao:US"' in r.text
    assert 'Em Alta EUA (0)' in r.text
    assert 'Em Alta Mundo' not in r.text
    assert 'Origem desconhecida' in r.text  # a tendência sem região continua visível
    assert f'data-filtro="pilar:{cat_id}"' in r.text
    assert 'Inovação (0)' in r.text
    assert 'id="btn-novo-pilar"' in r.text
    assert '+ Novo pilar' in r.text

    # 2. Feedback de carregamento real (indicador da casca + texto do botão)
    assert 'id="indicador-carregando"' in r.text and 'aria-live="polite"' in r.text
    assert 'btn-refresh-trends' in r.text
    assert "↻ Buscando…" in r.text

    # 3. «Criar vídeo deste tema» leva o tema (e o canal ativo) para o Início
    assert 'data-usar-tendencia="Tema Brasil Teste"' in r.text
    assert "Criar vídeo deste tema" in r.text
    # KEEP-01 (A33): o link já carrega o canal ativo junto do tema, sem trocar de canal
    assert re.search(r'href="/studio/panel\?project_id=[^"]+&amp;topic=Tema\+Brasil\+Teste"', r.text)

    # 4. Strict CSP & XSS safety
    assert 'innerHTML' not in r.text


def test_panel_uses_the_single_shell_palette_and_preview_stays_consistent(client_env):
    # Paleta única (tokens da casca V3, claro+escuro) para o painel e para a prévia:
    # a casca compartilhada é a fonte de verdade do CSS.
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "color-scheme: light dark" in r.text
    assert "light-dark(" in r.text
    assert "--accentfill-l:#6b4cd6" in r.text  # token aprovado do protótipo V3
    assert "--bg: #0f0f0f" not in r.text  # paleta antiga não volta
    assert "--surface: #181818" not in r.text

    # A prévia não tem paleta própria: usa a mesma casca do painel.
    import app.studio.api.preview as preview
    assert not hasattr(preview, "CSS"), "a prévia não deve manter CSS/paleta próprios"
    v = client_env["videos"].create_video(client_env["project_id"], "Preview Palette Video", VideoFormat.short)
    preview_page = client.get(f"/studio/videos/{v.id}/preview", headers=AUTH_HEADER).text
    assert "--accentfill-l:#6b4cd6" in preview_page
    assert "light-dark(" in preview_page
    assert "--bg: #0f0f0f" not in preview_page
    assert "--surface: #181818" not in preview_page


def test_panel_has_project_selector_and_create_project_modal(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    p_id_1 = client_env["project_id"]
    p2 = videos.create_project("Canal Secundário", niche="Curiosidades", language="en-US")
    p_id_2 = p2.id

    # 1. Default request selects first project in the topbar (UX V3: `#canal-ativo`).
    r1 = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r1.status_code == 200
    assert 'id="canal-ativo"' in r1.text
    assert 'id="btn-novo-canal"' in r1.text
    assert 'id="dlg-canal"' in r1.text
    assert 'id="form-canal"' in r1.text
    assert 'id="btn-salvar-canal"' in r1.text
    assert 'id="canal-feedback"' in r1.text
    assert 'value="pt-BR"' in r1.text
    assert 'value="en-US"' in r1.text
    assert 'value="es-ES"' in r1.text

    # Default project (p_id_1) is selected
    assert f'<option value="{p_id_1}" selected>' in r1.text

    # 2. Specifying project_id selects project 2
    r2 = client.get(f"/studio/panel?project_id={p_id_2}", headers=AUTH_HEADER)
    assert r2.status_code == 200
    assert f'<option value="{p_id_2}" selected>' in r2.text
    # O seletor lista os canais reais, não só o ativo.
    assert "Canal Visual" in r2.text and "Canal Secundário" in r2.text


def test_panel_renders_production_board_and_modern_video_cards(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Workflow Modern Cards Video", VideoFormat.short)
    # IA-01: o quadro de produção vive na tela Produção (/studio/panel/producao)...
    r_prod = client.get("/studio/panel/producao", headers=AUTH_HEADER)
    assert r_prod.status_code == 200

    # FS31-A3/UX V3: quadro de execução na casca V3, com dado real do vídeo e custo rotulado.
    assert 'id="pagina-producao"' in r_prod.text
    assert "Workflow Modern Cards Video" in r_prod.text
    assert "Short · 9:16" in r_prod.text
    assert "Não iniciado" in r_prod.text
    assert "Custo:" in r_prod.text
    # O funil V2 (grid-summary e bordas coloridas) não volta.
    assert '<div class="grid-summary">' not in r_prod.text
    assert "border-left: 4px solid" not in r_prod.text
    assert "Faceless Studio V2" not in r_prod.text and 'class="sidebar"' not in r_prod.text

    # ...e os cartões modernos de vídeo continuam no Início, no bloco Vídeos.
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "cartao-projeto" in r.text
    assert "Workflow Modern Cards Video" in r.text
    assert "Short · 9:16" in r.text
    assert 'aria-label="Abrir o vídeo Workflow Modern Cards Video"' in r.text


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
    assert '<aside class="side">' in r.text
    assert '<div class="app">' in r.text
    assert '<main class="main">' in r.text
    assert "Faceless Studio" in r.text and "ESTÚDIO DO CANAL" in r.text

    # A navegação renderizada na prévia é a mesma casca das outras telas do painel.
    items = _nav_items(r.text)
    labels = [" ".join(re.sub(r"<[^>]+>", " ", item).split()) for item in items]
    for expected in ("Início", "Criar vídeo", "Vídeos", "Tendências e ideias", "Desempenho"):
        assert any(expected in label for label in labels), expected
    active = [item for item in items if 'aria-current="page"' in item]
    assert len(active) == 1 and "Vídeos" in " ".join(re.sub(r"<[^>]+>", " ", active[0]).split())
    # IA-01/V3: "Vídeos" é tela real; a prévia é aberta a partir dela.
    assert 'href="/studio/panel/videos' in r.text

    # Conteúdo da prévia intacto.
    assert "Prévia do corte final" in r.text
    assert "Voltar ao vídeo" in r.text

    # O template antigo (marca, navegação e CTA) não pode voltar.
    for stale in ("FACELESS STUDIO", "Pipeline de Vídeos", "Temas em Alta", "+ Novo Vídeo"):
        assert stale not in r.text, stale


def test_panel_trends_lists_every_trend_with_an_honest_count(client_env):
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

    # IA-01/V3: a tela Tendências lista todas as tendências do período (sem esconder dado
    # atrás de um "ver mais") e a contagem dos filtros é medida a partir da mesma lista.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert 'class="cartao-tendencia"' in r.text
    assert r.text.count('class="cartao-tendencia"') == 8
    assert "Todas (8)" in r.text
    assert "Em Alta Brasil (8)" in r.text
    for i in range(8):
        assert f"Trend Topic {i}" in r.text

    # Sem tendências não aparece cartão algum e o vazio é explícito.
    conn.execute("DELETE FROM studio.trend_topics WHERE project_id = %s", (p_id,))
    conn.commit()
    r_empty = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r_empty.status_code == 200
    assert 'class="cartao-tendencia"' not in r_empty.text
    assert "Ainda não há tendências coletadas" in r_empty.text
    assert "Todas (0)" in r_empty.text

    # Script restrito à CSP (sem innerHTML).
    assert "innerHTML" not in r.text











def _without_style_and_script(html: str) -> str:
    return re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)


def _nav_items(html: str):
    """Itens da navegação principal (casca V3 e a casca antiga de Produção)."""
    match = re.search(r'<nav(?: class="nav")? aria-label="Principal">(.*?)</nav>',
                      _without_style_and_script(html), re.S)
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

    # W1.5: menu do protótipo (rótulos novos + Biblioteca); Configurações fica no rodapé.
    for expected in ("Início", "Criar vídeo", "Vídeos", "Tendências e ideias", "Desempenho"):
        assert any(expected in label for label in labels), expected

    active = [item for item in items if 'aria-current="page"' in item]
    assert len(active) == 1 and "Início" in " ".join(re.sub(r"<[^>]+>", " ", active[0]).split())
    assert _without_style_and_script(r.text).count('aria-current="page"') == 1

    # Nenhum item indisponível na casca: todos são destinos reais.
    assert not any('aria-disabled="true"' in item for item in items)
    configuracoes = re.search(r'<a href="/studio/configuracoes/canais[^"]*"[^>]*>.*?</a>', r.text, re.S)
    assert configuracoes is not None, "Configurações sem destino real"

    # IA-01/V3: Início/Novo vídeo/Tendências/Vídeos/Desempenho são rotas de servidor reais.
    for label, href in (("Início", "/studio/panel"), ("Criar vídeo", "/studio/panel/novo-video"),
                        ("Tendências e ideias", "/studio/panel/tendencias"),
                        ("Vídeos", "/studio/panel/videos"), ("Desempenho", "/studio/panel/analytics")):
        item = next(item for item in items if label in " ".join(re.sub(r"<[^>]+>", " ", item).split()))
        assert re.search(rf'href="{href}(?:\?project_id=[^"]+)?"', item), (label, item)


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
    # UX V3: sem vídeo, o Início diz o próximo passo (não desenha produção fictícia).
    assert "Nenhum vídeo ainda" in r.text
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
    # IA-01/V3: o Início publica só as suas seções; Produção e Tendências são telas próprias.
    assert 'id="pagina-inicio"' in r.text
    assert 'id="videos"' in r.text
    assert 'id="pagina-tendencias"' not in r.text
    assert 'id="producao-section"' not in r.text
    assert r.text.count("<h1") == 1

    # O contrato de filtro de tendências mudou de página: agora é da tela Tendências.
    # E o filtro passou a viver na URL (link, não botão): o scroll infinito precisa do mesmo
    # recorte no servidor para o próximo lote — filtrar só o lote atual seria enganoso.
    r_trend = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r_trend.status_code == 200
    assert ('<a class="chip-filtro" href="/studio/panel/tendencias?filtro=todas&amp;project_id='
            in r_trend.text)
    assert 'data-filtro="todas" aria-current="true">Todas (8)</a>' in r_trend.text
    assert 'data-filtro="regiao:BR"' in r_trend.text
    assert "Em Alta Brasil (8)" in r_trend.text
    # Com 8 tendências (menos que um lote), todas são publicadas e não há "carregar mais".
    assert r_trend.text.count('class="cartao-tendencia"') == 8
    assert 'id="btn-carregar-mais"' not in r_trend.text


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

    # IA-01/V3: o tema e a origem da tendência aparecem (escapados) na tela Tendências.
    r = client.get("/studio/panel/tendencias", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "<script>alert" not in r.text
    assert "&lt;script&gt;alert(&#x27;topic&#x27;)&lt;/script&gt;" in r.text
    assert "&lt;script&gt;alert(&#x27;source&#x27;)&lt;/script&gt;" in r.text
    # A URL da fonte não é publicada na V3; nada dela pode chegar crua ao HTML.
    assert "https://example.com/?q=<script>" not in r.text


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


def test_panel_cost_note_labels_four_cost_categories(client_env):
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
    # UX V3: o custo do mês vive na nota da casca, com as quatro categorias rotuladas.
    note = re.search(r'<p class="nota-custo">(.*?)</p>', r.text, re.S)
    assert note is not None, "nota de custo ausente na casca"
    note = note.group(1)
    assert "Real US$ 0,07" in note
    assert "Estimado US$ 0,05" in note
    assert "Sem custo" in note and "Desconhecido" in note
    assert "US$ 0,12" not in note  # sem número único que funda real e estimado
    assert "US$ 0,00" not in note


def test_panel_absence_of_cost_is_not_rendered_as_zero(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    p_id = client_env["project_id"]
    videos.create_video(p_id, "Sem Uso Registrado", VideoFormat.short)

    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    # UX V3: ausência de chamada é dita por extenso, nunca como US$ 0,00.
    assert "Não disponível: nenhuma chamada registrada neste mês." in r.text
    assert "US$ 0,00" not in r.text


def test_panel_declares_viewport_and_responsive_media_query(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert 'name="viewport"' in r.text
    # UX V3: o breakpoint da casca aprovada é 820px (sem espaço, como no protótipo).
    assert re.search(r"@media\s*\(max-width:\s*820px\)", r.text), "media query responsiva ausente"


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


# ---------- PROD-04 (achado 3): o vídeo base da tendência chega à página (Postgres) ----------


def test_video_detail_page_prefills_the_base_video_url_from_the_matching_trend(client_env):
    """Um vídeo cujo tema casa com uma `trend_topics` (mesmo `topic_key`) traz a URL preenchida."""
    from app.studio.domain.panel import topic_key

    client, videos, conn, p_id = (client_env["client"], client_env["videos"],
                                  client_env["conn"], client_env["project_id"])
    topic = "Tema Com Base"
    v = videos.create_video(p_id, topic, VideoFormat.short)
    now = datetime.now(timezone.utc)
    base_url = "https://youtube.com/watch?v=BASEVIDEO01"
    conn.execute(
        """
        INSERT INTO studio.trend_topics (
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, metric_name, metric_value, evidence
        ) VALUES (%s, %s, %s, %s, 'YouTube Brasil (Em Alta)',
                  'https://www.youtube.com/feed/trending', %s, %s, %s, 'views', 1000, %s::jsonb)
        """,
        (uuid.uuid4().hex, p_id, topic, topic_key(topic), now, now - timedelta(days=7), now,
         json.dumps([{"url": base_url}])),
    )
    conn.commit()

    r = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert f'value="{base_url}"' in r.text
    assert "vídeo base" in r.text


def test_video_detail_page_leaves_the_source_url_empty_without_a_matching_trend(client_env):
    """Sem tendência correspondente, o campo continua vazio (como hoje)."""
    client, videos = client_env["client"], client_env["videos"]
    v = videos.create_video(client_env["project_id"], "Tema Sem Base Alguma", VideoFormat.short)

    r = client.get(f"/studio/panel/videos/{v.id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "vídeo base" not in r.text
    match = re.search(r'<input[^>]*id="source-url"[^>]*>', r.text)
    assert match is not None and "value=" not in match.group(0)


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
    assert 'id="pagina-inicio"' in inicio.text
    assert 'id="videos"' in inicio.text
    assert 'id="pagina-producao"' in producao.text
    assert 'id="pagina-tendencias"' in tendencias.text

    # ...e o HTML completo de uma tela nunca aparece dentro da outra.
    assert 'id="pagina-producao"' not in inicio.text
    assert 'id="pagina-tendencias"' not in inicio.text
    assert 'id="lista-producao"' not in inicio.text
    assert 'id="pagina-inicio"' not in producao.text
    assert 'id="pagina-tendencias"' not in producao.text
    assert 'id="grade-tendencias"' not in producao.text
    assert 'id="pagina-inicio"' not in tendencias.text
    assert 'id="pagina-producao"' not in tendencias.text
    assert 'id="lista-producao"' not in tendencias.text

    # Exatamente um aria-current="page" por página, no item certo da nav.
    for r, label in ((inicio, "Início"), (producao, "Vídeos"), (tendencias, "Tendências")):
        assert _without_style_and_script(r.text).count('aria-current="page"') == 1
        active = next(item for item in _nav_items(r.text) if 'aria-current="page"' in item)
        assert label in re.sub(r"<[^>]+>", " ", active)


def test_panel_ia01_videos_route_is_a_real_screen(client_env):
    """UX V3: "Vídeos" deixou de ser âncora/redirect — é a tela real `/studio/panel/videos`."""
    client = client_env["client"]
    r = client.get("/studio/panel/videos", headers=AUTH_HEADER, follow_redirects=False)
    assert r.status_code == 200
    assert 'id="pagina-videos"' in r.text
    active = next(item for item in _nav_items(r.text) if 'aria-current="page"' in item)
    assert "Vídeos" in re.sub(r"<[^>]+>", " ", active)
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

    # O quadro completo de produção (lista + custo por vídeo) fica só em Produção...
    assert 'id="pagina-producao"' in producao.text
    assert "Vídeo para funil" in producao.text
    assert "Custo:" in producao.text
    assert 'id="pagina-producao"' not in inicio.text
    assert "Custo:" not in inicio.text
    # ...e o Início traz o resumo de produção, com link para a tela cheia.
    assert re.search(r'href="/studio/panel/producao(?:\?project_id=[^"]+)?"', inicio.text)
    assert "Acompanhar produção" in inicio.text


def test_panel_ia01_trend_create_link_prefills_the_home_topic(client_env):
    """O «Criar Vídeo deste Tema» (Tendências) leva o tema pré-preenchido para o Início.

    KEEP-01 (A33): o link também carrega o canal ativo; criar a partir de uma tendência não
    pode trocar o canal em silêncio (o handler JS antigo navegava só com `?topic=`).
    """
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
    # UX V3/KEEP-01: o link carrega o tema e o canal ativo; o destino já está correto sem JS.
    match = re.search(r'<a[^>]*data-usar-tendencia="([^"]+)"[^>]*>', r.text)
    assert match is not None, "link «Criar vídeo deste tema» sem o tema"
    assert html_module.unescape(match.group(1)) == "Tema com Acento & Cia"
    assert f"project_id={p_id}" in match.group(0)
    assert "topic=Tema+com+Acento+%26+Cia" in match.group(0)

    # O Início trata o parâmetro: o tema chega pré-preenchido (e escapado) no formulário.
    home = client.get("/studio/panel?topic=Tema%20com%20Acento%20%26%20Cia", headers=AUTH_HEADER)
    assert home.status_code == 200
    assert 'value="Tema com Acento &amp; Cia"' in home.text
