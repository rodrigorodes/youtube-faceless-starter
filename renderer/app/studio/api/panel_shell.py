"""Casca compartilhada das telas do painel do Studio (S5 — CORE-ISOLATION-GUIDE).

Reúne o que **toda** tela usa e nada que pertença a uma tela só: rótulos de estado, selo e
custo, menu lateral, sidebar, tema (tokens claros + CSS) e os cabeçalhos CSP. É a base da
pilha de módulos `panel_*`: não importa nenhum outro `panel_*` (evita ciclo); os demais
importam daqui. `_duration_text` vive aqui porque Roteiro e Vídeo a compartilham.
"""
import html

from ..application.panel import CostBreakdown, MonthCost
from ..domain.panel import Stage

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

STAGE_LABELS = {
    Stage.PENDING: "Pendente",
    Stage.IN_PRODUCTION: "Em Produção",
    Stage.AWAITING_APPROVAL: "Aguardando Aprovação",
    Stage.APPROVED: "Aprovado",
    Stage.COMPLETED: "Concluído",
    Stage.FAILED: "Falha",
    Stage.REJECTED: "Rejeitado",
}

# Três estados operacionais da jornada. PENDING não é execução: é ausência de execução.
STATE_BY_STAGE = {
    Stage.COMPLETED: ("done", "✓", "Concluído"),
    Stage.IN_PRODUCTION: ("running", "▶", "Em execução"),
    Stage.AWAITING_APPROVAL: ("action", "!", "Ação necessária"),
    Stage.APPROVED: ("action", "!", "Ação necessária"),
    Stage.FAILED: ("fail", "×", "Falhou"),
    Stage.REJECTED: ("fail", "×", "Rejeitado"),
    Stage.PENDING: ("idle", "·", "Sem execução registrada"),
}
ACTION_STAGES = (Stage.AWAITING_APPROVAL, Stage.APPROVED, Stage.FAILED, Stage.REJECTED)


def _state_badge(stage: Stage, count: int | None = None) -> str:
    kind, icon, label = STATE_BY_STAGE.get(stage, ("idle", "·", "Sem execução registrada"))
    count_html = f': <span class="state-count">{count}</span>' if count is not None else ""
    return (
        f'<span class="state s-{kind}" data-state="{kind}">'
        f'<span class="state-icon" aria-hidden="true">{icon}</span> '
        f'<span>{label}</span>{count_html}</span>'
    )


def _cost_html(text: str) -> str:
    """Renderiza um custo já rotulado (Real/Estimado/Sem custo/Desconhecido)."""
    return f'<span class="cost-origin">{e(text)}</span>'


def cost_breakdown_rows(breakdown: CostBreakdown) -> str:
    """Quatro linhas rotuladas de custo (Real/Estimado/Sem custo/Desconhecido).

    Ausência de uso vira "nenhum" — nunca `US$ 0,00`; desconhecido nunca é somado ao real.
    """
    rows = [
        ("Real", f"US$ {breakdown.real_usd:.2f}".replace(".", ",") if breakdown.real_calls else "nenhum"),
        ("Estimado", f"US$ {breakdown.estimate_usd:.2f}".replace(".", ",") if breakdown.estimate_calls else "nenhum"),
        ("Sem custo", f"{breakdown.free_calls} chamada(s)" if breakdown.free_calls else "nenhum"),
        ("Desconhecido", f"{breakdown.unknown_calls} chamada(s)" if breakdown.unknown_calls else "nenhum"),
    ]
    return "".join(
        f'<div class="kv"><span>{e(label)}</span><span>{e(value)}</span></div>'
        for label, value in rows
    )


