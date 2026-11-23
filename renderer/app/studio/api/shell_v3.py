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

from .active_channel import propagate, with_channel

from html import escape as e

from .shell_v3_css import V3_CSS

# Extensões funcionais do produto sobre o CSS aprovado (o protótipo é estático e não cobre estes casos).
PRODUCT_CSS = """
/* Utilitários específicos do produto */
.nota-custo { font-size: 12px; color: var(--muted); padding: 4px 11px 8px; margin: 0; }
.feedback { font-size: 12px; color: var(--muted); min-height: 18px; margin: 8px 0 0; }
.feedback[data-tipo="erro"] { color: var(--warn); font-weight: 600; }
.cartao-projeto, .cartao-tendencia {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 18px;
  display: flex;
  flex-direction: column;
}
.grade, .grade-tendencias {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.campo-tema { margin-top: 10px; }
.tabela-lista, .tabela { width: 100%; border-collapse: collapse; font-size: 13px; }
.tabela-lista th, .tabela-lista td, .tabela th, .tabela td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); }
.tabela-lista th, .tabela th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; }
.tabela-kv { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.tabela-kv th, .tabela-kv td { padding: 8px 0; border-bottom: 1px solid var(--line); text-align: left; }
.tabela-kv th { color: var(--muted); width: 35%; font-weight: normal; }
.tabela-kv td { color: var(--text); font-weight: 600; }
.kv { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid var(--line); font-size: 12.5px; }
.kv:last-child { border-bottom: 0; }
.kv span:last-child { color: var(--text); font-weight: 600; }

/* Spinner e barra de progresso */
@keyframes spin { to { transform: rotate(1turn); } }
.btn.carregando::before, .btn.is-loading::before {
  content: ''; display: inline-block; width: 14px; height: 14px; margin-right: 8px;
  border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%;
  animation: spin 0.75s linear infinite; vertical-align: -2px;
}
#barra-progresso-topo {
  position: fixed; top: 0; left: 0; height: 3px; width: 0%;
  background: var(--accent); z-index: 99999;
  transition: width 0.25s ease, opacity 0.3s ease; pointer-events: none; opacity: 0;
}
#barra-progresso-topo.ativo { opacity: 1; }
#barra-progresso-topo.finalizado { width: 100% !important; opacity: 0; }
#indicador-carregando {
  position: fixed; bottom: 24px; right: 24px; z-index: 99999;
  display: inline-flex; align-items: center; gap: 10px;
  background: var(--panel2); color: var(--text); border: 1px solid var(--line2);
  border-radius: 999px; padding: 8px 16px; font-size: 12.5px; font-weight: 600;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5); pointer-events: none; opacity: 0;
  transition: opacity 0.2s ease;
}
#indicador-carregando.ativo { opacity: 1; }
.indicador-spinner {
  width: 14px; height: 14px; border: 2px solid var(--accent);
  border-right-color: transparent; border-radius: 50%;
  animation: spin 0.75s linear infinite; flex-shrink: 0;
}

/* Modais e diálogos */
.dialogo-corpo .campo input, .dialogo-corpo .campo select { width: 100%; }
.modal-card { width: 100%; }
.modal-close { background: transparent; border: 0; font-size: 18px; color: var(--muted); cursor: pointer; }
.modal-close:hover { color: var(--text); }
.modal-footer { margin-top: 16px; display: flex; justify-content: flex-end; gap: 8px; }
.form-feedback { font-size: 12px; color: var(--muted); margin-top: 6px; }

/* Configurações grid */
.grade-config { display: grid; grid-template-columns: 210px 1fr; gap: 24px; align-items: start; }
.menu-config { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.menu-config a {
  display: block; padding: 8px 12px; border-radius: 8px; color: var(--muted); font-weight: 550; text-decoration: none;
}
.menu-config a:hover { background: var(--panel2); color: var(--text); }
.menu-config a[aria-current=page] { background: var(--accentbg); color: var(--accent2); font-weight: 650; }
.config-corpo { display: flex; flex-direction: column; gap: 18px; }

/* Galeria de estilos (novo vídeo / biblioteca) */
.galeria { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.cartao-estilo {
  border: 1px solid var(--line); border-radius: 10px; background: var(--panel2);
  padding: 12px; cursor: pointer; display: flex; flex-direction: column; gap: 8px;
}
.cartao-estilo:has(input:checked) { border-color: var(--accent); background: var(--accentbg); }
.cartao-estilo .amostra {
  height: 50px; background: var(--panel3); border-radius: 6px; display: grid; place-items: center;
  font-weight: 700; font-size: 11px; letter-spacing: 0.5px; color: var(--accent2);
}
.cartao-estilo .cartao-rodape { font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 6px; }

/* Linha de busca e filtros da biblioteca de vídeos */
.linha-busca { display: flex; justify-content: space-between; align-items: flex-end; gap: 14px; margin-bottom: 18px; flex-wrap: wrap; }
.filtros { border: 0; padding: 0; margin: 0; }
.pills { display: flex; gap: 6px; flex-wrap: wrap; }
.pills .pill { cursor: pointer; }
.pills .pill:has(input:checked) { background: var(--accentbg); border-color: var(--accent); color: var(--accent2); font-weight: 650; }
"""

