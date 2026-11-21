"""Tela Novo vídeo da UX V3 — três etapas: Conceito -> Revisão -> Criação.

Fonte da verdade visual: `docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html` (#pagina-novo-video).
A criação usa POST /studio/videos; a produção não começa aqui (começa na página do vídeo).
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
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var etapa1 = $('#etapa-1');
  var etapa2 = $('#etapa-2');
  var etapa3 = $('#etapa-3');
  var passos = $$('#passos-criar li:not(.risco)');

  function irParaEtapa(n) {
    if (etapa1) etapa1.hidden = n !== 1;
    if (etapa2) etapa2.hidden = n !== 2;
    if (etapa3) etapa3.hidden = n !== 3;
    passos.forEach(function (li, idx) {
      var num = idx + 1;
      li.classList.toggle('feito', num < n);
      if (num === n) li.setAttribute('aria-current', 'step');
      else li.removeAttribute('aria-current');
      var b = $('b', li);
      if (b) b.textContent = num < n ? '✓' : String(num);
    });
  }

  var btnRevisao = $('#btn-para-revisao');
  var temaCampo = $('#tema-novo');
  var erroTema = $('#erro-tema');

  if (btnRevisao && temaCampo) {
    btnRevisao.addEventListener('click', function () {
      var tema = temaCampo.value.trim();
      if (!tema || tema.length < 3) {
        if (erroTema) erroTema.style.display = 'block';
        temaCampo.focus();
        return;
      }
      if (erroTema) erroTema.style.display = 'none';
      var fmt = $('input[name="formato-novo"]:checked');
      var est = $('input[name="estilo-novo"]:checked');
      var canalSel = $('#canal-ativo');
      var canalNome = canalSel && canalSel.selectedOptions && canalSel.selectedOptions[0] ? canalSel.selectedOptions[0].textContent : (canalSel ? canalSel.value : '');

      var elTema = $('#rev-tema');
      if (elTema) elTema.textContent = tema.length > 90 ? tema.slice(0, 90) + '…' : tema;
      var elFmt = $('#rev-formato');
      if (elFmt) elFmt.textContent = fmt && fmt.value === 'long' ? 'Vídeo (16:9)' : 'Short (9:16)';
      var elEst = $('#rev-estilo');
      if (elEst) elEst.textContent = est ? est.value : 'Padrão do canal';
      var elCanal = $('#rev-canal');
      if (elCanal) elCanal.textContent = canalNome || 'Canal ativo';
      irParaEtapa(2);
    });
  }

  var btnVoltar = $('#btn-voltar-editar');
  if (btnVoltar) {
    btnVoltar.addEventListener('click', function () { irParaEtapa(1); });
  }

  var btnCriar = $('#btn-criar');
  var fb = $('#feedback-criar');
  if (btnCriar && temaCampo) {
    btnCriar.addEventListener('click', function () {
      var tema = temaCampo.value.trim();
      var canalSel = $('#canal-ativo');
      if (!tema || !canalSel) return;
      var fmt = $('input[name="formato-novo"]:checked');
      btnCriar.disabled = true;
      if (fb) { fb.removeAttribute('data-tipo'); fb.textContent = 'Criando vídeo…'; }

      fetch('/studio/videos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: canalSel.value,
          topic: tema,
          format: fmt ? fmt.value : 'short'
        })
      }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return [r, d]; }); })
        .then(function (par) {
          var r = par[0], d = par[1];
          if (r.ok && d.id) {
            var link = $('#link-abrir-video');
            if (link) link.href = '/studio/panel/videos/' + encodeURIComponent(d.id);
            irParaEtapa(3);
          } else {
            if (fb) {
              fb.setAttribute('data-tipo', 'erro');
              fb.textContent = 'Erro ao criar: ' + (typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail || d));
            }
            btnCriar.disabled = false;
          }
        })
        .catch(function (err) {
          if (fb) {
            fb.setAttribute('data-tipo', 'erro');
            fb.textContent = 'Falha de rede: ' + err.message;
          }
          btnCriar.disabled = false;
        });
    });
  }

  var btnOutro = $('#btn-novo-outro');
  if (btnOutro) {
    btnOutro.addEventListener('click', function () {
      if (temaCampo) temaCampo.value = '';
      if (fb) { fb.removeAttribute('data-tipo'); fb.textContent = ''; }
      if (btnCriar) btnCriar.disabled = false;
      irParaEtapa(1);
    });
  }
})();
"""


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

    body = f"""      <section class="pagina" id="pagina-novo-video" aria-labelledby="t-novo">
        <div class="secao-cab">
          <div>
            <p class="eyebrow">CRIAR / NOVO VÍDEO</p>
            <h1 class="h1" id="t-novo">Novo vídeo do canal</h1>
            <p class="lead">Uma ideia é tudo o que você precisa para começar.</p>
          </div>
          <a class="btn" href="/studio/panel">← Voltar ao Início</a>
        </div>
        {gate}

        <ol class="passos" id="passos-criar" aria-label="Etapas de criação">
          <li aria-current="step" id="passo-1"><b>1</b> Conceito</li>
          <li class="risco" aria-hidden="true"></li>
          <li id="passo-2"><b>2</b> Revisão</li>
          <li class="risco" aria-hidden="true"></li>
          <li id="passo-3"><b>3</b> Criação</li>
        </ol>

        <div class="grade-criar">
          <div class="painel" id="etapa-1">
            <h3>Comece pelo conceito</h3>
            <p>O Estúdio usa o que está definido no canal para montar a produção.</p>
            <div class="campo">
              <label for="tema-novo">Sobre o que é o vídeo?</label>
              <textarea id="tema-novo" maxlength="300" required aria-describedby="dica-tema"
                        placeholder="Descreva o assunto. Ex.: o futuro dos agentes de IA autônomos e o que muda no trabalho."{disabled}></textarea>
              <p class="dica" id="dica-tema">De 3 a 300 caracteres.</p>
              <p class="campo-erro" id="erro-tema">Informe o tema do vídeo (mínimo de 3 caracteres).</p>
            </div>
            <fieldset class="pills">
              <legend>Formato</legend>
              <label class="pill"><input type="radio" name="formato-novo" value="long" checked{disabled}>
                Vídeo · horizontal 16:9</label>
              <label class="pill"><input type="radio" name="formato-novo" value="short"{disabled}>
                Short · vertical 9:16</label>
            </fieldset>
            <fieldset class="pills" style="margin-top:18px">
              <legend>Estilo visual</legend>
              <label class="pill"><input type="radio" name="estilo-novo" value="Padrão do canal" checked{disabled}>
                Padrão do canal</label>
              <label class="pill"><input type="radio" name="estilo-novo" value="Cinemático"{disabled}>
                Cinemático</label>
              <label class="pill"><input type="radio" name="estilo-novo" value="Documentário"{disabled}>
                Documentário</label>
              <label class="pill"><input type="radio" name="estilo-novo" value="Tech Clean"{disabled}>
                Tech Clean</label>
            </fieldset>
            <div class="acoes">
              <span class="micro">Voz, idioma e identidade vêm do canal.</span>
              <button class="btn btn-primario" type="button" id="btn-para-revisao"{disabled}>Continuar →</button>
            </div>
          </div>

          <div class="painel" id="etapa-2" hidden>
            <h3>Está tudo certo?</h3>
            <p>Revise antes de criar — depois disso o vídeo vai para a sua lista.</p>
            <table class="tabela-kv">
              <caption class="sr-only">Resumo do vídeo a criar</caption>
              <tr><th scope="row">Tema</th><td id="rev-tema">—</td></tr>
              <tr><th scope="row">Formato</th><td id="rev-formato">—</td></tr>
              <tr><th scope="row">Estilo visual</th><td id="rev-estilo">—</td></tr>
              <tr><th scope="row">Canal</th><td id="rev-canal">—</td></tr>
              <tr><th scope="row">Voz</th><td>Padrão do canal</td></tr>
            </table>
            <p class="feedback" id="feedback-criar" role="status"></p>
            <div class="acoes">
              <button class="btn" type="button" id="btn-voltar-editar">← Editar</button>
              <button class="btn btn-primario" type="button" id="btn-criar">✦ Criar vídeo</button>
            </div>
          </div>

          <div class="painel" id="etapa-3" hidden>
            <h3>Vídeo criado</h3>
            <div class="aviso">
              <p style="margin:0 0 10px"><b>Próximo passo: as fontes.</b> O roteiro só é escrito a partir
              de fatos das fontes — sem fonte aproveitável, a produção para no primeiro passo.</p>
              <p class="micro" style="margin:0">Por isso a produção <b>não</b> começa aqui: ela começa na
              página do vídeo, depois que você informar a fonte.</p>
            </div>
            <div class="acoes">
              <button class="btn" type="button" id="btn-novo-outro">Criar outro</button>
              <a class="btn btn-primario" href="/studio/panel" id="link-abrir-video">Abrir o vídeo e informar a fonte →</a>
            </div>
          </div>

          <aside class="painel" aria-labelledby="t-preset">
            <h3 id="t-preset">Predefinição do canal</h3>
            <table class="tabela-kv">
              <caption class="sr-only">O que o canal define para cada vídeo</caption>
              <tr><th scope="row">Canal</th><td class="texto-canal">{e(current_channel_name)}</td></tr>
              <tr><th scope="row">Idioma</th><td>Português (BR)</td></tr>
              <tr><th scope="row">Voz</th><td>Natural / Narrador</td></tr>
              <tr><th scope="row">Legendas</th><td>Dinâmicas</td></tr>
              <tr><th scope="row">Música</th><td>Ambiente</td></tr>
            </table>
            <p class="micro" style="margin:14px 0 0">
              <a href="/studio/configuracoes/canais">Personalizar identidade do canal →</a></p>
          </aside>
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
