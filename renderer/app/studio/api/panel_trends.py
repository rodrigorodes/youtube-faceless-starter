"""Tela Tendências da UX V3 — pilares de conteúdo, filtros por região/pilar, diálogo e evidências.

Fonte da verdade visual: `docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html` (#pagina-tendencias e #dialog-pilares).
"""

from __future__ import annotations

import secrets
from html import escape as e

from ..application.panel import PanelView, TrendItemView
from . import panel as legacy
from . import panel_home
from . import shell_v3

TRENDS_JS = """
(function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var canalSel = $('#canal-ativo');
  var canalId = canalSel ? canalSel.value : '';

  // ---- Diálogo de Pilares ----
  var dlg = $('#dialog-pilares');
  var btnGerenciar = $('#btn-gerenciar-pilares');
  var btnNovoPilar = $('#btn-novo-pilar');

  function abrirPilares() {
    if (dlg) {
      if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
      var campo = $('#pilar-nome'); if (campo) campo.focus();
    }
  }

  if (btnGerenciar) btnGerenciar.addEventListener('click', abrirPilares);
  if (btnNovoPilar) btnNovoPilar.addEventListener('click', abrirPilares);

  if (dlg) {
    dlg.addEventListener('click', function (ev) {
      if (ev.target === dlg || (ev.target.closest && ev.target.closest('[data-fechar-dialogo]'))) dlg.close();
    });

    // Excluir pilar
    dlg.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-excluir-pilar]');
      if (!btn || !canalId) return;
      var catId = btn.getAttribute('data-excluir-pilar');
      btn.disabled = true;
      fetch('/studio/projects/' + encodeURIComponent(canalId) + '/categories/' + encodeURIComponent(catId), {
        method: 'DELETE'
      }).then(function () { location.reload(); })
        .catch(function () { btn.disabled = false; });
    });

    // Salvar pilar
    var formPilar = $('#form-pilar');
    var fbPilar = $('#feedback-pilar');
    if (formPilar) {
      formPilar.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var nome = ($('#pilar-nome').value || '').trim();
        if (!nome || !canalId) return;
        var termosRaw = ($('#pilar-termos').value || '').trim();
        var queries = termosRaw ? termosRaw.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : [];
        var btnSalvar = $('#btn-salvar-pilar');
        btnSalvar.disabled = true;
        if (fbPilar) { fbPilar.removeAttribute('data-tipo'); fbPilar.textContent = 'Salvando pilar…'; }

        fetch('/studio/projects/' + encodeURIComponent(canalId) + '/categories', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: nome, queries: queries })
        }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return [r, d]; }); })
          .then(function (par) {
            var r = par[0], d = par[1];
            if (r.ok && d.id) {
              location.reload();
            } else {
              if (fbPilar) {
                fbPilar.setAttribute('data-tipo', 'erro');
                fbPilar.textContent = 'Erro ao salvar: ' + (typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail || d));
              }
              btnSalvar.disabled = false;
            }
          })
          .catch(function (err) {
            if (fbPilar) {
              fbPilar.setAttribute('data-tipo', 'erro');
              fbPilar.textContent = 'Falha de rede: ' + err.message;
            }
            btnSalvar.disabled = false;
          });
      });
    }
  }

  // ---- Atualizar tendências (Buscar agora) ----
  var btnRefresh = $('#btn-refresh-trends');
  if (btnRefresh && canalId) {
    btnRefresh.addEventListener('click', function () {
      btnRefresh.disabled = true;
      btnRefresh.textContent = '↻ Buscando…';
      fetch('/studio/projects/' + encodeURIComponent(canalId) + '/trends/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      }).then(function () { location.reload(); })
        .catch(function () {
          btnRefresh.disabled = false;
          btnRefresh.textContent = '↻ Buscar agora';
        });
    });
  }

  // ---- Scroll infinito (o botão é o caminho acessível; o observer só antecipa) ----
  var mais = $('#mais-tendencias');
  var listaCartoes = $('#lista-tendencias');

  function carregarMais() {
    if (!mais || mais.getAttribute('data-carregando') === '1') return;
    var url = mais.getAttribute('data-proximo');
    if (!url) return;
    var btn = $('#btn-carregar-mais');
    var st = $('#status-carregar-mais');
    mais.setAttribute('data-carregando', '1');
    if (btn) { btn.disabled = true; btn.textContent = 'Carregando…'; }
    fetch(url, { headers: { 'Accept': 'text/html' } })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var lote = doc.querySelector('.lote-tendencias');
        if (!lote || !listaCartoes) return;
        Array.prototype.slice.call(lote.querySelectorAll('.cartao-tendencia')).forEach(function (c) {
          listaCartoes.appendChild(c);
        });
        if (lote.getAttribute('data-tem-mais') === 'true') {
          mais.setAttribute('data-proximo', lote.getAttribute('data-proximo') || '');
          mais.removeAttribute('data-carregando');
          if (btn) { btn.disabled = false; btn.textContent = 'Carregar mais tendências'; }
          if (st) st.textContent = 'Mostrando ' + (lote.getAttribute('data-mostrados') || '') +
            ' de ' + (lote.getAttribute('data-total') || '') + '.';
        } else {
          mais.remove();
        }
      })
      .catch(function () {
        mais.removeAttribute('data-carregando');
        if (btn) { btn.disabled = false; btn.textContent = 'Tentar novamente'; }
        if (st) st.textContent = 'Não foi possível carregar mais tendências. Tente novamente.';
      });
  }

  if (mais) {
    var btnMais = $('#btn-carregar-mais');
    if (btnMais) btnMais.addEventListener('click', carregarMais);
    if (typeof IntersectionObserver === 'function') {
      new IntersectionObserver(function (entradas) {
        entradas.forEach(function (e) { if (e.isIntersecting) carregarMais(); });
      }, { rootMargin: '600px 0px' }).observe(mais);
    }
  }

  // ---- Criar vídeo deste tema ----
  document.addEventListener('click', function (ev) {
    var alvo = ev.target.closest ? ev.target.closest('[data-usar-tendencia]') : null;
    if (!alvo) return;
    var tema = alvo.getAttribute('data-usar-tendencia') || '';
    location.href = '/studio/panel?topic=' + encodeURIComponent(tema);
  });
})();
"""


