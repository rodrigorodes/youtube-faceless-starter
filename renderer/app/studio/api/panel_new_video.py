"""Tela Novo vídeo da UX V3 — criação direta em tela única e layout do protótipo.

Fonte da verdade visual: `prototype/index.html` (linha 611, `newVideo`).
O fluxo é direto: 1 formulário, 1 ação ('Criar e abrir vídeo →'), suporte a roteiro colado,
meta de duração, predefinição do canal e card educativo dos 4 passos da esteira.
A criação usa POST /studio/videos; fontes coladas usam POST /studio/videos/{id}/sources.
"""

from __future__ import annotations

import secrets
from html import escape as e

from . import panel as legacy
from . import shell_v3
from .panel_production import NewVideoView

NEW_VIDEO_JS = """
(function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };

  var form = $('#form-novo-video');
  var temaCampo = $('#tema-novo');
  var erroTema = $('#erro-tema');
  var btnCriar = $('#btn-criar-abrir') || $('#btn-criar');
  var fb = $('#feedback-criar');
  var useScript = $('#usar-roteiro');
  function linkHttp(texto) {
    try { var u = new URL(texto); return (u.protocol === 'http:' || u.protocol === 'https:') && !!u.hostname; } catch (e) { return false; }
  }
  function updateSummary() {
    var mode = $('input[name="modo-producao"]:checked');
    var format = $('input[name="formato-novo"]:checked');
    $('#resumo-modo').textContent = mode && mode.value === 'diretor' ? 'Modo Diretor' : 'Piloto automático';
    $('#resumo-formato').textContent = format && format.value === 'long' ? 'Vídeo 16:9' : 'Short 9:16';
    var diretor = mode && mode.value === 'diretor';
    var rotulo = $('#btn-criar-abrir');
    if (rotulo && !rotulo.classList.contains('carregando')) {
      rotulo.textContent = diretor ? '\\uD83C\\uDFAC Criar e abrir storyboard \\u2192' : '\\u26A1 Criar e abrir v\\u00eddeo \\u2192';
    }
    var dica = $('#resumo-dica');
    if (dica) {
      var comRoteiro = useScript.checked;
      dica.textContent = diretor
        ? (comRoteiro
          ? 'O roteiro colado vira as cenas e voc\\u00ea cai no storyboard para edit\\u00e1-las. M\\u00eddia e voz s\\u00f3 s\\u00e3o geradas quando voc\\u00ea pedir.'
          : 'Voc\\u00ea cai no storyboard. As cenas nascem das fontes: adicione uma fonte e gere o roteiro. M\\u00eddia e voz s\\u00f3 s\\u00e3o geradas quando voc\\u00ea pedir.')
        : (comRoteiro
          ? 'A produ\\u00e7\\u00e3o come\\u00e7a assim que o v\\u00eddeo \\u00e9 criado. Nada \\u00e9 publicado sem sua aprova\\u00e7\\u00e3o.'
          : 'O Studio pesquisa o tema na Wikip\\u00e9dia, escreve o roteiro s\\u00f3 com os fatos encontrados e produz at\\u00e9 a sua aprova\\u00e7\\u00e3o. Se n\\u00e3o achar fonte, avisa e voc\\u00ea adiciona uma. Nada \\u00e9 publicado sem sua aprova\\u00e7\\u00e3o.');
    }
    $('#campo-roteiro').hidden = !useScript.checked;
    $('#estrutura-roteiro').hidden = useScript.checked;
  }
  var duracao = $('#duracao-alvo');
  function fillDuration() {
    if (!duracao) return;
    var format = $('input[name="formato-novo"]:checked');
    var long = format && format.value === 'long';
    var options = long ? [['120', '2 min'], ['180', '3 min'], ['300', '5 min']] : [['30', '30 s'], ['45', '45 s'], ['60', '60 s']];
    var wanted = long ? '180' : '60';
    duracao.innerHTML = '';
    options.forEach(function (o) {
      var opt = document.createElement('option');
      opt.value = o[0]; opt.textContent = o[1]; opt.selected = o[0] === wanted;
      duracao.appendChild(opt);
    });
  }
  fillDuration();
  document.querySelectorAll('input[name="formato-novo"]').forEach(function (el) { el.addEventListener('change', fillDuration); });
  if (form) form.addEventListener('change', updateSummary);

  document.querySelectorAll('.modecard').forEach(function (mc) {
    mc.addEventListener('click', function () {
      document.querySelectorAll('.modecard').forEach(function (m) { m.setAttribute('aria-pressed', 'false'); });
      mc.setAttribute('aria-pressed', 'true');
      var r = mc.querySelector('input[type="radio"]');
      if (r) r.checked = true;
      updateSummary();
    });
  });
  try {
    var draft = JSON.parse(sessionStorage.getItem('studio-video-draft') || 'null');
    if (draft) {
      useScript.checked = draft.kind === 'script';
      temaCampo.value = useScript.checked ? 'Vídeo a partir do meu roteiro' : draft.text;
      $('#roteiro-pronto').value = useScript.checked ? draft.text : '';
      ['formato-novo', 'modo-producao'].forEach(function (name, index) {
        var value = index ? draft.mode : draft.format;
        var input = Array.from(document.getElementsByName(name)).find(function (el) { return el.value === value; });
        if (input) { input.checked = true; input.dispatchEvent(new Event('change', {bubbles:true})); }
      });
      document.querySelectorAll('.modecard').forEach(function (mc) {
        mc.setAttribute('aria-pressed', String(mc.querySelector('input').checked));
      });
      sessionStorage.removeItem('studio-video-draft');
    }
  } catch (e) {}
  // Vindo de Tendências: /novo-video?topic=...&modo=piloto|diretor só preenche o formulário.
  try {
    var qs = new URLSearchParams(location.search);
    var qTopic = (qs.get('topic') || '').trim();
    var qModo = qs.get('modo');
    if (qTopic && temaCampo && !temaCampo.value) temaCampo.value = qTopic.slice(0, 200);
    if (qModo === 'piloto' || qModo === 'diretor') {
      var qInput = Array.from(document.getElementsByName('modo-producao')).find(function (el) { return el.value === qModo; });
      if (qInput) {
        qInput.checked = true;
        document.querySelectorAll('.modecard').forEach(function (mc) {
          mc.setAttribute('aria-pressed', String(mc.querySelector('input').checked));
        });
      }
    }
  } catch (e) {}
  updateSummary();
  document.querySelectorAll('input[name="estilo-novo"]').forEach(function (r) {
    r.addEventListener('change', function () {
      document.querySelectorAll('[data-estilo-choice]').forEach(function (c) {
        c.setAttribute('aria-pressed', String(c.querySelector('input').checked));
      });
    });
  });

  if (form && temaCampo && btnCriar) {
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var tema = temaCampo.value.trim();
      if (!tema || tema.length < 3) {
        if (erroTema) erroTema.style.display = 'block';
        temaCampo.focus();
        return;
      }
      if (erroTema) erroTema.style.display = 'none';

      var canalSel = $('#canal-ativo');
      if (!canalSel || !canalSel.value) return;

      var fmt = $('input[name="formato-novo"]:checked');
      var est = $('input[name="estilo-novo"]:checked');
      var modo = $('input[name="modo-producao"]:checked');
      var scriptField = $('#roteiro-pronto');
      var scriptText = (useScript.checked && scriptField ? scriptField.value : '').trim();
      var urlCampo = $('#roteiro-url'), erroUrl = $('#erro-roteiro-url');
      var scriptUrl = urlCampo ? urlCampo.value.trim() : '';
      if (erroUrl) erroUrl.style.display = 'none';
      if (scriptText && !linkHttp(scriptUrl)) {
        // O backend só aceita texto colado com um link http(s) de referência (ele entra em "Fontes" na descrição).
        if (erroUrl) erroUrl.style.display = 'block';
        if (urlCampo) urlCampo.focus();
        return;
      }

      var payload = {
        project_id: canalSel.value,
        topic: tema,
        format: fmt ? fmt.value : 'short',
        production_mode: modo ? modo.value : 'piloto'
      };
      if (est && est.value) payload.style_id = est.value;

      btnCriar.disabled = true;
      btnCriar.classList.add('carregando');
      if (window.StudioLoading) window.StudioLoading.start('Criando rascunho do vídeo…');
      if (fb) { fb.removeAttribute('data-tipo'); fb.textContent = 'Criando rascunho…'; }

      fetch('/studio/videos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) { return [r, d]; });
      }).then(function (par) {
        var r = par[0], d = par[1];
        if (!(r.ok && d.id)) throw new Error(window.StudioErro.texto(d, 'tente novamente.', r.status));
        return d.id;
      }).then(function (videoId) {
        // O vídeo já existe: o que falha daqui em diante vira aviso na tela do vídeo, nunca silêncio.
        var base = '/studio/videos/' + encodeURIComponent(videoId);
        var flash = '';
        function post(path, body, headers) {
          return fetch(base + path, {
            method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, headers || {}),
            body: JSON.stringify(body || {})
          }).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, status: r.status, data: d }; });
          }).catch(function () { return { ok: false, status: 0, data: {} }; });
        }
        function falhou(prefixo, res) {
          flash = prefixo + ' ' + window.StudioErro.texto(res.data, 'tente novamente.', res.status);
        }
        // Piloto sem roteiro colado: a produção pesquisa o tema sozinha (1ª etapa); Diretor sem fonte para no storyboard.
        var etapa = Promise.resolve(!scriptText && payload.production_mode !== 'diretor');
        if (scriptText) {
          // O roteiro colado entra como fonte: é dele que o roteiro em cenas é escrito.
          if (fb) fb.textContent = 'Registrando o roteiro como fonte\u2026';
          etapa = post('/sources', { url: scriptUrl, text: scriptText }).then(function (res) {
            if (!res.ok) falhou('O roteiro colado n\u00e3o foi registrado como fonte:', res);
            return res.ok;
          });
        }
        return etapa.then(function (temFonte) {
          if (!temFonte) return null;
          if (payload.production_mode === 'diretor') {
            // Diretor: "cria o roteiro em cenas e para" — as cenas ficam prontas para editar.
            if (fb) fb.textContent = 'Escrevendo o roteiro em cenas\u2026';
            return post('/script', {}).then(function (res) { if (!res.ok) falhou('O roteiro n\u00e3o p\u00f4de ser gerado:', res); });
          }
          // Piloto: gera de ponta a ponta; a aprova\u00e7\u00e3o final continua sendo sua.
          if (fb) fb.textContent = 'Iniciando a produ\u00e7\u00e3o\u2026';
          var chave = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
          return post('/production-runs', {}, { 'Idempotency-Key': chave }).then(function (res) {
            if (!res.ok) falhou('A produ\u00e7\u00e3o n\u00e3o p\u00f4de iniciar:', res);
          });
        }).then(function () {
          if (flash) { try { sessionStorage.setItem('flash-' + videoId, flash); } catch (e) {} }
          if (fb) fb.textContent = 'V\u00eddeo criado. Abrindo\u2026';
          location.href = '/studio/panel/videos/' + encodeURIComponent(videoId) + '/cenas';
        });
      }).catch(function (err) {
        btnCriar.disabled = false;
        btnCriar.classList.remove('carregando');
        if (window.StudioLoading) window.StudioLoading.done();
        if (fb) {
          fb.setAttribute('data-tipo', 'erro');
          fb.textContent = 'Erro ao criar: ' + err.message;
        }
      });
    });
  }
})();
"""


