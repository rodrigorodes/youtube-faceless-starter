"""Página de prévia e aprovação. HTML estático e sem dependências; todo texto vem escapado e a CSP só libera o script/estilo desta página.

A página usa a **casca compartilhada** (`api.panel.render_sidebar`): a navegação lateral e o
design system têm uma única fonte de verdade. Nada de paleta, `.sidebar` ou `.nav-menu` aqui.
"""
import html
import secrets

from . import panel as shell
from . import shell_v3
from ..application.publishing import Preview
from ..domain.contracts import VideoStatus

e = lambda value: html.escape(str(value), quote=True)  # noqa: E731

JS = """
const form = document.getElementById('review');
const out = document.getElementById('result');
async function send(action) {
  if (!form || !out) return;
  const v = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const body = {};
  if (action === 'approve') {
    body.output_asset_id = form.dataset.outputAssetId;
    body.title = v('title'); body.description = v('description');
    body.tags = v('tags') ? v('tags').split(',').map((t) => t.trim()).filter(Boolean) : [];
    if (v('publish_at')) body.publish_at = new Date(v('publish_at')).toISOString();
    if (v('override_reason')) body.override_reason = v('override_reason');
  } else if (v('reject_reason')) { body.reason = v('reject_reason'); }
  const btn = action === 'approve' ? btnApprove : btnReject;
  if (btn) { btn.disabled = true; btn.classList.add('carregando'); }
  if (window.StudioLoading) window.StudioLoading.start();
  out.textContent = 'Enviando…';
  try {
    const r = await fetch(form.dataset.base + '/' + action, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (r.ok) {
      out.textContent = action === 'approve' ? 'Aprovado. A publicação é feita pelo workflow do n8n.' : 'Rejeitado.';
      setTimeout(() => location.reload(), 900);
    } else {
      out.textContent = 'Erro ' + r.status + ': ' + (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
      if (btn) { btn.disabled = false; btn.classList.remove('carregando'); }
      if (window.StudioLoading) window.StudioLoading.done();
    }
  } catch (err) {
    out.textContent = 'Falha de rede: ' + err.message;
    if (btn) { btn.disabled = false; btn.classList.remove('carregando'); }
    if (window.StudioLoading) window.StudioLoading.done();
  }
}
const btnApprove = document.getElementById('approve');
if (btnApprove) btnApprove.addEventListener('click', () => send('approve'));
const btnReject = document.getElementById('reject');
if (btnReject) btnReject.addEventListener('click', () => send('reject'));
"""


