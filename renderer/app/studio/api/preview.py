"""Página de prévia e aprovação. HTML estático e sem dependências; todo texto vem escapado e a CSP só libera o script/estilo desta página.

A página usa a **casca compartilhada** (`api.panel.render_sidebar`): a navegação lateral e o
design system têm uma única fonte de verdade. Nada de paleta, `.sidebar` ou `.nav-menu` aqui.
"""
import html
import secrets

from . import panel as shell
from ..application.publishing import Preview
from ..domain.contracts import VideoStatus

e = lambda value: html.escape(str(value), quote=True)  # noqa: E731

JS = """
const form = document.getElementById('review');
const out = document.getElementById('result');
async function send(action) {
  const v = (id) => document.getElementById(id).value.trim();
  const body = {};
  if (action === 'approve') {
    body.output_asset_id = form.dataset.outputAssetId;
    body.title = v('title'); body.description = v('description');
    body.tags = v('tags') ? v('tags').split(',').map((t) => t.trim()).filter(Boolean) : [];
    if (v('publish_at')) body.publish_at = new Date(v('publish_at')).toISOString();
    if (v('override_reason')) body.override_reason = v('override_reason');
  } else if (v('reject_reason')) { body.reason = v('reject_reason'); }
  out.textContent = 'Enviando…';
  try {
    const r = await fetch(form.dataset.base + '/' + action, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (r.ok) { out.textContent = action === 'approve' ? 'Aprovado. A publicação é feita pelo workflow do n8n.' : 'Rejeitado.'; setTimeout(() => location.reload(), 900); }
    else out.textContent = 'Erro ' + r.status + ': ' + (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
  } catch (err) { out.textContent = 'Falha de rede: ' + err.message; }
}
document.getElementById('approve').addEventListener('click', () => send('approve'));
document.getElementById('reject').addEventListener('click', () => send('reject'));
"""


