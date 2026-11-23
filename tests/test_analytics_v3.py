"""UX V3: Tela Desempenho segue a proposta aprovada (docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html).

Sem dado inventado, sem percentual sem medição, começa vazio quando não há métricas reais.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.studio.application.analytics_dashboard import AnalyticsDashboardView, CollectionReadiness
from app.studio.application.panel import CostBreakdown, MonthCost
from app.studio.domain.analytics_learning import AnalyticsPeriod
from test_ux_contract import assert_ux_contract

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)


def _analytics_page():
    from app.studio.api.panel_analytics import render_analytics

    month = MonthCost(cap_usd=15.0, known_usd=0.0, unknown_calls=0, percent=None,
                      text="sem registro de uso", breakdown=CostBreakdown())
    view = AnalyticsDashboardView(
        project_id="p1",
        project_name="Canal Principal",
        period=AnalyticsPeriod(days=7, end_at=NOW),
        generated_at=NOW,
        selected_video_id=None,
        selected_pillar_id=None,
        projects=(),
        videos=(),
        pillars=(),
        tiles=(),
        video_rows=(),
        pillar_rows=(),
        insights=(),
        recommendations=(),
        experiments=(),
        readiness=CollectionReadiness(
            channel_connected=False, scope_granted=False, publication_available=False,
            reasons=("canal não conectado",),
        ),
        last_collected_at=None,
        has_measurements=False,
        insufficient_sample=False,
        notes=(),
        observation_ids=(),
        experiment_ids=(),
        scope_text="",
        channel_text="",
    )
    return render_analytics(view, month)


def test_analytics_uses_v3_shell_and_nav():
    html, _ = _analytics_page()
    assert html.count("<h1") == 1
    assert 'class="crumb"' not in html
    assert "CRESCIMENTO DO CANAL" in html
    assert "Desempenho</h1>" in html
    assert "Acompanhe o resultado sem perder o foco na criação." in html

    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    assert re.search(r'href="/studio/panel/analytics(?:\?project_id=[^"]+)?" aria-current="page"', main)
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S)
    assert markup.count('aria-current="page"') == 1


def test_analytics_period_selector():
    html, _ = _analytics_page()
    assert '<select id="periodo"' in html
    assert 'value="7"' in html
    assert 'value="28"' in html
    assert 'value="90"' in html


def test_analytics_empty_state_without_invented_data_or_percentages():
    html, _ = _analytics_page()
    assert 'id="desempenho-vazio"' in html
    assert "Sem medição neste período" in html
    assert "Publique um vídeo e conecte o canal para ver os números reais aqui" in html

    from test_panel import _visible_text
    visible = _visible_text(html)
    assert re.search(r"\d+(?:[.,]\d+)?\s*%", visible) is None


def test_analytics_satisfies_ux_contract():
    html, _ = _analytics_page()
    assert_ux_contract(html, page="painel/desempenho")
    assert not re.search(r"\son[a-z]+=", html)
