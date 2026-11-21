"""Casca da UX V3 (proposta aprovada): barra lateral, topbar, tema e diálogo de novo canal.

Fonte da verdade visual: `docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html` — o CSS vem
verbatim de lá (`shell_v3_css.V3_CSS`). Aqui ficam só a marcação da casca e as poucas extensões
que o produto precisa e o protótipo (estático) não tem.

Regras que atravessam todas as telas V3:
- CSP por nonce: nenhum handler inline; todo comportamento vem de `<script nonce>`.
- Exatamente um `<h1>` por página (o da tela) e um `aria-current="page"` na navegação principal.
- Dado ausente aparece como texto explícito, nunca como zero ou número inventado.
"""

from __future__ import annotations

from html import escape as e

from .shell_v3_css import V3_CSS

# Extensões do produto sobre o CSS aprovado (o protótipo é estático e não cobre estes casos).
PRODUCT_CSS = """
/* seletor de canal + novo canal na topbar */
.tools .link-btn { white-space: nowrap; }
.nota-custo { font-size: 12px; color: var(--muted); padding: 4px 11px 8px; margin: 0; }
.dialogo-corpo .campo input, .dialogo-corpo .campo select { width: 100%; }
.feedback { font-size: 12px; color: var(--muted); min-height: 18px; margin: 8px 0 0; }
.feedback[data-tipo="erro"] { color: var(--warn); font-weight: 600; }
.cartao-tendencia .selo { margin-left: 4px; }
.cartao-projeto a:focus-visible { outline-offset: -2px; }
.pagina-cab { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start;
  flex-wrap: wrap; }
.tabela-lista { width: 100%; border-collapse: collapse; font-size: 13px; }
.tabela-lista th, .tabela-lista td { text-align: left; padding: 12px 10px; border-bottom: 1px solid var(--line); }
.tabela-lista th { color: var(--muted); font-weight: 600; font-size: 12px; }
.tabela-lista a { font-weight: 650; }
.rolagem-x { overflow-x: auto; }

/* Compatibilidade e layout para telas de Configurações, Execução e formulários */
:root {
  --border: var(--line);
  --border-soft: var(--line);
  --border-hover: var(--accent);
  --surface: var(--panel);
  --surface-raised: var(--panel2);
  --input-bg: var(--panel2);
  --text-dim: var(--sub);
  --text-muted: var(--muted);
  --primary: var(--accent);
  --primary-focus: var(--accent);
  --gold: var(--warn);
  --info: var(--accent);
  --warn-surface: var(--soft);
  --info-surface: var(--soft);
  --bad: var(--err);
}
.card, .painel { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 24px; margin-bottom: 18px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12); }
.card h2, .painel h2 { font-size: 16px; margin: 0 0 10px; font-weight: 750; color: light-dark(#111116, #ffffff); letter-spacing: -0.3px; }
.card h3, .painel h3 { font-size: 15px; margin: 0 0 8px; font-weight: 700; color: light-dark(#111116, #ffffff); letter-spacing: -0.2px; }
.card.empty, .painel.empty { text-align: center; padding: 36px 20px; color: var(--muted); }
.config-corpo { display: flex; flex-direction: column; gap: 16px; }
.spread, .acoes { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.acoes-linha { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.dim { color: var(--sub); font-size: 12px; }
.muted { color: var(--muted); font-size: 13px; }
.fine, .micro { color: var(--sub); font-size: 11.5px; line-height: 1.45; }
.kv { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid var(--line); font-size: 12.5px; }
.kv:last-child { border-bottom: 0; }
.kv span:last-child { color: light-dark(#111116, #ffffff); font-weight: 600; }
.item-title { font-weight: 650; font-size: 13.5px; color: light-dark(#111116, #ffffff); }
.item-sub { color: var(--muted); font-size: 12px; margin-top: 2px; }

/* Botões do Design System V3 */
.btn {
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
}
.btn:hover:not(:disabled) {
  background: var(--panel3, #22222d);
  border-color: #595268;
}
.btn-primary, .btn-primario {
  background: var(--accentfill); color: var(--onaccent); border-color: var(--accentfill); font-weight: 700;
  box-shadow: 0 4px 14px color-mix(in srgb, var(--accentfill) 32%, transparent);
}
.btn-primary:hover, .btn-primario:hover { filter: brightness(1.1); box-shadow: 0 4px 20px color-mix(in srgb, var(--accentfill) 45%, transparent); }
.btn-danger, .btn-perigo { background: #7a2436; color: #fff; border-color: #7a2436; font-weight: 650; }
.btn-danger:hover, .btn-perigo:hover { background: #8e2b40; filter: brightness(1.08); }
.btn-sm { padding: 6px 12px; font-size: 12px; border-radius: 8px; }
.btn-ghost { background: transparent; border-color: var(--line); }
.btn-ghost:hover { background: var(--panel2); border-color: #595268; }

/* Campos e formulários V3 */
.field, .campo { margin-bottom: 18px; display: flex; flex-direction: column; gap: 6px; }
.field > label, .campo > label, .campo > .rotulo { display: block; font-size: 13px; font-weight: 650; margin-bottom: 2px; color: light-dark(#1c1b22, #ffffff); }
.field input, .field select, .field textarea, .campo input, .campo select, .campo textarea, .input {
  width: 100%; border: 1px solid var(--line); background: var(--panel2); color: light-dark(#111116, #ffffff);
  border-radius: 9px; padding: 11px 12px; font: inherit; font-size: 13px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.field input:focus, .field select:focus, .field textarea:focus, .campo input:focus, .campo select:focus, .campo textarea:focus, .input:focus {
  border-color: var(--accentfill) !important; outline: none;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accentfill) 20%, transparent);
}
.hint, .dica { font-size: 12px; color: var(--muted); margin: 3px 0 0; line-height: 1.45; }
.error-msg, .campo-erro { font-size: 12px; color: var(--warn); font-weight: 600; margin-top: 4px; }
.form-feedback, .feedback { font-size: 12px; color: var(--muted); min-height: 18px; margin-top: 6px; }

/* ComboBox e Select estilizados (Modern Web Guidance › branded-select-styling) */
select, .field select, .campo select, select.input {
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23a19cad' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 14px center;
  background-size: 16px 16px;
  padding-right: 42px !important;
  cursor: pointer;
}
select option, .field select option, .campo select option, select.input option {
  background-color: var(--panel2, #1a1a22) !important;
  color: #ffffff !important;
  padding: 10px 14px !important;
  font-size: 13px;
}
select option:checked {
  background-color: var(--accentfill, #7928ca) !important;
  color: #ffffff !important;
}
@supports (appearance: base-select) {
  select, .field select, .campo select, select.input, select.canal-select {
    appearance: base-select;
    background-image: none !important;
  }
  select::picker-icon {
    color: var(--muted, #a19cad);
  }
  select::picker(select) {
    background-color: var(--panel2, #1a1a22);
    border: 1px solid var(--line, #2a2833);
    border-radius: 10px;
    padding: 6px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    color: #ffffff;
  }
}

/* Estados e Badges */
.state { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 650; }
.state.s-done { color: var(--ok); }
.state.s-run { color: var(--accent); }
.state.s-act, .state.s-active { color: var(--warn); }
.state.s-fail { color: var(--err); }
.state.s-idle, .state.state-idle { color: var(--muted); }

/* Indicador de atividade e spinner (Modern Web Guidance › spinner) */
@keyframes spin {
  to { transform: rotate(1turn); }
}
.state.s-run .state-icon {
  display: inline-block;
  animation: spin 1.2s linear infinite;
  transform-origin: center center;
}

/* Spinner integrado nos botões para ações assíncronas */
.btn.carregando, .btn.is-loading {
  position: relative;
  pointer-events: none;
  opacity: 0.85;
}
.btn.carregando::before, .btn.is-loading::before {
  content: '';
  display: inline-block;
  width: 14px;
  height: 14px;
  margin-right: 8px;
  border: 2.5px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 0.75s linear infinite;
  vertical-align: -2px;
}

/* Barra de progresso de atividade no topo da página (padrão YouTube/Vercel/Modern Web) */
#barra-progresso-topo {
  position: fixed;
  top: 0;
  left: 0;
  height: 4px;
  width: 0%;
  background: linear-gradient(90deg, var(--accent), var(--accentfill), #e0aaff);
  z-index: 99999;
  transition: width 0.25s ease, opacity 0.3s ease;
  pointer-events: none;
  box-shadow: 0 0 14px var(--accentfill), 0 0 24px var(--accent);
  opacity: 0;
}
#barra-progresso-topo.ativo {
  opacity: 1;
}
#barra-progresso-topo.finalizado {
  width: 100% !important;
  opacity: 0;
  transition: width 0.12s ease, opacity 0.35s ease 0.1s;
}

/* Indicador flutuante de carregamento altamente visível */
#indicador-carregando {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 99999;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: var(--panel2, #1a1a22);
  color: #ffffff;
  border: 1px solid var(--accentfill);
  border-radius: 999px;
  padding: 10px 18px;
  font-size: 13px;
  font-weight: 650;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5), 0 0 18px color-mix(in srgb, var(--accentfill) 40%, transparent);
  pointer-events: none;
  opacity: 0;
  transform: translateY(12px) scale(0.96);
  transition: opacity 0.22s ease, transform 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}
#indicador-carregando.ativo {
  opacity: 1;
  transform: translateY(0) scale(1);
}
.indicador-spinner {
  width: 15px;
  height: 15px;
  border: 2.5px solid var(--accent);
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 0.75s linear infinite;
  flex-shrink: 0;
}

/* Shimmer / Skeleton screens para carregamento de conteúdo */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton, .esqueleto {
  background: linear-gradient(90deg, var(--panel2) 25%, var(--soft) 50%, var(--panel2) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.8s infinite ease-in-out;
  border-radius: 8px;
}

@media (prefers-reduced-motion: reduce) {
  .state.s-run .state-icon, .btn.carregando::before, .btn.is-loading::before, .skeleton, .esqueleto, .indicador-spinner {
    animation: none !important;
  }
}

/* Ação necessária e avisos */
.act-card { border-color: var(--warn); border-left-width: 4px; background: var(--soft); }

/* Etapas e checklist da execução */
.steps { list-style: none; margin: 12px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.steps li {
  display: flex; gap: 11px; align-items: center; padding: 10px 12px;
  background: var(--panel2); border: 1px solid var(--line); border-radius: 9px;
  font-size: 13px; font-weight: 550;
}
.steps li[aria-current="step"] {
  border-color: var(--accentfill); background: var(--soft); font-weight: 700; color: light-dark(#111116, #ffffff);
}

/* Detalhe do vídeo e diagnóstico */
.timeline { list-style: none; padding-left: 1.5rem; position: relative; margin: 0; }
.timeline-item { position: relative; margin-bottom: 1.25rem; }
.timeline-dot {
  position: absolute; left: -1.5rem; top: 0.25rem; width: 10px; height: 10px;
  border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 3px var(--soft);
}
.timeline-title { font-weight: 650; font-size: 0.875rem; color: light-dark(#111116, #ffffff); }
.timeline-desc { font-size: 0.8rem; color: var(--muted); margin-top: 0.15rem; }
.advanced { margin-top: 1.25rem; padding: 0; }
.advanced-summary { cursor: pointer; padding: 1rem 1.25rem; font-weight: 650; list-style: none; color: light-dark(#111116, #ffffff); }
.advanced-summary::-webkit-details-marker { display: none; }
.advanced-summary::after { content: "▾"; float: right; color: var(--muted); }
.advanced[open] .advanced-summary { border-bottom: 1px solid var(--line); }
.advanced-body { padding: 1.25rem; font-size: 0.85rem; }
.advanced-body code { color: var(--text); word-break: break-all; }
.failure-summary {
  background: var(--soft); border: 1px solid var(--err); border-radius: 8px;
  padding: 1rem; margin-top: 1rem; color: var(--text);
}
.failure-summary p { margin-bottom: 0.4rem; }
.failure-summary p:last-child { margin-bottom: 0; }
.warning {
  background: var(--soft); border-left: 3px solid var(--warn); padding: 0.6rem 0.8rem;
  margin-top: 0.75rem; font-size: 0.8rem;
}
/* Badges de situação */
span.pill {
  display: inline-flex; align-items: center; padding: 0.2rem 0.55rem; border-radius: 999px;
  font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
}
.pill-PENDING { background: var(--panel2); color: var(--muted); }
.pill-IN_PRODUCTION { background: var(--soft); color: var(--accent); border: 1px solid var(--accent); }
.pill-AWAITING_APPROVAL { background: var(--soft); color: var(--warn); border: 1px solid var(--warn); }
.pill-APPROVED { background: var(--soft); color: var(--ok); border: 1px solid var(--ok); }
.pill-COMPLETED { background: var(--soft); color: var(--ok); }
.pill-FAILED { background: var(--soft); color: var(--err); border: 1px solid var(--err); }
.pill-REJECTED { background: var(--soft); color: var(--err); }

/* Filtros por rádio e pílulas interativas (Tela de vídeos e formulários) */
.pills {
  border: 0; padding: 4px; margin: 0; display: inline-flex; gap: 5px; flex-wrap: wrap;
  background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
}
.filtros { border: 0; padding: 0; margin: 0; }
.filtros legend { font-size: 13px; font-weight: 650; margin-bottom: 8px; padding: 0; }

label.pill, .pills .pill {
  display: inline-flex; align-items: center; gap: 8px; border: 1px solid transparent;
  background: transparent; border-radius: 8px; padding: 7px 13px; font-size: 12.5px;
  font-weight: 600; color: var(--muted); cursor: pointer; text-transform: none; letter-spacing: normal;
  transition: all 0.15s ease; user-select: none;
}
label.pill:hover, .pills .pill:hover {
  color: light-dark(#111116, #ffffff); background: var(--panel2);
}

/* Custom radio visual elegante */
label.pill input[type="radio"], .pills .pill input[type="radio"] {
  appearance: none; -webkit-appearance: none;
  width: 14px; height: 14px; border: 1.5px solid var(--line); border-radius: 50%;
  margin: 0; display: grid; place-content: center; cursor: pointer;
  background: var(--panel2); transition: border-color 0.15s ease, background-color 0.15s ease;
}
label.pill input[type="radio"]::before, .pills .pill input[type="radio"]::before {
  content: ""; width: 6px; height: 6px; border-radius: 50%;
  transform: scale(0); transition: transform 0.15s ease-in-out;
  background-color: var(--accentfill);
}
label.pill input[type="radio"]:checked, .pills .pill input[type="radio"]:checked {
  border-color: var(--accentfill);
}
label.pill input[type="radio"]:checked::before, .pills .pill input[type="radio"]:checked::before {
  transform: scale(1);
}
label.pill:has(input[type="radio"]:checked), .pills .pill:has(input[type="radio"]:checked) {
  border-color: var(--line); background: var(--panel2); color: light-dark(#111116, #ffffff);
  font-weight: 680; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.22);
}

.nav-item-unavailable { opacity: 0.55; cursor: not-allowed; }
.nav-tag { font-size: 0.65rem; padding: 2px 5px; border-radius: 4px; background: var(--panel2); color: var(--muted); margin-left: 6px; }
"""

