"""Início da UX V3 — hero de criação, "Continuar de onde parou" e "Tendências do canal".

Só mostra o que existe: vídeos e tendências reais da `PanelView`; sem dado, estado vazio com texto.
O fluxo de criação é o mesmo do produto (POST /studio/videos → abre o vídeo para informar a fonte);
a produção NÃO começa aqui, porque sem fonte a primeira etapa falharia (SourceRefused).
"""

from __future__ import annotations

import secrets
from html import escape as e

from ..application.panel import PanelView, Stage, TrendItemView, VideoItem
from . import shell_v3

# Situação mostrada no cartão: (texto, classe do ponto, descrição da etapa). Sem estimativa de progresso.
_SITUACAO = {
    Stage.PENDING: ("Não iniciado", "parado", "Ainda sem produção. Abra o vídeo para informar a fonte."),
    Stage.IN_PRODUCTION: ("Em produção", "", "Produção em andamento."),
    Stage.AWAITING_APPROVAL: ("Esperando você", "espera", "Esperando sua aprovação."),
    Stage.APPROVED: ("Aprovado", "ok", "Aprovado e pronto para publicar."),
    Stage.COMPLETED: ("Concluído", "ok", "Produção concluída."),
    Stage.FAILED: ("Falhou", "espera", "A produção falhou. Abra o vídeo para ver o motivo."),
    Stage.REJECTED: ("Rejeitado", "parado", "Vídeo rejeitado."),
}
_NEEDS_YOU = {Stage.AWAITING_APPROVAL, Stage.FAILED}
_FORMATOS = {"short": "Short · 9:16", "long": "Vídeo · 16:9"}
_REGIOES = {"BR": "Brasil", "US": "Estados Unidos", "UNKNOWN": "Origem desconhecida"}
MAX_VIDEOS = 3
MAX_TRENDS = 2


def _format_label(video: VideoItem) -> str:
    value = getattr(video.format, "value", str(video.format))
    return _FORMATOS.get(value, str(value))


def pick_videos(view: PanelView, limit: int = MAX_VIDEOS) -> list[VideoItem]:
    """O que precisa de você vem primeiro; dentro de cada grupo, o mais recente antes."""
    videos = [v for topic in view.topics for v in topic.videos]
    videos.sort(key=lambda v: v.updated_at, reverse=True)
    videos.sort(key=lambda v: 0 if v.stage in _NEEDS_YOU else 1)
    return videos[:limit]


def video_card(video: VideoItem) -> str:
    label, css, step = _SITUACAO.get(video.stage, (video.stage.value, "parado", ""))
    title = video.title or video.topic
    dot = f"situacao {css}".strip()
    return f"""<article class="cartao-projeto">
            <a href="/studio/panel/videos/{e(video.id, quote=True)}" aria-label="Abrir o vídeo {e(title)}">
              <div class="miniatura"><b>{e(_format_label(video))}</b></div>
              <div class="cartao-corpo">
                <h3>{e(title)}</h3>
                <p class="linha-meta"><span class="{dot}"><i aria-hidden="true"></i>{e(label)}</span></p>
                <p class="etapa-atual">{e(step)}</p>
              </div>
            </a>
          </article>"""


def _origin(trend: TrendItemView) -> str:
    return "YouTube (origem desconhecida)" if trend.source_name == "YouTube Global (Em Alta)" else trend.source_name


def trend_card(trend: TrendItemView) -> str:
    region = _REGIOES.get(trend.region or "", trend.region or "Não informada")
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
    return f"""<article class="cartao-tendencia">
            <div class="pilha"><span class="origem">{e(_origin(trend))}</span>{pillar}{stale}</div>
            <h3>{e(trend.topic)}</h3>
            <ul class="evidencias">{items}</ul>
            <div class="pilha">
              <button class="btn btn-primario" type="button" data-usar-tendencia="{e(trend.topic, quote=True)}">Criar vídeo deste tema</button>
            </div>
          </article>"""


