"""Tela Tendências da UX V3 — pilares de conteúdo, filtros por região/pilar, diálogo e evidências.

Fonte da verdade visual: `docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html` (#pagina-tendencias e #dialog-pilares).
"""

from __future__ import annotations

import secrets
from html import escape as e
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..application.errors import ProjectNotFound
from ..application.panel import PanelView, TrendItemView
from ..domain.ids import check_id
from ..domain.trend_priority import SavedTrendSnapshot
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
                fbPilar.textContent = 'Erro ao salvar: ' + (window.StudioErro.texto(d, 'tente novamente.'));
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
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) {
          if (r.ok && data.stored) { location.reload(); return; }
          // Sem recarregar: a mensagem do motivo precisa ficar visível (sem termos, nada novo, cota, chave).
          btnRefresh.disabled = false;
          btnRefresh.textContent = '↻ Buscar agora';
          var st = $('#status-refresh');
          if (st) st.textContent = r.ok
            ? 'Nada novo: os termos foram buscados há menos de 6 horas. Isso poupa a cota diária da API.'
            : 'A busca não rodou: ' + window.StudioErro.texto(data, 'tente novamente.', r.status);
        });
      }).catch(function () {
          btnRefresh.disabled = false;
          btnRefresh.textContent = '↻ Buscar agora';
          var st = $('#status-refresh');
          if (st) st.textContent = 'A busca não rodou: falha de rede. Tente novamente.';
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

  // ---- Diálogo Como Calculamos ----
  var dlgComo = $('#dialog-como-calculamos');
  var btnComo = $('#btn-como-calculamos');
  if (btnComo && dlgComo) {
    btnComo.addEventListener('click', function () {
      if (typeof dlgComo.showModal === 'function') dlgComo.showModal(); else dlgComo.setAttribute('open', '');
    });
    dlgComo.addEventListener('click', function (ev) {
      if (ev.target === dlgComo || (ev.target.closest && ev.target.closest('[data-fechar-dialogo]'))) {
        dlgComo.close();
      }
    });
  }

  // ---- Botão Guardar / Desfavoritar Ideia ----
  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('.btn-guardar');
    if (!btn || !canalId) return;
    var videoId = btn.getAttribute('data-video-id');
    if (!videoId) return;

    var isSaved = btn.getAttribute('data-guardado') === 'true';
    var novoEstado = !isSaved;

    btn.disabled = true;
    btn.setAttribute('data-guardado', novoEstado ? 'true' : 'false');
    btn.textContent = novoEstado ? '★ Guardado' : '☆ Guardar';

    var art = btn.closest('.cartao-tendencia');
    if (art) art.setAttribute('data-guardado', novoEstado ? 'true' : 'false');

    var req;
    if (novoEstado) {
      var payload = {
        video_id: videoId,
        title: btn.getAttribute('data-title') || (art && art.querySelector('h3') ? art.querySelector('h3').textContent : ''),
        channel_title: btn.getAttribute('data-channel') || null,
        thumbnail_url: btn.getAttribute('data-thumbnail') || null,
        video_url: btn.getAttribute('data-video-url') || null,
        duration: btn.getAttribute('data-duration') || '',
        views: parseInt(btn.getAttribute('data-views') || '0', 10) || 0,
        category_name: btn.getAttribute('data-category') || null,
        score: parseInt(btn.getAttribute('data-score') || '0', 10) || 0
      };
      req = fetch('/studio/projects/' + encodeURIComponent(canalId) + '/saved-trends', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } else {
      req = fetch('/studio/projects/' + encodeURIComponent(canalId) + '/saved-trends/' + encodeURIComponent(videoId), {
        method: 'DELETE'
      });
    }

    req.then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      btn.disabled = false;
    }).catch(function () {
      btn.disabled = false;
      btn.setAttribute('data-guardado', isSaved ? 'true' : 'false');
      btn.textContent = isSaved ? '★ Guardado' : '☆ Guardar';
      if (art) art.setAttribute('data-guardado', isSaved ? 'true' : 'false');
    });
  });
})();
"""

TRENDS_CSS = """
.cardthumb {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 9px;
  overflow: hidden;
  background: var(--panel2);
}
.cardthumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.cardthumb .tag {
  position: absolute;
  top: 8px;
  left: 8px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.7);
  color: #fff;
}
.cardthumb .time {
  position: absolute;
  bottom: 8px;
  right: 8px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.8);
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.signals {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin: 10px 0;
  font-size: 12px;
  color: var(--muted);
}
.signals .sig {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.signals .sig b {
  color: var(--text);
}
.signals .sig b.up {
  color: var(--ok);
}
.src {
  font-size: 9.5px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 1px 5px;
  border-radius: 3px;
  letter-spacing: 0.3px;
}
.src.api {
  background: rgba(88, 166, 255, 0.15);
  color: #58a6ff;
}
.src.calc {
  background: rgba(188, 140, 255, 0.15);
  color: #bc8cff;
}
.src.own {
  background: rgba(126, 231, 135, 0.15);
  color: #7ee787;
}
.score {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0 8px;
  padding: 8px 12px;
  background: var(--panel2);
  border-radius: 8px;
  border: 1px solid var(--line);
}
.score .n {
  font-size: 20px;
  font-weight: 800;
  color: var(--text);
  min-width: 28px;
}
.score .t {
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.35;
}
.score .t b {
  color: var(--text);
}
details.more {
  font-size: 11.5px;
  color: var(--muted);
  margin-top: 4px;
}
details.more summary {
  cursor: pointer;
  color: var(--muted);
  font-size: 11.5px;
  user-select: none;
}
details.more summary:hover {
  color: var(--text);
}
details.more .bd {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 0;
}
details.more .r {
  display: grid;
  grid-template-columns: 140px 1fr 28px auto;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}
.meter {
  height: 6px;
  border-radius: 3px;
  background: var(--line2);
  overflow: hidden;
}
.meter b {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: var(--accent);
}
.meter.ok b {
  background: var(--ok);
}
.meter.warn b {
  background: var(--warn);
}
.meter.bad b {
  background: var(--bad);
}
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


def _control_url(view: PanelView, filtro: str | None = None, sort: str | None = None,
                 tipo: str | None = None) -> str:
    from urllib.parse import urlencode

    f_val = filtro if filtro is not None else _FILTRO_TODAS
    s_val = sort if sort is not None else getattr(view, "sort", "prioridade")
    t_val = tipo if tipo is not None else getattr(view, "tipo", "todos")

    params: dict[str, Any] = {"filtro": f_val}
    if s_val and s_val != "prioridade":
        params["sort"] = s_val
    elif sort == "prioridade" and getattr(view, "sort", "prioridade") != "prioridade":
        params["sort"] = "prioridade"
    if t_val and t_val != "todos":
        params["tipo"] = t_val
    elif tipo == "todos" and getattr(view, "tipo", "todos") != "todos":
        params["tipo"] = "todos"
    if view.project_id:
        params["project_id"] = view.project_id
    params["days"] = view.days
    return "/studio/panel/tendencias?" + urlencode(params)


def _trends_url(view: PanelView, filtro: str) -> str:
    """Link estável: preserva o canal e o período; só o filtro muda."""
    return _control_url(view, filtro=filtro)


def _trends_cards_url(view: PanelView, filtro: str, offset: int) -> str:
    """Próximo lote do scroll infinito: mesma lista filtrada, a partir de `offset`."""
    from urllib.parse import urlencode

    params: dict[str, Any] = {"filtro": filtro, "offset": offset, "limite": TRENDS_PAGE_SIZE}
    s_val = getattr(view, "sort", "prioridade")
    t_val = getattr(view, "tipo", "todos")
    if s_val and s_val != "prioridade":
        params["sort"] = s_val
    if t_val and t_val != "todos":
        params["tipo"] = t_val
    if view.project_id:
        params["project_id"] = view.project_id
    params["days"] = view.days
    return "/studio/panel/tendencias/cartoes?" + urlencode(params)


def _chip(href: str, valor: str, rotulo: str, ativo: bool) -> str:
    marca = ' aria-current="true"' if ativo else ""
    return (f'<a class="pill btnlike chip-filtro{" accent" if ativo else ""}" href="{e(href, quote=True)}" '
            f'data-filtro="{e(valor, quote=True)}"{marca}>{rotulo}</a>')


def _mais_html(view: PanelView, filtro: str, mostrados: int, total: int) -> str:
    """Scroll infinito com controle real: o botão é o caminho sem JS e o alvo do observer."""
    if mostrados >= total:
        return ""
    proximo = _trends_cards_url(view, filtro, mostrados)
    return (f'<div class="mais-tendencias" id="mais-tendencias" style="text-align:center;margin-top:16px"\n'
            f'             data-proximo="{e(proximo, quote=True)}">\n'
            f'          <button class="btn small" type="button" id="btn-carregar-mais">Carregar mais tendências</button>\n'
            f'          <p class="sr-only" role="status" id="status-carregar-mais">Mostrando {mostrados} de {total}.</p>\n'
            f'        </div>')


def _lote_html(view: PanelView, filtro: str, offset: int, limite: int, itens: list[TrendItemView],
               total: int) -> str:
    """Lote de cartões + o próximo offset: a resposta que o scroll consome."""
    fim = offset + len(itens)
    tem_mais = fim < total
    proximo = _trends_cards_url(view, filtro, fim) if tem_mais else ""
    project_id = view.project_id or (view.projects[0][0] if view.projects else "")
    cards = "".join(_trend_card(t, project_id) for t in itens)
    return (f'<div class="lote-tendencias" data-tem-mais="{str(tem_mais).lower()}"\n'
            f'     data-proximo="{e(proximo, quote=True)}" data-mostrados="{fim}"\n'
            f'     data-total="{total}">\n{cards}</div>')


def _create_video_url(project_id: str | None, topic: str, mode: str = "piloto") -> str:
    """Link de Criar vídeo que preserva o canal ativo (KEEP-01) e leva tema e modo.

    Criar a partir de uma tendência não pode trocar o canal em silêncio. A tela Criar vídeo lê
    `topic` e `modo` da URL e só preenche o formulário: nada é criado sem o clique do usuário.
    """
    from urllib.parse import urlencode

    params: dict[str, str] = {}
    if project_id:
        params["project_id"] = project_id
    params["topic"] = topic
    params["modo"] = mode
    return "/studio/panel/novo-video?" + urlencode(params)


def _trend_card(trend: TrendItemView, project_id: str | None = None) -> str:
    """Cartão de Tendência Variação A com miniatura, sinais, score e diagnóstico."""
    region = panel_home._REGIOES.get(trend.region or "", trend.region or "Região não informada")
    canal = trend.channel_title or "canal não informado"
    data_relativa = trend.published_text or "data não informada"

    link_referencia = ""
    if trend.video_url:
        link_referencia = (
            f'<a href="{e(trend.video_url, quote=True)}" target="_blank" rel="noopener noreferrer">'
            f'Assistir referência ↗<span class="sr-only"> (abre em nova aba)</span></a>'
        )

    partes = [e(canal), e(data_relativa)]
    if link_referencia:
        partes.append(link_referencia)
    sub_line = " · ".join(partes)

    pillar = e(trend.category_name) if trend.category_name else ""
    reg_val = trend.region or "UNKNOWN"
    cat_val = trend.category_id or ""
    piloto = _create_video_url(project_id, trend.topic, "piloto")
    diretor = _create_video_url(project_id, trend.topic, "diretor")

    # Origem e badge da miniatura
    if trend.region == "BR":
        origem_rotulo = "Brasil · Em alta"
    elif trend.region in ("US", "GLOBAL", "WORLD"):
        origem_rotulo = "Mundo · Em alta"
    elif trend.region:
        origem_rotulo = f"{region} · Em alta"
    elif trend.category_name:
        origem_rotulo = f"Pilar · {trend.category_name}"
    else:
        origem_rotulo = "Em alta"

    duracao = trend.duration_text or "--:--"

    # Sinais formatados
    views_fmt = trend.metric_text.replace(" visualizações", "") if trend.metric_text else "--"
    vel_fmt = trend.velocity_text or "--/h"
    ratio_fmt = trend.niche_ratio_text or "1,0×"

    # Score e diagnósticos
    score = trend.priority_score
    if ": " in trend.priority_summary:
        resumo_prioridade, _, motivo_prioridade = trend.priority_summary.partition(": ")
    else:
        resumo_prioridade = "Prioridade"
        motivo_prioridade = trend.priority_summary or "Diagnóstico calculado"

    if trend.risk_level == "danger":
        status_classe = "bad"
    elif trend.risk_level == "warn":
        status_classe = "warn"
    else:
        status_classe = "ok"
    status_texto = trend.risk_status or "Sem risco detectado"

    # Parcelas (details.more)
    bd = trend.priority_breakdown
    p_vel = bd.velocity_score if bd else score
    p_nicho = bd.niche_ratio_score if bd else score
    p_conc = bd.competition_score if bd else 50
    p_ad = bd.adherence_score if bd else 70
    p_var = bd.variety_score if bd else 100

    if p_conc == 50:
        rotulo_conc = "Geral (Ampla)"
    elif p_conc >= 70:
        rotulo_conc = "Baixa"
    else:
        rotulo_conc = "Alta"

    c_vel = " ok" if p_vel >= 70 else (" warn" if p_vel < 40 else "")
    c_nicho = " ok" if p_nicho >= 70 else (" warn" if p_nicho < 40 else "")
    c_conc = " ok" if p_conc >= 70 else (" warn" if p_conc < 40 else "")
    c_ad = " ok" if p_ad >= 70 else (" warn" if p_ad < 40 else "")
    c_var = " ok" if p_var >= 70 else (" warn" if p_var < 40 else "")

    btn_guardar_texto = "★ Guardado" if trend.is_saved else "☆ Guardar"

    views_raw = 0
    if trend.metric_text:
        try:
            views_raw = int("".join(c for c in trend.metric_text.split()[0] if c.isdigit()))
        except Exception:
            views_raw = 0

    return f"""<article class="card cartao-tendencia" data-prioridade="{score}" data-velocidade="{int(round(trend.views_per_hour))}" data-perene="{str(trend.is_evergreen).lower()}" data-guardado="{str(trend.is_saved).lower()}" data-regiao="{e(reg_val)}" data-pilar="{e(cat_val)}">
            <div class="cardthumb">
              <img src="{e(trend.thumbnail_url or '')}" alt="{e(trend.topic)}" loading="lazy">
              <span class="tag">{e(origem_rotulo)}</span>
              <span class="time">{e(duracao)}</span>
            </div>
            <div class="between" style="margin-top:12px">
              <span class="pill accent">{e(panel_home._origin(trend))}</span>
              <span class="sample">{pillar}</span>
            </div>
            <h3 style="margin:8px 0 2px">{e(trend.topic)}</h3>
            <p class="sub">{sub_line}</p>
            <div class="signals">
              <span class="sig"><b>{e(views_fmt)}</b> views <span class="src api">API</span></span>
              <span class="sig"><b class="up">{e(vel_fmt)}</b> velocidade <span class="src calc">Calc.</span></span>
              <span class="sig"><b class="up">{e(ratio_fmt)}</b> vs. nicho <span class="src calc">Calc.</span></span>
            </div>
            <div class="score">
              <div class="n">{score}</div>
              <div class="t"><b>{e(resumo_prioridade)}.</b> {e(motivo_prioridade)}</div>
              <span class="pill {status_classe}" style="margin-left:auto">{e(status_texto)}</span>
            </div>
            <details class="more">
              <summary>Por que esta nota</summary>
              <div class="bd">
                <div class="r"><span>Velocidade</span><div class="meter{c_vel}"><b style="width:{p_vel}%"></b></div><b>{p_vel}</b><span class="src calc">Calc.</span></div>
                <div class="r"><span>Acima do nicho</span><div class="meter{c_nicho}"><b style="width:{p_nicho}%"></b></div><b>{p_nicho}</b><span class="src calc">Calc.</span></div>
                <div class="r"><span>Concorrência ({e(rotulo_conc)})</span><div class="meter{c_conc}"><b style="width:{p_conc}%"></b></div><b>{p_conc}</b><span class="src calc">Calc.</span></div>
                <div class="r"><span>Aderência ao canal</span><div class="meter{c_ad}"><b style="width:{p_ad}%"></b></div><b>{p_ad}</b><span class="src own">Canal</span></div>
                <div class="r"><span>Variedade vs. últimos 5</span><div class="meter{c_var}"><b style="width:{p_var}%"></b></div><b>{p_var}</b><span class="src own">Canal</span></div>
              </div>
            </details>
            <div class="row" style="margin-top:12px">
              <a class="btn primary small" href="{e(piloto, quote=True)}" data-usar-tendencia="{e(trend.topic, quote=True)}">⚡ Criar com piloto</a>
              <a class="btn small" href="{e(diretor, quote=True)}">🎬 Modo Diretor</a>
              <button class="btn ghost small btn-guardar" type="button" data-video-id="{e(trend.video_id or '')}" data-guardado="{str(trend.is_saved).lower()}" data-title="{e(trend.topic)}" data-channel="{e(trend.channel_title or '')}" data-thumbnail="{e(trend.thumbnail_url or '')}" data-video-url="{e(trend.video_url or '')}" data-duration="{e(trend.duration_text or '')}" data-views="{views_raw}" data-category="{e(trend.category_name or '')}" data-score="{score}">{btn_guardar_texto}</button>
            </div>
          </article>"""


def _barra_controles(view: PanelView, filtro: str) -> str:
    sort_ativo = getattr(view, "sort", "prioridade") or "prioridade"
    tipo_ativo = getattr(view, "tipo", "todos") or "todos"

    def _sort_link(val: str, label: str) -> str:
        ativo = (sort_ativo == val)
        marca = ' aria-current="true"' if ativo else ""
        href = _control_url(view, filtro=filtro, sort=val, tipo=tipo_ativo)
        return (f'<a class="pill btnlike small{" accent" if ativo else ""}" '
                f'href="{e(href, quote=True)}"{marca}>{label}</a>')

    def _tipo_link(val: str, label: str) -> str:
        ativo = (tipo_ativo == val)
        marca = ' aria-current="true"' if ativo else ""
        href = _control_url(view, filtro=filtro, sort=sort_ativo, tipo=val)
        return (f'<a class="pill btnlike small{" accent" if ativo else ""}" '
                f'href="{e(href, quote=True)}"{marca}>{label}</a>')

    sort_links = "".join([
        _sort_link("prioridade", "Prioridade"),
        _sort_link("velocidade", "Velocidade"),
        _sort_link("recentes", "Mais recentes"),
    ])

    tipo_links = "".join([
        _tipo_link("todos", "Todos"),
        _tipo_link("perenes", "Perenes"),
        _tipo_link("sem_risco", "Sem risco"),
        _tipo_link("guardados", "Guardados"),
    ])

    return f"""        <div class="row between wrap" id="barra-controles-tendencias" style="margin:12px 0 16px;gap:12px">
          <div class="row" style="gap:16px;align-items:center;flex-wrap:wrap">
            <div class="row" style="gap:6px;align-items:center">
              <span class="sample" style="font-weight:600">Ordenar por</span>
              {sort_links}
            </div>
            <div class="row" style="gap:6px;align-items:center">
              <span class="sample" style="font-weight:600">Mostrar</span>
              {tipo_links}
            </div>
          </div>
          <div class="row" style="gap:8px">
            <button class="btn ghost small" type="button" id="btn-como-calculamos">ⓘ Como calculamos</button>
          </div>
        </div>"""


def _dialog_como_calculamos() -> str:
    return """<dialog id="dialog-como-calculamos" class="modal" aria-labelledby="titulo-como-calculamos" aria-describedby="desc-como-calculamos" style="max-width:760px">
    <div class="modal-header">
      <div>
        <h2 id="titulo-como-calculamos">Como calculamos</h2>
        <p class="sub" id="desc-como-calculamos" style="margin:4px 0 0">Transparência de métricas, proveniência dos dados e fórmula da pontuação de prioridade.</p>
      </div>
      <button class="modal-close" type="button" data-fechar-dialogo aria-label="Fechar">✕</button>
    </div>
    <div class="dialogo-corpo stack" style="gap:16px;max-height:70vh;overflow-y:auto;padding-right:4px">
      <div class="card flat" style="padding:14px">
        <h3 style="margin:0 0 6px;font-size:14px">Fórmula da Prioridade (0–100)</h3>
        <p class="sub" style="margin:0 0 8px">A nota final é uma média ponderada equilibrada de 5 parcelas (20% cada), com penalidade de 30 pontos para temas de risco de monetização:</p>
        <code style="display:block;padding:8px 12px;background:var(--panel2);border-radius:6px;font-size:12px;color:var(--accent2)">
          Prioridade = 20% Velocidade + 20% Acima do Nicho + 20% Concorrência + 20% Aderência + 20% Variedade (-30 se risco)
        </code>
      </div>
      <div>
        <h3 style="margin:0 0 8px;font-size:14px">Origem dos Sinais e Métricas</h3>
        <table class="tabela-lista" style="font-size:12px">
          <thead>
            <tr>
              <th>Métrica / Campo</th>
              <th>Origem</th>
              <th>Cálculo / Definição</th>
              <th>Cota</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><b>Views, Canal, Data, Duração</b></td>
              <td><span class="src api">API YOUTUBE</span></td>
              <td>Dados oficiais extraídos via <code>videos.list</code> (snippet, statistics, contentDetails).</td>
              <td>1 unidade / lote de 50</td>
            </tr>
            <tr>
              <td><b>Velocidade (views/h)</b></td>
              <td><span class="src calc">CALCULADO</span></td>
              <td><code>views / max(1, horas_desde_publicacao)</code>.</td>
              <td>0 unidades</td>
            </tr>
            <tr>
              <td><b>Tração vs. Nicho (▲ X.X×)</b></td>
              <td><span class="src calc">CALCULADO</span></td>
              <td>Razão entre as views do vídeo e a mediana de views da categoria/pilar.</td>
              <td>0 unidades</td>
            </tr>
            <tr>
              <td><b>Concorrência</b></td>
              <td><span class="src calc">CALCULADO</span></td>
              <td>80 para pilares com baixa concorrência; 50 (neutro) para Em Alta Geral.</td>
              <td>0 unidades</td>
            </tr>
            <tr>
              <td><b>Aderência ao Canal</b></td>
              <td><span class="src own">SEU CANAL</span></td>
              <td>95 se alinhado a um pilar cadastrado do canal; 70 se veio do Em Alta Geral.</td>
              <td>0 unidades</td>
            </tr>
            <tr>
              <td><b>Variedade Temática</b></td>
              <td><span class="src own">SEU CANAL</span></td>
              <td>Ineditismo comparado aos últimos 5 vídeos produzidos para evitar repetição.</td>
              <td>0 unidades</td>
            </tr>
            <tr>
              <td><b>Risco de Monetização</b></td>
              <td><span class="src calc">CALCULADO</span></td>
              <td>Lista determinística de temas sensíveis, desmonetização e violência.</td>
              <td>0 unidades</td>
            </tr>
            <tr>
              <td><b>Vídeos Perenes</b></td>
              <td><span class="src calc">CALCULADO</span></td>
              <td>Publicados há mais de 180 dias mantendo mais de 100.000 visualizações.</td>
              <td>0 unidades</td>
            </tr>
            <tr>
              <td><b>Ideias Guardadas</b></td>
              <td><span class="src own">SEU CANAL</span></td>
              <td>Snapshot permanente salvo no banco do estúdio para o canal ativo.</td>
              <td>0 unidades</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </dialog>"""


def _dialog_pilares(view: PanelView) -> str:
    if view.categories:
        items = "".join(
            f'<li class="card flat between" style="padding:10px 14px"><div><b>{e(c.name)}</b>'
            f'<p class="sample">{e(" · ".join(c.queries)) if c.queries else "sem termos — a busca usa o nicho do canal"}</p></div>'
            f'<button class="btn ghost small" type="button" data-excluir-pilar="{e(c.id)}" style="color:var(--bad)">Excluir</button></li>'
            for c in view.categories
        )
    else:
        items = ('<li class="card flat" style="padding:10px 14px"><b>Nenhum pilar cadastrado</b>'
                 '<p class="sample">Sem pilar, a busca usa o nicho do canal e o Em Alta só aparece quando o nicho casa com uma categoria do YouTube.</p></li>')

    return f"""<dialog id="dialog-pilares" class="modal" aria-labelledby="titulo-pilares" aria-describedby="desc-pilares">
    <div class="modal-header">
      <div>
        <h2 id="titulo-pilares">Pilares de conteúdo</h2>
        <p class="sub" id="desc-pilares" style="margin:4px 0 0">Um pilar reúne os termos de busca que alimentam a coleta de tendências do canal.</p>
      </div>
      <button class="modal-close" type="button" data-fechar-dialogo aria-label="Fechar">✕</button>
    </div>
    <div class="dialogo-corpo">
      <ul class="lista-pilares stack" id="lista-pilares" style="list-style:none;padding:0;margin:0 0 18px;gap:8px">
        {items}
      </ul>

      <form class="form-pilar" id="form-pilar" novalidate>
        <h3 id="titulo-form-pilar">Novo pilar</h3>
        <p class="sub" style="margin:2px 0 14px">O nome é o que aparece nos filtros; os termos vão para a coleta.</p>
        <div class="field">
          <label for="pilar-nome">Nome do pilar</label>
          <input type="text" id="pilar-nome" maxlength="100" required placeholder="Ex.: Games">
        </div>
        <div class="field">
          <label for="pilar-termos">Termos de busca</label>
          <input type="text" id="pilar-termos" placeholder="Ex.: GTA 6, GTA VI gameplay, lançamento GTA 6">
          <p class="sample">Separe por vírgula. Até 10 termos por pilar.</p>
        </div>
        <p class="feedback sample" id="feedback-pilar" role="status"></p>
        <div class="modal-footer">
          <button class="btn primary small" type="submit" id="btn-salvar-pilar">Salvar pilar</button>
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

    filtro = filtro if isinstance(filtro, str) and filtro else _FILTRO_TODAS
    selecionadas = [t for t in view.trends if _trend_matches(t, filtro)]
    limite = max(1, limite if isinstance(limite, int) else TRENDS_PAGE_SIZE)
    do_lote = selecionadas[:limite]

    # Chips do protótipo (`ideasPage`, `prototype/index.html:633`): "Todas" + os **pilares** do
    # canal, só com o nome — sem "Em Alta <região>" e sem contagem entre parênteses. A região
    # continua na evidência de cada cartão e o filtro por região segue válido na URL
    # (`?filtro=regiao:BR`), para links antigos não quebrarem.
    chips = [_chip(_trends_url(view, _FILTRO_TODAS), _FILTRO_TODAS, "Todos", filtro == _FILTRO_TODAS)]
    for c in view.categories:
        valor = f"pilar:{c.id}"
        chips.append(_chip(_trends_url(view, valor), valor, e(c.name), filtro == valor))
    chips_html = "".join(chips)

    if view.trends and not selecionadas:
        cards_html = ""
        vazio_msg = ('<div class="card" id="tendencias-vazio"><p class="sub">Nenhuma tendência encontrada para este filtro.</p></div>')
    elif view.trends:
        cards_html = "".join(_trend_card(t, project_id) for t in do_lote)
        vazio_msg = '<p class="vazio" id="tendencias-vazio" hidden style="display:none;"></p>'
    else:
        cards_html = ""
        vazio_msg = ('<div class="card" id="tendencias-vazio"><p class="sub">Ainda não há tendências coletadas para este período. '
                     'Clique em <strong>Buscar agora</strong> para atualizar.</p></div>')

    mais_html = _mais_html(view, filtro, len(do_lote), len(selecionadas))

    coleta_info = (
        f"Última coleta: {view.last_collected_at.strftime('%d/%m às %H:%M')}."
        if view.last_collected_at else "Nenhuma coleta realizada ainda."
    )

    body = f"""      <section class="pagina" id="pagina-tendencias" aria-labelledby="t-tendencias">
        <div class="head"><div><p class="eyebrow">Radar</p><h1 id="t-tendencias">Tendências e ideias</h1><p class="sub">Ideias para o nicho do canal. Escolha como produzir.</p></div>
          <div class="row" id="barra-tendencias">{chips_html}
            <button class="btn ghost small" type="button" id="btn-refresh-trends" title="{e(coleta_info)} Cada termo buscado custa 100 unidades da cota diária da API do YouTube (10.000 por dia, divididas com o upload de vídeos). Termos buscados há menos de 6 horas não são buscados de novo.">↻ Buscar agora</button>
            <span class="sample" id="status-refresh" role="status" aria-live="polite"></span>
            <button class="btn ghost small" type="button" id="btn-gerenciar-pilares">Gerenciar pilares ({len(view.categories)})</button>
          </div></div>
        {_barra_controles(view, filtro)}
        <div class="grid2" id="lista-tendencias">{cards_html}</div>
        {mais_html}
        {vazio_msg}
      </section>
      {_dialog_pilares(view)}
      {_dialog_como_calculamos()}"""

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
        extra_css=TRENDS_CSS,
    )
    return html, legacy._headers(nonce)


class SavedTrendIn(BaseModel):
    video_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    channel_title: str | None = Field(default=None, max_length=200)
    thumbnail_url: str | None = Field(default=None, max_length=2000)
    video_url: str | None = Field(default=None, max_length=2000)
    duration: str = Field(default="", max_length=32)
    views: int = Field(default=0, ge=0)
    category_name: str | None = Field(default=None, max_length=200)
    score: int = Field(default=0, ge=0, le=100)


def save_saved_trend(uc: Any, project_id: str, body: SavedTrendIn) -> dict[str, Any]:
    if uc.trends_repo is None:
        raise HTTPException(503, "trends services unavailable")
    p_id = check_id(project_id)
    if uc.create_project.repo.get_project(p_id) is None:
        raise ProjectNotFound(p_id)
    snapshot = SavedTrendSnapshot(
        project_id=p_id,
        video_id=body.video_id,
        title=body.title,
        channel_title=body.channel_title,
        thumbnail_url=body.thumbnail_url,
        video_url=body.video_url,
        duration=body.duration,
        views=body.views,
        category_name=body.category_name,
        score=body.score,
    )
    uc.trends_repo.save_trend_snapshot(p_id, snapshot)
    return {"ok": True, "video_id": body.video_id}


def delete_saved_trend(uc: Any, project_id: str, video_id: str) -> dict[str, Any]:
    if uc.trends_repo is None:
        raise HTTPException(503, "trends services unavailable")
    p_id = check_id(project_id)
    if uc.create_project.repo.get_project(p_id) is None:
        raise ProjectNotFound(p_id)
    uc.trends_repo.unsave_trend(p_id, video_id)
    return {"ok": True}

