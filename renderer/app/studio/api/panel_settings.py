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
        ("producao",),
    ),
}

_CARDS = {
    "perfil": panel_channels._profile_card,
    "aparencia": panel_channels._appearance_card,
    "orcamento": panel_channels._budget_card,
    "providers": panel_channels._providers_card,
    "preferencias": panel_channels._prefs_card,
    "producao": lambda view: _producao_cards(view),
}


_PERFIS = (("ECONOMY", "⚡ Econômico", "Prioriza custo conhecido. Rápido e simples."),
           ("BALANCED", "⚖ Equilibrado", "Equilibra custo e qualidade elegível."),
           ("PREMIUM", "💎 Premium", "Prioriza qualidade. Exige providers de alta qualidade."))
_PERFIL_ROTULO = {valor: rotulo.split(" ", 1)[1] for valor, rotulo, _ in _PERFIS}
_ROTAS = (("TEXT", "Roteiro (texto)"), ("VOICE", "Narração (voz)"), ("IMAGE", "Imagens por IA"),
          ("SEARCH", "Banco de mídia (stock)"), ("RENDERER", "Montagem de vídeo"))

_PRODUCAO_JS = """
(function () {
  var form = document.getElementById('budget-form');
  if (!form) return;
  form.querySelectorAll('input[name="economic_profile"]').forEach(function (r) {
    r.addEventListener('change', function () {
      form.querySelectorAll('[data-perfil-choice]').forEach(function (c) {
        c.setAttribute('aria-pressed', String(c.querySelector('input').checked));
      });
    });
  });
  form.querySelectorAll('input[type=range][data-out]').forEach(function (r) {
    var saida = document.getElementById(r.getAttribute('data-out'));
    r.addEventListener('input', function () {
      if (saida) saida.textContent = 'US$ ' + Number(r.value).toFixed(r.step && r.step.indexOf('.') >= 0 ? 2 : 0).replace('.', ',');
    });
  });
})();
"""