TRENDS_PAGE_SIZE = 24
_FILTRO_TODAS = "todas"


def _trend_matches(trend: TrendItemView, filtro: str) -> bool:
    """O filtro é resolvido no servidor: mesma regra para a contagem e para a página."""
    if filtro == _FILTRO_TODAS:
        return True
    if filtro.startswith("regiao:"):
        return (trend.region or "UNKNOWN") == filtro.split(":", 1)[1]
    if filtro.startswith("pilar:"):
        return (trend.category_id or "") == filtro.split(":", 1)[1]
    return False


def _trends_url(view: PanelView, filtro: str) -> str:
    """Link estável: preserva o canal e o período; só o filtro muda."""
    from urllib.parse import urlencode

    params = {"filtro": filtro}
    if view.project_id:
        params["project_id"] = view.project_id
    params["days"] = view.days
    return "/studio/panel/tendencias?" + urlencode(params)


def _trends_cards_url(view: PanelView, filtro: str, offset: int) -> str:
    """Próximo lote do scroll infinito: mesma lista filtrada, a partir de `offset`."""
    from urllib.parse import urlencode

    params = {"filtro": filtro, "offset": offset, "limite": TRENDS_PAGE_SIZE}
    if view.project_id:
        params["project_id"] = view.project_id
    params["days"] = view.days
    return "/studio/panel/tendencias/cartoes?" + urlencode(params)


def _chip(href: str, valor: str, rotulo: str, ativo: bool) -> str:
    marca = ' aria-current="true"' if ativo else ""
    return (f'<a class="chip-filtro" href="{e(href, quote=True)}" data-filtro="{e(valor, quote=True)}"'
            f'{marca}>{rotulo}</a>')


def _mais_html(view: PanelView, filtro: str, mostrados: int, total: int) -> str:
    """Scroll infinito com controle real: o botão é o caminho sem JS e o alvo do observer."""
    if mostrados >= total:
        return ""
    proximo = _trends_cards_url(view, filtro, mostrados)
    return (f'<div class="mais-tendencias" id="mais-tendencias"\n'
            f'             data-proximo="{e(proximo, quote=True)}">\n'
            f'          <button class="btn" type="button" id="btn-carregar-mais">Carregar mais tendências</button>\n'
            f'          <p class="micro" role="status" id="status-carregar-mais">Mostrando {mostrados} de {total}.</p>\n'
            f'        </div>')


def _lote_html(view: PanelView, filtro: str, offset: int, limite: int, itens: list[TrendItemView],
               total: int) -> str:
    """Lote de cartões + o próximo offset: a resposta que o scroll consome."""
    fim = offset + len(itens)
    tem_mais = fim < total
    proximo = _trends_cards_url(view, filtro, fim) if tem_mais else ""
    cards = "".join(_trend_card(t) for t in itens)
    return (f'<div class="lote-tendencias" data-tem-mais="{str(tem_mais).lower()}"\n'
            f'     data-proximo="{e(proximo, quote=True)}" data-mostrados="{fim}"\n'
            f'     data-total="{total}">\n{cards}</div>')


