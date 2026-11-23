"""W1.5 (SET): seções de Configurações com **página própria**, reusando os cartões de Canais.

`Estratégia editorial`, `Marca e estilo` e `Produção e orçamento` eram âncoras dentro de
`/studio/canais`. Aqui cada uma vira uma rota real (`/studio/configuracoes/{secao}`) que renderiza
a **mesma casca e os mesmos cartões** da tela de Canais — o mesmo formulário, o mesmo endpoint de
escrita e a mesma validação (`panel_channels`). Nada de segunda persistência nem de contrato
paralelo: um conceito, um dono.

O JavaScript é o mesmo da tela de Canais (`panel_channels._channels_page_js`), então os
formulários reusados continuam funcionando sem duplicar lógica no cliente.
"""

from __future__ import annotations

import secrets
from html import escape as e

from ..application.channels_page import ChannelsPageView
from . import panel as legacy
from . import panel_channels
from . import shell_v3
from .panel_channel_style import CHANNEL_STYLE_CSS, CHANNEL_STYLE_JS, render_channel_style

# Seção → (título, lead, cartões reusados). Rótulos do protótipo (`prototype/index.html:585`).
SECTIONS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "estrategia": (
        "Estratégia editorial",
        "Identidade editorial do canal: estratégia, público, pilares, narrativa, duração padrão e CTA.",
        ("perfil",),
    ),
    "marca": (
        "Marca e estilo",
        "Estilo visual, voz e legenda do canal ativo. Personalizar o canal não copia nem edita o estilo da biblioteca.",
        ("perfil", "aparencia"),
    ),
    "producao": (
        "Produção e orçamento",
        "Perfil econômico, tetos de gasto, preferências de produção e providers por tarefa.",
        ("orcamento", "providers", "preferencias"),
    ),
}

_CARDS = {
    "perfil": panel_channels._profile_card,
    "aparencia": panel_channels._appearance_card,
    "orcamento": panel_channels._budget_card,
    "providers": panel_channels._providers_card,
    "preferencias": panel_channels._prefs_card,
}


_CHANNELS_VISIBLE = 6
_MODOS = {"piloto": "Piloto automático", "diretor": "Modo Diretor"}


def _channel_card(pid: str, name: str, profile, active: bool) -> str:
    """Cartão de `pgSettings` (canais): só o que o `ChannelProfile` real define; ausente é dito, não inventado."""
    pills = ""
    detail = '<p class="sub">Sem perfil editorial · valem os padrões do estúdio.</p>'
    if profile is not None:
        niche = ", ".join(profile.pillars[:3]) or "sem nicho definido"
        detail = f'<p class="sub">{e(niche)} · {e(profile.language)}</p>'
        mode = getattr(profile.default_mode, "value", str(profile.default_mode))
        fmt = getattr(profile.default_format, "value", str(profile.default_format))
        pills = "".join((
            f'<span class="pill">🎙 {e(profile.voice)}</span>' if profile.voice else "",
            f'<span class="pill">{e(_MODOS.get(mode, mode))}</span>',
            f'<span class="pill">{"Short 9:16" if fmt == "short" else "Vídeo 16:9"}</span>',
            f'<span class="pill {"ok" if profile.youtube_channel_id else "warn"}">YouTube '
            f'{"conectado" if profile.youtube_channel_id else "desconectado"}</span>',
        ))
    q = f"project_id={e(pid)}"
    return (f'<div class="card{" channel-active" if active else ""}">'
            f'<div class="between"><h3>{e(name)}</h3>'
            + ('<span class="pill accent">Canal ativo</span>' if active else "")
            + f'</div>{detail}<div class="row" style="margin:10px 0">{pills}</div>'
            f'<div class="row" style="margin-top:10px"><a class="btn small" href="/studio/panel?{q}">Abrir estúdio</a>'
            f'<a class="btn ghost small" href="/studio/configuracoes/marca?{q}">Editar</a></div></div>')