_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true" '
        'focusable="false">{}</svg>')

_ICONS = {
    "inicio": _SVG.format('<path d="m3 11 9-8 9 8v9H3z"/><path d="M9 20v-7h6v7"/>'),
    "novo-video": _SVG.format('<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>'),
    "videos": _SVG.format('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 9 5 3-5 3z"/>'),
    "tendencias": _SVG.format('<path d="M9 18h6m-5 3h4M8 14c-6-7-1-12 4-12s10 5 4 12l-1 2H9z"/>'),
    "desempenho": _SVG.format('<path d="M3 20h18M6 16V9m6 7V4m6 12v-5"/>'),
    "configuracoes": _SVG.format(
        '<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/>'),
}

NAV_OPERACAO: tuple[tuple[str, str, str], ...] = (
    ("inicio", "Início", "/studio/panel"),
    ("novo-video", "Novo vídeo", "/studio/panel/novo-video"),
    ("videos", "Vídeos", "/studio/panel/videos"),
    ("tendencias", "Tendências", "/studio/panel/tendencias"),
    ("desempenho", "Desempenho", "/studio/panel/analytics"),
)
CONFIG_HREF = "/studio/configuracoes/canais"

# Telas que existem fora do menu e herdam o item atual do menu mais próximo.
_ALIASES = {
    "producao": "videos",
    "analytics": "desempenho",
    "video": "videos",
    "roteiro": "videos",
    "execucao": "videos",
    "preview": "videos",
    "canais": "configuracoes",
    "estilos": "configuracoes",
    "conexoes": "configuracoes",
    "equipe": "configuracoes",
}

