"""Formulário de decisão de aprovação — uma única fonte para a prévia e a aba Publicação (W5.1).

Extraído de `api.preview` para ser reutilizado sem duplicar HTML/JS: a página de prévia e a aba
Publicação do workspace renderizam o **mesmo** bloco. Quem hospeda define a CSP; todo texto do
vídeo entra escapado (`html.escape(..., quote=True)`).
"""
from __future__ import annotations

import html

from ..application.publishing import Preview
from ..domain.contracts import VideoStatus

e = lambda value: html.escape(str(value), quote=True)  # noqa: E731

# Executado dentro do `<script nonce>` do documento. O formulário não navega: o envio é por fetch.
APPROVAL_JS = """
(function () {
  var form = document.getElementById('review');
  var out = document.getElementById('result');
  if (!form) return;
  form.addEventListener('submit', function (event) { event.preventDefault(); });
  async function send(action) {
    var v = function (id) {
      var el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };
    var body = {};
    if (action === 'approve') {
      body.output_asset_id = form.dataset.outputAssetId;
      body.title = v('title'); body.description = v('description');
      body.tags = v('tags') ? v('tags').split(',').map(function (t) { return t.trim(); }).filter(Boolean) : [];
      if (v('publish_at')) body.publish_at = new Date(v('publish_at')).toISOString();
      if (v('override_reason')) body.override_reason = v('override_reason');
    } else if (v('reject_reason')) { body.reason = v('reject_reason'); }
    var btn = action === 'approve' ? document.getElementById('approve') : document.getElementById('reject');
    if (btn) { btn.disabled = true; btn.classList.add('carregando'); }
    if (window.StudioLoading) window.StudioLoading.start();
    if (out) out.textContent = 'Enviando…';
    try {
      var r = await fetch(form.dataset.base + '/' + action, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      var data = await r.json().catch(function () { return {}; });
      if (r.ok) {
        if (out) out.textContent = action === 'approve' ? 'Aprovado. A publicação é feita pelo servidor do Studio.' : 'Rejeitado.';
        setTimeout(function () { location.reload(); }, 900);
      } else {
        if (out) out.textContent = 'Erro ' + r.status + ': ' + (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
        if (btn) { btn.disabled = false; btn.classList.remove('carregando'); }
        if (window.StudioLoading) window.StudioLoading.done();
      }
    } catch (err) {
      if (out) out.textContent = 'Falha de rede: ' + err.message;
      if (btn) { btn.disabled = false; btn.classList.remove('carregando'); }
      if (window.StudioLoading) window.StudioLoading.done();
    }
  }
  var btnApprove = document.getElementById('approve');
  if (btnApprove) btnApprove.addEventListener('click', function () { send('approve'); });
  var btnReject = document.getElementById('reject');
  if (btnReject) btnReject.addEventListener('click', function () { send('reject'); });
})();
"""


def render_decision_summary(p: Preview, *, bare: bool = False) -> str:
    """Resumo da decisão já registrada (ou a ausência explícita de revisão)."""
    who = ""
    if p.approval:
        who = f"<p>Decisão: <strong>{'aprovado' if p.approval.decision == 'approved' else 'rejeitado'}</strong>"
        who += f" — {e(p.approval.reason)}" if p.approval.reason else ""
        who += " (aprovado com override do QA)" if p.approval.qa_override else ""
        who += "</p>"
    if p.publication:
        link = (f' <a href="https://www.youtube.com/watch?v={e(p.publication.youtube_video_id)}" rel="noopener noreferrer" target="_blank">abrir no YouTube</a>'
                if p.publication.youtube_video_id else "")
        who += (f"<p>Publicação: <span class=\"selo\">{e(p.publication.status.value)}</span>{link}"
                f"{(' — ' + e(p.publication.error)) if p.publication.error else ''}</p>")
    fallback = '<p class="muted">Este vídeo não está em revisão.</p>'
    if bare:  # dentro do cartão "Dados de publicação" do workspace: sem moldura própria
        return f"<div class='card flat' style='margin-top: 14px;'><h3>Decisão</h3>{who or fallback}</div>"
    return f"<div class='card painel' style='margin-top: 18px;'><h3>Decisão</h3>{who or fallback}</div>"


def render_approval_decision(p: Preview, *, base: str | None = None, bare: bool = False) -> str:
    """Formulário de aprovação quando o vídeo está em revisão; senão, o resumo da decisão.

    O formulário é idêntico ao da prévia. `base` é o prefixo das rotas de aprovação/rejeição
    (`/studio/videos/{id}`); o padrão mantém a mesma URL da prévia.
    """
    v = p.video
    base = base or f"/studio/videos/{v.id}"
    if v.status not in (VideoStatus.AWAITING_APPROVAL, VideoStatus.RENDERED):
        return render_decision_summary(p, bare=bare)

    qa_failed = p.qa is not None and not p.qa.is_publishable
    override = ""
    if qa_failed:
        override = ('<div class="campo"><label for="override_reason">O QA reprovou. Para aprovar mesmo assim, explique o motivo '
                    '<span class="micro">(obrigatório e fica registrado)</span></label><textarea id="override_reason" rows="2" maxlength="500"></textarea></div>')
    frame_open = "" if bare else "<div class='card painel' style='margin-top: 18px;'><h3>Decisão de Aprovação</h3>"
    frame_close = "" if bare else "</div>"
    return (f"{frame_open}<form id=\"review\" data-base=\"{e(base)}\" data-output-asset-id=\"{e(p.output_asset_id or '')}\" onsubmit=\"return false\">"
            f'<div class="campo"><label for="title">Título <span class="micro">(até 100 caracteres, sem &lt; ou &gt;)</span></label>'
            f'<input id="title" class="campo" maxlength="100" value="{e(p.default_title)}"></div>'
            f'<div class="campo"><label for="description">Descrição <span class="micro">(créditos, fontes e aviso de IA são acrescentados na publicação)</span></label>'
            f'<textarea id="description" class="campo" rows="4" maxlength="4000">{e(p.default_description)}</textarea></div>'
            f'<div class="campo"><label for="tags">Tags <span class="micro">(separadas por vírgula, até 15)</span></label><input id="tags" class="campo" value="{e(", ".join(v.tags))}"></div>'
            f'<div class="campo"><label for="publish_at">Agendar publicação <span class="micro">(opcional; o vídeo sobe privado e o YouTube publica no horário; '
            f'mínimo 15 minutos à frente)</span></label><input id="publish_at" class="campo" type="datetime-local"></div>'
            f'{override}<div class="acoes" style="margin-top: 14px;"><button type="button" id="approve" class="btn btn-primario btn-primary">Aprovar Vídeo</button></div>'
            f'<div class="campo" style="margin-top: 20px; border-top: 1px solid var(--line); padding-top: 16px;"><label for="reject_reason">Motivo da rejeição <span class="micro">(opcional)</span></label><textarea id="reject_reason" class="campo" rows="2" maxlength="500" placeholder="Informe o motivo caso rejeite"></textarea></div>'
            f'<div class="acoes" style="margin-top: 10px;"><button type="button" id="reject" class="btn btn-perigo btn-danger">Rejeitar</button></div><output id="result" role="status" aria-live="polite" class="feedback"></output></form>'
            f'{frame_close}')