_SVG = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
        'focusable="false" style="width:16px;height:16px;min-width:16px;min-height:16px;flex-shrink:0">{}</svg>')

_ICONS = {
    "inicio": _SVG.format('<path d="m3 11 9-8 9 8v9H3z"/><path d="M9 20v-7h6v7"/>'),
    "novo-video": _SVG.format('<path d="M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z"/>'),
    "videos": _SVG.format('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 9 5 3-5 3z"/>'),
    "tendencias": _SVG.format('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>'),
    "desempenho": _SVG.format('<path d="M3 20h18M6 16V9m6 7V4m6 12v-5"/>'),
    "configuracoes": _SVG.format(
        '<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/>'),
    "biblioteca": _SVG.format(
        '<path d="M4 4h5v16H4zM10 4h4v16h-4zM16 5l4 1-3 15-4-1z"/>'),
}

# W1.5 (SET): item "Biblioteca" do protótipo (`prototype/index.html:583`) apontando para a
# biblioteca de estilos que já existe. Vozes e mídias entram quando houver provider/ativo a listar.
BIBLIOTECA_HREF = "/studio/panel/estilos"
CONFIG_HREF = "/studio/configuracoes/canais"

# Navegação principal = `NAV` do protótipo (`prototype/index.html:583`): **sete itens numa lista
# só**, com "Configurações" como o sétimo. Antes, Configurações vivia num `<nav>` separado no rodapé
# da casca — duas listas para a mesma navegação e o item "escondido" (comparação em
# `docs/backlogs/faceless-visual-evolution 2/analysis/NAVEGACAO-COMPARACAO.md`).
NAV_OPERACAO: tuple[tuple[str, str, str], ...] = (
    ("inicio", "Início", "/studio/panel"),
    ("novo-video", "Criar vídeo", "/studio/panel/novo-video"),
    ("videos", "Vídeos", "/studio/panel/videos"),
    ("tendencias", "Tendências e ideias", "/studio/panel/tendencias"),
    ("desempenho", "Desempenho", "/studio/panel/analytics"),
    ("biblioteca", "Biblioteca", BIBLIOTECA_HREF),
    ("configuracoes", "Configurações", CONFIG_HREF),
)

# Telas que existem fora do menu e herdam o item atual do menu mais próximo.
_ALIASES = {
    "producao": "videos",
    "analytics": "desempenho",
    "video": "videos",
    "roteiro": "videos",
    "execucao": "videos",
    "preview": "videos",
    "canais": "configuracoes",
    "estilos": "biblioteca",
    "biblioteca": "biblioteca",
    "conexoes": "configuracoes",
    "equipe": "configuracoes",
}

# W1.5: sete seções de Configurações, com os rótulos do protótipo (`CFG`,
# `prototype/index.html:585`). Cada item aponta para conteúdo real: páginas próprias
# (`/studio/configuracoes/{secao}`) ou a tela que já existe.
SETTINGS_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("canais", "Canais", "/studio/configuracoes/canais"),
    ("estrategia", "Estratégia editorial", "/studio/configuracoes/estrategia"),
    ("marca", "Marca e estilo", "/studio/configuracoes/marca"),
    ("producao", "Produção e orçamento", "/studio/configuracoes/producao"),
    ("conexoes", "Conexões e providers", "/studio/panel/conexoes"),
    ("equipe", "Conta e equipe", "/studio/panel/equipe"),
    ("avancado", "Avançado e diagnóstico", "/studio/panel/avancado"),
)


def render_settings_nav(active_section: str, project_id: str = "") -> str:
    items = []
    for key, label, href in SETTINGS_SECTIONS:
        curr = ' aria-current="page"' if key == active_section else ""
        items.append(f'<li><a href="{e(with_channel(href, project_id))}"{curr}>{e(label)}</a></li>')
    return f"""<nav aria-label="Seções de configuração">
      <ul class="menu-config" id="menu-config">
        {"".join(items)}
      </ul>
    </nav>"""