SETTINGS_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("canais", "Canais", "/studio/canais"),
    ("estilos", "Estilos", "/studio/panel/estilos"),
    ("conexoes", "Conexões", "/studio/panel/conexoes"),
    ("equipe", "Equipe", "/studio/panel/equipe"),
)


def render_settings_nav(active_section: str) -> str:
    items = []
    for key, label, href in SETTINGS_SECTIONS:
        curr = ' aria-current="page"' if key == active_section else ""
        items.append(f'<li><a href="{href}"{curr}>{e(label)}</a></li>')
    return f"""<nav aria-label="Seções de configuração">
      <ul class="menu-config" id="menu-config">
        {"".join(items)}
      </ul>
    </nav>"""


def render_settings_page_body(*, active_section: str, section_title: str, content_html: str) -> str:
    return f"""      <section class="pagina" id="pagina-configuracoes" aria-labelledby="t-config">
        <p class="eyebrow">SEU ESTÚDIO</p>
        <h1 class="h1" id="t-config">Configurações · {e(section_title)}</h1>
        <p class="lead" style="margin-bottom:24px">Fora do caminho quando você está criando.</p>

        <div class="grade-config">
          {render_settings_nav(active_section)}
          <div class="config-corpo">
            {content_html}
          </div>
        </div>
      </section>"""