def render_preview(p: Preview) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    v = p.video
    base = f"/studio/videos/{v.id}"
    reviewable = v.status in (VideoStatus.AWAITING_APPROVAL, VideoStatus.RENDERED)
    qa_failed = p.qa is not None and not p.qa.is_publishable
    player = (f'<video controls preload="metadata" poster="{base}/thumbnail" src="{base}/file?output_asset_id={e(p.output_asset_id)}"><track kind="captions" srclang="pt-BR" label="Português" '
              f'src="{base}/subtitles.vtt" default></video>') if p.has_file else '<p class="bad" role="alert" style="padding: 2rem; background: var(--surface); border-radius: 8px; text-align: center;">Sem arquivo de vídeo renderizado.</p>'
    qa = "<p style='color: var(--text-muted); font-size: 0.85rem;'>Sem relatório de QA.</p>"
    if p.qa is not None:
        aprovado = p.qa.is_publishable
        counts = p.qa.severity_counts
        findings = "".join(f"<li>{e(f.evidence)} <span class='hint'>({e(f.severity)} · {e(f.check_id)})</span></li>" for f in p.qa.findings)
        resumo = (f"{counts['blocking']} bloqueante(s), {counts['warning']} aviso(s), {counts['info']} informativo(s) · "
                  f"cobertura {e(p.qa.coverage.status)}")
        findings_html = f"<ul class='bad' style='margin: 0.35rem 0;'>{findings}</ul>" if findings else ""
        qa = (f'<p class="{"ok" if aprovado else "bad"}" style="font-weight: 600; font-size: 0.9rem;">QA {"aprovado" if aprovado else "REPROVADO"}</p>'
              f"{findings_html}"
              f"<p class='hint' style='color: var(--text-muted); font-size: 0.8rem;'>{resumo}</p>")
    scenes = "".join(f"<li>{('<strong>' + e(s.label) + '</strong> ') if s.label else ''}{e(s.narration)}</li>" for s in p.scenes)
    sources = "".join(f'<li><a href="{e(u)}" rel="noopener noreferrer" target="_blank">{e(u)}</a></li>' for u in p.sources if u.startswith(("https://", "http://")))
    credits = "".join(f"<li>{e(c)}</li>" for c in p.credits)
    side = [
        f"<div class='card'><h2>Qualidade (QA)</h2>{qa}</div>",
        f"<div class='card' style='margin-top: 1rem;'><h2>Roteiro narrado</h2><ol>{scenes}</ol></div>",
        f"<div class='card' style='margin-top: 1rem;'><h2>Fontes</h2><ul>{sources or '<li>Nenhuma registrada.</li>'}</ul></div>"
    ]
    if credits:
        side.append(f"<div class='card' style='margin-top: 1rem;'><h2>Créditos de imagem</h2><ul>{credits}</ul></div>")
    review = ""
    if reviewable:
        override = ""
        if qa_failed:
            override = ('<label for="override_reason">O QA reprovou. Para aprovar mesmo assim, explique o motivo '
                        '<span class="hint">(obrigatório e fica registrado)</span></label><textarea id="override_reason" rows="2" maxlength="500"></textarea>')
        review = (f"<div class='card' style='margin-top: 1rem;'><h2>Decisão de Aprovação</h2><form id=\"review\" data-base=\"{base}\" data-output-asset-id=\"{e(p.output_asset_id or '')}\" onsubmit=\"return false\">"
                  f'<label for="title">Título <span class="hint">(até 100 caracteres, sem &lt; ou &gt;)</span></label>'
                  f'<input id="title" maxlength="100" value="{e(p.default_title)}">'
                  f'<label for="description">Descrição <span class="hint">(créditos, fontes e aviso de IA são acrescentados na publicação)</span></label>'
                  f'<textarea id="description" rows="5" maxlength="4000">{e(p.default_description)}</textarea>'
                  f'<label for="tags">Tags <span class="hint">(separadas por vírgula, até 15)</span></label><input id="tags" value="{e(", ".join(v.tags))}">'
                  f'<label for="publish_at">Agendar publicação <span class="hint">(opcional; o vídeo sobe privado e o YouTube publica no horário; '
                  f'mínimo 15 minutos à frente)</span></label><input id="publish_at" type="datetime-local">'
                  f'{override}<div style="margin-top: 0.5rem;"><button type="button" id="approve" class="btn btn-primary">Aprovar Vídeo</button></div>'
                  f'<label for="reject_reason" style="margin-top: 1.25rem;">Motivo da rejeição <span class="hint">(opcional)</span></label><textarea id="reject_reason" rows="2" maxlength="500"></textarea>'
                  f'<div><button type="button" id="reject" class="btn btn-danger">Rejeitar</button></div><output id="result" role="status" aria-live="polite" style="display: block; margin-top: 0.75rem; font-weight: 600; font-size: 0.85rem;"></output></form>'
                  f'<script nonce="{nonce}">{JS}</script></div>')
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
            who += f"<p>Publicação: <span class=\"badge\">{e(p.publication.status.value)}</span>{link}{(' — ' + e(p.publication.error)) if p.publication.error else ''}</p>"
        review = f"<div class='card' style='margin-top: 1rem;'><h2>Decisão</h2>{who or '<p>Este vídeo não está em revisão.</p>'}</div>"

    # Card lateral da casca: repete só o que é fato sobre a revisão — sem inventar custo do mês.
    side_card_html = (
        "<div class='side-card'><h2>Sobre esta prévia</h2>"
        "<p>Revise QA, roteiro e fontes antes de decidir. A publicação é feita pelo workflow do "
        "n8n — o Studio não publica sozinho.</p></div>"
    )

    doc = (
        f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Prévia: {e(p.default_title)}</title><style nonce="{nonce}">{shell.CSS}</style></head><body>'
        f'<div class="app-layout">'
        f'{shell.render_sidebar(active="videos", base_href="/studio/panel", side_card_html=side_card_html)}'
        f'<main class="main-content">'
        f'<header class="topbar">'
        f'  <div>'
        f'    <div style="font-size: 0.8rem; margin-bottom: 0.25rem;"><a href="/studio/panel">&larr; Voltar ao Painel</a></div>'
        f'    <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.25rem;">Painel / Prévia do Vídeo</div>'
        f'    <h1>{e(p.default_title)}</h1>'
        f'    <div style="margin-top: 0.25rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">'
        f'      <span class="badge">{e(v.status.value)}</span>'
        f'      <span class="badge">{e(v.format.value)}</span>'
        f'      <span style="font-size: 0.85rem; color: var(--text-muted);">Tema: {e(v.topic)}</span>'
        f'    </div>'
        f'  </div>'
        f'</header>'
        f'<div class="content-body">'
        f'  <div class="layout-detail"><section aria-label="Vídeo">{player}</section><section aria-label="Detalhes">{"".join(side)}{review}</section></div>'
        f'</div>'
        f'</main>'
        f'</div>'
        f'</body></html>'
    )
    headers = {"Content-Security-Policy": f"default-src 'none'; media-src 'self'; img-src 'self'; style-src 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; script-src 'nonce-{nonce}'; "
                                          "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
               "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    return doc, headers