def render_preview(p: Preview) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    v = p.video
    base = f"/studio/videos/{v.id}"
    reviewable = v.status in (VideoStatus.AWAITING_APPROVAL, VideoStatus.RENDERED)
    qa_failed = p.qa is not None and not p.qa.is_publishable
    player = (f'<video controls preload="metadata" poster="{base}/thumbnail" src="{base}/file?output_asset_id={e(p.output_asset_id)}" style="width:100%;max-height:460px;display:block"><track kind="captions" srclang="pt-BR" label="Português" '
              f'src="{base}/subtitles.vtt" default></video>') if p.has_file else '<p class="muted" role="alert" style="padding: 2rem; text-align: center;">Sem arquivo de vídeo renderizado.</p>'
    qa = "<p class='muted' style='font-size: 0.85rem;'>Sem relatório de QA.</p>"
    if p.qa is not None:
        aprovado = p.qa.is_publishable
        counts = p.qa.severity_counts
        findings = "".join(f"<li>{e(f.evidence)} <span class='hint'>({e(f.severity)} · {e(f.check_id)})</span></li>" for f in p.qa.findings)
        resumo = (f"{counts['blocking']} bloqueante(s), {counts['warning']} aviso(s), {counts['info']} informativo(s) · "
                  f"cobertura {e(p.qa.coverage.status)}")
        findings_html = f"<ul style='margin: 0.35rem 0;color:var(--err)'>{findings}</ul>" if findings else ""
        selo_qa = '<span class="selo" style="color:var(--good);border-color:var(--good)">✓ QA Aprovado</span>' if aprovado else '<span class="selo" style="color:var(--err);border-color:var(--err)">× QA Reprovado</span>'
        qa = (f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">{selo_qa}</div>'
              f"{findings_html}"
              f"<p class='micro'>{resumo}</p>")
    scenes = "".join(f"<li><span class='cena-n'>{i + 1}</span><div>{('<b>' + e(s.label) + '</b><br>') if s.label else ''}<span>{e(s.narration)}</span></div></li>" for i, s in enumerate(p.scenes))
    sources = "".join(f'<li><a href="{e(u)}" rel="noopener noreferrer" target="_blank">{e(u)}</a></li>' for u in p.sources if u.startswith(("https://", "http://")))
    credits = "".join(f"<li>{e(c)}</li>" for c in p.credits)
    side = [
        f"<div class='card painel'><h3>Qualidade (QA)</h3>{qa}</div>",
        f"<div class='card painel' style='margin-top: 18px;'><h3>Roteiro narrado</h3><ul class='cenas'>{scenes}</ul></div>",
        f"<div class='card painel' style='margin-top: 18px;'><h3>Fontes</h3><ul>{sources or '<li>Nenhuma registrada.</li>'}</ul></div>"
    ]
    if credits:
        side.append(f"<div class='card painel' style='margin-top: 18px;'><h3>Créditos de imagem</h3><ul>{credits}</ul></div>")
    review = ""
    if reviewable:
        override = ""
        if qa_failed:
            override = ('<div class="campo"><label for="override_reason">O QA reprovou. Para aprovar mesmo assim, explique o motivo '
                        '<span class="micro">(obrigatório e fica registrado)</span></label><textarea id="override_reason" rows="2" maxlength="500"></textarea></div>')
        review = (f"<div class='card painel' style='margin-top: 18px;'><h3>Decisão de Aprovação</h3><form id=\"review\" data-base=\"{base}\" data-output-asset-id=\"{e(p.output_asset_id or '')}\" onsubmit=\"return false\">"
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
                  f'</div>')
    else:
        who = ""
        if p.approval:
            who = f"<p>Decisão: <strong>{'aprovado' if p.approval.decision == 'approved' else 'rejeitado'}</strong>"
            who += f" — {e(p.approval.reason)}" if p.approval.reason else ""
            who += " (aprovado com override do QA)" if p.approval.qa_override else ""
            who += "</p>"
        if p.publication:
            link = (f' <a href="https://www.youtube.com/watch?v={e(p.publication.youtube_video_id)}" rel="noopener noreferrer" target="_blank">abrir no YouTube</a>'
                    if p.publication.youtube_video_id else "")
            who += f"<p>Publicação: <span class=\"selo\">{e(p.publication.status.value)}</span>{link}{(' — ' + e(p.publication.error)) if p.publication.error else ''}</p>"
        fallback_review = '<p class="muted">Este vídeo não está em revisão.</p>'
        review = f"<div class='card painel' style='margin-top: 18px;'><h3>Decisão</h3>{who or fallback_review}</div>"

    body_html = f"""      <section class="pagina" id="pagina-previa" aria-labelledby="previa-heading">
        <p class="crumb" style="margin:0 0 10px"><a href="/studio/panel/videos/{e(v.id)}">← Voltar ao vídeo</a> /
          <span>Prévia do corte final</span></p>
        <div class="cab-video">
          <div>
            <p class="eyebrow">PRÉVIA E APROVAÇÃO</p>
            <h1 class="h1" id="previa-heading">{e(p.default_title)}</h1>
            <p class="lead" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <span class="pill pill-{e(v.status.value)}">{e(v.status.value)}</span>
              <span class="selo">{e(v.format.value)}</span>
              <span class="micro">Tema: {e(v.topic)}</span>
            </p>
          </div>
        </div>

        <div class="grade-video">
          <div>
            <div class="player" style="aspect-ratio:auto;padding:0;overflow:hidden;background:#000">
              {player}
            </div>
            {review}
          </div>

          <div>
            {"".join(side)}
          </div>
        </div>
      </section>"""

    doc = shell_v3.render_document(
        title=f"Faceless Studio — Prévia: {p.default_title}",
        active="videos",
        crumb="Vídeos / Prévia",
        body_html=body_html,
        nonce=nonce,
        projects=[],
        project_id="",
        cost_note="",
        page_js=JS,
    )
    headers = {"Content-Security-Policy": f"default-src 'none'; media-src 'self'; img-src 'self'; style-src 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; script-src 'nonce-{nonce}'; "
                                          "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
               "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    return doc, headers