def render_settings_page_body(*, active_section: str, section_title: str, content_html: str,
                              project_id: str = "") -> str:
    # W1.5/UX: textos do protótipo (`prototype/index.html:622` → `heading('CONFIGURAÇÕES', ...)`).
    return f"""      <section class="pagina" id="pagina-configuracoes" aria-labelledby="t-config">
        <p class="eyebrow">CONFIGURAÇÕES</p>
        <h1 class="h1" id="t-config">Seu estúdio, do seu jeito</h1>
        <p class="lead" style="margin-bottom:24px">Identidade do canal, produção, integrações e controles avançados.</p>

        <div class="grade-config">
          {render_settings_nav(active_section, project_id)}
          <div class="config-corpo" aria-label="{e(section_title)}">
            {content_html}
          </div>
        </div>
      </section>"""


def render_library_page_body(*, title: str, lead: str, content_html: str) -> str:
    """Corpo da página **Biblioteca** (W1.5): destino de topo, não uma seção de Configurações.

    O protótipo trata a biblioteca como item próprio do menu (`NAV` → `library`), fora de `CFG`;
    por isso a página não carrega a navegação de configurações. O conteúdo é o mesmo componente
    da biblioteca de estilos, só sem o layout de Configurações.
    """
    return f"""      <section class="pagina" id="pagina-biblioteca" aria-labelledby="t-biblioteca">
        <div class="head">
          <div>
            <p class="eyebrow">RECURSOS REUTILIZÁVEIS</p>
            <h1 class="h1" id="t-biblioteca">{e(title)}</h1>
            <p class="sub">{e(lead)}</p>
          </div>
        </div>
        <div class="stack" style="gap:16px">
          {content_html}
        </div>
      </section>"""


_NAV_LABELS = {key: label for key, label, _ in NAV_OPERACAO}
_NAV_LABELS["configuracoes"] = "Configurações"


def _nav_item(key: str, label: str, href: str, active: str) -> str:
    current = ' aria-current="page"' if key == active else ""
    return f'<li><a href="{e(href)}"{current}>{_ICONS[key]}{e(label)}</a></li>'


def render_sidebar(*, active: str, cost_note: str = "", project_id: str = "") -> str:
    active = _ALIASES.get(active, active)
    # F02.T01/G11: a navegação leva o canal ativo; sem ele a próxima tela voltaria ao primeiro canal.
    items = "".join(_nav_item(k, label, with_channel(href, project_id), active)
                    for k, label, href in NAV_OPERACAO)
    cost = f'<span class="sub" style="font-size:11px">{e(cost_note)}</span>' if cost_note else '<span class="sub" style="font-size:11px">Consumo em tempo real</span>'
    return f"""<aside class="side" aria-label="Menu principal">
    <div class="logo"><i>✦</i> Faceless Studio</div>
    <nav aria-label="Principal">
      <ul class="nav-list">{items}</ul>
    </nav>
    <div class="sp"></div>
    <div class="budget" id="budget">
      <b style="color:var(--text)">Orçamento do mês</b><br>
      {cost}
      <div class="bar"><b style="width:28%"></b></div>
      <span class="sample">Valores reais</span>
    </div>
  </aside>"""


def render_topbar(*, crumb: str, projects: list[tuple[str, str]], project_id: str,
                  video_channel: str = "") -> str:
    if video_channel:
        select = (f'<span class="canal-video pill" id="canal-do-video" title="Canal dono deste vídeo">'
                  f'Canal: <b style="color:var(--text)">{e(video_channel)}</b></span>')
    elif projects:
        options = "".join(
            f'<option value="{e(pid)}"{" selected" if pid == project_id else ""}>{e(name)}</option>'
            for pid, name in projects
        )
        select = (f'<label class="sr-only" for="canal-ativo">Canal ativo</label>'
                  f'<select class="canal-select" id="canal-ativo">{options}</select>')
    else:
        select = '<span class="pill" id="sem-canal">Nenhum canal cadastrado</span>'

    novo_vid_url = with_channel("/studio/panel/novo-video", project_id)
    return f"""<header class="top">
      <div class="l">
        {select}
        <button class="btn ghost small" type="button" id="btn-novo-canal" title="Novo canal" aria-label="Novo canal" style="white-space:nowrap">＋ Canal</button>
        <span class="pill" id="chstyle">🎨 Padrão do canal · 🎙 Voz vinculada</span>
      </div>
      <div class="r">
        <p class="crumb">Estúdio &nbsp;/&nbsp; <b>{e(crumb)}</b></p>
        <button class="icon-btn" type="button" id="btn-tema" aria-pressed="false" hidden
                title="Alternar tema claro/escuro" aria-label="Alternar tema claro/escuro">◐</button>
        <a class="btn primary" href="{e(novo_vid_url)}">✦ Criar vídeo</a>
      </div>
    </header>"""