HOME_JS = """
(function () {
  var form = document.getElementById('create-video-form');
  var topic = document.getElementById('topic');
  var fb = document.getElementById('create-video-feedback');
  if (form) form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var tema = topic.value.trim();
    var canal = document.getElementById('canal-ativo');
    if (!tema || !canal) return;
    var formato = form.querySelector('input[name="format"]:checked');
    var btn = document.getElementById('btn-create-video');
    btn.disabled = true;
    btn.classList.add('carregando');
    if (window.StudioLoading) window.StudioLoading.start();
    fb.removeAttribute('data-tipo'); fb.textContent = 'Criando vídeo…';
    fetch('/studio/videos', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: canal.value, topic: tema, format: formato ? formato.value : 'short' })
    }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return [r, d]; }); })
      .then(function (par) {
        var r = par[0], d = par[1];
        if (!r.ok || !d.id) {
          fb.setAttribute('data-tipo', 'erro');
          fb.textContent = 'Erro ao criar: ' + (typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail || d));
          btn.disabled = false;
          btn.classList.remove('carregando');
          if (window.StudioLoading) window.StudioLoading.done();
          return;
        }
        // A produção não começa aqui: o vídeo abre para você informar a fonte.
        fb.textContent = 'Vídeo criado. Abrindo para você informar a fonte…';
        location.href = '/studio/panel/videos/' + encodeURIComponent(d.id);
      })
      .catch(function (err) {
        fb.setAttribute('data-tipo', 'erro'); fb.textContent = 'Falha de rede: ' + err.message;
        btn.disabled = false;
        btn.classList.remove('carregando');
        if (window.StudioLoading) window.StudioLoading.done();
      });
  });
  document.addEventListener('click', function (ev) {
    var alvo = ev.target.closest ? ev.target.closest('[data-usar-tendencia]') : null;
    if (!alvo || !topic) return;
    topic.value = alvo.getAttribute('data-usar-tendencia') || '';
    topic.scrollIntoView({ behavior: 'smooth', block: 'center' });
    topic.focus();
  });
})();
"""


def cost_note(view: PanelView) -> str:
    if view.month.breakdown.calls > 0:
        return f"Custo do mês: {view.month.text}"
    return "Não disponível: nenhuma chamada registrada neste mês."


def render_home(view: PanelView, *, topic: str = "") -> tuple[str, dict[str, str]]:
    from . import panel as legacy  # cabeçalhos CSP compartilhados; import tardio evita ciclo

    nonce = secrets.token_urlsafe(16)
    project_id = view.project_id or (view.projects[0][0] if view.projects else "")
    videos = pick_videos(view)
    trends = view.trends[:MAX_TRENDS]

    videos_html = (
        "".join(video_card(v) for v in videos)
        if videos
        else '<p class="vazio">Nenhum vídeo ainda. Descreva um tema acima para criar o primeiro.</p>'
    )
    trends_html = (
        "".join(trend_card(t) for t in trends)
        if trends
        else '<p class="vazio">Ainda não há tendências coletadas para este período. '
             'Abra Tendências para buscar agora.</p>'
    )
    warning = (
        '<p class="aviso">Exibindo os 500 vídeos mais recentes do período selecionado.</p>'
        if view.truncated else ""
    )
    if view.projects:
        gate = ""
        disabled = ""
    else:
        gate = '<p class="aviso" role="status">Cadastre um canal (botão «+ Novo canal», no topo) para criar vídeos.</p>'
        disabled = " disabled"

    body = f"""      <section class="pagina" id="pagina-inicio" aria-labelledby="t-inicio">
        <p class="eyebrow">SEU ESPAÇO DE CRIAÇÃO</p>
        <div class="hero">
          <h1 id="t-inicio">O que você vai criar hoje?</h1>
          <p>De uma ideia para um vídeo pronto — o canal já define estilo, voz e idioma.</p>
          {gate}
          <form id="create-video-form">
            <div class="hero-linha">
              <div class="campo-tema">
                <label for="topic">Tema do vídeo</label>
                <input type="text" id="topic" name="topic" minlength="3" maxlength="300" required{disabled}
                       placeholder="Ex.: por que os agentes de IA estão mudando o trabalho" value="{e(topic, quote=True)}">
              </div>
              <button class="btn btn-primario" type="submit" id="btn-create-video"{disabled}>Criar vídeo →</button>
            </div>
            <fieldset class="formatos">
              <legend>Formato</legend>
              <label class="formato"><input type="radio" name="format" value="long" checked> Vídeo (16:9)</label>
              <label class="formato"><input type="radio" name="format" value="short"> Short (9:16)</label>
            </fieldset>
            <p class="feedback" id="create-video-feedback" role="status"></p>
            <p class="micro">Ao criar, o vídeo abre para você informar a fonte; a produção só começa depois disso.</p>
          </form>
        </div>

        <div class="secao" id="videos">
          <div class="secao-cab">
            <h2>Continuar de onde parou</h2>
            <span><a class="link-btn" href="/studio/panel/producao">Acompanhar produção</a>
            <a class="link-btn" href="/studio/panel/videos">Ver todos os vídeos</a></span>
          </div>
          {warning}
          <div class="grade">{videos_html}</div>
        </div>

        <div class="secao">
          <div class="secao-cab">
            <h2>Tendências do canal</h2>
            <a class="link-btn" href="/studio/panel/tendencias">Ver todas as tendências</a>
          </div>
          <div class="grade-tendencias">{trends_html}</div>
        </div>
      </section>"""

    html = shell_v3.render_document(
        title="Faceless Studio — Início", active="inicio", crumb="Início", body_html=body, nonce=nonce,
        projects=list(view.projects), project_id=project_id, cost_note=cost_note(view), page_js=HOME_JS,
    )
    return html, legacy._headers(nonce)