def _producao_cards(view: ChannelsPageView) -> str:
    """`pgSettings` → Produção & Orçamento: perfil, orçamento e saída, roteamento de providers.

    Perfil, tetos e roteamento são dado real. Resolução, quadros/s, preferência de mídia, falha de
    provider e B-roll não têm configuração por canal no produto: aparecem desabilitados, "Em breve".
    """
    budget = view.budget
    if budget is None:
        return '<div class="card"><p class="sub">Sem canal selecionado: não há orçamento de canal para exibir.</p></div>'
    limits = budget.limits
    atual = limits.economic_profile.value
    amount = panel_channels._input_amount
    perfis = "".join(
        f'<label class="choice" data-perfil-choice aria-pressed="{"true" if v == atual else "false"}">'
        f'<input type="radio" name="economic_profile" value="{v}"{" checked" if v == atual else ""} class="sr-only">'
        f'<b>{t}</b><p class="sub">{d}</p></label>' for v, t, d in _PERFIS)
    hm, hv = float(limits.hard_monthly_usd), float(limits.hard_video_usd)
    max_m, max_v = max(100, int(hm) + 1), max(5.0, round(hv + 0.1, 1))
    gasto = float(budget.summary.spent_usd)
    pct = min(100, round(gasto / hm * 100)) if hm > 0 else 0
    desconhecidas = budget.summary.unknown_calls
    nota_desc = (f" {desconhecidas} chamada(s) de custo desconhecido não entram na soma." if desconhecidas else "")
    origem = ("Limites persistidos neste canal." if budget.configured
              else "Nenhum limite persistido: valem os tetos padrão do servidor; salvar passa a persistir.")

    def em_breve(i, rotulo, opcoes):
        ops = "".join(f"<option>{o}</option>" for o in opcoes)
        return (f'<div class="field"><label for="{i}">{rotulo}</label><select id="{i}" disabled>{ops}</select></div>')

    orcamento = f"""<div class="card"><h3 style="margin-bottom:12px">Orçamento e saída</h3>
      <div class="field"><label for="limite-hard-mensal">Teto mensal: <b id="p1v">US$ {hm:.0f}</b></label>
        <input type="range" id="limite-hard-mensal" name="hard_monthly_usd" min="5" max="{max_m}" step="1" value="{hm:.0f}" data-out="p1v"></div>
      <div class="field"><label for="limite-hard-video">Teto por vídeo: <b id="p2v">US$ {hv:.2f}</b></label>
        <input type="range" id="limite-hard-video" name="hard_video_usd" min="0.2" max="{max_v}" step="0.1" value="{hv:.1f}" data-out="p2v"></div>
      <input type="hidden" id="limite-soft-mensal" name="soft_monthly_usd" value="{e(amount(limits.soft_monthly_usd))}">
      <input type="hidden" id="limite-soft-video" name="soft_video_usd" value="{e(amount(limits.soft_video_usd))}">
      <div class="grid2">{em_breve("p3", "Resolução", ("1080p", "720p"))}{em_breve("p4", "Quadros/s", ("30", "24", "60"))}</div>
      {em_breve("p5", "Preferência de mídia", ("Banco de mídia primeiro", "IA primeiro", "Somente meus arquivos"))}
      {em_breve("p6", "Se um provider falhar", ("Pedir confirmação", "Usar alternativa dentro dos limites"))}
      <div class="field"><label class="tog"><input type="checkbox" id="p7" checked disabled><i></i><span>B-roll ligado por padrão</span></label></div>
      <p class="sample">Resolução, quadros/s, mídia, falha de provider e B-roll: em breve (ainda sem configuração por canal).</p>
      <div class="hr"></div><p class="lbl">Uso no mês</p><div class="bar"><b style="width:{pct}%"></b></div>
      <p class="sample" style="margin-top:4px">{e(panel_channels._usd(gasto, zero_text="US$ 0 (nenhum gasto registrado)"))} usados (real + estimado).{e(nota_desc)}</p>
      <div class="row" style="margin-top:14px"><button class="btn primary small" type="submit" id="btn-salvar-orcamento">Salvar limites</button>
        <span class="sample">{e(origem)}</span></div>
      <div id="budget-feedback" class="form-feedback" role="status" aria-live="polite"></div></div>"""

    por_tipo = {d.kind.name: d for d in view.routes}
    falhas = {k.name: r for k, r in view.route_failures}
    rotulo_perfil = _PERFIL_ROTULO.get(atual, atual)
    linhas, faltando = [], 0
    for kind, rotulo in _ROTAS:
        d = por_tipo.get(kind)
        if d is not None:
            pill = f'<span class="pill ok">✓ {e(d.primary.name)}</span>'
            fb = " → ".join(e(c.name) for c in d.fallbacks)
            texto = (f'<p class="sample" style="margin-top:4px">Escolha no perfil {e(rotulo_perfil)}'
                     f'{" · fallback: " + fb if fb else " · sem fallback"}</p>')
        else:
            faltando += 1
            pill = '<span class="pill bad">✕ sem provider</span>'
            motivo = (panel_channels._route_failure_text(next(k for k, _ in view.route_failures if k.name == kind), limits.economic_profile, falhas[kind])
                      if kind in falhas else "Nenhuma porta de provider configurada para esta tarefa.")
            texto = f'<p class="sample" style="color:var(--bad);margin-top:6px">{e(motivo)}</p>'
        linhas.append(
            f'<div class="card flat" style="padding:12px 14px"><div class="between"><b>{rotulo}</b>{pill}</div>{texto}'
            f'<div class="row" style="margin-top:8px"><label class="sr-only" for="rt-{kind}">Provider de {rotulo}</label>'
            f'<select id="rt-{kind}" disabled style="max-width:300px"><option>Automático (pelo perfil)</option></select></div></div>')
    pronto = ('<span class="pill ok">✓ Pronto para produzir</span>' if not faltando
              else f'<span class="pill bad">✕ {faltando} sem provider</span>')
    roteamento = f"""<div class="card" style="margin-top:16px"><div class="between"><div><h3>Roteamento de providers deste canal</h3>
      <p class="sub">Escolha automática pelo perfil {e(rotulo_perfil)}, recalculada a cada leitura. Fixar um provider por tarefa ainda não está disponível.</p></div>{pronto}</div>
      <div class="grid2" style="margin-top:12px">{"".join(linhas)}</div>
      <p class="sample" style="margin-top:10px">Custo estimado não é preço cobrado e custo desconhecido não é tratado como zero. Sem provider elegível, a tarefa aparece indisponível com o motivo.</p></div>"""
    return f"""<form id="budget-form" data-project-id="{e(view.project.id)}">
      <div class="grid2"><div class="card"><h3 style="margin-bottom:12px">Perfil de produção</h3>
        <div class="stack" style="gap:10px">{perfis}</div>
        <p class="sample" style="margin-top:8px">O perfil muda o roteamento de providers abaixo e é salvo junto com os limites.</p></div>
      {orcamento}</div></form>{roteamento}"""


