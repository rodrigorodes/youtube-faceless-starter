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

  // ---- Filtro de chips ----
  var barra = $('#barra-tendencias');
  var lista = $('#lista-tendencias');
  var vazio = $('#tendencias-vazio');
  var cards = lista ? $$('.cartao-tendencia', lista) : [];

  function aplicarFiltro(filtro) {
    var visiveis = 0;
    cards.forEach(function (c) {
      var reg = c.getAttribute('data-regiao') || 'UNKNOWN';
      var pil = c.getAttribute('data-pilar') || '';
      var bate = false;
      if (filtro === 'todas') bate = true;
      else if (filtro.indexOf('regiao:') === 0) bate = reg === filtro.slice(7);
      else if (filtro.indexOf('pilar:') === 0) bate = pil === filtro.slice(6);
      if (bate) {
        c.hidden = false;
        c.style.display = '';
        visiveis++;
      } else {
        c.hidden = true;
        c.style.display = 'none';
      }
    });

    if (vazio) {
      if (visiveis === 0 && cards.length > 0) {
        vazio.hidden = false;
        vazio.style.display = '';
        vazio.textContent = 'Nenhuma tendência encontrada para este filtro.';
      } else if (cards.length > 0) {
        vazio.hidden = true;
        vazio.style.display = 'none';
      }
    }

    if (barra) {
      $$('.chip-filtro', barra).forEach(function (btn) {
        btn.setAttribute('aria-pressed', String(btn.getAttribute('data-filtro') === filtro));
      });
    }
  }

  if (barra) {
    barra.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-filtro]');
      if (btn) aplicarFiltro(btn.getAttribute('data-filtro') || 'todas');
    });
  }

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

  // ---- Criar vídeo deste tema ----
  document.addEventListener('click', function (ev) {
    var alvo = ev.target.closest ? ev.target.closest('[data-usar-tendencia]') : null;
    if (!alvo) return;
    var tema = alvo.getAttribute('data-usar-tendencia') || '';
    location.href = '/studio/panel?topic=' + encodeURIComponent(tema);
  });
})();
"""


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


def render_tendencias_v3(view: PanelView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    project_id = view.project_id or (view.projects[0][0] if view.projects else "")

    count_total = len(view.trends)
    count_br = sum(1 for t in view.trends if t.region == "BR")
    count_us = sum(1 for t in view.trends if t.region == "US")

    cat_chips = []
    for c in view.categories:
        c_count = sum(1 for t in view.trends if t.category_id == c.id)
        cat_chips.append(
            f'<button class="chip-filtro" type="button" data-filtro="pilar:{e(c.id)}" aria-pressed="false">'
            f'{e(c.name)} ({c_count})</button>'
        )

    chips_html = (
        f'<button class="chip-filtro" type="button" data-filtro="todas" aria-pressed="true">Todas ({count_total})</button>'
        f'<button class="chip-filtro" type="button" data-filtro="regiao:BR" aria-pressed="false">Em Alta Brasil ({count_br})</button>'
        f'<button class="chip-filtro" type="button" data-filtro="regiao:US" aria-pressed="false">Em Alta EUA ({count_us})</button>'
        + "".join(cat_chips)
        + '<button class="chip-filtro novo" type="button" id="btn-novo-pilar">+ Novo pilar</button>'
    )

    if view.trends:
        cards_html = "".join(_trend_card(t) for t in view.trends)
        vazio_msg = '<p class="vazio" id="tendencias-vazio" hidden style="display:none;"></p>'
    else:
        cards_html = ""
        vazio_msg = ('<p class="vazio" id="tendencias-vazio">Ainda não há tendências coletadas para este período. '
                     'Clique em <strong>Buscar agora</strong> para atualizar.</p>')

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
