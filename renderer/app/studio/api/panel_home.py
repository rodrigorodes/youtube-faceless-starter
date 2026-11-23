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
_NEEDS_YOU = {Stage.AWAITING_APPROVAL, Stage.FAILED, Stage.PENDING}
_NEEDS_ORDER = {Stage.AWAITING_APPROVAL: 0, Stage.PENDING: 1, Stage.FAILED: 2}
# (classe do pill, rótulo, linha de apoio, ação, ação primária?) — rótulos de `pgHome`; apoio fala só do que o produto sabe.
_NEEDS_CARD = {
    Stage.AWAITING_APPROVAL: ("warn", "Aguardando aprovação", "Esperando sua aprovação.", "Revisar e aprovar", True),
    Stage.PENDING: ("accent", "Rascunho", "Ainda sem produção. Abra o vídeo para informar a fonte.", "Continuar editando", False),
    Stage.FAILED: ("bad", "Falhou na produção", "A produção falhou. Abra o vídeo para ver o motivo.", "Ver e retomar", False),
}
_FORMATOS = {"short": "Short · 9:16", "long": "Vídeo · 16:9"}
_REGIOES = {"BR": "Brasil", "US": "Estados Unidos", "UNKNOWN": "Origem desconhecida"}
MAX_TRENDS = 3
MAX_NEEDS = 3


def _format_label(video: VideoItem) -> str:
    value = getattr(video.format, "value", str(video.format))
    return _FORMATOS.get(value, str(value))


def pick_videos(view: PanelView, limit: int | None = None) -> list[VideoItem]:
    """Só o que depende do usuário (`pgHome` → "Precisa de você"): aprovar, retomar falha, continuar rascunho.

    Dentro do grupo, o mais recente antes. Vídeo em produção, aprovado ou concluído não pede ação aqui.
    """
    videos = [v for topic in view.topics for v in topic.videos if v.stage in _NEEDS_YOU]
    videos.sort(key=lambda v: v.updated_at, reverse=True)
    videos.sort(key=lambda v: _NEEDS_ORDER[v.stage])
    return videos if limit is None else videos[:limit]


def video_card(video: VideoItem) -> str:
    """Cartão `.card` do protótipo: pill de estado, título, uma linha, uma ação."""
    pill, label, step, action, primary = _NEEDS_CARD[video.stage]
    title = video.title or video.topic
    href = f"/studio/panel/videos/{e(video.id, quote=True)}"
    return (f'<div class="card cartao-projeto"><div><span class="pill {pill}">{e(label)}</span></div>'
            f'<h3 style="margin:8px 0 2px">{e(title)}</h3><p class="sub">{e(step)}</p>'
            f'<div style="margin-top:12px"><a class="btn {"primary " if primary else ""}small" href="{href}" '
            f'aria-label="{e(action)}: {e(title)}">{e(action)}</a></div></div>')


def first_steps(channel_name: str) -> str:
    """"Primeiros passos do canal" do protótipo — só aparece quando o canal ainda não tem vídeo.

    Não afirma o estado dos providers nem do YouTube (a Início não os consulta): leva às telas que mostram.
    """
    return f"""<div class="card" style="margin-bottom:26px;border-color:var(--line2)" id="primeiros-passos">
          <h2>Primeiros passos do canal {e(channel_name)}</h2>
          <p class="sub" style="margin-bottom:12px">Canal criado. Falta pouco para o primeiro vídeo.</p>
          <div class="stack" style="gap:8px">
            <div class="gate"><span>Canal criado e configurado</span><span class="pill ok">✓ Feito</span></div>
            <div class="gate"><span>Providers para produzir<small>Confira roteiro, voz, imagem e montagem.</small></span><a class="btn small" href="/studio/panel/conexoes">Verificar</a></div>
            <div class="gate"><span>Conectar o YouTube<small>Opcional agora; necessário só para publicar.</small></span><a class="btn small" href="/studio/panel/conexoes">Conectar</a></div>
            <div class="gate"><span>Criar o primeiro vídeo</span><a class="btn primary small" href="/studio/panel/novo-video">✦ Criar vídeo</a></div>
          </div>
        </div>"""


