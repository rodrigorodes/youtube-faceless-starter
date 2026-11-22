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
      var scriptField = $('#roteiro-pronto');
      var scriptText = (scriptField ? scriptField.value : '').trim();

      var payload = {
        project_id: canalSel.value,
        topic: tema,
        format: fmt ? fmt.value : 'short'
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

    body = f"""      <section class="pagina" id="pagina-novo-video" aria-labelledby="t-novo">
        <div class="secao-cab">
          <div>
            <p class="eyebrow">CRIAR / NOVO VÍDEO</p>
            <h1 class="h1" id="t-novo">Novo vídeo do canal</h1>
            <p class="lead">Qual história você quer contar? · Canal: <b>{e(current_channel_name)}</b></p>
          </div>
          <a class="btn" href="/studio/panel">← Voltar ao Início</a>
        </div>
        {gate}

        <div class="grade-criar" style="display:grid;grid-template-columns:1.6fr 1fr;gap:22px;align-items:start">
          <form id="form-novo-video" class="card painel" novalidate>
            <div class="campo">
              <label for="tema-novo">Sobre o que é o vídeo?</label>
              <textarea id="tema-novo" name="topic" maxlength="300" required aria-describedby="dica-tema"
                        placeholder="Descreva a história que você quer contar. Ex.: por que as cidades surgiram?"{disabled}></textarea>
              <p class="dica" id="dica-tema">De 3 a 300 caracteres.</p>
              <p class="campo-erro" id="erro-tema">Informe o tema do vídeo (mínimo de 3 caracteres).</p>
            </div>

            <div class="grid-2" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:14px">
              <div class="field">
                <label>Formato</label>
                <fieldset class="pills" style="margin:0">
                  <legend class="sr-only">Formato</legend>
                  <label class="pill pill-formato"><input type="radio" name="formato-novo" value="long" checked{disabled}>
                    <svg class="icone-formato" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                      <rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 9h20M2 15h20"/></svg>
                    Vídeo · horizontal 16:9</label>
                  <label class="pill pill-formato"><input type="radio" name="formato-novo" value="short"{disabled}>
                    <svg class="icone-formato" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                      <rect x="7" y="2" width="10" height="20" rx="2"/><path d="M7 6h10M7 18h10"/></svg>
                    Short · vertical 9:16</label>
                </fieldset>
              </div>
              <div class="field">
                <label for="duracao-alvo">Duração-alvo em segundos</label>
                <input class="input" id="duracao-alvo" name="duration" type="number" min="10" max="36000" value="60" required{disabled}
                       style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--line);background:var(--panel2);color:var(--txt)">
                <p class="dica" style="margin:4px 0 0;font-size:11px;color:var(--muted)">Meta de duração estimada.</p>
              </div>
            </div>

            <div class="campo" style="margin-top:16px">
              <label for="roteiro-pronto">Roteiro pronto (opcional)</label>
              <textarea id="roteiro-pronto" name="script" rows="4" maxlength="50000"
                        placeholder="Cole seu roteiro ou escreva depois. Separe as cenas por uma linha em branco."{disabled}></textarea>
              <p class="dica" style="margin:4px 0 0;font-size:11px;color:var(--muted)">Seu texto será preservado nas fontes e usado na criação das cenas.</p>
            </div>

            <div class="campo" style="margin-top:12px">
              <label class="check" for="revisar-roteiro" style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer">
                <input id="revisar-roteiro" type="checkbox" checked{disabled}>
                Revisar roteiro antes de gerar voz e imagens
              </label>
            </div>

            <fieldset class="pills" style="margin-top:16px;display:block;width:100%">
              <legend>Estilo visual</legend>
              {style_options}
            </fieldset>
            <p class="micro" style="margin:8px 0 0">
              <a href="/studio/panel/estilos">Gerenciar estilos da biblioteca →</a></p>

            <p class="feedback" id="feedback-criar" role="status"></p>

            <div class="acoes" style="margin-top:20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
              <span class="micro dim">Criar rascunho não inicia geração paga.</span>
              <button class="btn btn-primario" type="submit" id="btn-criar-abrir"{disabled}>Criar e abrir vídeo →</button>
            </div>
          </form>

          <div class="stack" style="display:grid;gap:16px">
            <aside class="painel" aria-labelledby="t-preset">
              <h3 id="t-preset">Predefinição do canal</h3>
              <table class="tabela-kv">
                <caption class="sr-only">O que o canal define para cada vídeo</caption>
                <tr><th scope="row">Canal</th><td class="texto-canal">{e(current_channel_name)}</td></tr>
                <tr><th scope="row">Idioma</th><td>{idioma}</td></tr>
                <tr><th scope="row">Voz</th><td>{voz}</td></tr>
                <tr><th scope="row">Estilo</th><td>{estilo}</td></tr>
              </table>
              <p class="micro" style="margin:14px 0 0">
                <a href="/studio/canais#painel-perfil">Personalizar identidade do canal →</a></p>
            </aside>

            <div class="card painel" aria-labelledby="t-caminho">
              <h3 id="t-caminho" style="font-size:15px;margin:0 0 10px">Seu caminho até publicar</h3>
              <p class="dim" style="font-size:13px;line-height:1.6;margin:0 0 10px">
                1. Adicione fontes e revise o roteiro.<br>
                2. Gere narração e monte as cenas.<br>
                3. Ajuste composição e confira a qualidade.<br>
                4. Aprove a versão e prepare a publicação.
              </p>
              <p class="micro dim" style="margin:0">
                Etapas reunidas dentro do vídeo. Você pode voltar para ajustar qualquer parte.
              </p>
            </div>
          </div>
        </div>
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