_LANGUAGES = {"pt-BR": "Português (BR)", "en-US": "Inglês (EUA)", "es-ES": "Espanhol"}


def _language_label(code: str | None) -> str:
    """Rótulo legível do idioma do canal; código desconhecido aparece como veio (sem inventar)."""
    if not code:
        return "não definido"
    return _LANGUAGES.get(code, code)


_THUMB = "linear-gradient(135deg,#2b2540,#15171c)"


def _style_choice(value: str, name: str, checked: bool, disabled: str) -> str:
    """`.choice` do protótipo (`nstyle`): miniatura + nome; o rádio fica oculto e dirige o formulário."""
    return (f'<label class="choice" data-estilo-choice aria-pressed="{"true" if checked else "false"}">'
            f'<input type="radio" name="estilo-novo" value="{e(value, quote=True)}"{" checked" if checked else ""}{disabled} class="sr-only">'
            f'<div class="thumb" style="height:54px;background:{_THUMB};margin-bottom:8px"><span style="font-size:22px">🎨</span></div>'
            f'<b style="font-size:12.5px">{e(name)}</b></label>')


def _style_options(view: NewVideoView, disabled: str) -> str:
    """Estilos reais da biblioteca como grade de `.choice` (`grid3`).

    A primeira opção é a herança do canal (sem override, valor vazio) com o nome real que será
    herdado; sem estilo no canal, é o padrão do estúdio. Nenhum estilo fictício é criado.
    """
    inherit = view.inherited_style_name or "Padrão do estúdio (canal sem estilo)"
    cards = [_style_choice("", inherit, True, disabled)]
    cards.extend(_style_choice(style_id, name, False, disabled)
                 for style_id, name in view.styles if name != view.inherited_style_name)
    return f'<div class="grid3">{"".join(cards)}</div>'