def _origin(trend: TrendItemView) -> str:
    return "YouTube (origem desconhecida)" if trend.source_name == "YouTube Global (Em Alta)" else trend.source_name


def trend_card(trend: TrendItemView) -> str:
    """Cartão do protótipo (pill + título + uma linha + ação). A evidência real cabe na linha de apoio."""
    region = _REGIOES.get(trend.region or "", trend.region or "Região não informada")
    evidence = " · ".join((
        region,
        trend.channel_title or "canal não informado",
        trend.metric_text or "visualizações não informadas",
        trend.published_text or "data não informada",
    ))
    pillar = f'<span class="pill" style="margin-left:6px">{e(trend.category_name)}</span>' if trend.category_name else ""
    stale = '<span class="pill bad" style="margin-left:6px">Desatualizada</span>' if trend.stale else ""
    if trend.video_url:
        label = f"youtube.com/watch?v={trend.video_id}" if trend.video_id else trend.video_url
        base = (f'<p class="sample" style="margin-top:4px">Vídeo base: <a href="{e(trend.video_url, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer">{e(label)}<span class="sr-only"> (abre em nova aba)</span></a></p>')
    else:
        base = '<p class="sample" style="margin-top:4px">Vídeo base: não informado</p>'
    return f"""<article class="card cartao-tendencia">
            <div><span class="pill accent">{e(_origin(trend))}</span>{pillar}{stale}</div>
            <h3 style="margin:8px 0 2px">{e(trend.topic)}</h3>
            <p class="sub">{e(evidence)}</p>{base}
            <div style="margin-top:12px">
              <button class="btn small" type="button" data-usar-tendencia="{e(trend.topic, quote=True)}">Criar com esta ideia</button>
            </div>
          </article>"""