def render_channel_list(view, profiles: dict | None = None):
    nonce = secrets.token_urlsafe(16)
    project_id = view.project.id if view.project else ""
    profiles = profiles or {}
    # O canal ativo vem primeiro; os demais aparecem em ordem, os excedentes ficam recolhidos.
    ordered = sorted(view.projects, key=lambda p: p[0] != project_id)
    shown = [_channel_card(pid, name, profiles.get(pid), pid == project_id) for pid, name in ordered]
    cards = "".join(shown[:_CHANNELS_VISIBLE])
    if len(shown) > _CHANNELS_VISIBLE:
        cards += (f'<details class="card" style="grid-column:1/-1"><summary>Mostrar os outros '
                  f'{len(shown) - _CHANNELS_VISIBLE} canais</summary><div class="grid2" style="margin-top:12px">'
                  + "".join(shown[_CHANNELS_VISIBLE:]) + '</div></details>')
    content = f"""<div class="between" style="margin-bottom:14px">
      <p class="sub">Cada canal tem identidade, visual, orçamento, providers e conexão com o YouTube próprios.</p>
      <a class="btn primary small" href="/studio/canais/novo">+ Novo canal</a></div>
      <div class="grid2">{cards}
      <a class="card channel-add" href="/studio/canais/novo"><span style="font-size:30px">＋</span><b>Criar novo canal</b>
      <span class="sample">Assistente em 6 passos</span></a></div>"""
    body = shell_v3.render_settings_page_body(active_section="canais", section_title="Canais",
                                              content_html=content, project_id=project_id)
    html = shell_v3.render_document(title="Faceless Studio — Canais", active="configuracoes",
        crumb="Canais", body_html=body, nonce=nonce, projects=list(view.projects), project_id=project_id,
        extra_css=".channel-active{border:2px solid var(--accent);background:var(--accentbg);padding:17px}.channel-add{border-style:dashed;text-align:center;display:flex;flex-direction:column;color:var(--muted)}")
    return html, legacy._headers(nonce)


def render_settings_section(section: str, view: ChannelsPageView, *, channel_style=None
                            ) -> tuple[str, dict[str, str]]:
    """Página de uma seção de Configurações. `section` precisa existir em `SECTIONS`."""
    title, lead, cards = SECTIONS[section]
    if view.project is None:
        return panel_channels._empty_page(panel_channels._sidebar_card(view))
    nonce = secrets.token_urlsafe(16)
    style_html = render_channel_style(channel_style) if channel_style is not None else ""
    reusados = "".join(_CARDS[kind](view) for kind in cards)
    # A personalização do canal (origem/efetivo/reset) só faz sentido junto da aparência.
    identidade_html = style_html if section == "marca" else ""
    content_html = f"""
      <div class="card">
        <div class="spread">
          <div>
            <h2>{e(title)}</h2>
            <p class="dim" style="margin:0">{e(lead)}</p>
          </div>
          <span class="selo">CANAL</span>
        </div>
        <p class="micro" style="margin:10px 0 0">Canal ativo: <b>{e(view.project.name)}</b> ·
        vídeos existentes preservam o snapshot deles.</p>
      </div>
      {reusados}
      {identidade_html}
    """
    body = shell_v3.render_settings_page_body(
        active_section=section,
        section_title=title,
        content_html=content_html,
        project_id=view.project.id,
    )
    html = shell_v3.render_document(
        title=f"Faceless Studio — {title}",
        active="configuracoes",
        crumb=f"Configurações / {title}",
        body_html=body,
        nonce=nonce,
        projects=list(view.projects),
        project_id=view.project.id,
        cost_note="",
        page_js=panel_channels._channels_page_js(view.project.id) + CHANNEL_STYLE_JS,
        extra_css=panel_channels.CHANNELS_CSS + CHANNEL_STYLE_CSS,
    )
    return html, legacy._headers(nonce)
