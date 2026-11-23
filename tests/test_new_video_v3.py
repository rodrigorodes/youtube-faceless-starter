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
          has_profile=False, channel_language=None, channel_voice=None, channel_profile=None):
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
        channel_profile=channel_profile,
    )


def _channel_profile(*, default_mode=None, default_format=None, **kwargs):
    from app.studio.domain.channel import ChannelProfile
    from app.studio.domain.contracts import ProductionMode, VideoFormat

    if default_mode is None:
        default_mode = ProductionMode.piloto
    if default_format is None:
        default_format = VideoFormat.short
    return ChannelProfile(
        id="a" * 32,
        project_id="b" * 32,
        name="Canal Gamer",
        default_mode=default_mode,
        default_format=default_format,
        **kwargs,
    )


def test_new_video_uses_v3_shell_and_nav():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert html.count("<h1") == 1
    assert "Novo vídeo do canal" in html
    assert "CRIAR / NOVO VÍDEO" in html
    assert 'class="crumb"' not in html

    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    assert re.search(r'href="/studio/panel/novo-video(?:\?project_id=[^"]+)?" aria-current="page"', main)
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S)
    assert markup.count('aria-current="page"') == 1


def test_new_video_single_screen_form_structure():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert '<form id="form-novo-video"' in html
    assert 'id="tema-novo"' in html
    assert 'maxlength="300"' in html
    assert 'name="formato-novo"' in html
    assert 'name="modo-producao"' in html
    assert 'name="estilo-novo"' in html
    assert 'id="btn-criar-abrir"' in html


def test_new_video_channel_preset_aside():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(selected_project_id="p1"))
    # `pgNew` do protótipo: cartão "Resumo" com o canal e o que ele define.
    assert 'aria-labelledby="t-preset"' in html and ">Resumo<" in html
    assert "Canal Gamer" in html


def test_new_video_empty_state_without_channels():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(projects=[]))
    assert "Cadastre um canal" in html
    assert re.search(r'<button[^>]*id="btn-criar-abrir"[^>]*disabled', html)


def test_new_video_satisfies_ux_contract():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert_ux_contract(html, page="painel/novo-video")
    assert not re.search(r"\son[a-z]+=", html)


def _bloco_estilo(html):
    return html.split('aria-label="Estilo visual">', 1)[1].split("</details>", 1)[0]


def test_new_video_style_options_are_the_real_library():
    """`nstyle` do protótipo: `.choice` em `grid3`; as opções são a biblioteca real, sem nomes fictícios."""
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(styles=[("s1", "Cinema Noturno"), ("s2", "Clean Tech")],
                                        inherited_style_name="Cinema Noturno"))
    bloco = _bloco_estilo(html)
    assert '<div class="grid3">' in bloco
    assert 'value="s2"' in bloco and "Clean Tech" in bloco
    assert re.search(r'value=""[^>]*checked', bloco), "herdar (estilo do canal) vem marcado"
    assert bloco.count('class="choice"') == 2  # herdado (= s1, sem duplicar) + s2
    for ficticio in ("Cinemático", "Documentário", "Tech Clean"):
        assert ficticio not in bloco


def test_format_is_a_segmented_control_short_first_like_the_prototype():
    """Protótipo (pgNew): Formato é um `.seg` com Short · 9:16 e Vídeo · 16:9, sem ícones, e a
    duração alvo é um select cujas opções acompanham o formato (preenchidas no navegador)."""
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    bloco = re.search(r'<fieldset class="pills seg"[^>]*>.*?</fieldset>', html, re.S).group(0)
    assert bloco.index("Short · 9:16") < bloco.index("Vídeo · 16:9")
    assert "<svg" not in bloco
    assert '<select id="duracao-alvo"' in html
    assert "Voz do narrador" in html and "3 · Formato, voz e estilo" in html


def test_style_options_are_choice_cards_with_thumb_and_real_name():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(styles=[("s1", "Cinema Noturno"), ("s2", "Clean Tech")]))
    bloco = _bloco_estilo(html)
    assert bloco.count('class="choice"') == 3  # padrão do estúdio + um por estilo real
    assert bloco.count('class="thumb"') == 3
    for nome in ("Cinema Noturno", "Clean Tech"):
        assert f'<b style="font-size:12.5px">{nome}</b>' in bloco
    assert re.search(r'aria-pressed="true"><input type="radio" name="estilo-novo" value=""', bloco)


