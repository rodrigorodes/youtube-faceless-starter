"""Páginas HTML do painel do Studio (operacional e detalhe de vídeo).
Sem dependências externas; todo texto é escapado e a CSP é protegida por nonce.
"""
import html
import secrets

from ..application.panel import CostBreakdown, CostKind, MonthCost, PanelView, VideoDetailView, cost_kind
from ..application.script_view import ScriptPageView
from ..domain.contracts import PublicationStatus, VideoFormat, VideoStatus
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


_NAV_ICONS = {
    "inicio": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>',
    "producao": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="2" y="4" width="20" height="16" rx="4"></rect><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>',
    "tendencias": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path></svg>',
    "videos": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect><line x1="7" y1="2" x2="7" y2="22"></line><line x1="17" y1="2" x2="17" y2="22"></line><line x1="2" y1="12" x2="22" y2="12"></line><line x1="2" y1="7" x2="7" y2="7"></line><line x1="2" y1="17" x2="7" y2="17"></line><line x1="17" y1="17" x2="22" y2="17"></line><line x1="17" y1="7" x2="22" y2="7"></line></svg>',
    "equipe": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>',
}
_NAV_UNAVAILABLE = (
    ("Canais", "em breve", '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="2" y="4" width="20" height="14" rx="2"></rect><line x1="8" y1="22" x2="16" y2="22"></line><line x1="12" y1="18" x2="12" y2="22"></line></svg>'),
    ("Analytics", "em breve", '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><line x1="4" y1="20" x2="4" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="20" y1="20" x2="20" y2="14"></line></svg>'),
    ("Configurações", "em breve", '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'),
)