def _trend_card(trend: TrendItemView) -> str:
    region = panel_home._REGIOES.get(trend.region or "", trend.region or "Não informada")
    pillar = f'<span class="chip-pilar">Pilar: {e(trend.category_name)}</span>' if trend.category_name else ""
    stale = '<span class="selo">Desatualizada</span>' if trend.stale else ""
    if trend.video_url:
        label = f"youtube.com/watch?v={trend.video_id}" if trend.video_id else trend.video_url
        base = (f'<a href="{e(trend.video_url, quote=True)}" target="_blank" rel="noopener noreferrer">{e(label)}'
                '<span class="sr-only"> (abre em nova aba)</span></a>')
    else:
        base = "Não informado"
    rows = (
        ("Região", e(region)),
        ("Canal do vídeo base", e(trend.channel_title or "Não informado")),
        ("Visualizações", e(trend.metric_text or "Não informado")),
        ("Publicado", e(trend.published_text or "Não informado")),
        ("Vídeo base", base),
    )
    items = "".join(f"<li><span>{k}</span><span>{v}</span></li>" for k, v in rows)
    reg_val = trend.region or "UNKNOWN"
    cat_val = trend.category_id or ""
    return f"""<article class="cartao-tendencia" data-regiao="{e(reg_val)}" data-pilar="{e(cat_val)}">
            <div class="pilha"><span class="origem">{e(panel_home._origin(trend))}</span>{pillar}{stale}</div>
            <h3>{e(trend.topic)}</h3>
            <ul class="evidencias">{items}</ul>
            <div class="pilha">
              <button class="btn btn-primario" type="button" data-usar-tendencia="{e(trend.topic, quote=True)}">Criar vídeo deste tema</button>
            </div>
          </article>"""


def _dialog_pilares(view: PanelView) -> str:
    if view.categories:
        items = "".join(
            f'<li><div><b>{e(c.name)}</b>'
            f'<small>{e(" · ".join(c.queries)) if c.queries else "sem termos — usa os termos padrão"}</small></div>'
            f'<button class="btn" type="button" data-excluir-pilar="{e(c.id)}">Excluir</button></li>'
            for c in view.categories
        )
    else:
        items = '<li><div><b>Nenhum pilar cadastrado</b><small>Sem pilar, a coleta usa os termos padrão do canal.</small></div></li>'

    return f"""<dialog id="dialog-pilares" aria-labelledby="titulo-pilares" aria-describedby="desc-pilares">
    <div class="dialogo-cab">
      <div>
        <h2 id="titulo-pilares">Pilares de conteúdo</h2>
        <p class="micro" id="desc-pilares" style="margin:4px 0 0">Um pilar reúne os termos de busca que alimentam a coleta de tendências do canal.</p>
      </div>
      <button class="icon-btn" type="button" data-fechar-dialogo aria-label="Fechar">✕</button>
    </div>
    <div class="dialogo-corpo">
      <ul class="lista-pilares" id="lista-pilares">
        {items}
      </ul>

      <form class="form-pilar" id="form-pilar" novalidate>
        <h3 id="titulo-form-pilar">Novo pilar</h3>
        <p class="micro" style="margin:0 0 14px">O nome é o que aparece nos filtros; os termos vão para a coleta.</p>
        <div class="campo">
          <label for="pilar-nome">Nome do pilar</label>
          <input type="text" id="pilar-nome" maxlength="100" required placeholder="Ex.: Games">
        </div>
        <div class="campo" style="margin-bottom:8px">
          <label for="pilar-termos">Termos de busca</label>
          <input type="text" id="pilar-termos" placeholder="Ex.: GTA 6, GTA VI gameplay, lançamento GTA 6">
          <p class="dica">Separe por vírgula. Até 10 termos por pilar.</p>
        </div>
        <p class="feedback" id="feedback-pilar" role="status"></p>
        <div class="acoes">
          <button class="btn btn-primario" type="submit" id="btn-salvar-pilar">Salvar pilar</button>
        </div>
      </form>
    </div>
  </dialog>"""


def render_tendencias_cartoes(view: PanelView, filtro: str = _FILTRO_TODAS, offset: int = 0,
                              limite: int = TRENDS_PAGE_SIZE) -> tuple[str, dict[str, str]]:
    """Fragmento HTML do próximo lote: mesma lista filtrada, sem casca e sem script.

    `offset` inválido (negativo ou além do fim) não inventa cartão: começa do início ou devolve
    lote vazio com `data-tem-mais="false"`.
    """
    filtro = filtro if isinstance(filtro, str) and filtro else _FILTRO_TODAS
    offset = max(0, offset if isinstance(offset, int) else 0)
    limite = max(1, min(limite if isinstance(limite, int) else TRENDS_PAGE_SIZE, 96))
    selecionadas = [t for t in view.trends if _trend_matches(t, filtro)]
    lote = selecionadas[offset:offset + limite]
    nonce = secrets.token_urlsafe(16)
    return _lote_html(view, filtro, offset, limite, lote, len(selecionadas)), legacy._headers(nonce)


