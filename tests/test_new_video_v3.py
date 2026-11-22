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


def _view(*, projects=None, selected_project_id="p1", styles=(), inherited_style_name=None,
          has_profile=False, channel_language=None, channel_voice=None):
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
        styles=tuple(styles),
        inherited_style_name=inherited_style_name,
        has_profile=has_profile,
        channel_language=channel_language,
        channel_voice=channel_voice,
    )


def test_new_video_uses_v3_shell_and_nav():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert html.count("<h1") == 1
    assert "Novo vídeo do canal" in html
    assert "CRIAR / NOVO VÍDEO" in html
    assert "Estúdio &nbsp;/&nbsp; <b>Novo vídeo</b>" in html

    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    assert re.search(r'href="/studio/panel/novo-video(?:\?project_id=[^"]+)?" aria-current="page"', main)
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
    # A identidade do canal é a sanfona real, não o topo genérico de Configurações.
    assert re.search(r'href="/studio/canais(?:\?project_id=[^"]*)?#painel-perfil"', html)


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


def test_new_video_style_options_are_the_real_library():
    """G15/F02.T02: as opções de estilo são a biblioteca real — nunca nomes fictícios."""
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(styles=[("s1", "Cinema Noturno"), ("s2", "Clean Tech")],
                                        inherited_style_name="Cinema Noturno"))
    opcoes = re.search(r'<fieldset class="pills"[^>]*>(.*?)</fieldset>', html, re.S)
    assert opcoes, "o campo de estilo precisa existir"
    bloco = [m for m in re.findall(r'<fieldset class="pills"[^>]*>.*?</fieldset>', html, re.S)
             if 'name="estilo-novo"' in m][0]
    assert 'name="estilo-novo"' in bloco
    assert 'value="s1"' in bloco and "Cinema Noturno" in bloco
    assert 'value="s2"' in bloco and "Clean Tech" in bloco
    assert re.search(r'name="estilo-novo"[^>]*value=""[^>]*checked', bloco), "herdar vem marcado"
    assert "Herdar do canal" in bloco
    # nenhum resíduo fictício
    for ficticio in ("Cinemático", "Documentário", "Tech Clean"):
        assert ficticio not in bloco


def test_format_options_carry_an_icon_each():
    """Protótipo: cada formato tem ícone próprio (16:9 horizontal × 9:16 vertical)."""
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    bloco = [m for m in re.findall(r'<fieldset class="pills"[^>]*>.*?</fieldset>', html, re.S)
             if 'name="formato-novo"' in m][0]
    icones = re.findall(r'<svg class="icone-formato"[^>]*aria-hidden="true"[^>]*>(.*?)</svg>', bloco, re.S)
    assert len(icones) == 2, "um ícone por formato"
    assert "width=\"20\" height=\"14\"" in icones[0]      # 16:9 deitado
    assert "width=\"10\" height=\"20\"" in icones[1]      # 9:16 em pé
    assert "focusable=\"false\"" in bloco


def test_style_options_are_cards_with_the_real_name_when_the_library_has_styles():
    """Protótipo: estilo vira cartão com amostra. A amostra é o nome real do estilo."""
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(styles=[("s1", "Cinema Noturno"), ("s2", "Clean Tech")]))
    bloco = [m for m in re.findall(r'<fieldset class="pills"[^>]*>.*?</fieldset>', html, re.S)
             if 'name="estilo-novo"' in m][0]
    # herdar do canal + um cartão por estilo real
    assert bloco.count('class="cartao-estilo"') == 3
    assert bloco.count('class="amostra"') == 3
    for nome in ("Cinema Noturno", "Clean Tech"):
        # amostra em caixa alta, como no protótipo
        assert f'<span class="amostra" aria-hidden="true">{nome.upper()}</span>' in bloco
    # herdar continua sendo a escolha marcada (e agora também é um cartão, como as demais)
    assert re.search(r'name="estilo-novo"[^>]*value=""[^>]*checked', bloco)
    assert 'class="galeria"' in bloco


def test_style_gallery_is_absent_when_the_library_is_empty():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(styles=()))
    bloco = [m for m in re.findall(r'<fieldset class="pills"[^>]*>.*?</fieldset>', html, re.S)
             if 'name="estilo-novo"' in m][0]
    assert 'class="galeria"' not in bloco and 'cartao-estilo' not in bloco


def test_new_video_style_inherit_shows_the_channel_style_name():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(styles=[("s1", "Cinema Noturno")],
                                        inherited_style_name="Cinema Noturno"))
    bloco = [m for m in re.findall(r'<fieldset class="pills"[^>]*>.*?</fieldset>', html, re.S)
             if 'name="estilo-novo"' in m][0]
    assert "Herdar do canal" in bloco
    assert "Cinema Noturno" in bloco
    assert "nenhum estilo" not in bloco.lower()


def test_new_video_without_styles_sends_to_the_library_and_does_not_fake_options():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(styles=(), inherited_style_name="Cinema Noturno"))
    bloco = [m for m in re.findall(r'<fieldset class="pills"[^>]*>.*?</fieldset>', html, re.S)
             if 'name="estilo-novo"' in m][0]
    # sem biblioteca: herdar continua sendo uma escolha real; sem rádios inventados
    assert 'name="estilo-novo"' in bloco
    assert 'value=""' in bloco and 'checked' in bloco
    assert "Cinema Noturno" in bloco  # o canal tem estilo: herdar aponta o nome real
    assert re.search(r'href="/studio/panel/estilos(?:\?project_id=[^"]+)?"', html)
    for ficticio in ("Cinemático", "Documentário", "Tech Clean"):
        assert ficticio not in html


def test_new_video_payload_carries_the_chosen_style():
    """O JS envia `style_id` quando há escolha e não envia quando herda (o Core resolve o canal)."""
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(styles=[("s1", "Cinema Noturno")]))
    assert "style_id" in html
    assert "estilo-novo" in html


def test_channel_preset_shows_what_the_channel_really_defines():
    """F02.T04: idioma/voz saem do perfil do canal; nada de "Português (BR)" fixo."""
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(has_profile=True, channel_language="en-US",
                                        channel_voice="piper:pt_BR-faber-medium"))
    aside = re.search(r'<aside class="painel" aria-labelledby="t-preset">(.*?)</aside>', html, re.S).group(1)
    assert "Inglês (EUA)" in aside
    assert "piper:pt_BR-faber-medium" in aside
    assert "Português (BR)" not in aside
    # as linhas fictícias (legendas/música) saíram
    assert "Legendas" not in aside and "Música" not in aside


def test_channel_preset_without_a_profile_says_so_instead_of_inventing():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(has_profile=False))
    aside = re.search(r'<aside class="painel" aria-labelledby="t-preset">(.*?)</aside>', html, re.S).group(1)
    assert "canal sem perfil" in aside
    assert "padrão do estúdio" in aside
    assert "Português (BR)" not in aside
