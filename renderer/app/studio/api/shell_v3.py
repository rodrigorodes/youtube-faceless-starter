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
_ALIASES = {"producao": "videos", "analytics": "desempenho", "video": "videos", "roteiro": "videos"}

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
        <button class="link-btn" type="button" id="btn-novo-canal">+ Novo canal</button>
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
            <button class="btn" type="button" data-fechar-dialogo>Cancelar</button>
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

  // ---- canal ativo: recarrega a tela no canal escolhido ----
  var sel = $('#canal-ativo');
  if (sel) sel.addEventListener('change', function () {
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
      btn.disabled = true; fb.removeAttribute('data-tipo'); fb.textContent = 'Cadastrando canal…';
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
          }
        })
        .catch(function (err) {
          fb.setAttribute('data-tipo', 'erro'); fb.textContent = 'Falha de rede: ' + err.message; btn.disabled = false;
        });
    });
  }
})();
"""


def render_document(*, title: str, active: str, crumb: str, body_html: str, nonce: str,
                    projects: list[tuple[str, str]], project_id: str, cost_note: str = "",
                    page_js: str = "") -> str:
    """Documento completo da tela V3. `body_html` é o conteúdo de `<div class="content">`."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{e(title)}</title>
  <style nonce="{nonce}">{V3_CSS}{PRODUCT_CSS}</style>
  <script nonce="{nonce}">{THEME_BOOT_JS}</script>
</head>
<body>
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