def render_tendencias_v3(view: PanelView, filtro: str = _FILTRO_TODAS,
                         limite: int = TRENDS_PAGE_SIZE) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    project_id = view.project_id or (view.projects[0][0] if view.projects else "")

    count_total = len(view.trends)
    count_br = sum(1 for t in view.trends if t.region == "BR")
    count_us = sum(1 for t in view.trends if t.region == "US")

    filtro = filtro if isinstance(filtro, str) and filtro else _FILTRO_TODAS
    selecionadas = [t for t in view.trends if _trend_matches(t, filtro)]
    limite = max(1, limite if isinstance(limite, int) else TRENDS_PAGE_SIZE)
    do_lote = selecionadas[:limite]

    chips = [
        _chip(_trends_url(view, _FILTRO_TODAS), _FILTRO_TODAS, f"Todas ({count_total})",
              filtro == _FILTRO_TODAS),
        _chip(_trends_url(view, "regiao:BR"), "regiao:BR", f"Em Alta Brasil ({count_br})",
              filtro == "regiao:BR"),
        _chip(_trends_url(view, "regiao:US"), "regiao:US", f"Em Alta EUA ({count_us})",
              filtro == "regiao:US"),
    ]
    for c in view.categories:
        valor = f"pilar:{c.id}"
        c_count = sum(1 for t in view.trends if t.category_id == c.id)
        chips.append(_chip(_trends_url(view, valor), valor, f"{e(c.name)} ({c_count})", filtro == valor))
    chips_html = "".join(chips) + (
        '<button class="chip-filtro novo" type="button" id="btn-novo-pilar">+ Novo pilar</button>')

    if view.trends and not selecionadas:
        cards_html = ""
        vazio_msg = ('<p class="vazio" id="tendencias-vazio">Nenhuma tendência encontrada para este filtro.</p>')
    elif view.trends:
        cards_html = "".join(_trend_card(t) for t in do_lote)
        vazio_msg = '<p class="vazio" id="tendencias-vazio" hidden style="display:none;"></p>'
    else:
        cards_html = ""
        vazio_msg = ('<p class="vazio" id="tendencias-vazio">Ainda não há tendências coletadas para este período. '
                     'Clique em <strong>Buscar agora</strong> para atualizar.</p>')

    mais_html = _mais_html(view, filtro, len(do_lote), len(selecionadas))

    coleta_info = (
        f"Última coleta: {view.last_collected_at.strftime('%d/%m às %H:%M')}."
        if view.last_collected_at else "Nenhuma coleta realizada ainda."
    )

    body = f"""      <section class="pagina" id="pagina-tendencias" aria-labelledby="t-tendencias">
        <div class="secao-cab">
          <div>
            <p class="eyebrow">O QUE ESTÁ SUBINDO</p>
            <h1 class="h1" id="t-tendencias">Tendências</h1>
            <p class="lead">Cada tendência vem com a evidência: origem, região, números e o vídeo base.</p>
          </div>
          <div class="pilha">
            <button class="btn" type="button" id="btn-refresh-trends">↻ Buscar agora</button>
            <button class="btn" type="button" id="btn-gerenciar-pilares">Gerenciar pilares ({len(view.categories)})</button>
          </div>
        </div>
        <div class="aviso" style="margin-bottom:16px">
          <p class="micro" style="margin:0">A coleta usa os <b>termos de busca dos pilares</b> do canal.
          {e(coleta_info)} Sem coleta, a tela fica vazia de propósito — nada é estimado.</p>
        </div>

        <search class="barra-pilares" id="barra-tendencias" aria-label="Filtrar tendências">
          {chips_html}
        </search>

        <div class="grade-tendencias" id="lista-tendencias">
          {cards_html}
        </div>
        {mais_html}
        {vazio_msg}
      </section>
      {_dialog_pilares(view)}"""

    html = shell_v3.render_document(
        title="Faceless Studio — Tendências",
        active="tendencias",
        crumb="Tendências",
        body_html=body,
        nonce=nonce,
        projects=list(view.projects),
        project_id=project_id,
        cost_note=panel_home.cost_note(view),
        page_js=TRENDS_JS,
    )
    return html, legacy._headers(nonce)
