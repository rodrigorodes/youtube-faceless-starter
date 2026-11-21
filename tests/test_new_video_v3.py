"""UX V3: Novo vídeo segue a proposta aprovada (docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html).

Três etapas: Conceito -> Revisão -> Criação.
A produção NÃO começa aqui: o vídeo é criado e abre para informar a fonte.
"""

from __future__ import annotations

import re

from app.studio.api.panel_production import NewVideoView, PipelineStage
from app.studio.application.panel import CostBreakdown, MonthCost
from app.studio.domain.production_run import ProductionStage
from test_ux_contract import assert_ux_contract


def _view(*, projects=None, selected_project_id="p1"):
    if projects is None:
        projects = [("p1", "Canal Gamer"), ("p2", "Tech News")]
    month = MonthCost(cap_usd=15.0, known_usd=0.0, unknown_calls=0, percent=None,
                      text="sem registro de uso", breakdown=CostBreakdown())
    pipeline = (
        PipelineStage(ProductionStage.SCRIPT, "Roteiro", True),
        PipelineStage(ProductionStage.RENDER, "Render", True),
    )
    return NewVideoView(
        projects=projects,
        month=month,
        pipeline=pipeline,
        selected_project_id=selected_project_id,
    )


def test_new_video_uses_v3_shell_and_nav():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert html.count("<h1") == 1
    assert "Novo vídeo do canal" in html
    assert "CRIAR / NOVO VÍDEO" in html
    assert "Estúdio &nbsp;/&nbsp; <b>Novo vídeo</b>" in html

    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    assert 'href="/studio/panel/novo-video" aria-current="page"' in main
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S)
    assert markup.count('aria-current="page"') == 1


def test_new_video_has_three_steps():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    passos = re.search(r'<ol class="passos"[^>]*id="passos-criar"[^>]*>(.*?)</ol>', html, re.S).group(1)
    for step in ("Conceito", "Revisão", "Criação"):
        assert step in passos

    assert 'id="etapa-1"' in html
    assert 'id="etapa-2"' in html and 'id="etapa-2" hidden' in html
    assert 'id="etapa-3"' in html and 'id="etapa-3" hidden' in html


def test_new_video_concept_fields():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert 'id="tema-novo"' in html
    assert 'maxlength="300"' in html
    assert 'name="formato-novo"' in html
    assert re.search(r'name="formato-novo"[^>]*value="long"[^>]*checked', html)
    assert 'name="estilo-novo"' in html
    assert 'id="btn-para-revisao"' in html


def test_new_video_review_and_creation_panels():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert 'id="rev-tema"' in html
    assert 'id="rev-formato"' in html
    assert 'id="rev-estilo"' in html
    assert 'id="rev-canal"' in html
    assert 'id="btn-voltar-editar"' in html
    assert 'id="btn-criar"' in html
    assert 'id="btn-novo-outro"' in html
    assert 'id="link-abrir-video"' in html
    assert "Próximo passo: as fontes" in html


def test_new_video_channel_preset_aside():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(selected_project_id="p1"))
    assert "Predefinição do canal" in html
    assert "Canal Gamer" in html
    assert 'href="/studio/configuracoes/canais"' in html


def test_new_video_empty_state_without_channels():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(projects=[]))
    assert "Cadastre um canal" in html
    btn = re.search(r'<button[^>]*id="btn-para-revisao"[^>]*>', html).group(0)
    assert "disabled" in btn


def test_new_video_satisfies_ux_contract():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert_ux_contract(html, page="painel/novo-video")
    assert not re.search(r"\son[a-z]+=", html)