def build_sidebar_nav(*, active: str = "inicio", base_href: str = "") -> str:
    """Navegação principal em dois grupos (G1), reutilizada por todas as páginas do painel.

    `active` marca o único item atual; `base_href` prefixa as âncoras quando a página aberta não
    contém as seções (as telas novas voltam ao painel em vez de apontar para âncora inexistente).
    """
    links = (
        ("inicio", "Início", f"{base_href}#inicio-section"),
        ("producao", "Produção", f"{base_href}#producao-section"),
        ("tendencias", "Tendências", f"{base_href}#trending-section"),
        ("videos", "Vídeos", f"{base_href}#videos-section"),
    )
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
      <p class="nav-label">Gestão</p>
      <ul class="nav-list">
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
    return f"""
      <nav class="nav" aria-label="Principal">
        <p class="nav-label">Operação</p>
        <ul class="nav-list">{''.join(items)}
        </ul>
        {management}
        <p class="nav-label">Indisponível nesta versão</p>
        <ul class="nav-list">{''.join(unavailable)}
        </ul>
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


def render_sidebar(*, active: str = "inicio", base_href: str = "", side_card_html: str) -> str:
    """Casca lateral completa (marca + navegação em grupos + card de orçamento + aviso)."""
    return f"""<aside class="sidebar" aria-label="Barra lateral">
      <div class="brand">
        <div class="brand-icon" aria-hidden="true">FS</div>
        <div>
          <div class="brand-title">Faceless Studio V2</div>
          <div class="brand-sub">YouTube Automation</div>
        </div>
      </div>
      {build_sidebar_nav(active=active, base_href=base_href)}
      {side_card_html}
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
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
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
"""


def _headers(nonce: str) -> dict[str, str]:
    return {
        "Content-Security-Policy": (
            f"default-src 'none'; style-src 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; script-src 'nonce-{nonce}'; "
            "img-src 'self' data: https://i.ytimg.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        ),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


def render_panel(view: PanelView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    days = view.days
    current_project_id = view.project_id or (view.projects[0][0] if view.projects else "")

    filters_html = "".join(
        f'<a class="filter-link {"active" if d == days else ""}" href="/studio/panel?project_id={e(current_project_id)}&days={d}">{d} dias</a>'
        if current_project_id
        else f'<a class="filter-link {"active" if d == days else ""}" href="/studio/panel?days={d}">{d} dias</a>'
        for d in (7, 14, 30)
    )

    warning_html = (
        '<div class="warning">Aviso: exibindo os 500 vídeos mais recentes do período selecionado.</div>'
        if view.truncated else ""
    )

    project_options = "".join(
        f'<option value="{e(p[0])}"{" selected" if p[0] == current_project_id else ""}>{e(p[1])}</option>'
        for p in view.projects
    )
    global_project_options = project_options
    create_form_html = f"""
      <details class="new-video-section" id="new-video-section">
        <summary class="new-video-summary">
          <div class="new-video-summary-inner">
            <div style="display: flex; align-items: center; gap: 0.6rem;">
              <span class="btn btn-primary btn-compact">+ Novo Vídeo</span>
              <span style="font-size: 0.85rem; color: var(--text-muted);">Criar vídeo a partir de tema ou tendência</span>
            </div>
            <span style="font-size: 0.8rem; color: var(--text-muted);">Clique para expandir</span>
          </div>
        </summary>
        <form id="create-video-form" class="new-video-form">
          <div class="form-grid-2">
            <div>
              <label for="new-video-project">Projeto</label>
              <select id="new-video-project" name="project_id" required>
                {project_options}
              </select>
            </div>
            <div>
              <label for="new-video-format">Formato</label>
              <select id="new-video-format" name="format">
                <option value="short">Short (vertical 1080x1920)</option>
                <option value="long">Long (horizontal 1920x1080)</option>
              </select>
            </div>
          </div>
          <div>
            <label for="topic">Tema <span style="font-weight: 400; opacity: 0.75;">(3 a 300 caracteres)</span></label>
            <input type="text" id="topic" name="topic" class="new-video-topic" minlength="3" maxlength="300" placeholder="Ex: ADE Lineup 2026 Revelado" required>
          </div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary" id="btn-create-video">Criar Vídeo</button>
            <div id="create-video-feedback" class="form-feedback"></div>
          </div>
        </form>
      </details>
    """

    total_trends = len(view.trends)
    pills = [
        f'<button type="button" class="cat-pill active" data-filter-type="all" aria-pressed="true">🔥 Todas ({total_trends})</button>',
    ]
    region_labels = {"BR": "🇧🇷 Em Alta Brasil", "US": "🇺🇸 Em Alta EUA", "UNKNOWN": "Origem desconhecida"}
    regions = ["BR", "US"] + sorted({t.region for t in view.trends if t.region and t.region not in ("BR", "US")})
    for region in regions:
        count = sum(1 for t in view.trends if t.region == region)
        label = region_labels.get(region, f"Em Alta {region}")
        pills.append(
            f'<button type="button" class="cat-pill" data-filter-type="region" data-region-code="{e(region)}" aria-pressed="false">{e(label)} ({count})</button>'
        )
    for cat in view.categories:
        cat_count = sum(1 for t in view.trends if t.category_id == cat.id)
        pills.append(
            f'<button type="button" class="cat-pill" data-filter-type="category" data-cat-id="{e(cat.id)}" data-category-id="{e(cat.id)}" aria-pressed="false">🏷️ {e(cat.name)} ({cat_count})</button>'
        )
    pills.append('<button type="button" class="cat-pill cat-pill-btn" id="btn-open-categories-modal">+ Novo Pilar</button>')
    cat_pills_html = f'<search class="cat-pills-bar" aria-label="Filtros de tendências">{"".join(pills)}</search>'

    action_buttons_html = f"""
      <div class="trends-actions">
        <button type="button" class="btn btn-compact" id="btn-refresh-trends" data-project-id="{e(current_project_id)}">🔄 Buscar Agora</button>
        <button type="button" class="btn btn-compact" id="btn-manage-categories" data-project-id="{e(current_project_id)}">⚙️ Gerenciar Categorias ({len(view.categories)})</button>
      </div>
    """

    if view.trends_status == "never_collected" or not view.trends:
        trends_html = f"""
          <div class="card trends-card" style="margin-bottom: 1.75rem;">
            <div class="trends-header">
              <div class="trends-title">
                <span>🔥 Temas em Alta nos Últimos {days} Dias</span>
              </div>
              {action_buttons_html}
            </div>
            {cat_pills_html}
            <div id="trends-refresh-feedback" class="form-feedback" style="margin-bottom: 0.5rem;"></div>
            <div class="empty" style="padding: 1.5rem 1rem;">Ainda não há coleta de tendências registrada para o período selecionado. Clique em <strong>Buscar Agora</strong> para atualizar.</div>
          </div>
        """
    else:
        last_dt_str = view.last_collected_at.strftime("%d/%m %H:%M") if view.last_collected_at else ""
        stale_badge = ' <span class="pill pill-FAILED" style="margin-left: 0.5rem;">Desatualizado</span>' if view.trends_status == "stale" else ""
        items_html = []
        for idx, t in enumerate(view.trends):
            extra_class = " trend-item-extra" if idx >= 6 else ""
            extra_style = ' style="display: none;"' if idx >= 6 else ""
            ev_list = []
            for ev in t.evidence:
                ev_title = e(ev.get("title", ""))
                ev_chan = e(ev.get("channel", ""))
                ev_views = f"{int(ev['views']):,} views".replace(",", ".") if ev.get("views") is not None else ""
                ev_list.append(
                    f"<div role='listitem' class='evidence-item'>"
                    f"<div class='evidence-title'><span style='color: var(--primary); font-size: 0.75rem; flex-shrink: 0;'>▶</span> <strong style='color: var(--text);'>{ev_title}</strong> <span style='color: var(--text-muted);'>· {ev_chan}</span></div>"
                    f"<div class='evidence-views'>{ev_views}</div>"
                    f"</div>"
                )
            ev_html = f'<div role="list" class="evidence-list">{"".join(ev_list)}</div>' if ev_list else ""

            # Thumbnail markup
            if t.thumbnail_url:
                thumb_inner = f'<img src="{e(t.thumbnail_url)}" alt="{e(t.topic)}" loading="lazy" class="trend-thumb-img" /><span class="thumb-play-overlay">▶</span>'
            else:
                thumb_inner = (
                    '<div class="trend-thumb-placeholder">'
                    '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                    '<rect x="2" y="4" width="20" height="16" rx="4"></rect>'
                    '<polygon points="10 8 16 12 10 16 10 8" fill="currentColor"></polygon>'
                    '</svg>'
                    '</div>'
                )

            if t.video_url:
                thumb_html = (
                    f'<a href="{e(t.video_url)}" target="_blank" rel="noopener noreferrer" class="trend-thumb-link" aria-label="Assistir {e(t.topic)} no YouTube">'
                    f'<div class="trend-thumb">{thumb_inner}</div>'
                    f'</a>'
                )
            else:
                thumb_html = f'<div class="trend-thumb">{thumb_inner}</div>'

            # Badges row
            badges_parts = []
            if t.region:
                label = region_labels.get(t.region, f"Em Alta {t.region}")
                badge_class = "badge-region-br" if t.region == "BR" else "badge-region-global"
                badges_parts.append(f'<span class="chip-metric {badge_class}">{e(label)}</span>')

            if t.category_name:
                badges_parts.append(f'<span class="chip-metric chip-category badge-pillar">🏷️ {e(t.category_name)}</span>')

            if t.metric_text:
                badges_parts.append(f'<span class="chip-metric" style="color: var(--info); font-weight: 600;">📊 {e(t.metric_text)}</span>')

            completed_count = t.counts.get(Stage.COMPLETED, 0)
            in_prod_count = t.counts.get(Stage.IN_PRODUCTION, 0)
            trend_action_count = sum(t.counts.get(stage, 0) for stage in ACTION_STAGES)
            trend_idle_count = t.counts.get(Stage.PENDING, 0)
            if completed_count + in_prod_count + trend_action_count + trend_idle_count == 0:
                badges_parts.append(_state_badge(Stage.PENDING))
            else:
                badges_parts.append(_state_badge(Stage.COMPLETED, completed_count))
                badges_parts.append(_state_badge(Stage.IN_PRODUCTION, in_prod_count))
                badges_parts.append(_state_badge(Stage.AWAITING_APPROVAL, trend_action_count))
            badges_parts.append(f'<span class="chip-metric">💰 {_cost_html(t.cost_text)}</span>')

            badges_html = f'<div class="trend-badges">{"".join(badges_parts)}</div>'

            # Title
            if t.video_url:
                title_html = (
                    f'<a href="{e(t.video_url)}" target="_blank" rel="noopener noreferrer" class="trend-title-link">'
                    f'<span class="trend-topic-name">{e(t.topic)}</span>'
                    f'<span class="trend-external-icon">↗</span>'
                    f'</a>'
                )
            else:
                title_html = f'<div class="trend-topic-name">{e(t.topic)}</div>'

            # Channel & metadata
            views_str = None
            if t.evidence and t.evidence[0].get("views") is not None:
                views_str = f"{int(t.evidence[0]['views']):,} views".replace(",", ".")
            elif t.metric_text:
                views_str = t.metric_text

            meta_parts = [f'<span class="trend-meta-item">📺 {e(t.channel_title or "Canal")}</span>']
            if views_str:
                meta_parts.append(f'<span class="trend-meta-item">👁️ {e(views_str)}</span>')
            if t.published_text:
                meta_parts.append(f'<span class="trend-meta-item">⏱️ {e(t.published_text)}</span>')
            meta_html = f'<div class="trend-meta-row">{" · ".join(meta_parts)}</div>'

            # Action buttons
            action_buttons = []
            if t.video_url:
                action_buttons.append(
                    f'<a href="{e(t.video_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-compact btn-watch-yt">▶️ Assistir no YouTube</a>'
                )
            if t.create_action:
                action_buttons.append(
                    f'<button type="button" class="btn btn-primary btn-create-from-trend" data-topic="{e(t.topic)}" style="white-space: nowrap;">✨ Criar Vídeo deste Tema</button>'
                )
            actions_html = f'<div class="trend-actions-row">{"".join(action_buttons)}</div>' if action_buttons else ""

            items_html.append(f"""
              <div class="trend-item{extra_class}"{extra_style} data-category-id="{e(t.category_id or '')}" data-region="{e(t.region or '')}">
                {thumb_html}
                <div class="trend-content">
                  {badges_html}
                  {title_html}
                  {meta_html}
                  {actions_html}
                  {ev_html}
                </div>
              </div>
            """)

        expansion_bar_html = ""
        if len(view.trends) > 6:
            extra_count = len(view.trends) - 6
            expansion_bar_html = f"""
              <div class="trends-expansion-bar" style="text-align: center; margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid var(--border);">
                <button type="button" class="btn btn-compact" id="btn-toggle-more-trends" data-expanded="false" data-total="{len(view.trends)}" aria-expanded="false">
                  Ver Mais Tendências (+{extra_count}) ▼
                </button>
              </div>
            """

        sources = dict.fromkeys(
            ("YouTube (origem desconhecida)" if t.source_name == "YouTube Global (Em Alta)" else t.source_name,
             t.source_url)
            for t in view.trends
        )
        sources_html = " · ".join(
            f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">{e(name)}</a>'
            for name, url in sources
        )
        trends_html = f"""
          <div class="card trends-card">
            <div class="trends-header">
              <div class="trends-title">
                <span>🔥 Temas em Alta nos Últimos {days} Dias</span>{stale_badge}
              </div>
              <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;">
                <div class="trends-source">
                  Fontes (todas as tendências): {sources_html} · Consulta: {last_dt_str}
                </div>
                {action_buttons_html}
              </div>
            </div>
            {cat_pills_html}
            <div id="trends-refresh-feedback" class="form-feedback" style="margin-bottom: 0.5rem;"></div>
            {''.join(items_html)}
            {expansion_bar_html}
          </div>
        """

    if not view.topics:
        body_html = '<div class="card empty">Nenhum vídeo no período selecionado.</div>'
    else:
        topic_blocks = []
        for g in view.topics:
            cards = []
            for v in g.videos:
                actions_html = []
                if "preview" in v.actions:
                    actions_html.append(f'<a class="btn btn-primary btn-compact" href="/studio/videos/{e(v.id)}/preview">Ver Prévia</a>')
                if "progress" in v.actions:
                    actions_html.append(f'<a class="btn btn-compact" href="/studio/panel/videos/{e(v.id)}">Ver Progresso</a>')

                fmt_label = "Short" if getattr(v, "format", VideoFormat.short) == VideoFormat.short else "Long"
                date_str = v.updated_at.strftime("%d/%m %H:%M")
                stage_label = STAGE_LABELS.get(v.stage, v.stage.value)

                cards.append(f"""
                  <div class="video-sample-card">
                    <div class="video-thumb-sample">
                      <div class="video-thumb-placeholder">
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                          <rect x="2" y="4" width="20" height="16" rx="4"></rect>
                          <polygon points="10 8 16 12 10 16 10 8" fill="currentColor"></polygon>
                        </svg>
                      </div>
                    </div>
                    <div class="video-sample-body">
                      <div class="video-state">
                        {_state_badge(v.stage)}
                        <span class="pill pill-{e(v.stage.value)}">{e(stage_label)}</span>
                      </div>
                      <div class="video-sample-title">{e(v.topic)}</div>
                      <div class="video-sample-meta">
                        <span>{e(fmt_label)}</span>
                        <span>·</span>
                        <span>{date_str}</span>
                        <span>·</span>
                        <span style="font-variant-numeric: tabular-nums;">{_cost_html(v.cost_text)}</span>
                      </div>
                    </div>
                    <div class="video-sample-actions">
                      {' '.join(actions_html)}
                    </div>
                  </div>
                """)

            topic_blocks.append(f"""
              <details open class="card topic-group-card" style="margin-bottom: 1.25rem;">
                <summary class="topic-group-summary" style="cursor: pointer; padding: 0.85rem 1rem; border-bottom: 1px solid var(--border); margin-bottom: 0.85rem;">
                  <div class="topic-group-summary-inner" style="display: flex; justify-content: space-between; align-items: center;">
                    <div class="topic-group-title" style="display: flex; align-items: center; gap: 0.6rem;">
                      <span class="topic-group-label" style="font-weight: 700; font-size: 1rem;">{e(g.label)}</span>
                      <span class="chip-metric" style="font-size: 0.72rem;">{len(g.videos)} vídeo{'s' if len(g.videos) > 1 else ''}</span>
                    </div>
                    <span class="topic-group-cost" style="font-weight: 600; font-size: 0.85rem; color: var(--text-muted);">{_cost_html(g.cost_text)}</span>
                  </div>
                </summary>
                <div class="topic-group-videos" style="display: flex; flex-direction: column; gap: 0.5rem;">
                  {''.join(cards)}
                </div>
              </details>
            """)
        body_html = "".join(topic_blocks)

    cat_items = []
    if not view.categories:
        categories_list_html = '<div class="empty" style="padding: 1rem; font-size: 0.85rem;" id="empty-cat-msg">Nenhum pilar cadastrado ainda. Preencha o formulário abaixo para adicionar o primeiro.</div>'
    else:
        for c in view.categories:
            queries_str = ", ".join(c.queries)
            queries_disp = e(queries_str) if c.queries else "Nenhum termo definido"
            cat_items.append(f"""
              <div class="cat-list-item" data-category-id="{e(c.id)}">
                <div class="cat-item-info">
                  <strong style="color: var(--text);">{e(c.name)}</strong>
                  <span style="color: var(--text-muted); font-size: 0.78rem;">Termos: {queries_disp}</span>
                </div>
                <div class="cat-item-actions">
                  <button type="button" class="btn btn-compact btn-edit-category" data-id="{e(c.id)}" data-name="{e(c.name)}" data-queries="{e(queries_str)}">Editar</button>
                  <button type="button" class="btn btn-compact btn-delete-category" data-id="{e(c.id)}" data-name="{e(c.name)}" style="color: var(--bad); border-color: var(--bad);">Excluir</button>
                </div>
              </div>
            """)
        categories_list_html = "".join(cat_items)

    modal_html = f"""
      <div class="modal-overlay" id="categories-modal" role="dialog" aria-modal="true" aria-labelledby="modal-categories-title">
        <div class="modal-content">
          <div class="modal-header">
            <div class="modal-title" id="modal-categories-title">Gerenciar Categorias (Pilares de Conteúdo)</div>
            <button type="button" class="modal-close" id="btn-close-modal" aria-label="Fechar">&times;</button>
          </div>
          <div class="modal-body">
            <div>
              <div style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.5rem;">Pilares Cadastrados</div>
              <div class="cat-list" id="modal-categories-list">
                {categories_list_html}
              </div>
            </div>

            <div style="border-top: 1px solid var(--border); padding-top: 1rem;">
              <div style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.65rem;" id="category-form-title">Novo Pilar de Conteúdo</div>
              <form id="form-category" style="display: flex; flex-direction: column; gap: 0.85rem;">
                <input type="hidden" id="category-id" name="id" value="">
                <div>
                  <label for="category-name">Nome do Pilar</label>
                  <input type="text" id="category-name" name="name" minlength="1" maxlength="100" placeholder="Ex: Tecnologia e IA" required>
                </div>
                <div>
                  <label for="category-queries">Termos de Busca <span style="font-weight: 400; opacity: 0.75;">(separados por vírgula, máx 10)</span></label>
                  <input type="text" id="category-queries" name="queries" placeholder="Ex: IA, inteligência artificial, ChatGPT">
                </div>
                <div class="form-actions">
                  <button type="submit" class="btn btn-primary" id="btn-save-category">Salvar Pilar</button>
                  <button type="button" class="btn btn-compact" id="btn-cancel-edit-category" style="display: none;">Cancelar</button>
                  <div id="category-form-feedback" class="form-feedback"></div>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    """

    project_modal_html = f"""
      <div class="modal-overlay" id="project-modal" role="dialog" aria-modal="true" aria-labelledby="modal-project-title">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <div class="modal-title" id="modal-project-title">Novo Projeto / Canal</div>
            <button type="button" class="modal-close" id="btn-close-project-modal" aria-label="Fechar">&times;</button>
          </div>
          <div class="modal-body">
            <form id="form-project" style="display: flex; flex-direction: column; gap: 0.85rem;">
              <div>
                <label for="project-name">Nome do Projeto / Canal <span style="color: var(--primary);">*</span></label>
                <input type="text" id="project-name" name="name" minlength="1" maxlength="120" placeholder="Ex: Canal de Curiosidades" required>
              </div>
              <div>
                <label for="project-niche">Nicho Editorial <span style="font-weight: 400; opacity: 0.75;">(opcional)</span></label>
                <input type="text" id="project-niche" name="niche" maxlength="200" placeholder="Ex: Música, Mistérios, Curiosidades">
              </div>
              <div>
                <label for="project-language">Idioma</label>
                <select id="project-language" name="language">
                  <option value="pt-BR" selected>Português Brasil (pt-BR)</option>
                  <option value="en-US">English US (en-US)</option>
                  <option value="es-ES">Español (es-ES)</option>
                </select>
              </div>
              <div class="form-actions" style="margin-top: 0.5rem;">
                <button type="submit" class="btn btn-primary" id="btn-save-project">Cadastrar Projeto</button>
                <button type="button" class="btn btn-compact" id="btn-cancel-project">Cancelar</button>
                <div id="project-form-feedback" class="form-feedback"></div>
              </div>
            </form>
          </div>
        </div>
      </div>
    """

    month_breakdown = view.month.breakdown
    if month_breakdown.calls == 0:
        month_display = "Sem registro de uso"
        month_origin = "Nenhuma chamada de IA registrada no mês."
    else:
        month_display = view.month.text
        month_origin = (
            "Real é cobrança confirmada; estimado aguarda reconciliação. "
            "“Sem custo” nunca vira valor e “desconhecido” não é zero."
        )

    budget_bar_html = ""
    if view.month.percent is not None and view.month.known_usd > 0:
        pct_width = min(100.0, max(0.0, view.month.percent))
        budget_bar_html = (
            f'<div class="budget-bar" aria-hidden="true">'
            f'<div class="budget-fill" style="width: {pct_width:.1f}%;"></div></div>'
        )

    done_count = view.totals.get(Stage.COMPLETED, 0)
    running_count = view.totals.get(Stage.IN_PRODUCTION, 0)
    action_count = sum(view.totals.get(stage, 0) for stage in ACTION_STAGES)
    idle_count = view.totals.get(Stage.PENDING, 0)
    total_videos = done_count + running_count + action_count + idle_count

    state_legend_html = (
        '<div class="state-legend" aria-label="Legenda de estados">'
        + _state_badge(Stage.COMPLETED, done_count)
        + _state_badge(Stage.IN_PRODUCTION, running_count)
        + _state_badge(Stage.AWAITING_APPROVAL, action_count)
        + '</div>'
    )

    steps_chips_html = """
      <ol class="steps" aria-label="Etapas da produção">
        <li><span class="n">1</span> Roteiro</li>
        <li><span class="n">2</span> Fontes</li>
        <li><span class="n">3</span> Fact-check</li>
        <li><span class="n">4</span> Cenas</li>
        <li><span class="n">5</span> Voz</li>
        <li><span class="n">6</span> Render</li>
        <li><span class="n">7</span> QA</li>
        <li><span class="n">8</span> Publicação</li>
      </ol>
    """

    if total_videos == 0:
        producao_body_html = f"""
          <article class="card empty" id="producao-vazia">
            <h3>Nenhuma execução registrada</h3>
            <p class="muted">Quando você produzir um vídeo, o andamento aparece aqui com etapa atual, próxima ação e custo.</p>
            {steps_chips_html}
            <p class="fine">Etapas exibidas sem estado: nenhuma foi iniciada. Não há percentual porque não existe execução registrada.</p>
          </article>
        """
    else:
        status_items = "".join(
            f'<li class="status-item" data-stage="{stage.value}">'
            f'<span class="status-label">{e(STAGE_LABELS[stage])}</span>'
            f'<span class="status-count">{view.totals.get(stage, 0)}</span></li>'
            for stage in Stage
        )
        producao_body_html = f"""
          <div class="grid-summary">
            <div class="card" style="border-left: 4px solid var(--info);">
              <div class="card-label">Em Produção</div>
              <div class="card-value" style="color: var(--info);">{running_count}</div>
              <div class="card-sub">Jobs de render/áudio ativos</div>
            </div>
            <div class="card" style="border-left: 4px solid var(--warn);">
              <div class="card-label">Aguardando Aprovação</div>
              <div class="card-value" style="color: var(--warn);">{view.totals.get(Stage.AWAITING_APPROVAL, 0)}</div>
              <div class="card-sub">Exigem revisão humana</div>
            </div>
            <div class="card" style="border-left: 4px solid var(--ok);">
              <div class="card-label">Concluídos / Publicados</div>
              <div class="card-value" style="color: var(--ok);">{done_count}</div>
              <div class="card-sub">No período selecionado</div>
            </div>
            <div class="card" style="border-left: 4px solid var(--accent);">
              <div class="card-label">Gasto no Mês vs Teto</div>
              <div class="card-value">{e(month_display)}</div>
              <div class="card-sub">Teto mensal: US$ {view.month.cap_usd:.2f}</div>
              <div class="card-sub">{e(month_origin)}</div>
            </div>
          </div>
          <div class="section-block">
            <h3>Status por fase</h3>
            <ul class="status-list">{status_items}</ul>
          </div>
          <p class="cost-note">Custos rotulados por tipo: <strong>Real</strong> (cobrança confirmada), <strong>Estimado</strong> (ainda sem confirmação), <strong>Sem custo</strong> e <strong>Desconhecido</strong>. Real e estimado nunca são fundidos num único número; ausência de uso é “sem registro de uso” e nunca vira zero.</p>
        """

    action_videos = [
        item
        for group in view.topics
        for item in group.videos
        if item.stage in ACTION_STAGES
    ]
    action_videos.sort(key=lambda item: item.updated_at, reverse=True)
    if not action_videos:
        precisa_body_html = (
            '<div class="card empty">Nada exige sua ação no período selecionado.</div>'
        )
    else:
        cards = []
        for item in action_videos[:6]:
            buttons = []
            if "preview" in item.actions:
                buttons.append(
                    f'<a class="btn btn-primary" href="/studio/videos/{e(item.id)}/preview">Abrir Prévia</a>'
                )
            if "progress" in item.actions:
                progress_label = "Ver correção" if item.stage in (Stage.FAILED, Stage.REJECTED) else "Ver Progresso"
                button_class = "btn btn-ghost" if "preview" in item.actions else "btn btn-primary"
                buttons.append(
                    f'<a class="{button_class}" href="/studio/panel/videos/{e(item.id)}">{progress_label}</a>'
                )
            if not buttons:
                buttons.append('<span class="dim">Sem ação disponível nesta versão.</span>')
            hints = {
                Stage.AWAITING_APPROVAL: "Aprovar ou editar antes de seguir para publicação.",
                Stage.APPROVED: "Aprovado; a publicação ainda não foi registrada.",
                Stage.FAILED: "Revisar o passo que falhou e reexecutar a produção.",
                Stage.REJECTED: "Rejeitado; revisar antes de retomar.",
            }
            cards.append(f"""
              <article class="card">
                <div class="spread">
                  <h3>{e(item.topic)}</h3>
                  {_state_badge(item.stage)}
                </div>
                <p class="muted">{_cost_html(item.cost_text)}</p>
                <p class="dim">{hints.get(item.stage, "Ação necessária para continuar.")}</p>
                <div class="row">{''.join(buttons)}</div>
              </article>
            """)
        remaining = len(action_videos) - 6
        remaining_html = (
            f'<p class="fine">E mais {remaining} item(ns) com ação necessária na seção Vídeos.</p>'
            if remaining > 0 else ""
        )
        precisa_body_html = f'<div class="next">{"".join(cards)}</div>{remaining_html}'

    latest_failure = next(
        (
            item
            for group in view.topics
            for item in group.videos
            if item.stage == Stage.FAILED
        ),
        None,
    )
    if latest_failure is None:
        ultima_falha_html = (
            '<p class="muted">Nenhuma falha registrada no período selecionado.</p>'
        )
    else:
        ultima_falha_html = f"""
          <p><strong>Falha registrada no vídeo «{e(latest_failure.topic)}».</strong></p>
          <p class="muted">O que fazer: abra o vídeo para ver o passo de correção. O botão de nova tentativa aparece no detalhe quando o estado permite.</p>
          <p class="dim">Detalhe técnico disponível em Avançado — diagnóstico.</p>
          <a class="btn btn-primary" style="width: 100%;" href="/studio/panel/videos/{e(latest_failure.id)}">Ver correção</a>
        """

    rail_cost_html = cost_breakdown_rows(view.month.breakdown)

    fases_html = """
      <div class="kv"><span>F0 Segurança e docs</span><span class="state s-done"><span class="state-icon" aria-hidden="true">✓</span> concluído</span></div>
      <div class="kv"><span>F1 Reservas e execução</span><span class="state s-act"><span class="state-icon" aria-hidden="true">!</span> parcial</span></div>
      <div class="kv"><span>F5 Audiovisual</span><span class="state s-act"><span class="state-icon" aria-hidden="true">!</span> domínio</span></div>
      <div class="kv"><span>F6 QA</span><span class="state s-act"><span class="state-icon" aria-hidden="true">!</span> contrato</span></div>
      <div class="kv"><span>F8 Publicação</span><span class="state s-fail"><span class="state-icon" aria-hidden="true">×</span> não iniciada</span></div>
      <div class="kv"><span>F11 SaaS</span><span class="state s-fail"><span class="state-icon" aria-hidden="true">×</span> adiada</span></div>
      <p class="fine">Rótulos do plano de implementação do repositório; não são estado de execução do Studio.</p>
    """

    side_card_html = budget_side_card(view.month, budget_bar_html)

    create_form_html = f"""
        <form id="create-video-form" class="idea-row">
          <div>
            <label class="sr-only" for="topic">Tema do vídeo</label>
            <input type="text" id="topic" name="topic" class="new-video-topic input" minlength="3" maxlength="300" placeholder="Ex: ADE Lineup 2026 Revelado" required>
          </div>
          <div>
            <label class="sr-only" for="new-video-project">Projeto</label>
            <select id="new-video-project" name="project_id" class="input" style="width: auto;" required>
              {project_options}
            </select>
          </div>
          <div>
            <label class="sr-only" for="new-video-format">Formato</label>
            <select id="new-video-format" name="format" class="input" style="width: auto;">
              <option value="short">Short (1080x1920)</option>
              <option value="long">Long (1920x1080)</option>
            </select>
          </div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary" id="btn-create-video">✦ Produzir vídeo</button>
            <div id="create-video-feedback" class="form-feedback"></div>
          </div>
        </form>
        <p class="note">A produção começa no modo assistido; a aprovação do roteiro e do preview acontece no vídeo.</p>
    """

    hero_html = f"""
        <section class="hero" id="inicio-section" aria-labelledby="hero-heading" tabindex="-1">
          <p class="eyebrow"><span class="dot" aria-hidden="true"></span> Um comando, do briefing à publicação</p>
          <h1 id="hero-heading">Transforme uma ideia em um vídeo <span class="accent-word">publicado</span></h1>
          <p class="lede">Produção assistida com aprovação humana e teto de custo. Esta visão mostra apenas o que está registrado no Studio.</p>
          <div class="tabs" role="tablist" aria-label="Origem do vídeo">
            <button type="button" class="tab" role="tab" id="tab-ideia" aria-selected="true" aria-controls="p-ideia">Minha ideia</button>
            <button type="button" class="tab" role="tab" id="tab-tend" aria-selected="false" aria-controls="p-tend" tabindex="-1">Tendência</button>
            <button type="button" class="tab" role="tab" id="tab-serie" aria-selected="false" aria-controls="p-serie" aria-disabled="true" tabindex="-1">Série / Playlist</button>
          </div>
          <div id="p-ideia" role="tabpanel" aria-labelledby="tab-ideia">
            <div id="new-video-section">{create_form_html}</div>
          </div>
          <div id="p-tend" role="tabpanel" aria-labelledby="tab-tend" hidden>
            <p class="note">Use a seção <a href="#trending-section">Tendências</a>; o botão «Criar Vídeo deste Tema» preenche o tema acima.</p>
          </div>
          <div id="p-serie" role="tabpanel" aria-labelledby="tab-serie" hidden>
            <p class="note">Séries e playlists ainda não têm backend nesta versão; por isso a aba está indisponível.</p>
          </div>
        </section>
    """

    advanced_panel_html = f"""
      <details class="advanced" id="advanced-diagnostics">
        <summary class="advanced-summary">Avançado — diagnóstico (IDs, traces, uso de modelos)</summary>
        <div class="advanced-body">
          <p>Projeto: <code>{e(current_project_id) or "não selecionado"}</code></p>
          <p>Visão gerada em {view.generated_at.strftime("%d/%m/%Y %H:%M")}.</p>
          <p>Identificadores técnicos apenas. Logs e traces por vídeo ficam no detalhe do vídeo, na mesma seção avançada.</p>
        </div>
      </details>
    """

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>Faceless Studio — Painel</title>
  <style nonce="{nonce}">{CSS}</style>
</head>
<body>
  <a class="skip-link" href="#inicio-section">Ir para o conteúdo</a>
  <div class="app-layout">
    {render_sidebar(active="inicio", side_card_html=side_card_html)}

    <main class="main-content">
      <header class="topbar">
        <div class="topbar-actions" style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
          <a class="btn btn-primary btn-compact" href="#new-video-section" id="nav-btn-new-video">+ Novo Vídeo</a>
          <div class="project-switcher">
            <label for="global-project-select" style="font-weight: 600; font-size: 0.85rem; color: var(--text-muted);">Canal Ativo:</label>
            <select id="global-project-select" class="form-select-compact">
              {global_project_options}
            </select>
            <button type="button" class="btn btn-compact" id="btn-open-project-modal">+ Novo Projeto</button>
          </div>
          <div class="filter-bar">
            <span style="padding-left: 0.4rem; color: var(--text-muted);">Período:</span>
            {filters_html}
          </div>
        </div>
      </header>

      {hero_html}

      <section class="block panel-section" id="producao-section" aria-labelledby="producao-heading">
        <div class="block-head">
          <h2 id="producao-heading">Produção</h2>
          {state_legend_html}
        </div>
        {producao_body_html}
      </section>

      <section class="block panel-section" id="precisa-section" aria-labelledby="precisa-heading">
        <h2 id="precisa-heading">Precisa de você</h2>
        {precisa_body_html}
      </section>

      <section class="block panel-section" id="trending-section" aria-labelledby="trending-heading">
        <div class="block-head">
          <h2 id="trending-heading">Tendências</h2>
        </div>
        <p class="section-sub">Temas coletados com evidências, região e origem. Origem não identificada aparece como desconhecida.</p>
        {trends_html}
      </section>

      {warning_html}

      <section class="block panel-section" id="videos-section" aria-labelledby="videos-heading">
        <h2 id="videos-heading">Vídeos</h2>
        {body_html}
      </section>

      {advanced_panel_html}
    </main>

    <aside class="rail" aria-label="Resumo">
      <section class="card" aria-labelledby="h-custo">
        <h2 id="h-custo">Custo do mês</h2>
        {rail_cost_html}
        <p class="fine">Real é cobrança confirmada; estimado aguarda reconciliação e consome o teto até lá. “Sem custo” nunca vira valor e “desconhecido” não é zero.</p>
      </section>
      <section class="card" aria-labelledby="h-falha">
        <h2 id="h-falha">Última falha</h2>
        {ultima_falha_html}
      </section>
      <section class="card" aria-labelledby="h-fase">
        <h2 id="h-fase">Estado das fases</h2>
        {fases_html}
      </section>
    </aside>
  </div>
  {modal_html}
  {project_modal_html}
  <script nonce="{nonce}">
    const form = document.getElementById('create-video-form');
    if (form) {{
      form.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const btn = document.getElementById('btn-create-video');
        const feedback = document.getElementById('create-video-feedback');
        const project_id = document.getElementById('new-video-project').value;
        const topicInput = document.getElementById('topic') || document.getElementById('new-video-topic');
        const topic = topicInput ? topicInput.value.trim() : '';
        const format = document.getElementById('new-video-format').value;
        if (!topic) return;
        if (btn) btn.disabled = true;
        feedback.textContent = 'Criando vídeo...';
        try {{
          const res = await fetch('/studio/videos', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ project_id, topic, format }})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            feedback.textContent = 'Vídeo criado com sucesso! Atualizando...';
            setTimeout(() => location.reload(), 800);
          }} else {{
            feedback.textContent = 'Erro ao criar: ' + (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
            if (btn) btn.disabled = false;
          }}
        }} catch (err) {{
          feedback.textContent = 'Falha de rede: ' + err.message;
          if (btn) btn.disabled = false;
        }}
      }});
    }}
    document.querySelectorAll('.btn-create-from-trend').forEach((btn) => {{
      btn.addEventListener('click', () => {{
        const topic = btn.getAttribute('data-topic') || btn.dataset.topic || '';
        const details = document.getElementById('new-video-section');
        const form = document.getElementById('create-video-form');
        const input = document.getElementById('topic') || document.getElementById('new-video-topic');
        if (details && 'open' in details) details.open = true;
        if (input) {{
          input.value = topic;
          input.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
          input.classList.remove('topic-pulse');
          void input.offsetWidth;
          input.classList.add('topic-pulse');
          setTimeout(() => input.focus(), 100);
          setTimeout(() => input.classList.remove('topic-pulse'), 1500);
        }} else if (form) {{
          form.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        }}
      }});
    }});
    const navBtnNew = document.getElementById('nav-btn-new-video');
    if (navBtnNew) {{
      navBtnNew.addEventListener('click', (ev) => {{
        ev.preventDefault();
        const details = document.getElementById('new-video-section');
        const input = document.getElementById('topic') || document.getElementById('new-video-topic');
        if (details) {{
          if ('open' in details) details.open = true;
          details.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        }}
        if (input) {{
          setTimeout(() => input.focus(), 200);
        }}
      }});
    }}

    // Abas de origem: só alterna entre painéis reais; a aba sem backend fica indisponível.
    const originTabs = Array.from(document.querySelectorAll('.tab[role="tab"]'));
    if (originTabs.length > 0) {{
      const selectTab = (selectedTab) => {{
        if (selectedTab.getAttribute('aria-disabled') === 'true') return;
        originTabs.forEach((tab) => {{
          const isSelected = tab === selectedTab;
          tab.setAttribute('aria-selected', isSelected ? 'true' : 'false');
          tab.tabIndex = isSelected ? 0 : -1;
          const panel = document.getElementById(tab.getAttribute('aria-controls'));
          if (panel) panel.hidden = !isSelected;
        }});
      }};
      originTabs.forEach((tab) => {{
        if (tab.getAttribute('aria-disabled') === 'true') return;
        tab.addEventListener('click', () => selectTab(tab));
      }});
    }}

    // Navegação por seções: aria-current acompanha a seção visível.
    const primaryNav = document.querySelector('nav[aria-label="Principal"]');
    if (primaryNav) {{
      const sectionLinks = Array.from(primaryNav.querySelectorAll('a.nav-item[href^="#"]'));
      const sectionTargets = sectionLinks
        .map((link) => document.querySelector(link.getAttribute('href')))
        .filter(Boolean);
      const markCurrentSection = (id) => {{
        sectionLinks.forEach((link) => {{
          const isCurrent = link.getAttribute('href') === '#' + id;
          link.classList.toggle('active', isCurrent);
          if (isCurrent) link.setAttribute('aria-current', 'page');
          else link.removeAttribute('aria-current');
        }});
      }};
      if ('IntersectionObserver' in window && sectionTargets.length > 0) {{
        const observer = new IntersectionObserver((entries) => {{
          entries.forEach((entry) => {{
            if (entry.isIntersecting) markCurrentSection(entry.target.id);
          }});
        }}, {{ rootMargin: '-30% 0px -55% 0px', threshold: 0 }});
        sectionTargets.forEach((target) => observer.observe(target));
      }}
      sectionLinks.forEach((link) => {{
        link.addEventListener('click', () => markCurrentSection(link.getAttribute('href').slice(1)));
      }});
    }}

    // Pill Filtering (Region, Category & All) & Compact Trends Expansion
    const filterPills = document.querySelectorAll('.cat-pill[data-filter-type]');
    const trendItems = document.querySelectorAll('.trend-item');
    const btnToggleTrends = document.getElementById('btn-toggle-more-trends');

    function applyTrendsFilter() {{
      const activePill = document.querySelector('.cat-pill.active[data-filter-type]');
      const filterType = activePill ? activePill.getAttribute('data-filter-type') : 'all';
      const isExpanded = btnToggleTrends ? btnToggleTrends.getAttribute('data-expanded') === 'true' : true;
      let shown = 0;

      trendItems.forEach((item) => {{
        let matches = false;
        if (filterType === 'all') {{
          matches = true;
        }} else if (filterType === 'region') {{
          const regCode = activePill ? activePill.getAttribute('data-region-code') : null;
          matches = (item.getAttribute('data-region') === regCode);
        }} else if (filterType === 'category') {{
          const catId = activePill ? (activePill.getAttribute('data-cat-id') || activePill.getAttribute('data-category-id')) : null;
          matches = (item.getAttribute('data-category-id') === catId);
        }}

        if (!matches) {{
          item.style.display = 'none';
        }} else {{
          if (!isExpanded && shown >= 6) {{
            item.style.display = 'none';
          }} else {{
            item.style.display = '';
          }}
          shown++;
        }}
      }});
      if (btnToggleTrends) {{
        const hidden = shown <= 6;
        btnToggleTrends.hidden = hidden;
        btnToggleTrends.parentElement.hidden = hidden;
        btnToggleTrends.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
        btnToggleTrends.textContent = isExpanded
          ? 'Recolher Tendências ▲'
          : 'Ver Mais Tendências (+' + Math.max(0, shown - 6) + ') ▼';
      }}
    }}

    filterPills.forEach((pill) => {{
      pill.addEventListener('click', () => {{
        filterPills.forEach((p) => {{
          p.classList.remove('active');
          p.setAttribute('aria-pressed', 'false');
        }});
        pill.classList.add('active');
        pill.setAttribute('aria-pressed', 'true');
        if (btnToggleTrends) btnToggleTrends.setAttribute('data-expanded', 'false');
        applyTrendsFilter();
      }});
    }});

    if (btnToggleTrends) {{
      btnToggleTrends.addEventListener('click', () => {{
        const isCurrentlyExpanded = btnToggleTrends.getAttribute('data-expanded') === 'true';
        if (!isCurrentlyExpanded) {{
          btnToggleTrends.setAttribute('data-expanded', 'true');
          applyTrendsFilter();
        }} else {{
          btnToggleTrends.setAttribute('data-expanded', 'false');
          applyTrendsFilter();
          const trendSection = document.getElementById('trending-section');
          if (trendSection) {{
            trendSection.scrollIntoView({{ behavior: 'smooth' }});
          }}
        }}
      }});
    }}

    // Modal Open & Close
    const modal = document.getElementById('categories-modal');
    const btnManage = document.getElementById('btn-manage-categories');
    const btnAddPillarPill = document.getElementById('btn-open-categories-modal') || document.getElementById('btn-add-pillar-pill');
    const btnCloseModal = document.getElementById('btn-close-modal');

    function openCatModal() {{
      if (modal) {{
        modal.style.display = 'flex';
        resetCategoryForm();
      }}
    }}
    function closeCatModal() {{
      if (modal) modal.style.display = 'none';
    }}

    if (btnManage) btnManage.addEventListener('click', openCatModal);
    if (btnAddPillarPill) btnAddPillarPill.addEventListener('click', openCatModal);
    if (btnCloseModal) btnCloseModal.addEventListener('click', closeCatModal);
    if (modal) {{
      modal.addEventListener('click', (ev) => {{
        if (ev.target === modal) closeCatModal();
      }});
    }}
    document.addEventListener('keydown', (ev) => {{
      if (ev.key === 'Escape') {{
        if (modal && modal.style.display === 'flex') closeCatModal();
        if (projectModal && projectModal.style.display === 'flex') closeProjectModal();
      }}
    }});

    // Global Project Switcher Change
    const globalProjectSelect = document.getElementById('global-project-select');
    if (globalProjectSelect) {{
      globalProjectSelect.addEventListener('change', () => {{
        const val = globalProjectSelect.value;
        const urlParams = new URLSearchParams(window.location.search);
        const days = urlParams.get('days') || '{days}';
        window.location.href = '/studio/panel?project_id=' + encodeURIComponent(val) + '&days=' + encodeURIComponent(days);
      }});
    }}

    // Project Creation Modal Open & Close
    const projectModal = document.getElementById('project-modal');
    const btnOpenProjectModal = document.getElementById('btn-open-project-modal');
    const btnCloseProjectModal = document.getElementById('btn-close-project-modal');
    const btnCancelProject = document.getElementById('btn-cancel-project');
    const projectForm = document.getElementById('form-project');
    const projectFeedback = document.getElementById('project-form-feedback');
    const btnSaveProject = document.getElementById('btn-save-project');

    function openProjectModal() {{
      if (projectModal) {{
        projectModal.style.display = 'flex';
        if (projectForm) projectForm.reset();
        if (projectFeedback) projectFeedback.textContent = '';
        if (btnSaveProject) btnSaveProject.disabled = false;
        const nameInput = document.getElementById('project-name');
        if (nameInput) nameInput.focus();
      }}
    }}
    function closeProjectModal() {{
      if (projectModal) projectModal.style.display = 'none';
    }}

    if (btnOpenProjectModal) btnOpenProjectModal.addEventListener('click', openProjectModal);
    if (btnCloseProjectModal) btnCloseProjectModal.addEventListener('click', closeProjectModal);
    if (btnCancelProject) btnCancelProject.addEventListener('click', closeProjectModal);
    if (projectModal) {{
      projectModal.addEventListener('click', (ev) => {{
        if (ev.target === projectModal) closeProjectModal();
      }});
    }}

    // Project Form Submit
    if (projectForm) {{
      projectForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const nameInput = document.getElementById('project-name');
        const nicheInput = document.getElementById('project-niche');
        const langInput = document.getElementById('project-language');
        const name = nameInput ? nameInput.value.trim() : '';
        const niche = nicheInput ? nicheInput.value.trim() : '';
        const language = langInput ? langInput.value : 'pt-BR';

        if (!name) return;
        if (btnSaveProject) btnSaveProject.disabled = true;
        if (projectFeedback) projectFeedback.textContent = 'Cadastrando projeto...';

        try {{
          const res = await fetch('/studio/projects', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ name, niche, language }})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok && data.id) {{
            if (projectFeedback) projectFeedback.textContent = 'Projeto criado com sucesso! Redirecionando...';
            const urlParams = new URLSearchParams(window.location.search);
            const days = urlParams.get('days') || '{days}';
            window.location.href = '/studio/panel?project_id=' + encodeURIComponent(data.id) + '&days=' + encodeURIComponent(days);
          }} else {{
            const errMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
            if (projectFeedback) projectFeedback.textContent = 'Erro ao cadastrar: ' + errMsg;
            if (btnSaveProject) btnSaveProject.disabled = false;
          }}
        }} catch (err) {{
          if (projectFeedback) projectFeedback.textContent = 'Falha de rede: ' + err.message;
          if (btnSaveProject) btnSaveProject.disabled = false;
        }}
      }});
    }}

    // Category Form Reset & Edit
    const catForm = document.getElementById('form-category');
    const catFormTitle = document.getElementById('category-form-title');
    const catIdInput = document.getElementById('category-id');
    const catNameInput = document.getElementById('category-name');
    const catQueriesInput = document.getElementById('category-queries');
    const btnSaveCat = document.getElementById('btn-save-category');
    const btnCancelEdit = document.getElementById('btn-cancel-edit-category');
    const catFeedback = document.getElementById('category-form-feedback');

    function resetCategoryForm() {{
      if (catIdInput) catIdInput.value = '';
      if (catNameInput) catNameInput.value = '';
      if (catQueriesInput) catQueriesInput.value = '';
      if (catFormTitle) catFormTitle.textContent = 'Novo Pilar de Conteúdo';
      if (btnSaveCat) {{
        btnSaveCat.textContent = 'Salvar Pilar';
        btnSaveCat.disabled = false;
      }}
      if (btnCancelEdit) btnCancelEdit.style.display = 'none';
      if (catFeedback) catFeedback.textContent = '';
    }}

    if (btnCancelEdit) {{
      btnCancelEdit.addEventListener('click', resetCategoryForm);
    }}

    document.querySelectorAll('.btn-edit-category').forEach((btn) => {{
      btn.addEventListener('click', () => {{
        const id = btn.dataset.id || '';
        const name = btn.dataset.name || '';
        const queries = btn.dataset.queries || '';
        if (catIdInput) catIdInput.value = id;
        if (catNameInput) {{
          catNameInput.value = name;
          catNameInput.focus();
        }}
        if (catQueriesInput) catQueriesInput.value = queries;
        if (catFormTitle) catFormTitle.textContent = 'Editar Pilar: ' + name;
        if (btnSaveCat) btnSaveCat.textContent = 'Atualizar Pilar';
        if (btnCancelEdit) btnCancelEdit.style.display = '';
        if (catFeedback) catFeedback.textContent = '';
      }});
    }});

    // Category Form Submit
    const activeProjectId = "{e(current_project_id)}";
    if (catForm) {{
      catForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const id = (catIdInput && catIdInput.value.trim()) || null;
        const name = catNameInput ? catNameInput.value.trim() : '';
        if (!name) return;

        const rawQueries = catQueriesInput ? catQueriesInput.value : '';
        const queries = rawQueries
          .split(',')
          .map((q) => q.trim())
          .filter((q) => q.length > 0);

        if (btnSaveCat) btnSaveCat.disabled = true;
        if (catFeedback) catFeedback.textContent = 'Salvando pilar...';

        try {{
          const payload = {{ name: name, queries: queries }};
          if (id) payload.id = id;

          const res = await fetch('/studio/projects/' + encodeURIComponent(activeProjectId) + '/categories', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload)
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            if (catFeedback) catFeedback.textContent = 'Pilar salvo com sucesso! Atualizando...';
            setTimeout(() => location.reload(), 600);
          }} else if (res.status === 409) {{
            if (catFeedback) catFeedback.textContent = 'Já existe um pilar com este nome no projeto.';
            if (btnSaveCat) btnSaveCat.disabled = false;
          }} else {{
            const errMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
            if (catFeedback) catFeedback.textContent = 'Erro: ' + errMsg;
            if (btnSaveCat) btnSaveCat.disabled = false;
          }}
        }} catch (err) {{
          if (catFeedback) catFeedback.textContent = 'Falha de rede: ' + err.message;
          if (btnSaveCat) btnSaveCat.disabled = false;
        }}
      }});
    }}

    // Category Delete
    document.querySelectorAll('.btn-delete-category').forEach((btn) => {{
      btn.addEventListener('click', async () => {{
        const catId = btn.dataset.id;
        const catName = btn.dataset.name || 'este pilar';
        if (!catId) return;
        if (!confirm('Deseja excluir o pilar "' + catName + '"?')) return;

        btn.disabled = true;
        if (catFeedback) catFeedback.textContent = 'Excluindo pilar...';

        try {{
          const res = await fetch('/studio/projects/' + encodeURIComponent(activeProjectId) + '/categories/' + encodeURIComponent(catId), {{
            method: 'DELETE'
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            if (catFeedback) catFeedback.textContent = 'Pilar excluído com sucesso! Atualizando...';
            setTimeout(() => location.reload(), 600);
          }} else {{
            const errMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
            if (catFeedback) catFeedback.textContent = 'Erro ao excluir: ' + errMsg;
            btn.disabled = false;
          }}
        }} catch (err) {{
          if (catFeedback) catFeedback.textContent = 'Falha de rede: ' + err.message;
          btn.disabled = false;
        }}
      }});
    }});

    // Refresh Trends
    const btnRefresh = document.getElementById('btn-refresh-trends');
    const refreshFeedback = document.getElementById('trends-refresh-feedback');
    if (btnRefresh) {{
      btnRefresh.addEventListener('click', async () => {{
        btnRefresh.disabled = true;
        const origText = btnRefresh.textContent;
        btnRefresh.textContent = ' Consultando YouTube...';
        const spinner = document.createElement('span');
        spinner.className = 'spinner-inline';
        btnRefresh.prepend(spinner);
        if (refreshFeedback) refreshFeedback.textContent = 'Consultando YouTube Data API com seus pilares de conteúdo...';

        try {{
          const res = await fetch('/studio/projects/' + encodeURIComponent(activeProjectId) + '/trends/refresh', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{}})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            const count = typeof data.stored === 'number' ? data.stored : 0;
            if (refreshFeedback) refreshFeedback.textContent = 'Coleta concluída (' + count + ' temas encontrados)! Atualizando...';
            setTimeout(() => location.reload(), 500);
          }} else {{
            const msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
            if (refreshFeedback) refreshFeedback.textContent = 'Erro na coleta: ' + msg;
            btnRefresh.disabled = false;
            btnRefresh.textContent = origText;
          }}
        }} catch (err) {{
          if (refreshFeedback) refreshFeedback.textContent = 'Falha de rede: ' + err.message;
          btnRefresh.disabled = false;
          btnRefresh.textContent = origText;
        }}
      }});
    }}
  </script>
</body>
</html>"""
    return html_content, _headers(nonce)


