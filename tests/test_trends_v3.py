"""UX V3: Tela Tendências segue a proposta aprovada (docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html).

Pilares de conteúdo, filtros por região/pilar, diálogo de pilares e cartões com evidência.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.studio.application.panel import BuildPanel
from app.studio.application.ports import TrendRecord
from test_panel import FakePanelRepo, FakeTrendRepo
from test_ux_contract import assert_ux_contract

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)


class FakeCategoryRepo:
    def __init__(self, categories=None):
        self._categories = categories or []

    def list(self, project_id):
        return [c for c in self._categories if c.project_id == project_id]


def _trends_page(trends=None, categories=None, project_id=None):
    from app.studio.api.panel_trends import render_tendencias_v3

    p_id = project_id or "1" * 32
    trend_repo = FakeTrendRepo(
        records=trends or [],
        last_collected=NOW if trends else None,
    )
    cat_repo = FakeCategoryRepo(categories=categories or [])
    panel_repo = FakePanelRepo(projects_list=[(p_id, "Canal Principal")])
    view = BuildPanel(panel_repo, 15.0, lambda: NOW, trends=trend_repo, categories_repo=cat_repo).execute(days=7)
    return render_tendencias_v3(view)


def _trend(topic="GTA VI: dia 3", region="BR", url="https://www.youtube.com/watch?v=abc123XYZ_0", channel="Canal Gamer", views=840000.0):
    source_name = "YouTube Brasil (Em Alta)" if region == "BR" else "YouTube EUA (Em Alta)"
    return TrendRecord(
        id="t1", project_id="p1", topic=topic, topic_key=topic.lower(),
        source_name=source_name,
        source_url="https://www.googleapis.com/youtube/v3/videos",
        observed_at=NOW, window_start=NOW - timedelta(days=7), window_end=NOW,
        metric_name="views", metric_value=views,
        evidence=[{"url": url, "title": topic, "channel": channel, "published_at": "2026-11-18T09:00:00Z"}],
    )


def test_trends_uses_v3_shell_and_nav():
    html, _ = _trends_page()
    assert html.count("<h1") == 1
    assert 'class="crumb"' not in html
    assert "Radar" in html
    assert "Tendências e ideias</h1>" in html
    assert "Ideias para o nicho do canal. Escolha como produzir." in html

    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    assert re.search(r'href="/studio/panel/tendencias(?:\?project_id=[^"]+)?" aria-current="page"', main)
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S)
    assert markup.count('aria-current="page"') == 1


def test_trends_has_action_buttons_and_filter_chips():
    from app.studio.domain.categories import ProjectCategory

    c_id = "c" * 32
    p_id = "1" * 32
    cats = [ProjectCategory(id=c_id, project_id=p_id, name="Games", queries=["GTA", "games"])]
    html, _ = _trends_page(trends=[_trend()], categories=cats, project_id=p_id)

    assert 'id="btn-refresh-trends"' in html
    assert 'id="btn-gerenciar-pilares"' in html
    assert "Gerenciar pilares (1)" in html
    assert 'id="barra-tendencias"' in html
    assert 'data-filtro="todas"' in html
    # Padrão do protótipo: "Todas" + pilares. Sem chip de região na tela.
    assert 'data-filtro="regiao:BR"' not in html
    assert 'data-filtro="regiao:US"' not in html
    assert f'data-filtro="pilar:{c_id}"' in html
    assert 'id="btn-novo-pilar"' not in html  # `pgIdeas` não tem "+ Novo pilar"; o diálogo abre por "Gerenciar pilares"


def test_trends_renders_cards_with_evidence():
    html, _ = _trends_page(trends=[_trend()])
    assert "GTA VI: dia 3" in html
    assert "YouTube Brasil (Em Alta)" in html
    assert "Canal Gamer" in html
    assert "https://www.youtube.com/watch?v=abc123XYZ_0" in html
    assert 'data-usar-tendencia="GTA VI: dia 3"' in html


def test_trends_empty_state_when_no_trends():
    html, _ = _trends_page(trends=[])
    assert "Ainda não há tendências coletadas" in html


# --------------------------------------- KEEP-01/W1.3: canal preservado ao criar vídeo


def test_create_video_link_keeps_the_active_channel_and_topic():
    """KEEP-01 (A33): "Criar vídeo deste tema" não troca o canal ativo em silêncio.

    O link precisa carregar o canal ativo (`project_id`) junto do tema; sem isso a tela
    Início recebia só o tema e caía no canal padrão do estúdio.
    """
    p_id = "1" * 32
    html, _ = _trends_page(trends=[_trend()], project_id=p_id)
    link = re.search(r'<a[^>]*data-usar-tendencia="GTA VI: dia 3"[^>]*>', html)
    assert link is not None, "link de criar vídeo ausente"
    assert f"project_id={p_id}" in link.group(0), link.group(0)
    assert "topic=GTA" in link.group(0), link.group(0)
    # o handler antigo navegava sem o canal; não pode continuar vencendo o href do link
    assert "location.href = '/studio/panel?topic='" not in html


def test_trends_has_pillar_dialog():
    html, _ = _trends_page()
    assert 'id="dialog-pilares"' in html
    assert 'id="lista-pilares"' in html
    assert 'id="form-pilar"' in html
    assert 'id="pilar-nome"' in html
    assert 'id="pilar-termos"' in html


def test_trends_satisfies_ux_contract():
    html, _ = _trends_page(trends=[_trend()])
    assert_ux_contract(html, page="painel/tendências")
    assert not re.search(r"\son[a-z]+=", html)


# ------------------------------------------- scroll infinito da lista (pedido do operador)


PAGE_SIZE = 24


def _many(n, region="BR"):
    return [_trend(topic=f"Tema {region} {i}", region=region,
                   url=f"https://www.youtube.com/watch?v={region.lower()}{i:08d}",
                   channel=f"Canal {region}{i}", views=1_000_000.0 - i) for i in range(n)]  # um canal por vídeo, mais vistos primeiro


def _view(trends, project_id="1" * 32):
    p_id = project_id
    trend_repo = FakeTrendRepo(records=trends, last_collected=NOW)
    panel_repo = FakePanelRepo(projects_list=[(p_id, "Canal Principal")])
    return BuildPanel(panel_repo, 15.0, lambda: NOW, trends=trend_repo,
                      categories_repo=FakeCategoryRepo()).execute(days=7)


def _page_html(trends, **kw):
    from app.studio.api.panel_trends import render_tendencias_v3
    return render_tendencias_v3(_view(trends, kw.pop("project_id", "1" * 32)), **kw)[0]


def _lote_html(trends, **kw):
    from app.studio.api.panel_trends import render_tendencias_cartoes
    view = _view(trends, kw.pop("project_id", "1" * 32))
    return render_tendencias_cartoes(view, **kw)[0]


def test_first_render_shows_one_batch_and_a_load_more_control():
    html = _page_html(_many(30))
    assert html.count('class="card cartao-tendencia"') == PAGE_SIZE
    assert 'id="btn-carregar-mais"' in html
    assert "Mostrando 24 de 30." in html
    assert "offset=24" in html                      # próximo lote aponta para o resto
    assert 'aria-label="Paginação de tendências"' not in html   # não há mais paginação por página


def test_load_more_is_absent_when_everything_already_fits():
    html = _page_html(_many(3))
    assert 'id="mais-tendencias"' not in html
    assert 'id="btn-carregar-mais"' not in html


def test_next_batch_returns_the_following_cards_and_says_when_it_ends():
    trends = _many(30)
    lote = _lote_html(trends, offset=PAGE_SIZE, limite=PAGE_SIZE)
    assert lote.count('class="card cartao-tendencia"') == 6
    assert "Tema BR 24" in lote and "Tema BR 29" in lote
    assert 'data-tem-mais="false"' in lote


def test_middle_batch_points_to_the_next_offset():
    lote = _lote_html(_many(60), offset=PAGE_SIZE, limite=PAGE_SIZE)
    assert lote.count('class="card cartao-tendencia"') == PAGE_SIZE
    assert 'data-tem-mais="true"' in lote
    assert "offset=48" in lote


def test_filter_runs_on_the_server_and_the_next_batch_follows_the_filtered_list():
    trends = _many(30, "BR") + _many(5, "US")
    only_us = _page_html(trends, filtro="regiao:US")
    assert only_us.count('class="card cartao-tendencia"') == 5
    assert "Tema US 0" in only_us and "Tema BR 0" not in only_us
    assert 'id="btn-carregar-mais"' not in only_us          # 5 cabe no primeiro lote

    br_lote = _lote_html(trends, filtro="regiao:BR", offset=PAGE_SIZE, limite=PAGE_SIZE)
    assert br_lote.count('class="card cartao-tendencia"') == 6
    assert "Tema BR 29" in br_lote and "Tema US" not in br_lote


def test_active_filter_is_marked_without_stealing_the_page_current_marker():
    # O chip ativo é o do filtro escolhido — hoje um pilar (o protótipo não tem chip de região).
    from app.studio.api.panel_trends import render_tendencias_v3
    from app.studio.domain.categories import ProjectCategory

    c_id = "c" * 32
    p_id = "1" * 32
    cats = [ProjectCategory(id=c_id, project_id=p_id, name="Games", queries=["GTA"])]
    trend_repo = FakeTrendRepo(records=_many(2), last_collected=NOW)
    panel_repo = FakePanelRepo(projects_list=[(p_id, "Canal Principal")])
    view = BuildPanel(panel_repo, 15.0, lambda: NOW, trends=trend_repo,
                      categories_repo=FakeCategoryRepo(cats)).execute(days=7)
    html, _ = render_tendencias_v3(view, filtro=f"pilar:{c_id}")
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S)
    assert markup.count('aria-current="page"') == 1        # só o item da navegação
    assert f'data-filtro="pilar:{c_id}" aria-current="true"' in html


def test_bad_or_out_of_range_offset_returns_an_empty_honest_batch():
    empty = _lote_html(_many(10), offset=999, limite=PAGE_SIZE)
    assert empty.count('class="card cartao-tendencia"') == 0
    assert 'data-tem-mais="false"' in empty
    negative = _lote_html(_many(10), offset=-5, limite=PAGE_SIZE)
    assert negative.count('class="card cartao-tendencia"') == 10   # offset inválido = começo


def test_unknown_filter_shows_an_explicit_empty_state_not_every_trend():
    html = _page_html(_many(3), filtro="pilar:inexistente")
    assert html.count('class="card cartao-tendencia"') == 0
    assert "Nenhuma tendência encontrada para este filtro." in html


def _search_row(term, videos):
    return TrendRecord(
        id="s-" + term, project_id="p1", topic=term, topic_key=term.lower(), source_name="YouTube Data API",
        source_url="https://www.googleapis.com/youtube/v3/search", observed_at=NOW,
        window_start=NOW - timedelta(days=7), window_end=NOW, metric_name="views",
        metric_value=float(sum(v[2] for v in videos)),
        evidence=[{"url": f"https://www.youtube.com/watch?v={vid}", "title": title, "channel": channel, "views": views}
                  for vid, channel, views, title in videos])


def test_a_search_row_shows_one_card_per_video_not_one_per_term():
    row = _search_row("Cane Corso", [("aaaaaaaaaa1", "Canal A", 300, "Cane Corso no quintal"),
                                     ("aaaaaaaaaa2", "Canal B", 200, "Cane Corso filhote"),
                                     ("aaaaaaaaaa3", "Canal C", 100, "Cane Corso treino")])
    html = _page_html([row])
    assert html.count('class="card cartao-tendencia"') == 3
    for title in ("Cane Corso no quintal", "Cane Corso filhote", "Cane Corso treino"):
        assert title in html


def test_the_same_video_collected_twice_and_a_busy_channel_do_not_flood_the_list():
    again = [_trend(topic="Mesmo vídeo", url="https://www.youtube.com/watch?v=repetido001", channel="Canal X") for _ in range(3)]
    busy = [_trend(topic=f"Do mesmo canal {n}", url=f"https://www.youtube.com/watch?v=mesmo{n:07d}", channel="Canal Cheio",
                   views=500.0 - n) for n in range(6)]
    html = _page_html(again + busy)
    assert html.count("Mesmo vídeo") >= 1 and html.count('class="card cartao-tendencia"') == 1 + 2  # 1 do repetido + 2 do canal cheio
