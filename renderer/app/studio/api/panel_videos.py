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
  var filtros = document.querySelectorAll('input[name="filtro"]');
  var lista = document.getElementById('lista-videos');
  var vazio = document.getElementById('videos-vazio');
  var cards = lista ? Array.prototype.slice.call(lista.querySelectorAll('.cartao-projeto')) : [];

  function filtrar() {
    var termo = (busca && busca.value ? busca.value : '').trim().toLowerCase();
    var checked = document.querySelector('input[name="filtro"]:checked');
    var filtro = checked ? checked.value : 'todos';
    var visiveis = 0;

    cards.forEach(function (c) {
      var tema = (c.getAttribute('data-tema') || '').toLowerCase();
      var sit = c.getAttribute('data-situacao') || '';
      var bateTexto = !termo || tema.indexOf(termo) !== -1;
      var bateFiltro = filtro === 'todos' || sit === filtro;
      if (bateTexto && bateFiltro) {
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
        vazio.textContent = 'Nenhum vídeo encontrado com esse filtro.';
      } else {
        vazio.hidden = true;
        vazio.style.display = 'none';
      }
    }
  }

  if (busca) busca.addEventListener('input', filtrar);
  filtros.forEach(function (r) { r.addEventListener('change', filtrar); });
})();
"""


def _situacao_key(stage: Stage) -> str:
    """Bucket do filtro de situação. "Publicados" é só o vídeo efetivamente publicado.

    Só `Stage.COMPLETED` entra em "publicados": esse estágio só é produzido pelo `classify` do
    domínio quando o status é `PUBLISHED` ou a publicação é `UPLOADED`. Um vídeo apenas aprovado
    (`Stage.APPROVED`) continua em "Em criação" — aprovar nunca é apresentado como publicar.
    """
    if stage in (Stage.AWAITING_APPROVAL, Stage.FAILED):
        return "aprovar"
    if stage is Stage.COMPLETED:
        return "publicados"
    return "producao"


def video_card(video: VideoItem) -> str:
    label, css, step = panel_home._SITUACAO.get(video.stage, (video.stage.value, "parado", ""))
    title = video.title or video.topic
    dot = f"situacao {css}".strip()
    sit_key = _situacao_key(video.stage)
    return f"""<article class="cartao-projeto" data-tema="{e(title.lower(), quote=True)}" data-situacao="{e(sit_key)}">
            <a href="/studio/panel/videos/{e(video.id, quote=True)}" aria-label="Abrir o vídeo {e(title)}">
              <div class="miniatura"><b>{e(panel_home._format_label(video))}</b></div>
              <div class="cartao-corpo">
                <h3>{e(title)}</h3>
                <p class="linha-meta"><span class="{dot}"><i aria-hidden="true"></i>{e(label)}</span></p>
                <p class="etapa-atual">{e(step)}</p>
              </div>
            </a>
          </article>"""


def render_videos(view: PanelView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    project_id = view.project_id or (view.projects[0][0] if view.projects else "")
    all_videos = [v for topic in view.topics for v in topic.videos]
    all_videos.sort(key=lambda v: v.updated_at, reverse=True)

    if all_videos:
        cards_html = "".join(video_card(v) for v in all_videos)
        vazio_msg = '<p class="vazio" id="videos-vazio" hidden style="display:none;"></p>'
    else:
        cards_html = '<p class="vazio">Nenhum vídeo ainda. Descreva um tema ou clique em «+ Novo vídeo» para criar o primeiro.</p>'
        vazio_msg = ""

    warning = (
        '<p class="aviso">Exibindo os 500 vídeos mais recentes do período selecionado.</p>'
        if view.truncated else ""
    )

    body = f"""      <section class="pagina" id="pagina-videos" aria-labelledby="t-videos">
        <div class="secao-cab">
          <div>
            <p class="eyebrow">SEU CONTEÚDO</p>
            <h1 class="h1" id="t-videos">Vídeos</h1>
            <p class="lead">Todos os vídeos do canal, em um só lugar.</p>
          </div>
          <a class="btn btn-primario" href="/studio/panel/novo-video">＋ Novo vídeo</a>
        </div>
        {warning}
        <div class="linha-busca">
          <div class="campo">
            <label for="busca-videos">Buscar por tema</label>
            <input type="text" id="busca-videos" placeholder="Ex.: cidades do futuro">
          </div>
          <fieldset class="filtros">
            <legend>Situação</legend>
            <div class="pills" id="filtro-situacao">
              <label class="pill"><input type="radio" name="filtro" value="todos" checked> Todos</label>
              <label class="pill"><input type="radio" name="filtro" value="producao"> Em criação</label>
              <label class="pill"><input type="radio" name="filtro" value="aprovar"> Esperando você</label>
              <label class="pill"><input type="radio" name="filtro" value="publicados"> Publicados</label>
            </div>
          </fieldset>
        </div>
        <div class="grade" id="lista-videos">
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