_NAV_LABELS = {key: label for key, label, _ in NAV_OPERACAO}
_NAV_LABELS["configuracoes"] = "Configurações"


def _nav_item(key: str, label: str, href: str, active: str) -> str:
    current = ' aria-current="page"' if key == active else ""
    return f'<li><a href="{e(href)}"{current}>{_ICONS[key]}{e(label)}</a></li>'


def render_sidebar(*, active: str, cost_note: str = "") -> str:
    active = _ALIASES.get(active, active)
    items = "".join(_nav_item(k, label, href, active) for k, label, href in NAV_OPERACAO)
    cost = f'<p class="nota-custo">{e(cost_note)}</p>' if cost_note else ""
    return f"""<aside class="side">
    <div class="brand">
      <span class="brand-logo" aria-hidden="true">✦</span>
      <div>Faceless <span class="muted">Studio</span><small>ESTÚDIO DO CANAL</small></div>
    </div>
    <nav aria-label="Principal">
      <p class="side-caption" id="rotulo-operacao">Operação</p>
      <ul class="nav-list" aria-labelledby="rotulo-operacao">{items}</ul>
    </nav>
    <div class="side-bottom">
      <nav aria-label="Configuração">
        <ul class="nav-list">{_nav_item("configuracoes", "Configurações", CONFIG_HREF, active)}</ul>
      </nav>
      {cost}
      <div class="side-note"><span class="avatar" aria-hidden="true">E</span>
        <div>Estúdio do canal<br><span class="micro">Dados reais do Studio</span></div></div>
    </div>
  </aside>"""