def render_novo_canal_dialog() -> str:
    return """<dialog id="dlg-canal" class="modal" aria-labelledby="t-dlg-canal">
    <div class="modal-header">
      <h2 id="t-dlg-canal">Novo canal</h2>
      <button class="modal-close" type="button" data-fechar-dialogo aria-label="Fechar">✕</button>
    </div>
    <div class="dialogo-corpo">
      <form id="form-canal" class="stack" style="gap:14px">
        <div class="field">
          <label for="dlg-canal-nome">Nome do canal *</label>
          <input class="input" type="text" id="dlg-canal-nome" name="name" minlength="1" maxlength="120" required
                 placeholder="Ex.: Curiosidades Históricas">
        </div>
        <div class="field">
          <label for="dlg-canal-nicho">Nicho editorial <span class="sample">(opcional)</span></label>
          <input class="input" type="text" id="dlg-canal-nicho" name="niche" maxlength="200"
                 placeholder="Ex.: História, mistérios e ciência">
        </div>
        <div class="field">
          <label for="dlg-canal-idioma">Idioma</label>
          <select class="input" id="dlg-canal-idioma" name="language">
            <option value="pt-BR" selected>Português (BR)</option>
            <option value="en-US">English</option>
            <option value="es-ES">Español</option>
          </select>
        </div>
        <div class="modal-footer">
          <p class="feedback" id="canal-feedback" role="status" style="margin-right:auto"></p>
          <button class="btn ghost small" type="button" data-fechar-dialogo>Fechar</button>
          <button class="btn primary small" type="submit" id="dlg-btn-salvar-canal">✦ Criar canal</button>
        </div>
      </form>
    </div>
  </dialog>"""


# Aplicado cedo (no <head>) para garantir 100% fidelidade ao dark mode nativo do protótipo.
THEME_BOOT_JS = (
    "try{var r=document.documentElement;"
    "r.style.colorScheme='dark';r.setAttribute('data-theme','dark');"
    "localStorage.setItem('studio-theme','dark');}catch(e){}"
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
      var campo = $('#dlg-canal-nome'); if (campo) campo.focus();
    });
    dlg.addEventListener('click', function (ev) {
      if (ev.target === dlg || (ev.target.closest && ev.target.closest('[data-fechar-dialogo]'))) dlg.close();
    });
    var form = $('#form-canal');
    var fb = $('#canal-feedback');
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var nome = $('#dlg-canal-nome').value.trim();
      if (!nome) return;
      var btn = $('#dlg-btn-salvar-canal');
      btn.disabled = true;
      btn.classList.add('carregando');
      window.StudioLoading.start();
      fb.removeAttribute('data-tipo'); fb.textContent = 'Cadastrando canal…';
      fetch('/studio/projects', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: nome, niche: $('#dlg-canal-nicho').value.trim(), language: $('#dlg-canal-idioma').value })
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
                    page_js: str = "", extra_css: str = "", video_channel: str = "") -> str:
    """Documento completo da tela V3. `body_html` é o conteúdo de `<div class="content">`.

    `video_channel` (W1.2/R6): nome do canal dono do vídeo, em leitura, para as páginas de vídeo.
    """
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{e(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;560;600;650;700;720;760;780;800&display=swap" rel="stylesheet">
  <style nonce="{nonce}">{V3_CSS}{PRODUCT_CSS}{extra_css}</style>
  <script nonce="{nonce}">{THEME_BOOT_JS}</script>
</head>
<body>
<div id="barra-progresso-topo" aria-hidden="true"></div>
<div id="indicador-carregando" class="indicador-carregando" aria-live="polite" aria-hidden="true"><span class="indicador-spinner"></span><span id="indicador-texto">Carregando…</span></div>
<a class="skip" href="#conteudo">Ir para o conteúdo</a>
<div class="app">
  {render_sidebar(active=active, cost_note=cost_note, project_id=project_id)}
  <main class="main">
    {render_topbar(crumb=crumb, projects=projects, project_id=project_id, video_channel=video_channel)}
    <div class="content" id="conteudo">
{propagate(body_html, project_id)}
    </div>
  </main>
</div>
{render_novo_canal_dialog()}
<script nonce="{nonce}">{SHELL_JS}</script>
{f'<script nonce="{nonce}">{page_js}</script>' if page_js else ''}
</body>
</html>"""