def test_without_styles_only_the_channel_default_is_offered_and_nothing_is_faked():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(styles=(), inherited_style_name="Cinema Noturno"))
    bloco = _bloco_estilo(html)
    assert bloco.count('class="choice"') == 1 and "Cinema Noturno" in bloco
    for ficticio in ("Cinemático", "Documentário", "Tech Clean"):
        assert ficticio not in html
    assert "Gerenciar estilos" not in html  # o protótipo não tem esse link; a Biblioteca está no menu


def test_new_video_payload_carries_the_chosen_style():
    """O JS envia `style_id` quando há escolha e não envia quando herda (o Core resolve o canal)."""
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(styles=[("s1", "Cinema Noturno")]))
    assert "style_id" in html
    assert "estilo-novo" in html


def _resumo(html: str) -> str:
    return re.search(r'<div class="card" id="resumo-card"[^>]*>(.*?)</div>\s*<div class="note info"', html, re.S).group(1)


def test_channel_preset_shows_what_the_channel_really_defines():
    """F02.T04: a voz sai do perfil do canal; nada de "Português (BR)" fixo.

    O Resumo do protótipo (`pgNew`) não tem linha de idioma: Modo, Formato, Voz, Estilo e custo.
    """
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(has_profile=True, channel_language="en-US",
                                        channel_voice="piper:pt_BR-faber-medium"))
    aside = _resumo(html)
    assert "piper:pt_BR-faber-medium" in aside
    assert "Português (BR)" not in aside
    assert "Idioma" not in aside
    # as linhas fictícias (legendas/música) saíram
    assert "Legendas" not in aside and "Música" not in aside


def test_channel_preset_without_a_profile_says_so_instead_of_inventing():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(has_profile=False))
    assert "Canal sem perfil" in html
    aside = _resumo(html)
    assert "padrão do estúdio" in aside
    assert "Português (BR)" not in aside


def test_new_video_has_prototype_usability_fields():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    # Campos canônicos do protótipo (prototype/index.html:611)
    assert 'id="roteiro-pronto"' in html or 'id="script"' in html
    assert "Roteiro pronto" in html
    assert 'id="duracao-alvo"' in html or 'id="duration"' in html
    assert "Duração" in html
    # protótipo V4/V3: o roteiro pronto é escolha explícita e a revisão acontece dentro do vídeo
    assert 'id="usar-roteiro"' in html
    assert "Criar e abrir vídeo" in html


def test_new_video_summary_follows_the_prototype_structure():
    """`pgNew`: Resumo (Modo/Formato/Voz/Estilo/custo), "Providers do canal" e a nota do canal.

    O cartão "Seu caminho até publicar" não existe no protótipo e saiu.
    """
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert "Seu caminho até publicar" not in html
    resumo = _resumo(html)
    for label in ("Modo", "Formato", "Voz", "Estilo", "Estimativa de custo", "Providers do canal"):
        assert label in resumo, label
    # com perfil de canal, a nota do protótipo; sem perfil, a nota diz que valem os padrões do estúdio
    com_perfil, _ = render_new_video_v3(_view(has_profile=True, channel_voice="piper:pt_BR-faber-medium"))
    assert "Mudar aqui vale só para este vídeo; para mudar o padrão, use Biblioteca ou Configurações." in com_perfil
    assert "Canal sem perfil: valem os padrões do estúdio" in html


def test_new_video_inherits_channel_mode_and_format_defaults():
    from app.studio.api.panel_new_video import render_new_video_v3
    from app.studio.domain.contracts import ProductionMode, VideoFormat

    profile = _channel_profile(default_mode=ProductionMode.diretor, default_format=VideoFormat.long)
    html, _ = render_new_video_v3(_view(channel_profile=profile))

    # O formato "long" deve vir checked por padrão
    assert re.search(r'name="formato-novo"[^>]*value="long"[^>]*checked', html)
    # Deve conter seletor de modo com diretor selecionado
    assert re.search(r'name="modo-producao"[^>]*value="diretor"[^>]*checked', html)

    # Canal com modo piloto e formato short
    profile_short = _channel_profile(default_mode=ProductionMode.piloto, default_format=VideoFormat.short)
    html_short, _ = render_new_video_v3(_view(channel_profile=profile_short))

    assert re.search(r'name="formato-novo"[^>]*value="short"[^>]*checked', html_short)
    assert re.search(r'name="modo-producao"[^>]*value="piloto"[^>]*checked', html_short)


def test_new_video_payload_carries_production_mode():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert "production_mode" in html
    assert "modo-producao" in html