def render_topbar(*, crumb: str, projects: list[tuple[str, str]], project_id: str) -> str:
    if projects:
        options = "".join(
            f'<option value="{e(pid)}"{" selected" if pid == project_id else ""}>{e(name)}</option>'
            for pid, name in projects
        )
        select = (f'<label class="sr-only" for="canal-ativo">Canal ativo</label>'
                  f'<select class="canal-select" id="canal-ativo">{options}</select>')
    else:
        select = '<span class="micro" id="sem-canal">Nenhum canal cadastrado</span>'
    return f"""<header class="top">
      <p class="crumb">Estúdio &nbsp;/&nbsp; <b>{e(crumb)}</b></p>
      <div class="tools">
        {select}
        <button class="icon-btn" type="button" id="btn-novo-canal" title="Novo canal" aria-label="Novo canal"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true" focusable="false"><path d="M12 5v14M5 12h14"/></svg></button>
        <button class="icon-btn" type="button" id="btn-tema" aria-pressed="false" hidden
                title="Alternar tema claro/escuro" aria-label="Alternar tema claro/escuro">◐</button>
        <a class="icon-btn" href="{CONFIG_HREF}" title="Configurações" aria-label="Configurações">⚙</a>
      </div>
    </header>"""


def render_novo_canal_dialog() -> str:
    return """<dialog id="dlg-canal" aria-labelledby="t-dlg-canal">
    <div class="dialogo-cab">
      <h2 id="t-dlg-canal">Novo canal</h2>
      <button class="icon-btn" type="button" data-fechar-dialogo aria-label="Fechar">✕</button>
    </div>
    <div class="dialogo-corpo">
      <form id="form-canal">
        <div class="campo">
          <label for="canal-nome">Nome do canal</label>
          <input type="text" id="canal-nome" name="name" minlength="1" maxlength="120" required
                 placeholder="Ex.: Curiosidades do Mundo">
        </div>
        <div class="campo">
          <label for="canal-nicho">Nicho editorial <span class="micro">(opcional)</span></label>
          <input type="text" id="canal-nicho" name="niche" maxlength="200"
                 placeholder="Ex.: Música, mistérios, curiosidades">
        </div>
        <div class="campo">
          <label for="canal-idioma">Idioma</label>
          <select id="canal-idioma" name="language">
            <option value="pt-BR" selected>Português (pt-BR)</option>
            <option value="en-US">English (en-US)</option>
            <option value="es-ES">Español (es-ES)</option>
          </select>
        </div>
        <div class="acoes">
          <p class="feedback" id="canal-feedback" role="status"></p>
          <div class="acoes-linha">
            <button class="btn" type="button" data-fechar-dialogo>Fechar</button>
            <button class="btn btn-primario" type="submit" id="btn-salvar-canal">Cadastrar canal</button>
          </div>
        </div>
      </form>
    </div>
  </dialog>"""