def _ui_icon(path: str) -> str:
    return ('<svg class="icon-inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'aria-hidden="true" focusable="false">{path}</svg>')


_ICON_FLAME = _ui_icon('<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path>')
_ICON_REFRESH = _ui_icon('<path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5"></path>')
_ICON_SLIDERS = _ui_icon('<path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h12M20 18h0"></path><circle cx="16" cy="6" r="2"></circle><circle cx="8" cy="12" r="2"></circle><circle cx="18" cy="18" r="2"></circle>')

_NAV_ICONS = {
    "novo-video": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v8M8 12h8"></path></svg>',
    "desempenho": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true" focusable="false"><path d="M3 20h18M6 16V9m6 7V4m6 12v-5"></path></svg>',
    "configuracao": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3"></circle><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"></path></svg>',
    "inicio": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>',
    "producao": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="2" y="4" width="20" height="16" rx="4"></rect><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>',
    "tendencias": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path></svg>',
    "videos": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect><line x1="7" y1="2" x2="7" y2="22"></line><line x1="17" y1="2" x2="17" y2="22"></line><line x1="2" y1="12" x2="22" y2="12"></line><line x1="2" y1="7" x2="7" y2="7"></line><line x1="2" y1="17" x2="7" y2="17"></line><line x1="17" y1="17" x2="22" y2="17"></line><line x1="17" y1="7" x2="22" y2="7"></line></svg>',
    "canais": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="2" y="4" width="20" height="14" rx="2"></rect><line x1="8" y1="22" x2="16" y2="22"></line><line x1="12" y1="18" x2="12" y2="22"></line></svg>',
    "equipe": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>',
    "analytics": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><line x1="4" y1="20" x2="4" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="20" y1="20" x2="20" y2="14"></line></svg>',
    "estilos": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="13.5" cy="6.5" r="1.5"></circle><circle cx="17.5" cy="10.5" r="1.5"></circle><circle cx="8.5" cy="7.5" r="1.5"></circle><circle cx="6.5" cy="12.5" r="1.5"></circle><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"></path></svg>',
    "conexoes": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>',
}

# Nenhum destino morto nesta versão: "Configurações — em breve" virou a tela real de **Estilos**
# (biblioteca compartilhada, VS-05a). A seção só aparece quando houver, de fato, algo indisponível.
_NAV_UNAVAILABLE: tuple[tuple[str, str, str], ...] = ()

# UX-01: telas que continuam existindo fora do menu mantêm um item atual na casca.
_NAV_ALIASES = {"analytics": "desempenho", "producao": "videos"}


def build_sidebar_nav(*, active: str = "inicio", base_href: str = "",
                      channels_href: str | None = "/studio/canais") -> str:
    """Navegação principal em dois grupos (G1), reutilizada por todas as páginas do painel.

    `active` marca o único item atual. IA-01: Início, Produção e Tendências deixaram de ser âncoras
    de uma página única e passaram a ser **rotas de servidor reais** — cada uma devolve só a sua
    tela. Por isso `base_href` não é mais usado (fica na assinatura por compatibilidade com as
    telas que o passavam); "Vídeos" aponta para `/studio/panel/videos`, a rota real que redireciona
    para o bloco `#videos` do Início (destino real, sem link morto).
    `channels_href` é o link real da tela de Canais (F10), já entregue nesta versão; `None` omite o item.
    """
    active = _NAV_ALIASES.get(active, active)
    links = [
        ("inicio", "Início", "/studio/panel"),
        ("novo-video", "Novo vídeo", "/studio/panel/novo-video"),
        ("videos", "Vídeos", "/studio/panel/videos"),
        ("tendencias", "Tendências", "/studio/panel/tendencias"),
        ("desempenho", "Desempenho", "/studio/panel/analytics"),
    ]
    items = []
    for key, label, href in links:
        current = ' aria-current="page"' if key == active else ""
        current_class = " active" if key == active else ""
        items.append(f"""
          <li>
            <a class="nav-item{current_class}" href="{e(href)}"{current}>
              {_NAV_ICONS[key]}
              <span>{e(label)}</span>
            </a>
          </li>""")
    management = f"""
      <p class="nav-label">Configuração</p>
      <ul class="nav-list">
        <li>
          <a class="nav-item{' active' if active == 'canais' else ''}" href="{e(channels_href or '/studio/canais')}"{' aria-current="page"' if active == 'canais' else ''}>
            {_NAV_ICONS['canais']}
            <span>Canais</span>
          </a>
        </li>
        <li>
          <a class="nav-item{' active' if active == 'estilos' else ''}" href="/studio/panel/estilos"{' aria-current="page"' if active == 'estilos' else ''}>
            {_NAV_ICONS['estilos']}
            <span>Estilos</span>
          </a>
        </li>
        <li>
          <a class="nav-item{' active' if active == 'conexoes' else ''}" href="/studio/panel/conexoes"{' aria-current="page"' if active == 'conexoes' else ''}>
            {_NAV_ICONS['conexoes']}
            <span>Conexões</span>
          </a>
        </li>
        <li>
          <a class="nav-item{' active' if active == 'equipe' else ''}" href="/studio/panel/equipe"{' aria-current="page"' if active == 'equipe' else ''}>
            {_NAV_ICONS['equipe']}
            <span>Equipe</span>
          </a>
        </li>
      </ul>"""
    unavailable = []
    for label, tag, icon in _NAV_UNAVAILABLE:
        unavailable.append(f"""
          <li>
            <span class="nav-item nav-item-unavailable is-disabled" aria-disabled="true" tabindex="-1">
              {icon}
              <span>{e(label)}</span><em class="nav-tag">{e(tag)}</em>
            </span>
          </li>""")
    # A seção só existe quando há de fato um destino indisponível; nada de grupo morto e vazio.
    unavailable_section = (
        f"""
        <p class="nav-label">Indisponível nesta versão</p>
        <ul class="nav-list">{''.join(unavailable)}
        </ul>"""
        if unavailable else ""
    )
    return f"""
      <nav class="nav" aria-label="Principal">
        <p class="nav-label">Operação</p>
        <ul class="nav-list">{''.join(items)}
        </ul>
        {management}{unavailable_section}
      </nav>
      <nav class="nav-resources" aria-label="Recursos externos">
        <ul class="nav-list">
          <li>
            <a class="nav-item" href="/docs" target="_blank" rel="noopener noreferrer">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
              <span>API Docs</span>
            </a>
          </li>
          <li>
            <a class="nav-item" href="http://localhost:5678" target="_blank" rel="noopener noreferrer">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
              <span>n8n Workflows</span>
            </a>
          </li>
        </ul>
      </nav>
    """


_THEME_JS = """(function(){var K='studio-theme',r=document.documentElement,b=document.getElementById('theme-toggle');
if(!b){return;}
function sys(){return window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}
function cur(){return r.getAttribute('data-theme')||sys();}
function paint(){var t=cur()==='light'?'Usar tema escuro':'Usar tema claro';b.textContent=t;b.setAttribute('aria-label',t);}
try{var s=localStorage.getItem(K);if(s==='light'||s==='dark'){r.setAttribute('data-theme',s);}}catch(e){}
b.hidden=false;paint();
b.addEventListener('click',function(){var n=cur()==='light'?'dark':'light';r.setAttribute('data-theme',n);try{localStorage.setItem(K,n);}catch(e){}paint();});})();"""


def theme_toggle_html(nonce: str | None) -> str:
    """Alternador de tema. Nasce `hidden`: sem JS (ou sem nonce) não existe controle morto."""
    if not nonce:
        return ""
    return ('<button type="button" class="btn btn-compact theme-toggle" id="theme-toggle" hidden>'
            f'Usar tema claro</button><script nonce="{nonce}">{_THEME_JS}</script>')


def render_sidebar(*, active: str = "inicio", base_href: str = "", side_card_html: str,
                   channels_href: str | None = "/studio/canais", nonce: str | None = None) -> str:
    """Casca lateral completa (marca + navegação em grupos + card de orçamento + aviso)."""
    return f"""<aside class="sidebar" aria-label="Barra lateral">
      <div class="brand">
        <div class="brand-icon" aria-hidden="true">FS</div>
        <div>
          <div class="brand-title">Faceless Studio V2</div>
          <div class="brand-sub">YouTube Automation</div>
        </div>
      </div>
      {build_sidebar_nav(active=active, base_href=base_href, channels_href=channels_href)}
      {side_card_html}
      {theme_toggle_html(nonce)}
      <p class="mock-note">Dados reais do Studio. Sem conteúdo ilustrativo.</p>
    </aside>"""


def budget_side_card(month: MonthCost, budget_bar_html: str = "") -> str:
    """Card "Orçamento do mês" com o resumo rotulado; ausência nunca vira `US$ 0,00`."""
    state = (
        f"Custo do mês: {month.text}"
        if month.breakdown.calls > 0
        else "Não disponível: nenhuma chamada registrada neste mês."
    )
    return f"""
        <div class="side-card">
          <h2>Orçamento do mês</h2>
          <p>{e(state)}</p>
          {budget_bar_html}
        </div>
    """


CSS = """
:root {
  /* Dark-only, tokens medidos do mockup aprovado (mockup-proposta.html). */
  color-scheme: dark;
  /* UX-01: tipografia do protótipo aprovado (docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html).
     Inter primeiro — se não estiver instalada, o fallback é o MESMO do protótipo. */
  --font-ui: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-scale-h1: 35px;
  --font-tracking-h1: -1.3px;
  --font-scale-eyebrow: 10px;
  --font-tracking-eyebrow: 2px;
  --bg-app: #0a0f19;
  --bg-canvas: #101827;
  --surface: #131b2d;
  --surface-raised: #1b263e;
  --border: #2a3350;
  --border-soft: #1f2942;
  --text: #e6e9f5;
  --text-muted: #aab3c8;
  --text-dim: #7f8aa6;
  --accent: #7c3aed;
  --accent-strong: #5b08f6;
  --accent-soft: #331e7e;
  --accent-contrast: #ffffff;
  --success: #74d6a6;
  --success-surface: #12322a;
  --success-contrast: #06130d;
  --info: #0abcff;
  --info-surface: #0b2c3f;
  --warn: #e3b341;
  --warn-surface: #33270e;
  --danger: #ff5a6e;
  --danger-surface: #38141c;
  --gold: #e3b341;
  --radius: 18px;
  --gap: 20px;

  /* Aliases semânticos dos componentes existentes, derivados dos tokens. */
  --bg: var(--bg-canvas);
  --sidebar: var(--bg-app);
  --sidebar-hover: var(--surface-raised);
  --surface-alt: var(--surface-raised);
  --surface-hover: var(--surface-raised);
  --surface-elevated: var(--surface-raised);
  --border-hover: #3a4568;
  --text-faint: var(--text-dim);
  --primary: var(--accent);
  --primary-hover: var(--accent-strong);
  --primary-focus: rgba(124, 58, 237, 0.32);
  --input-bg: #0c1322;
  --input-focus-bg: var(--surface);
  --ok: var(--success);
  --ok-bg: rgba(116, 214, 166, 0.14);
  --warn-bg: rgba(227, 179, 65, 0.14);
  --bad: var(--danger);
  --bad-bg: rgba(255, 90, 110, 0.14);
  --info-bg: rgba(10, 188, 255, 0.14);
  accent-color: var(--accent);
  scrollbar-color: var(--border) var(--bg-app);
  font-family: var(--font-ui);
  line-height: 1.5;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); min-height: 100vh; }

.app-layout {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 250px;
  background: var(--sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 1.25rem 1rem;
  flex-shrink: 0;
  z-index: 10;
}
@media (max-width: 1180px) {
  .app-layout { grid-template-columns: 220px minmax(0, 1fr); }
  .rail { grid-column: 1 / -1; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
}
@media (max-width: 820px) {
  .app-layout { grid-template-columns: minmax(0, 1fr); padding: 12px; }
  .sidebar { position: static; }
  .nav-list:first-of-type { display: flex; gap: 0.4rem; overflow-x: auto; padding-bottom: 0.25rem; }
  .nav-list:first-of-type li { flex: none; }
  .nav-list:last-of-type { display: grid; grid-template-columns: 1fr 1fr; gap: 0.25rem; }
  .nav-tag { display: none; }
  .idea-row { grid-template-columns: minmax(0, 1fr); }
  .item { grid-template-columns: minmax(0, 1fr); gap: 0.4rem; }
  .item .btn { width: 100%; }
  .hero h1 { font-size: 1.6rem; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }

.brand {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding-bottom: 1.25rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.25rem;
}
.brand-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  box-shadow: 0 2px 6px rgba(124, 58, 237, 0.35);
}
.brand-title {
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text);
  line-height: 1.2;
}
.brand-sub {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.nav-menu {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
}
.nav-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.55rem 0.75rem;
  min-height: 44px;
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.85rem;
  font-weight: 500;
  transition: background-color 0.15s ease, color 0.15s ease;
  text-decoration: none;
}
.nav-item svg {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  stroke-width: 2;
  fill: none;
  flex-shrink: 0;
}
.nav-item:hover {
  background: var(--sidebar-hover);
  color: var(--text);
  text-decoration: none;
}
.nav-item.active,
.nav-item[aria-current] {
  background: var(--accent-soft);
  color: var(--text);
  font-weight: 600;
  box-shadow: inset 3px 0 0 var(--accent);
}
.nav-item-unavailable {
  color: var(--text-muted);
  cursor: not-allowed;
}
.nav-item-unavailable:hover {
  background: transparent;
  color: var(--text-muted);
}
.nav-tag {
  margin-left: auto;
  padding: 0.05rem 0.45rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-muted);
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  white-space: nowrap;
}
.nav-resources {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
}

.skip-link {
  position: absolute;
  top: -100px;
  left: 1rem;
  z-index: 2000;
  padding: 0.6rem 1rem;
  border: 1px solid var(--info);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
}
.skip-link:focus {
  top: 1rem;
}

.sidebar-footer {
  padding-top: 1rem;
  border-top: 1px solid var(--border);
  font-size: 0.75rem;
  color: var(--text-muted);
}
.budget-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.65rem 0.8rem;
  margin-bottom: 0.75rem;
}
.budget-bar {
  background: var(--border);
  border-radius: 4px;
  height: 6px;
  overflow: hidden;
  margin: 0.35rem 0 0.25rem;
}
.budget-fill {
  background: var(--primary);
  height: 100%;
}

.main-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.75rem;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  gap: 1rem;
  flex-wrap: wrap;
}
.content-body {
  padding: 1.75rem;
  max-width: 80rem;
  width: 100%;
}

h1 { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.01em; }
h2 { font-size: 1.05rem; font-weight: 600; margin-bottom: 0.85rem; display: flex; align-items: center; gap: 0.5rem; }
a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }

label, .form-label {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 0.4rem;
}

input, select, textarea {
  box-sizing: border-box;
}

input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]),
select,
textarea {
  width: 100%;
  display: block;
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.65rem 0.9rem;
  font: inherit;
  font-size: 0.875rem;
  color: var(--text);
  line-height: 1.5;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease;
}
input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]):hover,
select:hover,
textarea:hover {
  border-color: var(--border-hover);
}
input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]):focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: 2px solid var(--info);
  outline-offset: 1px;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--primary-focus);
  background: var(--input-focus-bg);
}
input::placeholder, textarea::placeholder {
  color: var(--text-faint);
  opacity: 1;
}

select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%238897a8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.75rem center;
  padding-right: 2.25rem;
  cursor: pointer;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  min-height: 44px;
  min-width: 44px;
  line-height: 1.4;
  text-align: center;
  transition: all 0.15s ease;
  text-decoration: none;
}
.btn:hover {
  background: var(--surface-hover);
  border-color: var(--border-hover);
  text-decoration: none;
}
.btn-primary {
  background: var(--accent);
  color: var(--accent-contrast);
  border-color: var(--accent);
  box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}
.btn-primary:hover {
  background: var(--primary-hover);
  border-color: var(--primary-hover);
  box-shadow: 0 2px 6px var(--primary-focus);
}
.btn:focus-visible,
a:focus-visible,
.nav-item:focus-visible,
.next-step:focus-visible { outline: 2px solid var(--info); outline-offset: 2px; }

.grid-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 1rem;
  margin-bottom: 1.75rem;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.card-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.04em;
  margin-bottom: 0.35rem;
}
.card-value {
  font-size: 1.55rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.card-sub {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.filter-bar {
  display: flex;
  gap: 0.35rem;
  align-items: center;
  font-size: 0.82rem;
  background: var(--input-bg);
  padding: 0.25rem;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.filter-link {
  padding: 0.3rem 0.75rem;
  border-radius: 6px;
  color: var(--text-muted);
  font-weight: 500;
  transition: all 0.15s ease;
  text-decoration: none;
}
.filter-link:hover {
  color: var(--text);
  text-decoration: none;
}
.filter-link.active {
  background: var(--surface-hover);
  color: var(--text);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}

table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 1.5rem;
}
th, td {
  padding: 0.85rem 1rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
  font-size: 0.875rem;
}
th {
  background: rgba(0,0,0,0.12);
  color: var(--text-muted);
  font-size: 0.72rem;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.04em;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--surface-hover); }

.pill {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 12px;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.pill-PENDING { background: var(--border); color: var(--text-muted); }
.pill-IN_PRODUCTION { background: var(--info-bg); color: var(--info); border: 1px solid var(--info); }
.pill-AWAITING_APPROVAL { background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn); }
.pill-APPROVED { background: var(--success-surface); color: var(--success-contrast); border: 1px solid var(--success); }
.pill-COMPLETED { background: var(--ok-bg); color: var(--ok); }
.pill-FAILED { background: var(--bad-bg); color: var(--bad); border: 1px solid var(--bad); }
.pill-REJECTED { background: var(--bad-bg); color: var(--bad); }

.warning {
  background: var(--warn-bg);
  color: var(--warn);
  padding: 0.85rem 1.15rem;
  border-radius: 8px;
  border: 1px solid rgba(227, 179, 65, 0.25);
  margin-bottom: 1.25rem;
  font-size: 0.85rem;
}
.empty {
  text-align: center;
  padding: 2.5rem 1rem;
  color: var(--text-muted);
}

.timeline { list-style: none; padding-left: 1.5rem; position: relative; }
.timeline-item { position: relative; margin-bottom: 1.25rem; }
.timeline-dot {
  position: absolute;
  left: -1.5rem;
  top: 0.25rem;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-focus);
}
.timeline-title { font-weight: 600; font-size: 0.875rem; }
.timeline-desc { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.15rem; }
.layout-detail { display: grid; grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr)); gap: 1.25rem; }

/* Modern Video Sample Cards */
.video-sample-card {
  display: flex;
  gap: 1rem;
  align-items: center;
  padding: 0.85rem 1rem;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.video-sample-card:hover {
  border-color: var(--border-hover);
  background: var(--surface-hover);
}
.video-thumb-sample {
  width: 120px;
  height: 68px;
  aspect-ratio: 16 / 9;
  border-radius: 6px;
  background: var(--bg-app);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid var(--border);
}
.video-thumb-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--text-faint);
}
.video-sample-body {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
  min-width: 0;
}
.video-sample-title {
  font-weight: 600;
  font-size: 0.92rem;
  color: var(--text);
  line-height: 1.3;
  word-break: break-word;
}
.video-sample-meta {
  font-size: 0.78rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;
}
.video-sample-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
  flex-wrap: wrap;
}
@media (max-width: 640px) {
  .video-sample-card {
    flex-direction: column;
    align-items: flex-start;
  }
  .video-thumb-sample {
    width: 100%;
    height: auto;
  }
}

details summary::-webkit-details-marker { display: none !important; }

/* Creation Form Section */
.new-video-section {
  margin-bottom: 1.75rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.new-video-section[open] {
  border-color: var(--primary);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}
.new-video-summary {
  display: block;
  padding: 0.85rem 1.25rem;
  background: var(--surface);
  cursor: pointer;
  user-select: none;
  list-style: none;
}
.new-video-summary-inner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.new-video-section[open] .new-video-summary {
  border-bottom: 1px solid var(--border);
  background: var(--surface-hover);
}
.new-video-form {
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  width: 100%;
}
.form-grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 1rem;
  width: 100%;
}
.form-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 0.25rem;
  flex-wrap: wrap;
}
.form-feedback {
  font-size: 0.85rem;
  font-weight: 500;
}

/* Trending Section */
.trends-card {
  margin-bottom: 1.75rem;
  background: linear-gradient(180deg, rgba(204, 0, 0, 0.04) 0%, var(--surface) 100%);
}
.trends-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.85rem;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.trends-title {
  font-weight: 700;
  font-size: 1.05rem;
  display: flex;
  align-items: center;
}
.trends-source {
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--input-bg);
  padding: 0.25rem 0.6rem;
  border-radius: 6px;
  border: 1px solid var(--border);
}
.trend-item {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1rem;
  margin-bottom: 0.85rem;
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  transition: border-color 0.15s ease;
}
.trend-item:hover {
  border-color: var(--border-hover);
}
.trend-thumb-link {
  text-decoration: none;
  display: block;
  flex-shrink: 0;
}
.trend-thumb {
  width: 168px;
  height: 94px;
  border-radius: 8px;
  position: relative;
  overflow: hidden;
  background: var(--bg-app);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.trend-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.2s ease;
}
.trend-thumb:hover img {
  transform: scale(1.05);
}
.trend-thumb-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: var(--surface-raised);
  color: var(--text-faint);
}
.thumb-play-overlay {
  position: absolute;
  bottom: 4px;
  right: 4px;
  background: rgba(0, 0, 0, 0.8);
  color: var(--accent-contrast);
  font-size: 0.68rem;
  font-weight: 600;
  padding: 1px 4px;
  border-radius: 4px;
  line-height: 1.2;
}
.trend-content {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  flex: 1;
  min-width: 0;
}
.trend-top-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  width: 100%;
}
.trend-topic-name {
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: -0.01em;
  color: var(--text);
  line-height: 1.35;
}
.trend-title-link {
  text-decoration: none;
  color: var(--text);
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  word-break: break-word;
}
.trend-title-link:hover .trend-topic-name {
  text-decoration: underline;
  color: var(--text);
}
.trend-external-icon {
  font-size: 0.82rem;
  color: var(--text-muted);
  flex-shrink: 0;
  transition: transform 0.15s ease, color 0.15s ease;
}
.trend-title-link:hover .trend-external-icon {
  transform: translate(1px, -1px);
  color: var(--info);
}
.trend-badges {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  align-items: center;
}
.trend-meta-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.82rem;
  color: var(--text-muted);
  flex-wrap: wrap;
}
.trend-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}
.trend-actions-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
  margin-top: 0.25rem;
}
.btn-watch-yt {
  background: var(--surface-raised);
  color: var(--text);
  border: 1px solid var(--border-hover);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.82rem;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}
.btn-watch-yt:hover {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-contrast);
}
.badge-region-br {
  background: rgba(239, 68, 68, 0.16);
  color: var(--bad);
  border: 1px solid rgba(239, 68, 68, 0.3);
  font-weight: 600;
}
.badge-region-global {
  background: rgba(56, 189, 248, 0.15);
  color: var(--info);
  border: 1px solid rgba(56, 189, 248, 0.3);
  font-weight: 600;
}
.badge-pillar {
  background: var(--surface-raised);
  color: var(--text);
  border: 1px solid var(--border);
  font-weight: 500;
}
@media (max-width: 640px) {
  .trend-item {
    flex-direction: column;
  }
  .trend-thumb {
    width: 100%;
    height: auto;
    aspect-ratio: 16 / 9;
  }
}
.chip-metric {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.6rem;
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.78rem;
  color: var(--text-muted);
}
.evidence-list {
  margin-top: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  width: 100%;
}
.evidence-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.55rem 0.85rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.82rem;
  width: 100%;
}
.evidence-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evidence-views {
  color: var(--info);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  margin-left: 1.5rem;
  white-space: nowrap;
  flex-shrink: 0;
}

/* Trends Actions and Category Pills */
.trends-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.cat-pills-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
  margin: 0.85rem 0;
  padding-bottom: 0.85rem;
  border-bottom: 1px solid var(--border);
}
.cat-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 5px 14px;
  border-radius: 18px;
  background: var(--surface-raised);
  border: 1px solid transparent;
  color: var(--text);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
}
.cat-pill:hover {
  background: var(--border);
  color: var(--text);
}
.cat-pill.active {
  background: var(--accent);
  border-color: transparent;
  color: var(--accent-contrast);
  font-weight: 600;
}
.cat-pill-btn {
  background: transparent;
  border: 1px dashed var(--border-hover);
  color: var(--text-muted);
}
.cat-pill-btn:hover {
  border-style: solid;
  border-color: var(--accent);
  color: var(--text);
  background: var(--surface-raised);
}
.chip-category {
  background: var(--surface-elevated);
  border-color: var(--primary);
  color: var(--primary);
  font-weight: 600;
}

/* Category Management Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
  backdrop-filter: blur(2px);
}
.modal-content {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.1rem 1.25rem;
  border-bottom: 1px solid var(--border);
}
.modal-title {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
}
.modal-close {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 1.4rem;
  cursor: pointer;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  line-height: 1;
}
.modal-close:hover {
  color: var(--text);
  background: var(--surface-hover);
}
.modal-body {
  padding: 1.25rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.cat-list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.cat-list-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.65rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-elevated);
  gap: 0.75rem;
}
.cat-item-info {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
}
.cat-item-actions {
  display: flex;
  gap: 0.4rem;
  flex-shrink: 0;
}

/* Topic Groups / Videos Details */
.topic-group-card {
  margin-bottom: 1.25rem;
  padding: 0.85rem 1.15rem;
}
.topic-group-summary {
  display: block;
  cursor: pointer;
  margin-bottom: 0.75rem;
  user-select: none;
  list-style: none;
}
.topic-group-summary-inner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.topic-group-title {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.topic-group-label {
  font-size: 0.95rem;
  font-weight: 700;
}
.topic-group-cost {
  font-size: 0.85rem;
  color: var(--text-muted);
  font-weight: 500;
}
.action-buttons {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.btn-compact {
  min-height: 44px;
  padding: 0.25rem 0.75rem;
  font-size: 0.8rem;
}
.project-switcher {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.project-switcher label {
  margin-bottom: 0;
  white-space: nowrap;
}
.form-select-compact {
  width: auto;
  min-height: 32px;
  padding: 0.25rem 0.75rem;
  font-size: 0.82rem;
  display: inline-block;
}

/* Inline loading spinner */
.spinner-inline {
  display: inline-block;
  width: 0.85rem;
  height: 0.85rem;
  border: 2px solid rgba(255,255,255,0.3);
  border-radius: 50%;
  border-top-color: var(--accent-contrast);
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
  margin-right: 0.35rem;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Topic input pulse/glow highlight */
@keyframes topicPulse {
  0% {
    box-shadow: 0 0 0 0 rgba(124, 58, 237, 0.6);
    border-color: var(--accent);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(124, 58, 237, 0.2);
    border-color: var(--accent);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(204, 0, 0, 0);
    border-color: var(--border);
  }
}
.topic-pulse {
  animation: topicPulse 1.2s ease-out;
}

/* Shell: navegação por seções, estados honestos e diagnóstico avançado */
.panel-section {
  scroll-margin-top: 1rem;
  margin-bottom: 2.25rem;
}
.panel-section:last-child { margin-bottom: 0; }
.panel-section > h2 { margin-bottom: 0.35rem; }
.section-sub {
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-bottom: 1rem;
}
.section-block { margin-bottom: 1.75rem; }
.section-block h3 {
  font-size: 0.95rem;
  font-weight: 600;
  margin-bottom: 0.6rem;
}

.state-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.state-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--text);
  font-size: 0.75rem;
}
.state-icon { font-weight: 700; }
.state-done { border-color: var(--success-surface); }
.state-done .state-icon { color: var(--success); }
.state-running { border-color: var(--info); }
.state-running .state-icon { color: var(--info); }
.state-action { border-color: var(--warn); }
.state-action .state-icon { color: var(--warn); }
.state-idle { border-color: var(--border); }
.state-idle .state-icon { color: var(--text-muted); }
.state-count { font-variant-numeric: tabular-nums; font-weight: 700; }

.next-steps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.next-step {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  border-left: 3px solid var(--accent);
  color: var(--text);
  text-decoration: none;
}
a.next-step:hover {
  background: var(--surface-hover);
  border-color: var(--border-hover);
  text-decoration: none;
}
.next-step-title { font-weight: 600; font-size: 0.9rem; }
.next-step-count { font-size: 1.4rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.next-step-hint { font-size: 0.78rem; color: var(--text-muted); }

.status-list {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}
.status-item {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.55rem 0.8rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  font-size: 0.82rem;
}
.status-label { color: var(--text-muted); }
.status-count {
  color: var(--text);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.cost-origin { font-weight: 600; }
.cost-note {
  color: var(--text-muted);
  font-size: 0.78rem;
  margin: 0.75rem 0 1rem;
}
.video-state { display: flex; align-items: center; gap: 0.45rem; flex-wrap: wrap; }

.advanced { margin-top: 1.25rem; padding: 0; }
.advanced-summary {
  cursor: pointer;
  padding: 0.85rem 1.15rem;
  color: var(--text);
  font-weight: 600;
  list-style: none;
}
.advanced-summary::-webkit-details-marker { display: none; }
.advanced-summary::after { content: "▾"; float: right; color: var(--text-muted); }
.advanced[open] .advanced-summary { border-bottom: 1px solid var(--border); }
.advanced-body {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  padding: 1rem 1.15rem;
  color: var(--text-muted);
  font-size: 0.82rem;
}
.advanced-body code { color: var(--text); word-break: break-all; }
.failure-summary {
  margin-top: 1rem;
  padding: 0.85rem 1rem;
  border: 1px solid var(--warn);
  border-radius: 8px;
  background: var(--warn-bg);
  color: var(--text);
  font-size: 0.85rem;
}
.failure-summary p { margin-bottom: 0.4rem; }
.failure-summary p:last-child { margin-bottom: 0; }

/* ===== Alinhamento ao mockup aprovado (mockup-proposta.html) ===== */
body {
  background-color: var(--bg-app);
  background-image: radial-gradient(1200px 620px at 72% -8%, #241b52 0%, transparent 62%);
  background-repeat: no-repeat;
}
.app-layout {
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr) 300px;
  gap: var(--gap);
  padding: 18px;
  max-width: 1600px;
  margin: 0 auto;
  align-items: start;
  min-height: 100vh;
}
.sidebar {
  width: auto;
  height: auto;
  position: sticky;
  top: 18px;
  gap: 18px;
  padding: 18px 14px;
  background: linear-gradient(180deg, #0c1222, #0a0f19);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  z-index: 1;
}
.brand {
  padding-bottom: 0.75rem;
  border-bottom: 0;
  margin-bottom: 0;
}
.brand-icon {
  border-radius: 10px;
  background: linear-gradient(160deg, var(--accent-strong), #9d6bff);
  font-size: 0.8rem;
  font-weight: 700;
  box-shadow: none;
}
.nav {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  flex: 1;
}
.nav-label {
  margin: 0.75rem 0 0.35rem 0.4rem;
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: var(--text-dim);
}
.nav-label:first-child { margin-top: 0; }
.nav-list { gap: 0.25rem; }
.nav-item {
  padding: 0.5rem 0.6rem;
  min-height: 40px;
  border-radius: 10px;
  font-size: 0.875rem;
}
.nav-item:hover { background: var(--surface-raised); color: var(--text); }
.nav-item.active,
.nav-item[aria-current] {
  background: linear-gradient(90deg, var(--accent-soft), #241a4f);
  color: var(--text);
  box-shadow: inset 0 0 0 1px #4b32a8;
  font-weight: 600;
}
.nav-item svg { width: 18px; height: 18px; }
.is-disabled,
.nav-item-unavailable { color: var(--text-dim); cursor: not-allowed; }
.nav-tag {
  margin-left: auto;
  padding: 0.1rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-dim);
  font-size: 0.62rem;
  font-style: normal;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  white-space: nowrap;
}
.side-card {
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  padding: 12px;
  background: var(--surface);
}
.side-card h2 {
  display: block;
  margin: 0 0 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
}
.side-card p { margin: 0; font-size: 0.78rem; color: var(--text-dim); }
.mock-note {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
  font-size: 0.68rem;
  color: var(--text-dim);
}
.topbar { background: transparent; border: 0; padding: 0 0.25rem; }
.hero {
  background: linear-gradient(135deg, #1a1440 0%, #141b30 55%, #121a2b 100%);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  padding: 26px 26px 22px;
  position: relative;
  overflow: hidden;
}
.hero::after {
  content: "";
  position: absolute;
  inset: auto -80px -120px auto;
  width: 320px;
  height: 320px;
  background: radial-gradient(circle, rgba(124, 58, 237, 0.33), transparent 70%);
  pointer-events: none;
}
.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.6rem;
  color: var(--text-dim);
  font-size: 0.72rem;
}
.eyebrow .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); }
.hero h1 {
  display: block;
  margin: 0 0 0.6rem;
  font-size: clamp(1.75rem, 3.2vw, 2.6rem);
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 1.08;
}
.accent-word {
  background: linear-gradient(92deg, #b79bff 0%, var(--accent) 45%, var(--gold) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.lede { margin: 0 0 1.1rem; color: var(--text-muted); max-width: 60ch; }
.tabs { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.75rem; }
.tab {
  min-height: 40px;
  padding: 0.5rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #0f1626;
  color: var(--text-muted);
  font-size: 0.82rem;
  cursor: pointer;
}
.tab[aria-selected="true"] {
  background: linear-gradient(180deg, #2a1f63, #1c1548);
  border-color: #4b32a8;
  color: #fff;
}
.tab[aria-disabled="true"] { color: var(--text-dim); cursor: not-allowed; opacity: 0.75; }
.idea-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: 0.6rem;
  align-items: end;
}
.idea-row .form-actions { margin: 0; }
.idea-row .btn { min-height: 46px; }
.note { margin: 0.75rem 0 0; font-size: 0.75rem; color: var(--text-dim); }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}
.block-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
}
.steps {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.85rem 0 0;
  padding: 0;
  list-style: none;
}
.steps li {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 32px;
  padding: 0.35rem 0.75rem;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: #0d1424;
  color: var(--text-dim);
  font-size: 0.75rem;
}
.steps li .n { color: var(--text-dim); font-variant-numeric: tabular-nums; }
.fine { margin: 0.75rem 0 0; color: var(--text-dim); font-size: 0.72rem; line-height: 1.5; }
.card.empty { border-style: dashed; background: #101728; }
.state {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.2rem 0.6rem;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
}
.state .state-icon { font-size: 0.7rem; line-height: 1; }
.s-done { color: var(--success); background: var(--success-surface); border-color: #1f6b4e; }
.s-run { color: var(--info); background: var(--info-surface); border-color: #14567a; }
.s-act { color: var(--warn); background: var(--warn-surface); border-color: #6b4a1c; }
.s-fail { color: var(--danger); background: var(--danger-surface); border-color: #7a2436; }
.state-idle { color: var(--text-muted); background: var(--surface-raised); border-color: var(--border); }
.next { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.75rem; }
.next .card { display: grid; gap: 0.6rem; }
.spread { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
.row { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; }
.muted { color: var(--text-muted); }
.dim { color: var(--text-dim); }
.item { border-top: 1px solid var(--border-soft); }
.item:first-child { border-top: 0; }
.rail { display: grid; gap: var(--gap); align-content: start; }
.rail .card h2 { display: block; margin-bottom: 0.5rem; }
.kv {
  display: flex;
  justify-content: space-between;
  gap: 0.6rem;
  padding: 0.45rem 0;
  border-top: 1px solid var(--border-soft);
  font-size: 0.8rem;
}
.kv:first-of-type { border-top: 0; }
.kv span:last-child { font-weight: 600; }
.tag { margin-left: 0.35rem; color: var(--text-dim); font-size: 0.65rem; }
details.advanced { background: #0e1524; }

/* Utilitários genéricos das telas (ex.: prévia). Fonte única de verdade do design system. */
.badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  color: var(--text-muted);
  margin-right: 0.35rem;
}
.ok { color: var(--ok); }
.bad { color: var(--bad); }
.hint { font-weight: 400; font-size: 0.78rem; opacity: 0.8; }
.field label { display: block; font-weight: 600; font-size: 0.85rem; margin-bottom: 0.35rem; }
.error-msg { display: none; margin-top: 0.35rem; font-size: 0.8rem; color: var(--bad); }
/* O erro visual e o aria-invalid acompanham :user-invalid: só depois da interação/erro, nunca no load. */
:is(input, textarea, select):user-invalid { border-color: var(--bad); }
:is(input, textarea, select):user-invalid + .error-msg { display: block; }
.btn-danger {
  background: var(--bad-bg);
  color: var(--bad);
  border-color: var(--bad);
}
.btn-danger:hover {
  background: var(--danger-surface);
  border-color: var(--bad);
}
video {
  width: 100%;
  max-height: 80vh;
  background: #000;
  border-radius: 12px;
  border: 1px solid var(--border);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}

/* ---------- UX-01: escala tipográfica do protótipo aprovado ----------
   Fica no fim de propósito: vence as definições espalhadas acima, sem reescrevê-las. */
h1 {
  font-size: var(--font-scale-h1);
  letter-spacing: var(--font-tracking-h1);
  font-weight: 730;
  line-height: 1.2;
}
.eyebrow {
  font-size: var(--font-scale-eyebrow);
  letter-spacing: var(--font-tracking-eyebrow);
}
.nav-item { font-weight: 560; }
.nav-item.active,
.nav-item[aria-current] { font-weight: 750; }
.brand-title { font-weight: 780; letter-spacing: -0.6px; }
.icon-inline { width: 16px; height: 16px; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex: none; vertical-align: -3px; margin-right: 0.4rem; }
.btn .icon-inline { margin-right: 0.45rem; }
.block-head h1 { margin: 1.25rem 0 0.35rem; }
/* Telas de Configuração: cabeçalho em cartão e conteúdo respirando entre blocos. */
.main-content > .card + * { margin-top: 1.25rem; }
.main-content > .card ~ .card { margin-top: 1.25rem; }
"""


# ---------- UX-03: tema claro ----------
# Paleta clara com pares de contraste medidos (>= 4,5:1; ver tests/test_ux_contract.py). O tema
# escuro continua o padrão histórico; o claro entra pelo SO (prefers-color-scheme) ou pela escolha
# explícita (`data-theme`), e a escolha explícita escura vence o SO.
LIGHT_TOKENS = {
    "bg-app": "#f3f4fa", "bg-canvas": "#f8f9fd", "surface": "#ffffff", "surface-raised": "#eef0f8",
    "border": "#cfd5e6", "border-soft": "#e3e7f2",
    "text": "#161b2e", "text-muted": "#444e6a", "text-dim": "#566082",
    "accent": "#6d28d9", "accent-strong": "#5b21b6", "accent-soft": "#e9e0fb", "accent-contrast": "#ffffff",
    "success": "#0d7a4d", "success-surface": "#dcf5e8", "success-contrast": "#ffffff",
    "info": "#0369a1", "info-surface": "#dbeefb",
    "warn": "#8a5a00", "warn-surface": "#fcf0d2",
    "danger": "#b4232f", "danger-surface": "#fde4e7", "gold": "#8a5a00",
    "border-hover": "#b4bdd6", "input-bg": "#ffffff",
}
_LIGHT_EXTRAS = {
    "primary-focus": "rgba(109, 40, 217, 0.28)", "ok-bg": "rgba(13, 122, 77, 0.12)",
    "warn-bg": "rgba(138, 90, 0, 0.12)", "bad-bg": "rgba(180, 35, 47, 0.10)",
    "info-bg": "rgba(3, 105, 161, 0.10)",
}


def _light_rules(root: str) -> str:
    tokens = "\n".join(f"  --{k}: {v};" for k, v in {**LIGHT_TOKENS, **_LIGHT_EXTRAS}.items())
    return f"""{root} {{
  color-scheme: light;
{tokens}
}}
{root} body {{ background-image: radial-gradient(1200px 620px at 72% -8%, #e4dcfa 0%, transparent 62%); }}
{root} .nav-item.active, {root} .nav-item[aria-current] {{
  background: var(--accent-soft); box-shadow: inset 0 0 0 1px #c9b8f3;
}}
{root} .accent-word {{ background: linear-gradient(92deg, var(--accent-strong), var(--accent) 55%, var(--gold)); -webkit-background-clip: text; background-clip: text; }}
{root} .sidebar {{ background: linear-gradient(180deg, #ffffff, var(--bg-app)); }}
{root} .hero {{ background: linear-gradient(135deg, #efe8fd 0%, #f6f4fd 55%, #ffffff 100%); }}
{root} .tab {{ background: var(--surface-raised); }}
{root} .tab[aria-selected="true"] {{ background: var(--accent-strong); color: var(--accent-contrast); }}
{root} .steps li, {root} .card.empty, {root} details.advanced, {root} .tile.na,
{root} .conn-channel, {root} .field input[disabled], {root} .field select[disabled] {{ background: var(--surface-raised); }}
{root} .s-act {{ border-color: #e3c37a; }}
{root} .s-fail {{ border-color: #eaa5ad; }}
"""


THEME_CSS = (
    _light_rules(':root[data-theme="light"]')
    + "@media (prefers-color-scheme: light) {\n"
    + _light_rules(':root:not([data-theme="dark"])')
    + "}\n"
    + """
.theme-toggle { width: 100%; margin-top: 0.75rem; }
@media (forced-colors: active) {
  .nav-item.active, .nav-item[aria-current] { outline: 2px solid Highlight; }
  .btn, .theme-toggle { border: 1px solid ButtonText; }
}
"""
)
CSS = CSS + THEME_CSS


def _headers(nonce: str) -> dict[str, str]:
    return {
        "Content-Security-Policy": (
            f"default-src 'none'; style-src 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; font-src 'self'; script-src 'nonce-{nonce}'; "
            "img-src 'self' data: https://i.ytimg.com https://pixabay.com https://*.pixabay.com https://cdn.pixabay.com; "
            "media-src 'self' data: https://pixabay.com https://*.pixabay.com https://cdn.pixabay.com; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        ),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


def _duration_text(seconds: float | None) -> str:
    """Duração legível a partir de segundos reais; vazio quando não há estimativa."""
    if seconds is None:
        return ""
    total = int(round(seconds))
    minutes, rest = divmod(total, 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"