HOME_JS = """
(function () {
  var form = document.getElementById('create-video-form');
  var topic = document.getElementById('homeTopic') || document.getElementById('topic');
  var fb = document.getElementById('create-video-feedback');
  var notice = document.getElementById('script-notice');
  var customize = document.getElementById('btn-customize-video');
  if (customize) customize.addEventListener('click', function (ev) {
    ev.preventDefault();
    var input = form.querySelector('input[name="tipo-entrada"]:checked');
    var format = form.querySelector('input[name="format"]:checked');
    sessionStorage.setItem('studio-video-draft', JSON.stringify({
      text: topic.value, kind: input ? input.value : 'idea',
      format: format ? format.value : 'short',
      mode: document.getElementById('production-mode').value
    }));
    location.href = customize.href;
  });

  function updateInputMode(mode) {
    if (!topic) return;
    if (mode === 'script') {
      topic.placeholder = 'Cole seu roteiro. Cada parágrafo será preservado como uma cena.';
      if (notice) notice.style.display = 'none';
    } else {
      topic.placeholder = 'Qual história você quer contar?';
      if (notice) notice.style.display = 'none';
    }
  }

  document.querySelectorAll('input[name="tipo-entrada"]').forEach(function (r) {
    r.addEventListener('change', function () {
      document.querySelectorAll('.seletor-entrada .chip').forEach(function (c) { c.classList.remove('on'); });
      var label = r.closest('.chip');
      if (label) label.classList.add('on');
      updateInputMode(r.value);
    });
  });

  document.querySelectorAll('.seletor-entrada .chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var r = chip.querySelector('input[type="radio"]');
      if (r && !r.checked) {
        r.checked = true;
        r.dispatchEvent(new Event('change'));
      }
    });
  });

  if (form) form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var rawText = topic ? topic.value.trim() : '';
    var canal = document.getElementById('canal-ativo');
    if (!rawText || !canal) return;

    var modoEntrada = form.querySelector('input[name="tipo-entrada"]:checked');
    var isScript = modoEntrada && modoEntrada.value === 'script';

    var tema = rawText;
    if (isScript) {
      var lines = rawText.split(/[\\r\\n]+/);
      var firstLine = (lines[0] || '').trim();
      tema = firstLine.length >= 3 ? firstLine.slice(0, 200) : rawText.slice(0, 200);
      if (tema.length < 3) tema = 'Roteiro: ' + tema;
      if (tema.length > 300) tema = tema.slice(0, 300);
    } else {
      if (tema.length > 300) tema = tema.slice(0, 300);
    }

    var formato = form.querySelector('input[name="format"]:checked');
    var prodModeInput = document.getElementById('production-mode');
    var prodMode = prodModeInput ? prodModeInput.value : 'piloto';

    var btn = document.getElementById('btn-create-video');
    if (btn) {
      btn.disabled = true;
      btn.classList.add('carregando');
    }
    if (window.StudioLoading) window.StudioLoading.start();
    if (fb) {
      fb.removeAttribute('data-tipo');
      fb.textContent = 'Criando vídeo…';
    }

    fetch('/studio/videos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: canal.value,
        topic: tema,
        format: formato ? formato.value : 'long',
        production_mode: prodMode
      })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return [r, d]; });
    }).then(function (par) {
      var r = par[0], d = par[1];
      if (!r.ok || !d.id) {
        if (fb) {
          fb.setAttribute('data-tipo', 'erro');
          fb.textContent = 'Erro ao criar: ' + (typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail || d));
        }
        if (btn) {
          btn.disabled = false;
          btn.classList.remove('carregando');
        }
        if (window.StudioLoading) window.StudioLoading.done();
        return;
      }

      if (isScript) {
        if (fb) fb.textContent = 'Gravando roteiro inicial nas fontes…';
        return fetch('/studio/videos/' + encodeURIComponent(d.id) + '/sources', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url: 'local://roteiro-inicial',
            text: rawText
          })
        }).then(function () {
          return d;
        }).catch(function () {
          return d;
        });
      }
      return d;
    }).then(function (d) {
      if (!d || !d.id) return;
      if (fb) fb.textContent = 'Vídeo criado. Redirecionando…';
      location.href = '/studio/panel/videos/' + encodeURIComponent(d.id);
    }).catch(function (err) {
      if (fb) {
        fb.setAttribute('data-tipo', 'erro');
        fb.textContent = 'Falha de rede: ' + err.message;
      }
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('carregando');
      }
      if (window.StudioLoading) window.StudioLoading.done();
    });
  });

  var modePiloto = document.getElementById('btn-mode-piloto');
  var modeDiretor = document.getElementById('btn-mode-diretor');
  var prodModeInput = document.getElementById('production-mode');
  if (modePiloto && modeDiretor && prodModeInput) {
    modePiloto.addEventListener('click', function () {
      modePiloto.classList.add('on');
      modePiloto.setAttribute('aria-pressed', 'true');
      modeDiretor.classList.remove('on');
      modeDiretor.setAttribute('aria-pressed', 'false');
      prodModeInput.value = 'piloto';
    });
    modeDiretor.addEventListener('click', function () {
      modeDiretor.classList.add('on');
      modeDiretor.setAttribute('aria-pressed', 'true');
      modePiloto.classList.remove('on');
      modePiloto.setAttribute('aria-pressed', 'false');
      prodModeInput.value = 'diretor';
    });
  }

  document.querySelectorAll('#seg-format .seg-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('#seg-format .seg-btn').forEach(function (b) { b.classList.remove('on'); });
      btn.classList.add('on');
      var r = btn.querySelector('input[type="radio"]');
      if (r) r.checked = true;
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

PANEL_JS = HOME_JS


def cost_note(view: PanelView) -> str:
    if view.month.breakdown.calls > 0:
        return f"Custo do mês: {view.month.text}"
    return "Não disponível: nenhuma chamada registrada neste mês."


def _hero(view: PanelView, topic: str = "", disabled: str = "", gate: str = "") -> str:
    project_id = view.project_id or (view.projects[0][0] if view.projects else "")
    channel_name = next((name for pid, name in view.projects if pid == project_id), "")
    if not channel_name and view.projects:
        channel_name = view.projects[0][1]
    if not channel_name:
        channel_name = "Canal Principal"

    channels = getattr(view, "channels", None) or []
    active_channel = None
    if isinstance(channels, dict):
        active_channel = channels.get(project_id)
    elif isinstance(channels, (list, tuple)):
        for ch in channels:
            if getattr(ch, "project_id", getattr(ch, "id", None)) == project_id:
                active_channel = ch
                break
            elif isinstance(ch, dict) and (ch.get("project_id") == project_id or ch.get("id") == project_id):
                active_channel = ch
                break
        if not active_channel and channels:
            active_channel = channels[0]

    duration = 60
    style_name = "Padrão"
    mode = "piloto"

    if active_channel:
        if isinstance(active_channel, dict):
            channel_name = active_channel.get("name", channel_name)
            duration = active_channel.get("target_duration_s", 60)
            style_name = (
                active_channel.get("visual_identity")
                or active_channel.get("style_name")
                or active_channel.get("style_id")
                or "Padrão"
            )
            mode = active_channel.get("default_mode", "piloto")
        else:
            channel_name = getattr(active_channel, "name", channel_name)
            duration = getattr(active_channel, "target_duration_s", 60)
            style_name = (
                getattr(active_channel, "visual_identity", "")
                or getattr(active_channel, "style_id", "")
                or "Padrão"
            )
            default_mode = getattr(active_channel, "default_mode", "piloto")
            mode = getattr(default_mode, "value", str(default_mode))

    if not style_name or style_name == "None":
        style_name = "Padrão"

    action_btn_text = "🎬 Abrir storyboard" if mode == "diretor" else "⚡ Gerar vídeo completo"

    return f"""        <div class="hero">
          <div class="between" style="align-items:flex-start">
            <div>
               <p class="eyebrow">ESTÚDIO DO CANAL · {e(channel_name)}</p>
              <h1 id="t-inicio">O que você vai criar hoje?</h1>
               <p class="sub" style="margin-top:4px">Digite um tema ou cole seu roteiro. Voz e estilo do canal já vêm prontos.</p>
            </div>
            <span class="pill accent">🎨 {e(style_name)}</span>
          </div>
          {gate}
          <form id="create-video-form">
            <div class="card flat" style="margin-top:18px;border-color:#4a435e">
            <fieldset class="seletor-entrada" data-kind="input-toggle" style="border:0;padding:0;margin:0 0 12px">
              <legend class="sr-only">Tipo de entrada</legend>
               <div class="seg">
                 <label class="chip seg-btn" id="toggle-idea">
                  <input type="radio" name="tipo-entrada" value="idea" checked class="sr-only">
                   Tenho uma ideia
                </label>
                 <label class="chip seg-btn" id="toggle-script">
                  <input type="radio" name="tipo-entrada" value="script" class="sr-only">
                   Já tenho roteiro
                </label>
              </div>
            </fieldset>
              <div>
                <label class="sr-only" for="homeTopic" id="label-topic">Tema ou roteiro do vídeo</label>
                <textarea class="prompt" id="homeTopic" name="topic" rows="3" minlength="3" maxlength="20000" required{disabled}
                          placeholder="Qual história você quer contar?"
                          value="{e(topic, quote=True)}"
                          style="background:transparent;border:0;padding:0;font-size:15px">{e(topic)}</textarea>
                <p class="micro dica-roteiro" id="script-notice" style="display:none;margin-top:6px;color:var(--muted)">Cada parágrafo será preservado como uma cena.</p>
              </div>
              <div style="margin-top:8px"><a class="btn ghost small" href="/studio/panel/novo-video" id="btn-customize-video">Personalizar este vídeo</a></div>
              <div class="hr"></div>
              <div class="between">
                <div class="row">
                  <div class="seg" id="seg-format">
                    <label class="chip formato seg-btn" id="homeShort" style="cursor:pointer;margin:0">
                      <input type="radio" name="format" value="short" checked class="sr-only">
                      <span>Short · 9:16</span>
                    </label>
                    <label class="chip formato seg-btn" id="homeLong" style="cursor:pointer;margin:0">
                      <input type="radio" name="format" value="long" class="sr-only">
                      <span>Vídeo · 16:9</span>
                    </label>
                  </div>
                  <span class="pill">🎙 Voz vinculada</span>
                  <span class="pill">🎨 {e(style_name)}</span>
                </div>
                <div class="row">
                  <input type="hidden" name="production_mode" id="production-mode" value="{e(mode, quote=True)}">
                  <div class="seg" id="seg-mode">
                    <button type="button" class="seg-btn" id="btn-mode-piloto" data-val="piloto" aria-pressed="{'true' if mode != 'diretor' else 'false'}">⚡ Piloto automático</button>
                    <button type="button" class="seg-btn" id="btn-mode-diretor" data-val="diretor" aria-pressed="{'true' if mode == 'diretor' else 'false'}">🎬 Modo Diretor</button>
                  </div>
                  <span class="sample padroes-canal" id="padroes-canal">Padrões de {e(channel_name)} · {duration}s · {e(style_name)}</span>
                  <button class="btn primary" type="submit" id="btn-create-video"{disabled}>{action_btn_text}</button>
                </div>
              </div>
            </div>
            <p class="feedback" id="create-video-feedback" role="status" style="margin-top:10px"></p>
          </form>
        </div>"""


def render_home(view: PanelView, *, topic: str = "") -> tuple[str, dict[str, str]]:
    from . import panel as legacy  # cabeçalhos CSP compartilhados; import tardio evita ciclo

    nonce = secrets.token_urlsafe(16)
    project_id = view.project_id or (view.projects[0][0] if view.projects else "")
    needs_all = pick_videos(view)
    videos = needs_all[:MAX_NEEDS]
    trends = view.trends[:MAX_TRENDS]
    has_any_video = any(topic.videos for topic in view.topics)
    channel_name = next((n for pid, n in view.projects if pid == project_id), "") or (
        view.projects[0][1] if view.projects else "Canal Principal")

    needs_html = (
        '<h2 style="margin-bottom:12px">Precisa de você</h2>'
        + ('<p class="aviso" style="margin-bottom:14px">Exibindo os 500 vídeos mais recentes do período selecionado.</p>'
           if view.truncated else "")
        + f'<div class="grade" style="margin-bottom:14px">{"".join(video_card(v) for v in videos)}</div>'
        + (f'<p class="sample" style="margin-bottom:26px"><a href="/studio/panel/videos">Ver os outros '
           f'{len(needs_all) - len(videos)} em Vídeos</a></p>' if len(needs_all) > len(videos)
           else '<div style="margin-bottom:12px"></div>')
    ) if videos else ""
    first_html = first_steps(channel_name) if (view.projects and not has_any_video) else ""
    trends_html = (
        "".join(trend_card(t) for t in trends)
        if trends
        else '<p class="vazio card" style="grid-column:1/-1">Ainda não há tendências coletadas para este período. '
             'Abra Tendências para buscar agora.</p>'
    )
    if view.projects:
        gate = ""
        disabled = ""
    else:
        gate = '<p class="aviso" role="status" style="margin-top:12px">Cadastre um canal (botão «＋ Novo canal», no topo) para criar vídeos.</p>'
        disabled = " disabled"

    body = f"""      <section class="pagina" id="pagina-inicio" aria-labelledby="t-inicio">
{_hero(view, topic=topic, disabled=disabled, gate=gate)}
        <div class="secao" id="videos">
          {needs_html}
          {first_html}
        </div>

        <div class="secao" id="tendencias">
          <h2 style="margin-bottom:12px">Comece por uma tendência no seu nicho</h2>
          <div class="grade-tendencias">{trends_html}</div>
          <p class="sample" style="margin-top:8px"><a href="/studio/panel/tendencias">Ver todas as tendências</a></p>
        </div>
      </section>"""

    html = shell_v3.render_document(
        title="Faceless Studio — Início", active="inicio", crumb="Início", body_html=body, nonce=nonce,
        projects=list(view.projects), project_id=project_id, cost_note=cost_note(view), page_js=HOME_JS,
    )
    return html, legacy._headers(nonce)