# Aplicado cedo (no <head>) para a escolha de tema não piscar. A chave é a mesma das telas legadas.
THEME_BOOT_JS = (
    "try{var t=localStorage.getItem('studio-theme');"
    "if(t==='light'||t==='dark'){var r=document.documentElement;"
    "r.style.colorScheme=t;r.setAttribute('data-theme',t);}}catch(e){}"
)

SHELL_JS = """
(function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var raiz = document.documentElement;

  // ---- tema (claro/escuro) — só aparece se o navegador entende light-dark() ----
  var btnTema = $('#btn-tema');
  function escuroAgora() {
    var f = raiz.style.colorScheme;
    return f ? f === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function pintarTema() { if (btnTema) btnTema.setAttribute('aria-pressed', String(escuroAgora())); }
  if (btnTema && window.CSS && CSS.supports('color', 'light-dark(white, black)')) {
    btnTema.hidden = false;
    pintarTema();
    btnTema.addEventListener('click', function () {
      var novo = escuroAgora() ? 'light' : 'dark';
      raiz.style.colorScheme = novo;
      raiz.setAttribute('data-theme', novo);
      try { localStorage.setItem('studio-theme', novo); } catch (e) {}
      pintarTema();
    });
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', pintarTema);
  }

  // ---- indicador de atividade / loading de topo e flutuante ----
  var bar = $('#barra-progresso-topo');
  var badge = $('#indicador-carregando');
  var badgeTexto = $('#indicador-texto');
  var barTimer = null;
  window.StudioLoading = {
    start: function (msg) {
      if (badge) {
        if (badgeTexto && msg) badgeTexto.textContent = msg;
        badge.classList.add('ativo');
      }
      if (!bar) return;
      clearTimeout(barTimer);
      bar.classList.remove('finalizado');
      bar.classList.add('ativo');
      bar.style.width = '28%';
      barTimer = setTimeout(function () {
        bar.style.width = '72%';
        barTimer = setTimeout(function () { bar.style.width = '88%'; }, 400);
      }, 150);
    },
    done: function () {
      if (badge) {
        badge.classList.remove('ativo');
        setTimeout(function () { if (badgeTexto) badgeTexto.textContent = 'Carregando…'; }, 300);
      }
      if (!bar) return;
      clearTimeout(barTimer);
      bar.classList.add('finalizado');
      barTimer = setTimeout(function () {
        bar.classList.remove('ativo', 'finalizado');
        bar.style.width = '0%';
      }, 450);
    }
  };

  // Carregamento visível em transições de página
  window.addEventListener('beforeunload', function () {
    if (window.StudioLoading) window.StudioLoading.start('Atualizando estúdio…');
  });

  // ---- canal ativo: recarrega a tela no canal escolhido ----
  var sel = $('#canal-ativo');
  if (sel) sel.addEventListener('change', function () {
    window.StudioLoading.start();
    var u = new URL(location.href);
    u.searchParams.set('project_id', sel.value);
    location.href = u.toString();
  });

  // ---- novo canal ----
  var dlg = $('#dlg-canal');
  var abrir = $('#btn-novo-canal');
  if (dlg && abrir) {
    abrir.addEventListener('click', function () {
      if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
      var campo = $('#canal-nome'); if (campo) campo.focus();
    });
    dlg.addEventListener('click', function (ev) {
      if (ev.target === dlg || (ev.target.closest && ev.target.closest('[data-fechar-dialogo]'))) dlg.close();
    });
    var form = $('#form-canal');
    var fb = $('#canal-feedback');
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var nome = $('#canal-nome').value.trim();
      if (!nome) return;
      var btn = $('#btn-salvar-canal');
      btn.disabled = true;
      btn.classList.add('carregando');
      window.StudioLoading.start();
      fb.removeAttribute('data-tipo'); fb.textContent = 'Cadastrando canal…';
      fetch('/studio/projects', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: nome, niche: $('#canal-nicho').value.trim(), language: $('#canal-idioma').value })
      }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return [r, d]; }); })
        .then(function (par) {
          var r = par[0], d = par[1];
          if (r.ok && d.id) {
            fb.textContent = 'Canal criado. Abrindo…';
            location.href = '/studio/panel?project_id=' + encodeURIComponent(d.id);
          } else {
            fb.setAttribute('data-tipo', 'erro');
            fb.textContent = 'Erro ao cadastrar: ' + (typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail || d));
            btn.disabled = false;
            btn.classList.remove('carregando');
            window.StudioLoading.done();
          }
        })
        .catch(function (err) {
          fb.setAttribute('data-tipo', 'erro'); fb.textContent = 'Falha de rede: ' + err.message;
          btn.disabled = false;
          btn.classList.remove('carregando');
          window.StudioLoading.done();
        });
    });
  }
})();
"""