def render_video(view: VideoDetailView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    v = view.video

    step_state_labels = {
        "SUCCEEDED": ("done", "✓", "Concluído"),
        "FAILED": ("action", "!", "Ação necessária"),
        "RUNNING": ("running", "▶", "Em execução"),
    }

    steps_html = []
    if not view.steps:
        steps_html.append(
            '<li class="timeline-item"><div class="timeline-desc">'
            'Nenhum passo executado ainda. Sem execução registrada.</div></li>'
        )
    else:
        for step in view.steps:
            kind, icon, label = step_state_labels.get(
                step.status, ("idle", "·", "Sem execução registrada")
            )
            steps_html.append(f"""
              <li class="timeline-item">
                <div class="timeline-dot"></div>
                <div class="timeline-title">{e(step.step)} (tentativa {step.attempt})</div>
                <div class="timeline-desc">
                  <span class="state s-{kind}" data-state="{kind}">
                    <span class="state-icon" aria-hidden="true">{icon}</span> <span>{label}</span>
                  </span>
                  <span style="margin-left: 0.4rem;">{step.started_at.strftime("%d/%m %H:%M:%S")}</span>
                </div>
              </li>
            """)

    usage_html = []
    if not view.usage:
        usage_html.append('<tr><td colspan="4" class="empty">Sem registro de uso de IA para este vídeo.</td></tr>')
    else:
        for usage in view.usage:
            kind = cost_kind(usage.cost_confirmation_kind, usage.provider, usage.model, usage.cost_usd)
            if kind is CostKind.REAL:
                cost_str = f"Real: US$ {usage.cost_usd:.2f}".replace(".", ",")
            elif kind is CostKind.ESTIMATE:
                cost_str = f"Estimado: US$ {usage.cost_usd:.2f}".replace(".", ",")
            elif kind is CostKind.FREE:
                cost_str = "Sem custo"
            else:
                cost_str = '<span style="color: var(--warn);">Desconhecido</span>'
            usage_html.append(f"""
              <tr>
                <td>{e(usage.step)}</td>
                <td>{e(usage.provider)}</td>
                <td>{e(usage.model)}</td>
                <td>{cost_str}</td>
              </tr>
            """)

    failed_steps = [step for step in view.steps if step.status == "FAILED"]
    has_render_failure = bool(view.render_error or failed_steps)
    has_publication_failure = bool(
        view.publication and view.publication.status == PublicationStatus.FAILED
    )

    failure_paragraphs = []
    retry_buttons = []
    if has_render_failure:
        failed_step_name = failed_steps[-1].step if failed_steps else "render"
        failure_paragraphs.append(f"<p><strong>Falha na etapa {e(failed_step_name)}.</strong></p>")
        failure_paragraphs.append(
            f"<p>Passo de correção: revise a etapa {e(failed_step_name)} e reexecute a produção.</p>"
        )
        if view.render_error and v.status == VideoStatus.ASSETS_READY:
            retry_buttons.append(
                f'<button type="button" class="btn btn-primary btn-compact" '
                f'id="btn-retry-render" data-video-id="{e(v.id)}">Tentar render novamente</button>'
            )
        else:
            failure_paragraphs.append(
                "<p>Nova tentativa de render só é válida quando o vídeo está pronto para renderizar. "
                "Corrija o passo no painel para voltar a esse estado.</p>"
            )
    if has_publication_failure:
        failure_paragraphs.append("<p><strong>Falha na publicação.</strong></p>")
        failure_paragraphs.append(
            "<p>Passo de correção: confira os dados da publicação e tente novamente.</p>"
        )
        retry_buttons.append(
            f'<button type="button" class="btn btn-primary btn-compact" '
            f'id="btn-retry-publication" data-video-id="{e(v.id)}">Tentar publicar novamente</button>'
        )

    failure_html = ""
    if failure_paragraphs:
        actions = (
            f'<div class="form-actions" style="margin-top: 0.6rem;">{"".join(retry_buttons)}</div>'
            if retry_buttons else ""
        )
        failure_html = f'<div class="failure-summary">{"".join(failure_paragraphs)}{actions}</div>'

    publication_summary_html = ""
    if view.publication:
        publication_summary_html = f"""
          <div class="section-block" style="margin-top: 1rem;">
            <h3>Publicação</h3>
            <p>Status: <span class="pill pill-{e(view.publication.status.value)}">{e(view.publication.status.value)}</span>
            (tentativa {view.publication.attempt})</p>
          </div>
        """

    render_err_html = (
        f'<div class="warning"><strong>Erro de renderização (bruto):</strong> '
        f'<code>{e(view.render_error)}</code></div>'
        if view.render_error else ""
    )
    step_errors_html = "".join(
        f'<div class="warning"><strong>Passo {e(step.step)} (tentativa {step.attempt}) — erro bruto:</strong> '
        f'<code>{e(step.error_message)}</code></div>'
        for step in view.steps
        if step.error_message
    )
    pub_err_html = ""
    if view.publication and view.publication.error:
        pub_err_html = (
            f'<div class="warning"><strong>Publicação (erro bruto):</strong> '
            f'<code>{e(view.publication.error)}</code></div>'
        )

    preview_nav_html = ""
    preview_stages = (Stage.AWAITING_APPROVAL, Stage.APPROVED, Stage.COMPLETED)
    if view.stage in preview_stages:
        preview_nav_html = f"""
          <li>
            <a class="nav-item" href="/studio/videos/{e(v.id)}/preview">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
              <span>Ver Prévia</span>
            </a>
          </li>
        """
    else:
        preview_nav_html = """
          <li>
            <span class="nav-item nav-item-unavailable" aria-disabled="true" tabindex="-1">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
              <span>Prévia após render</span><span class="nav-tag">indisponível</span>
            </span>
          </li>
        """

    if view.stage == Stage.AWAITING_APPROVAL:
        header_action_html = (
            f'<a class="btn btn-primary" href="/studio/videos/{e(v.id)}/preview">Abrir Prévia e Aprovar</a>'
        )
    elif view.stage in (Stage.APPROVED, Stage.COMPLETED):
        header_action_html = (
            f'<a class="btn btn-primary" href="/studio/videos/{e(v.id)}/preview">Abrir Prévia</a>'
        )
    else:
        header_action_html = (
            '<span class="section-sub" style="margin: 0;">Prévia e aprovação ficam disponíveis após a renderização.</span>'
        )

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Faceless Studio — Detalhe do Vídeo</title>
  <style nonce="{nonce}">{CSS}</style>
</head>
<body>
  <a class="skip-link" href="#detalhe-heading">Ir para o conteúdo</a>
  <div class="app-layout">
    <aside class="sidebar" aria-label="Barra lateral">
      <div class="brand">
        <div class="brand-icon">🎬</div>
        <div>
          <div class="brand-title">FACELESS STUDIO</div>
          <div class="brand-sub">Pipeline de Vídeos</div>
        </div>
      </div>
      <nav class="nav-menu" aria-label="Navegação do vídeo">
        <ul class="nav-list">
          <li>
            <a class="nav-item" href="/studio/panel">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
              <span>Painel</span>
            </a>
          </li>
          <li>
            <span class="nav-item active" aria-current="page">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect><line x1="7" y1="2" x2="7" y2="22"></line><line x1="17" y1="2" x2="17" y2="22"></line><line x1="2" y1="12" x2="22" y2="12"></line></svg>
              <span>Detalhe do Vídeo</span>
            </span>
          </li>
          <li>
            <a class="nav-item" href="/studio/videos/{e(v.id)}/roteiro">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 4h16v16H4z"></path><line x1="8" y1="9" x2="16" y2="9"></line><line x1="8" y1="13" x2="14" y2="13"></line></svg>
              <span>Roteiro</span>
            </a>
          </li>
          {preview_nav_html}
          <li>
            <a class="nav-item" href="/docs" target="_blank" rel="noopener noreferrer">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
              <span>API Docs</span>
            </a>
          </li>
        </ul>
      </nav>
      <div class="sidebar-footer">
        <div style="font-size: 0.72rem; color: var(--text-muted);">ID, erros brutos e uso de modelos ficam em Avançado — diagnóstico.</div>
      </div>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div>
          <div style="font-size: 0.8rem; margin-bottom: 0.25rem;"><a href="/studio/panel">&larr; Voltar ao Painel</a></div>
          <h1 id="detalhe-heading">{e(v.topic)}</h1>
          <div style="margin-top: 0.25rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
            {_state_badge(view.stage)}
            <span class="pill pill-{e(view.stage.value)}">{e(STAGE_LABELS.get(view.stage, view.stage.value))}</span>
            <span style="font-size: 0.85rem; color: var(--text-muted);">Custo do vídeo: {_cost_html(view.cost_text)}</span>
          </div>
        </div>
        <div>{header_action_html}</div>
      </header>

      <div class="content-body">
        <div class="layout-detail">
          <div class="card">
            <h2>Linha do Tempo dos Passos</h2>
            <ul class="timeline">
              {''.join(steps_html)}
            </ul>
            {failure_html}
            {publication_summary_html}
          </div>
        </div>

        <details class="card advanced" id="advanced-diagnostics">
          <summary class="advanced-summary">Avançado — diagnóstico</summary>
          <div class="advanced-body">
            <p>ID do vídeo: <code>{e(v.id)}</code></p>
            <div>
              <h3>Registro de Uso de Modelos</h3>
              <p class="cost-note">Cada chamada vem rotulada: “Real”, “Estimado”, “Sem custo” ou “Desconhecido”. Real e estimado nunca são fundidos.</p>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Passo</th>
                    <th scope="col">Provedor</th>
                    <th scope="col">Modelo</th>
                    <th scope="col">Custo</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(usage_html)}
                </tbody>
              </table>
            </div>
            {render_err_html}
            {step_errors_html}
            {pub_err_html}
          </div>
        </details>
      </div>
    </main>
  </div>
  <script nonce="{nonce}">
    function wireRetry(buttonId, url) {{
      const button = document.getElementById(buttonId);
      if (!button) return;
      button.addEventListener('click', async () => {{
        button.disabled = true;
        const original = button.textContent;
        button.textContent = 'Enviando...';
        try {{
          const response = await fetch(url, {{ method: 'POST' }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok) {{
            button.textContent = 'Solicitado. Atualizando...';
            setTimeout(() => location.reload(), 800);
          }} else {{
            button.disabled = false;
            button.textContent = original;
            const message = typeof data.detail === 'string' ? data.detail : 'Não foi possível repetir a operação.';
            window.alert(message);
          }}
        }} catch (error) {{
          button.disabled = false;
          button.textContent = original;
          window.alert('Falha de rede: ' + error.message);
        }}
      }});
    }}
    wireRetry('btn-retry-render', '/studio/videos/{e(v.id)}/resume');
    wireRetry('btn-retry-publication', '/studio/videos/{e(v.id)}/publication/retry');
  </script>
</body>
</html>"""
    return html_content, _headers(nonce)


def _duration_text(seconds: float | None) -> str:
    """Duração legível a partir de segundos reais; vazio quando não há estimativa."""
    if seconds is None:
        return ""
    total = int(round(seconds))
    minutes, rest = divmod(total, 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"


def _fact_check_text(fact_check) -> str:
    if fact_check is None:
        return "sem fact-check"
    if not fact_check.current:
        return f"desatualizado (cobre a versão {fact_check.script_version})"
    if fact_check.passed:
        return "aprovado" + (" (override)" if fact_check.overridden else "")
    return "reprovado"


def render_script(view: ScriptPageView) -> tuple[str, dict[str, str]]:
    """Página do Roteiro (mockup #roteiro) com dado real ou estado vazio explícito."""
    nonce = secrets.token_urlsafe(16)

    if not view.has_script:
        body_html = (
            '<article class="card empty" id="roteiro-vazio">'
            '<h2>Nenhum roteiro registrado para este vídeo</h2>'
            '<p class="section-sub">Gere um roteiro longo para ver capítulos, duração estimada e aprovação por versão.</p>'
            '</article>'
        )
        rail_html = (
            '<section class="card" aria-labelledby="h-duracao"><h2 id="h-duracao">Duração</h2>'
            '<p class="fine">Sem roteiro não há estimativa de duração. A duração real só existe depois do TTS.</p></section>'
        )
        approve_button = ""
    else:
        duration = _duration_text(view.estimated_seconds)
        chapter_items = "".join(
            f'<div class="kv"><span>{chapter.index + 1}. {e(chapter.title)} — {e(chapter.block_label)} · '
            f'{chapter.scene_count} cena(s)</span><span>{e(_duration_text(chapter.estimated_seconds))}</span></div>'
            for chapter in view.chapters
        )
        if not chapter_items:
            chapter_items = '<p class="empty">Capítulos não registrados para esta versão.</p>'

        badge = (
            '<span class="state s-done"><span class="state-icon" aria-hidden="true">✓</span> Versão aprovada</span>'
            if view.approved else
            '<span class="state s-act"><span class="state-icon" aria-hidden="true">!</span> Aguardando sua aprovação</span>'
        )
        fact_text = _fact_check_text(view.fact_check)
        hash_of_latest = next((v.content_hash for v in view.versions if v.current and v.content_hash), None)
        version_no = view.version or 0
        if view.approved:
            approve_button = (
                f'<button type="button" class="btn btn-primary" id="btn-approve-script" disabled '
                f'aria-disabled="true">Versão {version_no} aprovada</button>'
            )
        else:
            approve_button = (
                f'<button type="button" class="btn btn-primary" id="btn-approve-script" '
                f'data-video-id="{e(view.video_id)}" data-version="{version_no}" '
                f'data-hash="{e(hash_of_latest or "")}">Aprovar versão {version_no}</button>'
            )

        body_html = f"""
          <section class="card" aria-labelledby="roteiro-versao">
            <div class="spread">
              <div>
                <h2 id="roteiro-versao">Versão {version_no} · {e(duration)} estimados</h2>
                <p class="section-sub" style="margin:0">{view.chapter_count} capítulos · {view.scene_count} cenas · fact-check {e(fact_text)}</p>
              </div>
              {badge}
            </div>
            <div class="list" style="margin-top:12px">{chapter_items}</div>
            <div class="spread" style="margin-top:16px">
              <p class="fine" style="margin:0">Aprovar congela esta versão (<code>script_v{version_no}</code>). Editar cria a v{version_no + 1} e invalida só o que depende dela.</p>
              <div class="row">
                <a class="btn" href="/studio/panel/videos/{e(view.video_id)}">Editar cenas</a>
                {approve_button}
              </div>
            </div>
          </section>
          <details class="advanced" id="roteiro-versoes">
            <summary class="advanced-summary">Avançado — versões e fact-check</summary>
            <div class="advanced-body">
              {"".join(_version_row(v) for v in view.versions)}
              <p class="fine">Cada claim aponta para o snapshot da fonte que o sustenta.</p>
            </div>
          </details>
          <div id="approve-feedback" class="form-feedback" role="status"></div>
        """

        review_html = ""
        if view.review is not None:
            review_html = f"""
              <section class="card" aria-labelledby="h-revisao">
                <h2 id="h-revisao">Revisão do roteiro</h2>
                <div class="kv"><span>Estrutura (gancho→fechamento)</span><span>{_mark(view.review.structure_ok)}</span></div>
                <div class="kv"><span>Continuidade dos capítulos</span><span>{_mark(view.review.continuity_ok)}</span></div>
                <div class="kv"><span>Duração dentro do alvo</span><span>{_mark(view.review.duration_ok)}</span></div>
                <div class="kv"><span>Cenas redundantes</span><span>{view.review.redundant_count}</span></div>
                <div class="kv"><span>Cenas sem citação</span><span>{view.review.uncited_count}</span></div>
                <div class="kv"><span>Itens sem lastro nas fontes</span><span>{view.review.invented_count}</span></div>
              </section>
            """
        rail_html = f"""
          <section class="card" aria-labelledby="h-duracao">
            <h2 id="h-duracao">Duração</h2>
            <div class="kv"><span>Alvo</span><span>{e(f"{int(round(view.target_seconds))} s") if view.target_seconds else "não definido"}</span></div>
            <div class="kv"><span>Estimado</span><span>{e(duration) or "sem estimativa"}</span></div>
            <p class="fine">Estimativa por palavras/minuto. A duração real só existe depois do TTS — por isso a página não promete “exato”.</p>
          </section>
          {review_html}
        """

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>Faceless Studio — Roteiro</title>
  <style nonce="{nonce}">{CSS}</style>
</head>
<body>
  <a class="skip-link" href="#roteiro-heading">Ir para o conteúdo</a>
  <div class="app-layout">
    <aside class="sidebar" aria-label="Barra lateral">
      <div class="brand">
        <div class="brand-icon" aria-hidden="true">FS</div>
        <div>
          <div class="brand-title">Faceless Studio V2</div>
          <div class="brand-sub">YouTube Automation</div>
        </div>
      </div>
      <nav class="nav" aria-label="Principal">
        <p class="nav-label">Operação</p>
        <ul class="nav-list">
          <li><a class="nav-item" href="/studio/panel">Início</a></li>
          <li><a class="nav-item" href="/studio/panel/videos/{e(view.video_id)}">Detalhe do vídeo</a></li>
        </ul>
      </nav>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div>
          <div style="font-size: 0.8rem; margin-bottom: 0.25rem;"><a href="/studio/panel/videos/{e(view.video_id)}">&larr; Voltar ao vídeo</a></div>
          <h1 id="roteiro-heading">Roteiro — {e(view.topic)}</h1>
          <p class="section-sub" style="margin:0">Aprovação fica presa a uma versão; editar cria outra.</p>
        </div>
      </header>
      <div class="content-body">
        {body_html}
      </div>
    </main>

    <aside class="rail" aria-label="Resumo">
      {rail_html}
    </aside>
  </div>
  <script nonce="{nonce}">
    const approveBtn = document.getElementById('btn-approve-script');
    if (approveBtn && !approveBtn.disabled) {{
      approveBtn.addEventListener('click', async () => {{
        const feedback = document.getElementById('approve-feedback');
        approveBtn.disabled = true;
        feedback.textContent = 'Registrando aprovação...';
        try {{
          const res = await fetch('/studio/videos/' + approveBtn.dataset.videoId + '/script/approve', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ version: Number(approveBtn.dataset.version), content_hash: approveBtn.dataset.hash }})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            feedback.textContent = 'Versão aprovada. Atualizando...';
            setTimeout(() => location.reload(), 800);
          }} else {{
            approveBtn.disabled = false;
            feedback.textContent = typeof data.detail === 'string' ? data.detail : 'Não foi possível aprovar a versão.';
          }}
        }} catch (err) {{
          approveBtn.disabled = false;
          feedback.textContent = 'Falha de rede: ' + err.message;
        }}
      }});
    }}
  </script>
</body>
</html>"""
    return html_content, _headers(nonce)


def _mark(ok: bool) -> str:
    return "✓ sem problema" if ok else "× atenção"


def _version_row(version) -> str:
    if version.current:
        label = f'atual · hash <code>{e(version.hash_short or "")}</code>'
    elif version.approved:
        label = "aprovada (superada)"
    elif version.rejected:
        label = "rejeitada"
    elif version.superseded:
        label = "substituída"
    else:
        label = "sem decisão"
    return f'<div class="kv"><span>script_v{version.version}</span><span>{label}</span></div>'
