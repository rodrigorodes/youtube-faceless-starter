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


def _trend(topic="GTA VI: dia 3", region="BR", url="https://www.youtube.com/watch?v=abc123XYZ_0"):
    source_name = "YouTube Brasil (Em Alta)" if region == "BR" else "YouTube EUA (Em Alta)"
    return TrendRecord(
        id="t1", project_id="p1", topic=topic, topic_key=topic.lower(),
        source_name=source_name,
        source_url="https://www.googleapis.com/youtube/v3/videos",
        observed_at=NOW, window_start=NOW - timedelta(days=7), window_end=NOW,
        metric_name="views", metric_value=840000.0,
        evidence=[{"url": url, "title": topic, "channel": "Canal Gamer", "published_at": "2026-11-18T09:00:00Z"}],
    )


def test_trends_uses_v3_shell_and_nav():
    html, _ = _trends_page()
    assert html.count("<h1") == 1
    assert "Estúdio &nbsp;/&nbsp; <b>Tendências</b>" in html
    assert "O QUE ESTÁ SUBINDO" in html
    assert "Tendências</h1>" in html
    assert "Cada tendência vem com a evidência" in html

    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    assert 'href="/studio/panel/tendencias" aria-current="page"' in main
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
    assert 'data-filtro="regiao:BR"' in html
    assert 'data-filtro="regiao:US"' in html
    assert f'data-filtro="pilar:{c_id}"' in html
    assert 'id="btn-novo-pilar"' in html


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