def render_document(*, title: str, active: str, crumb: str, body_html: str, nonce: str,
                    projects: list[tuple[str, str]], project_id: str, cost_note: str = "",
                    page_js: str = "", extra_css: str = "") -> str:
    """Documento completo da tela V3. `body_html` é o conteúdo de `<div class="content">`."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{e(title)}</title>
  <style nonce="{nonce}">{V3_CSS}{PRODUCT_CSS}{extra_css}</style>
  <script nonce="{nonce}">{THEME_BOOT_JS}</script>
</head>
<body>
<div id="barra-progresso-topo" aria-hidden="true"></div>
<div id="indicador-carregando" class="indicador-carregando" aria-live="polite" aria-hidden="true"><span class="indicador-spinner"></span><span id="indicador-texto">Carregando…</span></div>
<a class="skip" href="#conteudo">Ir para o conteúdo</a>
<div class="app">
  {render_sidebar(active=active, cost_note=cost_note)}
  <main class="main">
    {render_topbar(crumb=crumb, projects=projects, project_id=project_id)}
    <div class="content" id="conteudo">
{body_html}
    </div>
  </main>
</div>
{render_novo_canal_dialog()}
<script nonce="{nonce}">{SHELL_JS}</script>
{f'<script nonce="{nonce}">{page_js}</script>' if page_js else ''}
</body>
</html>"""