_MARCA_JS = """
(function () {
  var form = document.getElementById('channel-form');
  if (!form) return;
  form.addEventListener('click', function (ev) {
    var el = ev.target.closest ? ev.target.closest('[data-mset]') : null;
    if (!el) return;
    ev.preventDefault();
    var alvo = document.getElementById(el.getAttribute('data-mset'));
    if (alvo) alvo.value = el.getAttribute('data-v');
    form.querySelectorAll('[data-mset="' + el.getAttribute('data-mset') + '"]').forEach(function (o) {
      o.setAttribute('aria-pressed', o === el ? 'true' : 'false');
    });
  });
  var r = document.getElementById('canal-duracao');
  var saida = document.getElementById('s5v');
  if (r && saida) r.addEventListener('input', function () { saida.textContent = r.value + ' s'; });
})();
"""


def _seg(alvo: str, opcoes, atual: str) -> str:
    botoes = "".join(f'<button type="button" aria-pressed="{"true" if v == atual else "false"}" data-mset="{alvo}" data-v="{v}">{e(t)}</button>'
                     for v, t in opcoes)
    return f'<div class="seg" role="group">{botoes}</div>'


def _marca_cards(view: ChannelsPageView) -> str:
    """`pgSettings` → Marca & Editorial: dois cartões. Os ids do formulário são os do perfil real."""
    project, profile = view.project, view.profile
    mode = getattr(getattr(profile, "default_mode", None), "value", getattr(profile, "default_mode", "piloto")) if profile else "piloto"
    fmt = getattr(getattr(profile, "default_format", None), "value", getattr(profile, "default_format", "short")) if profile else "short"
    nome = profile.name if profile else project.name
    dur = int(profile.target_duration_s) if profile and profile.target_duration_s else 60
    languages = (("pt-BR", "Português (BR)"), ("en-US", "English"), ("es-ES", "Español"))
    lang = profile.language if profile else (project.language or "pt-BR")
    idiomas = "".join(f'<option value="{c}"{" selected" if c == lang else ""}>{t}</option>' for c, t in languages)
    if lang not in {c for c, _ in languages}:
        idiomas += f'<option value="{e(lang)}" selected>{e(lang)}</option>'
    estilo_atual = profile.style_id if profile else ""
    estilos = '<option value="">Padrão do estúdio</option>' + "".join(
        f'<option value="{e(st.id)}"{" selected" if st.id == (estilo_atual or "") else ""}>{e(st.name)}</option>'
        for st in view.styles)
    pillars = ", ".join(profile.pillars) if profile else ""

    def campo(i, rotulo, valor, extra=""):
        return f'<div class="field"><label for="{i}">{rotulo}</label><input type="text" id="{i}" value="{e(valor)}" {extra}></div>'

    sem_perfil = ('' if profile else '<div class="note" style="margin-bottom:14px" id="canal-sem-perfil">Este canal ainda não tem perfil editorial. '
                  'Preencha e salve para criar a versão 1.</div>')
    salvar = "Salvar nova versão" if profile else "Criar perfil do canal"
    versao = f"Versão {profile.version} registrada." if profile else ""
    return f"""{sem_perfil}
      <form id="channel-form" data-profile-id="{e(profile.id if profile else "")}" data-profile-version="{profile.version if profile else 0}" data-project-id="{e(project.id)}">
        <input type="hidden" id="canal-modo" value="{e(mode)}"><input type="hidden" id="canal-formato" value="{e(fmt)}">
        <input type="hidden" id="canal-identidade" value="{e(profile.visual_identity if profile else "")}">
        <div class="grid2"><div class="card"><h3 style="margin-bottom:12px">Identidade e linha editorial</h3>
          {campo("canal-nome", "Nome do canal", nome, 'maxlength="120" required')}
          {campo("canal-nicho", "Nicho", project.niche or "", 'disabled title="Definido na criação do canal."')}
          {campo("canal-publico", "Público", profile.audience if profile else "", 'maxlength="500"')}
          <div class="field"><label for="canal-estrategia">Estratégia</label><textarea id="canal-estrategia" rows="3" maxlength="500">{e(profile.strategy if profile else "")}</textarea></div>
          {campo("canal-pilares", "Pilares (separados por vírgula)", pillars, 'maxlength="600"')}
          {campo("canal-narrativa", "Estilo narrativo", profile.narrative if profile else "", 'maxlength="4000"')}
          {campo("canal-cta", "Chamada para ação padrão", profile.cta if profile else "", 'maxlength="500"')}
          <div class="grid2"><div class="field"><label for="canal-idioma">Idioma</label><select id="canal-idioma">{idiomas}</select></div>
            <div class="field"><label for="canal-cor">Cor da marca</label><input type="color" id="canal-cor" value="#8f6ef7" disabled title="Ainda não é gravada no perfil do canal." style="width:60px;height:34px;padding:2px"></div></div>
        </div>
        <div class="card"><h3 style="margin-bottom:12px">Padrões para novos vídeos</h3>
          <div class="field"><span class="lbl">Modo padrão</span>{_seg("canal-modo", [("piloto", "⚡ Piloto automático"), ("diretor", "🎬 Modo Diretor")], mode)}</div>
          <div class="field"><span class="lbl">Formato padrão</span>{_seg("canal-formato", [("short", "Short · 9:16"), ("long", "Vídeo · 16:9")], fmt)}</div>
          <div class="field"><label for="canal-duracao">Duração padrão: <b id="s5v">{dur} s</b></label><input type="range" id="canal-duracao" min="15" max="{max(600, dur)}" step="5" value="{dur}"></div>
          <div class="field"><label for="canal-voz">Voz padrão</label><input type="text" id="canal-voz" maxlength="200" value="{e(profile.voice if profile else "")}" placeholder="provedor:modelo"></div>
          <div class="field"><label for="canal-estilo">Estilo visual vinculado (Biblioteca)</label><select id="canal-estilo">{estilos}</select></div>
          <div class="grid2"><div class="field"><label for="canal-fonte-legenda">Fonte da legenda</label><select id="canal-fonte-legenda" disabled title="A legenda é definida pelo estilo visual vinculado."><option>Inter</option><option>Roboto</option><option>Georgia</option></select></div>
            <div class="field"><label for="canal-estilo-legenda">Estilo da legenda</label><select id="canal-estilo-legenda" disabled title="A legenda é definida pelo estilo visual vinculado."><option>Destaque por palavra</option><option>Caixa discreta</option><option>Texto simples</option></select></div></div>
          <p class="sample" style="margin:-4px 0 12px">Cor da marca e legenda: em breve (a legenda segue o estilo visual vinculado; ainda sem ajuste por canal aqui).</p>
          <div class="note info">O piloto automático sempre para na aprovação. Publicar exige um clique seu.</div>
          <div class="row" style="margin-top:14px"><button class="btn primary small" type="submit" id="btn-salvar-canal">{salvar}</button><span class="sample">{versao}</span></div>
          <div id="channel-feedback" class="form-feedback" role="status" aria-live="polite"></div>
        </div></div>
      </form>"""


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
    if section == "marca":
        return _render_marca(view, nonce, _marca_cards(view) + identidade_html)
    # `pgSettings` não tem cartão de cabeçalho por aba: o título/subtítulo da página já dizem o canal.
    content_html = f"""
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
        page_js=panel_channels._channels_page_js(view.project.id) + CHANNEL_STYLE_JS + (_PRODUCAO_JS if section == "producao" else ""),
        extra_css=panel_channels.CHANNELS_CSS + CHANNEL_STYLE_CSS,
    )
    return html, legacy._headers(nonce)


def _render_marca(view: ChannelsPageView, nonce: str, content_html: str) -> tuple[str, dict[str, str]]:
    body = shell_v3.render_settings_page_body(active_section="marca", section_title="Marca e estilo",
                                              content_html=content_html, project_id=view.project.id)
    html = shell_v3.render_document(
        title="Faceless Studio — Marca e estilo", active="configuracoes", crumb="Configurações / Marca e estilo",
        body_html=body, nonce=nonce, projects=list(view.projects), project_id=view.project.id, cost_note="",
        page_js=panel_channels._channels_page_js(view.project.id) + CHANNEL_STYLE_JS + _MARCA_JS,
        extra_css=panel_channels.CHANNELS_CSS + CHANNEL_STYLE_CSS)
    return html, legacy._headers(nonce)
