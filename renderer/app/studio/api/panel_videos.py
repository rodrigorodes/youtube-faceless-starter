"""Tela Vídeos da UX V3 — lista de todos os vídeos com busca e filtro por situação.

Fonte da verdade visual: `docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html` (#pagina-videos).
"""

from __future__ import annotations

import secrets
from html import escape as e

from ..application.panel import PanelView, Stage, VideoItem
from . import panel as legacy
from . import panel_home
from . import shell_v3

VIDEOS_JS = """
(function () {
  var busca = document.getElementById('busca-videos');
  var botoes = Array.prototype.slice.call(document.querySelectorAll('[data-filtro]'));
  var lista = document.getElementById('lista-videos');
  var vazio = document.getElementById('videos-vazio');
  var linhas = lista ? Array.prototype.slice.call(lista.querySelectorAll('[data-situacao]')) : [];
  var atual = 'todos';

  function filtrar() {
    var termo = (busca && busca.value ? busca.value : '').trim().toLowerCase();
    var visiveis = 0;
    linhas.forEach(function (c) {
      var tema = (c.getAttribute('data-tema') || '').toLowerCase();
      var sit = c.getAttribute('data-situacao') || '';
      var ok = (!termo || tema.indexOf(termo) !== -1) && (atual === 'todos' || sit === atual);
      c.hidden = !ok;
      c.style.display = ok ? '' : 'none';
      if (ok) visiveis++;
    });
    if (vazio) {
      vazio.hidden = !(visiveis === 0 && linhas.length > 0);
      vazio.style.display = vazio.hidden ? 'none' : '';
    }
  }

  function escolher(btn) {
    atual = btn.getAttribute('data-filtro');
    botoes.forEach(function (b) {
      var on = b === btn;
      b.classList.toggle('accent', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    filtrar();
  }

  if (busca) busca.addEventListener('input', filtrar);
  botoes.forEach(function (b) {
    b.addEventListener('click', function () { escolher(b); });
    b.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); escolher(b); }
    });
  });
  linhas.forEach(function (row) {
    row.addEventListener('click', function (ev) {
      if (!ev.target.closest('a')) row.querySelector('a').click();
    });
    row.addEventListener('keydown', function (ev) {
      if (ev.target === row && (ev.key === 'Enter' || ev.key === ' ')) {
        ev.preventDefault(); row.querySelector('a').click();
      }
    });
  });
})();
"""


# Filtros de `pgVideos`: (chave, rótulo). "Publicados" é só `Stage.COMPLETED` — o `classify` do domínio só
# o produz para PUBLISHED/UPLOADED; aprovar nunca é apresentado como publicar.
FILTROS = (("todos", "Todos"), ("aprovar", "Para aprovar"), ("rascunho", "Rascunhos"),
           ("falha", "Com falha"), ("publicados", "Publicados"))
_KEY = {Stage.AWAITING_APPROVAL: "aprovar", Stage.PENDING: "rascunho",
        Stage.FAILED: "falha", Stage.COMPLETED: "publicados"}
# (rótulo, classe do pill) por estágio — rótulos de `statePill` do protótipo.
_ESTADO = {
    Stage.PENDING: ("Rascunho", "accent"),
    Stage.IN_PRODUCTION: ("Em produção", "accent"),
    Stage.AWAITING_APPROVAL: ("Aguardando aprovação", "warn"),
    Stage.APPROVED: ("Aprovado", "ok"),
    Stage.COMPLETED: ("Publicado", "ok"),
    Stage.FAILED: ("Falhou na produção", "bad"),
    Stage.REJECTED: ("Rejeitado", "bad"),
}


def _situacao_key(stage: Stage) -> str:
    """Chave do filtro; o que não tem filtro próprio (produção, aprovado, rejeitado) só aparece em "Todos"."""
    return _KEY.get(stage, "outros")


def _formato(video: VideoItem) -> str:
    value = getattr(video.format, "value", str(video.format))
    return {"short": "9:16", "long": "16:9"}.get(value, str(value))


def video_row(video: VideoItem) -> str:
    title = video.title or video.topic
    label, tone = _ESTADO.get(video.stage, (video.stage.value, ""))
    return (f'<tr class="click" tabindex="0" data-tema="{e(title.lower(), quote=True)}" data-situacao="{_situacao_key(video.stage)}">'
            f'<td><a href="/studio/panel/videos/{e(video.id, quote=True)}" style="text-decoration:none;color:inherit">'
            f'<b>{e(title)}</b></a></td>'
            f'<td>{e(_formato(video))}</td><td><span class="pill {tone}">{e(label)}</span></td>'
            f'<td class="sample">{e(video.cost_text)}</td><td class="sample">{video.updated_at:%d/%m/%Y}</td></tr>')


def render_videos(view: PanelView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    project_id = view.project_id or (view.projects[0][0] if view.projects else "")
    all_videos = [v for topic in view.topics for v in topic.videos]
    all_videos.sort(key=lambda v: v.updated_at, reverse=True)

    if all_videos:
        cards_html = ('<div class="card" style="padding:0;overflow:auto"><table class="vtable">'
                      '<thead><tr><th>Vídeo</th><th>Formato</th><th>Estado</th><th>Custo</th><th>Atualizado</th></tr></thead><tbody>'
                      + "".join(video_row(v) for v in all_videos) + '</tbody></table></div>')
        vazio_msg = '<p class="vazio card" id="videos-vazio" hidden style="display:none;grid-column:1/-1"></p>'
    else:
        cards_html = '<p class="vazio card" style="grid-column:1/-1">Nenhum vídeo ainda. Descreva um tema ou clique em «✦ Criar vídeo» para criar o primeiro.</p>'
        vazio_msg = ""

    pills = "".join(
        f'<span class="pill btnlike{" accent" if k == "todos" else ""}" role="button" tabindex="0" '
        f'aria-pressed="{"true" if k == "todos" else "false"}" data-filtro="{k}">{label} · '
        f'{len(all_videos) if k == "todos" else sum(1 for v in all_videos if _situacao_key(v.stage) == k)}</span>'
        for k, label in FILTROS)
    channel_name = next((n for pid, n in view.projects if pid == project_id), "") or "Todos os vídeos do canal"
    warning = (
        '<p class="aviso" style="margin-bottom:14px">Exibindo os 500 vídeos mais recentes do período selecionado.</p>'
        if view.truncated else ""
    )

    body = f"""      <section class="pagina" id="pagina-videos" aria-labelledby="t-videos">
        <div class="head">
          <div>
            <p class="eyebrow">Biblioteca de vídeos</p>
            <h1 id="t-videos">Vídeos</h1>
            <p class="sub">{e(channel_name)}</p>
          </div>
          <a class="btn primary" href="/studio/panel/novo-video">✦ Criar vídeo</a>
        </div>
        {warning}
        <div class="row" style="margin-bottom:16px" id="filtro-situacao">
          {pills}
          <div style="flex:1;min-width:220px;max-width:340px;margin-left:auto">
            <label class="sr" for="busca-videos">Buscar por tema</label>
            <input type="text" id="busca-videos" placeholder="Buscar por tema…">
          </div>
        </div>
        <div id="lista-videos" style="min-width:0">
          {cards_html}
        </div>
        {vazio_msg}
      </section>"""

    html = shell_v3.render_document(
        title="Faceless Studio — Vídeos",
        active="videos",
        crumb="Vídeos",
        body_html=body,
        nonce=nonce,
        projects=list(view.projects),
        project_id=project_id,
        cost_note=panel_home.cost_note(view),
        page_js=VIDEOS_JS,
    )
    return html, legacy._headers(nonce)