def _cost_note(view: NewVideoView) -> str:
    if view.month.breakdown.calls > 0:
        return f"Custo do mês: {view.month.text}"
    return "Não disponível: nenhuma chamada registrada neste mês."


def render_new_video_v3(view: NewVideoView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    project_id = view.selected_project_id or (view.projects[0][0] if view.projects else "")
    current_channel_name = next((name for pid, name in view.projects if pid == project_id),
                                view.projects[0][1] if view.projects else "Nenhum canal cadastrado")

    if view.projects:
        gate = ""
        disabled = ""
    else:
        gate = '<p class="aviso" role="status">Cadastre um canal (botão «+ Novo canal», no topo) para criar vídeos.</p>'
        disabled = " disabled"

    style_options = _style_options(view, disabled)
    providers_rows = "".join(
        '<div class="between sub" style="padding:2px 0">'
        f'<span>{e(stage.label)}</span>'
        + ('<span style="color:var(--ok)">✓ Disponível</span>' if stage.available
           else f'<span style="color:var(--bad)">✕ {e(stage.reason or "Indisponível")}</span>')
        + "</div>"
        for stage in view.pipeline) or '<p class="sample">Disponibilidade não informada.</p>'
    missing = [stage for stage in view.pipeline if not stage.available]
    providers_note = (
        f'<div class="note" style="margin:8px 0">{e(missing[0].reason or missing[0].label + " indisponível")} '
        '<a class="btn small" href="/studio/panel/conexoes">Resolver em Configurações</a></div>'
        if missing else "")
    providers_summary = "✓ Pronto para produzir" if not missing else "Configuração precisa de atenção"
    nota_canal = ("O canal tem estilo e voz vinculados. Mudar aqui vale só para este vídeo; para mudar o padrão, use Biblioteca ou Configurações."
                  if view.has_profile else "Canal sem perfil: valem os padrões do estúdio para voz e estilo.")
    voz = e(view.channel_voice) if (view.has_profile and view.channel_voice) else "padrão do estúdio"
    estilo = e(view.inherited_style_name) if view.inherited_style_name else "padrão do estúdio"
    voz_vinculo = (' <span class="pill" style="margin-left:6px">padrão do canal</span>'
                   if (view.has_profile and view.channel_voice) else "")
    estilo_vinculo = (' <span class="pill" style="margin-left:6px">vinculado ao canal</span>'
                      if view.inherited_style_name else "")

    default_mode = "piloto"
    default_format = "short"
    if getattr(view, "channel_profile", None) is not None:
        prof = view.channel_profile
        if getattr(prof, "default_mode", None) is not None:
            default_mode = prof.default_mode.value if hasattr(prof.default_mode, "value") else str(prof.default_mode)
        if getattr(prof, "default_format", None) is not None:
            default_format = prof.default_format.value if hasattr(prof.default_format, "value") else str(prof.default_format)
    else:
        if getattr(view, "channel_default_mode", None) is not None:
            dm = view.channel_default_mode
            default_mode = dm.value if hasattr(dm, "value") else str(dm)
        if getattr(view, "channel_default_format", None) is not None:
            df = view.channel_default_format
            default_format = df.value if hasattr(df, "value") else str(df)

    format_long_checked = " checked" if default_format == "long" else ""
    format_short_checked = " checked" if default_format != "long" else ""

    mode_diretor_checked = " checked" if default_mode == "diretor" else ""
    mode_piloto_checked = " checked" if default_mode != "diretor" else ""

    body = f"""      <section class="pagina" id="pagina-novo-video" aria-labelledby="t-novo">
        <div class="head">
          <div>
            <p class="eyebrow">CRIAR / NOVO VÍDEO</p>
            <h1 id="t-novo">Novo vídeo do canal</h1>
            <p class="sub">Tudo em uma tela. Voz e estilo vêm do canal e você pode trocar só para este vídeo.</p>
          </div>
        </div>
        {gate}

        <form id="form-novo-video" novalidate>
          <div class="two">
            <div class="stack">
              <div class="card">
                <h3 style="margin-bottom:10px">1 · Como você quer produzir?</h3>
                <fieldset class="pills" style="border:0;padding:0;margin:0">
                  <legend class="sr-only">Modo de produção</legend>
                  <div class="grid2">
                    <label class="modecard" id="card-modo-piloto" style="cursor:pointer" aria-pressed="{'true' if default_mode != 'diretor' else 'false'}">
                      <input type="radio" name="modo-producao" value="piloto"{mode_piloto_checked}{disabled} class="sr-only">
                      <span class="pill ok">⚡ Rápido · 1 clique</span>
                      <h3>Piloto automático</h3>
                      <p class="sub">Gera roteiro, voz, imagens e composição de ponta a ponta com os padrões do canal. Você só aprova no final.</p>
                    </label>
                    <label class="modecard" id="card-modo-diretor" style="cursor:pointer" aria-pressed="{'true' if default_mode == 'diretor' else 'false'}">
                      <input type="radio" name="modo-producao" value="diretor"{mode_diretor_checked}{disabled} class="sr-only">
                      <span class="pill accent">🎬 Controle total</span>
                      <h3>Modo Diretor</h3>
                      <p class="sub">Cria o roteiro em cenas e para. Você edita texto, mídia, voz e legendas antes de renderizar.</p>
                    </label>
                  </div>
                </fieldset>
              </div>

              <div class="card">
                <h3 style="margin-bottom:10px">2 · Tema ou roteiro</h3>
                <div class="field">
                  <label for="tema-novo">Tema do vídeo</label>
                  <input type="text" id="tema-novo" name="topic" minlength="3" maxlength="300" required
                            placeholder="Ex.: A cidade subterrânea de Derinkuyu"{disabled}>
                  <p class="campo-erro" id="erro-tema" style="display:none;color:var(--bad)">Informe o tema do vídeo (mínimo de 3 caracteres).</p>
                </div>
                <div class="field"><label class="tog"><input type="checkbox" id="usar-roteiro"{disabled}><i></i><span>Já tenho um roteiro pronto para colar</span></label></div>
                <div id="campo-roteiro" hidden>
                <div class="field">
                  <label for="roteiro-pronto">Roteiro pronto (opcional)</label>
                  <textarea id="roteiro-pronto" name="script" rows="4" maxlength="50000"
                            placeholder="Cole seu roteiro ou escreva depois. Separe as cenas por uma linha em branco."{disabled}></textarea>
                  <p class="sub" style="font-size:11px;margin-top:4px">Seu texto será preservado nas fontes e usado na criação das cenas.</p>
                </div>
                <div class="field">
                  <label for="roteiro-url">Link de referência do texto <span aria-hidden="true">*</span></label>
                  <input type="url" id="roteiro-url" name="script-url" placeholder="https://..."{disabled}
                         aria-describedby="roteiro-url-regra">
                  <p class="sample" id="roteiro-url-regra">De onde vem o texto (artigo, vídeo, documento). O Studio exige um link http(s)
                    e ele aparece em «Fontes» na descrição do vídeo publicado.</p>
                  <p class="campo-erro" id="erro-roteiro-url" style="display:none;color:var(--bad)">Informe um link http(s) válido para o texto colado.</p>
                </div>
                </div>
                <div class="field" id="estrutura-roteiro">
                  <label for="estrutura">Estrutura do roteiro</label>
                  <select id="estrutura" disabled><option>Definida pelo perfil editorial do canal</option></select>
                </div>
              </div>

              <details class="diag" id="video-custom">
                <summary>Personalizar este vídeo · formato, voz e estilo</summary>
              <div class="card">
                <h3 style="margin-bottom:10px">3 · Formato, voz e estilo</h3>
                <div class="row" style="margin-bottom:14px">
                  <span class="lbl">Formato</span>
                  <fieldset class="pills seg" id="seg-formato-novo" style="margin:0;padding:2px;gap:0;flex-wrap:nowrap">
                    <legend class="sr-only">Formato</legend>
                    <label class="seg-btn"><input type="radio" name="formato-novo" value="short"{format_short_checked}{disabled} class="sr-only"><span>Short · 9:16</span></label>
                    <label class="seg-btn"><input type="radio" name="formato-novo" value="long"{format_long_checked}{disabled} class="sr-only"><span>Vídeo · 16:9</span></label>
                  </fieldset>
                  <label class="lbl" for="duracao-alvo" style="margin-left:10px">Duração alvo</label>
                  <select id="duracao-alvo" name="duration"{disabled} style="width:auto"></select>
                </div>
                <p class="lbl" style="margin-bottom:6px">Voz do narrador{voz_vinculo}</p>
                <div class="row" style="margin-bottom:14px">
                  <span class="pill accent">{voz}</span>
                  <span class="sample">A voz vem do canal; a troca por vídeo ainda não está disponível.</span>
                </div>
                <p class="lbl" style="margin-bottom:6px">Estilo visual{estilo_vinculo}</p>
                <div role="radiogroup" aria-label="Estilo visual">{style_options}</div>
              </div>
              </details>
            </div>

            <aside class="stack" style="position:sticky;top:80px">
              <div class="card" id="resumo-card" role="group" aria-labelledby="t-preset">
                <h3 id="t-preset">Resumo</h3>
                <p class="sub" style="margin:4px 0 12px">{e(current_channel_name)}</p>
                <div class="between sub"><span>Modo</span><b id="resumo-modo" style="color:var(--text)"></b></div>
                <div class="between sub"><span>Formato</span><b id="resumo-formato" style="color:var(--text)"></b></div>
                <div class="between sub"><span>Voz</span><b style="color:var(--text)">{voz}</b></div>
                <div class="between sub"><span>Estilo</span><b style="color:var(--text)">{estilo}</b></div>
                <div class="between sub"><span>Estimativa de custo</span><b style="color:var(--text)">Não disponível</b></div>
                <div class="hr"></div>
                <details class="diag" data-keep="providers-summary" id="providers-resumo">
                  <summary>{providers_summary}</summary>
                  <p class="lbl" style="margin-bottom:6px">Providers do canal</p>
                  {providers_rows}
                  {providers_note}
                  <div class="hr"></div>
                </details>
                <p class="sample" id="resumo-dica" style="margin-bottom:10px">Criar o rascunho prepara as cenas e fontes sem iniciar cobrança.</p>
                <button class="btn primary long" type="submit" id="btn-criar-abrir"{disabled}>Criar e abrir vídeo →</button>
                <p class="feedback" id="feedback-criar" role="status" style="margin-top:8px"></p>
              </div>

              <div class="note info">{nota_canal}</div>
            </aside>
          </div>
        </form>
      </section>"""

    html = shell_v3.render_document(
        title="Faceless Studio — Novo vídeo",
        active="novo-video",
        crumb="Novo vídeo",
        body_html=body,
        nonce=nonce,
        projects=list(view.projects),
        project_id=project_id,
        cost_note=_cost_note(view),
        page_js=NEW_VIDEO_JS,
    )
    return html, legacy._headers(nonce)
