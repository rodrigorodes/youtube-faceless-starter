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

  document.querySelectorAll('.modecard').forEach(function (mc) {
    mc.addEventListener('click', function () {
      document.querySelectorAll('.modecard').forEach(function (m) { m.setAttribute('aria-pressed', 'false'); });
      mc.setAttribute('aria-pressed', 'true');
      var r = mc.querySelector('input[type="radio"]');
      if (r) r.checked = true;
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
      var scriptText = (scriptField ? scriptField.value : '').trim();

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
        if (r.ok && d.id) {
          if (scriptText) {
            return fetch('/studio/videos/' + encodeURIComponent(d.id) + '/sources', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ url: 'local://roteiro-inicial', text: scriptText })
            }).catch(function () {}).then(function () { return d.id; });
          }
          return d.id;
        } else {
          throw new Error(typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail || d));
        }
      }).then(function (videoId) {
        if (fb) fb.textContent = 'Vídeo criado. Abrindo…';
        location.href = '/studio/panel/videos/' + encodeURIComponent(videoId);
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


def _style_options(view: NewVideoView, disabled: str) -> str:
    """Opções reais de estilo (F02.T02/G15).

    "Herdar do canal" é a escolha de não criar override — e mostra o nome real que será herdado.
    Sem nenhum estilo na biblioteca, não há opção fictícia: só a herança (que é o padrão real do
    estúdio) e o link para a biblioteca.
    """
    if view.inherited_style_name:
        inherit = f"Herdar do canal — {e(view.inherited_style_name)}"
        inherit_sample = "HERDAR DO CANAL"
    else:
        inherit = "Padrão do estúdio (canal sem estilo)"
        inherit_sample = "PADRÃO DO ESTÚDIO"
    if not view.styles:
        return (f'<label class="pill"><input type="radio" name="estilo-novo" value="" checked{disabled}>'
                f' {inherit}</label>')
    cards = [
        f'<label class="cartao-estilo"><span class="amostra" aria-hidden="true">{inherit_sample}</span>'
        f'<span class="cartao-rodape"><input type="radio" name="estilo-novo" value="" checked{disabled}>'
        f' {inherit}</span></label>'
    ]
    cards.extend(
        f'<label class="cartao-estilo"><span class="amostra" aria-hidden="true">{e(name.upper())}</span>'
        f'<span class="cartao-rodape"><input type="radio" name="estilo-novo" '
        f'value="{e(style_id, quote=True)}"{disabled}> {e(name)}</span></label>'
        for style_id, name in view.styles
    )
    return f'<div class="galeria" style="width:100%">{"".join(cards)}</div>'


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
    idioma = e(_language_label(view.channel_language)) if view.has_profile else "nenhum idioma definido (canal sem perfil)"
    voz = e(view.channel_voice) if (view.has_profile and view.channel_voice) else "padrão do estúdio"
    estilo = e(view.inherited_style_name) if view.inherited_style_name else "padrão do estúdio"

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
          <a class="btn ghost small" href="/studio/panel">← Voltar ao Início</a>
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
                  <label for="tema-novo">Sobre o que é o vídeo?</label>
                  <textarea id="tema-novo" name="topic" rows="3" maxlength="300" required aria-describedby="dica-tema"
                            placeholder="Descreva a história que você quer contar. Ex.: por que as cidades surgiram?"{disabled}></textarea>
                  <p class="sub" id="dica-tema" style="font-size:11px;margin-top:4px">De 3 a 300 caracteres.</p>
                  <p class="campo-erro" id="erro-tema" style="display:none;color:var(--bad)">Informe o tema do vídeo (mínimo de 3 caracteres).</p>
                </div>
                <div class="field" style="margin-top:10px">
                  <label for="roteiro-pronto">Roteiro pronto (opcional)</label>
                  <textarea id="roteiro-pronto" name="script" rows="4" maxlength="50000"
                            placeholder="Cole seu roteiro ou escreva depois. Separe as cenas por uma linha em branco."{disabled}></textarea>
                  <p class="sub" style="font-size:11px;margin-top:4px">Seu texto será preservado nas fontes e usado na criação das cenas.</p>
                </div>
                <div class="field" style="margin-top:10px">
                  <label class="check" for="revisar-roteiro" style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer">
                    <input id="revisar-roteiro" type="checkbox" checked{disabled}>
                    Revisar roteiro antes de gerar voz e imagens
                  </label>
                </div>
              </div>

              <div class="card">
                <h3 style="margin-bottom:10px">3 · Formato, duração e estilo</h3>
                <div class="row" style="margin-bottom:14px">
                  <span class="lbl">Formato</span>
                  <fieldset class="pills" style="margin:0;border:0;padding:0">
                    <legend class="sr-only">Formato</legend>
                    <label class="pill pill-formato"><input type="radio" name="formato-novo" value="long"{format_long_checked}{disabled}>
                      <svg class="icone-formato" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" aria-hidden="true" focusable="false">
                        <rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 9h20M2 15h20"/></svg>
                      Vídeo · 16:9</label>
                    <label class="pill pill-formato"><input type="radio" name="formato-novo" value="short"{format_short_checked}{disabled}>
                      <svg class="icone-formato" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" aria-hidden="true" focusable="false">
                        <rect x="7" y="2" width="10" height="20" rx="2"/><path d="M7 6h10M7 18h10"/></svg>
                      Short · 9:16</label>
                  </fieldset>
                  <span class="lbl" style="margin-left:10px">Duração alvo</span>
                  <input class="input" id="duracao-alvo" name="duration" type="number" min="10" max="36000" value="60" required{disabled} style="width:90px">
                </div>
                <p class="lbl" style="margin-bottom:8px">Estilo visual</p>
                <fieldset class="pills" style="margin:0;border:0;padding:0;display:block;width:100%">
                  <legend class="sr-only">Estilo visual</legend>
                  {style_options}
                </fieldset>
                <p class="sub" style="font-size:11px;margin-top:8px">
                  <a href="/studio/panel/estilos">Gerenciar estilos da biblioteca →</a>
                </p>
              </div>
            </div>

            <aside class="stack" style="position:sticky;top:80px">
              <aside class="painel" aria-labelledby="t-preset">
                <h3 id="t-preset">Predefinição do canal</h3>
                <p class="sub" style="margin:4px 0 12px">{e(current_channel_name)}</p>
                <table class="tabela-kv">
                  <caption class="sr-only">O que o canal define para cada vídeo</caption>
                  <tr><th scope="row">Canal</th><td class="texto-canal">{e(current_channel_name)}</td></tr>
                  <tr><th scope="row">Idioma</th><td>{idioma}</td></tr>
                  <tr><th scope="row">Voz</th><td>{voz}</td></tr>
                  <tr><th scope="row">Estilo</th><td>{estilo}</td></tr>
                </table>
                <p class="sub" style="font-size:11px;margin:12px 0 14px">
                  <a href="/studio/canais#painel-perfil">Personalizar identidade do canal →</a>
                </p>
                <div class="hr"></div>
                <p class="sample" style="margin-bottom:10px">Criar o rascunho prepara as cenas e fontes sem iniciar cobrança.</p>
                <button class="btn primary long" type="submit" id="btn-criar-abrir"{disabled}>Criar e abrir vídeo →</button>
                <p class="feedback" id="feedback-criar" role="status" style="margin-top:8px"></p>
              </aside>

              <div class="card painel" aria-labelledby="t-caminho">
                <h3 id="t-caminho" style="font-size:15px;margin:0 0 10px">Seu caminho até publicar</h3>
                <p class="sub" style="font-size:13px;line-height:1.6;margin:0 0 10px">
                  1. Adicione fontes e revise o roteiro.<br>
                  2. Gere narração e monte as cenas.<br>
                  3. Ajuste composição e confira a qualidade.<br>
                  4. Aprove a versão e prepare a publicação.
                </p>
                <p class="sample" style="margin:0">
                  Etapas reunidas dentro do vídeo. Você pode voltar para ajustar qualquer parte.
                </p>
              </div>

              <div class="note info">O canal tem estilo e voz vinculados. Mudar aqui vale só para este vídeo.</div>
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
