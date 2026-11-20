"""Página de prévia e aprovação. HTML estático e sem dependências; todo texto vem escapado e a CSP só libera o script/estilo desta página."""
import html
import secrets

from ..application.publishing import Preview
from ..domain.contracts import VideoStatus

e = lambda value: html.escape(str(value), quote=True)  # noqa: E731

CSS = """
:root { color-scheme: light dark; --gap: 1rem; font-family: system-ui, sans-serif; line-height: 1.5; }
body { margin: 0 auto; padding: 1rem; max-width: 70rem; }
h1 { font-size: 1.5rem; margin-block: .5rem; } h2 { font-size: 1.15rem; margin-block: 1.25rem .5rem; }
.layout { display: grid; gap: var(--gap); grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr)); align-items: start; }
video { width: 100%; max-height: 80vh; background: #000; border-radius: .5rem; }
.badge { display: inline-block; padding: .1rem .6rem; border-radius: 1rem; border: 1px solid currentColor; font-size: .85rem; }
.ok { color: #0a7d33; } .bad { color: #b3261e; }
@media (prefers-color-scheme: dark) { .ok { color: #5fd28a; } .bad { color: #ff8a80; } }
label { display: block; font-weight: 600; margin-block-start: .75rem; } .hint { font-weight: 400; font-size: .85rem; opacity: .8; }
input, textarea { width: 100%; box-sizing: border-box; font: inherit; padding: .4rem; }
button { font: inherit; padding: .6rem 1.2rem; margin: .75rem .5rem 0 0; cursor: pointer; min-block-size: 2.75rem; }
:where(a, button, input, textarea, video):focus-visible { outline: 3px solid Highlight; outline-offset: 2px; }
table { border-collapse: collapse; } th, td { text-align: start; padding: .2rem .8rem .2rem 0; }
"""

JS = """
const form = document.getElementById('review');
const out = document.getElementById('result');
async function send(action) {
  const v = (id) => document.getElementById(id).value.trim();
  const body = {};
  if (action === 'approve') {
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
    qa_failed = p.qa is not None and not p.qa.passed
    parts = [f"<h1>{e(p.default_title)}</h1>",
             f'<p><span class="badge">{e(v.status.value)}</span> <span class="badge">{e(v.format.value)}</span> Tema: {e(v.topic)}</p>']
    player = (f'<video controls preload="metadata" poster="{base}/thumbnail" src="{base}/file"><track kind="captions" srclang="pt-BR" label="Português" '
              f'src="{base}/subtitles.vtt" default></video>') if p.has_file else '<p class="bad" role="alert">Sem arquivo de vídeo renderizado.</p>'
    qa = "<p>Sem relatório de QA.</p>"
    if p.qa is not None:
        rows = "".join(f"<tr><th scope='row'>{e(k)}</th><td>{e(val)}</td></tr>" for k, val in sorted(p.qa.metrics.items()))
        fails = "".join(f"<li>{e(f)}</li>" for f in p.qa.failures)
        qa = (f'<p class="{"ok" if p.qa.passed else "bad"}"><strong>QA {"aprovado" if p.qa.passed else "REPROVADO"}</strong></p>'
              f"{f'<ul>{fails}</ul>' if fails else ''}<table><caption class='hint'>Métricas medidas</caption>{rows}</table>")
    scenes = "".join(f"<li>{('<strong>' + e(s.label) + '</strong> ') if s.label else ''}{e(s.narration)}</li>" for s in p.scenes)
    sources = "".join(f'<li><a href="{e(u)}" rel="noopener noreferrer" target="_blank">{e(u)}</a></li>' for u in p.sources if u.startswith(("https://", "http://")))
    credits = "".join(f"<li>{e(c)}</li>" for c in p.credits)
    side = [f"<h2>Qualidade (QA)</h2>{qa}", f"<h2>Roteiro narrado</h2><ol>{scenes}</ol>",
            f"<h2>Fontes</h2><ul>{sources or '<li>Nenhuma registrada.</li>'}</ul>"]
    if credits:
        side.append(f"<h2>Créditos de imagem</h2><ul>{credits}</ul>")
    review = ""
    if reviewable:
        override = ""
        if qa_failed:
            override = ('<label for="override_reason">O QA reprovou. Para aprovar mesmo assim, explique o motivo '
                        '<span class="hint">(obrigatório e fica registrado)</span></label><textarea id="override_reason" rows="2" maxlength="500"></textarea>')
        review = (f'<h2>Decisão</h2><form id="review" data-base="{base}" onsubmit="return false">'
                  f'<label for="title">Título <span class="hint">(até 100 caracteres, sem &lt; ou &gt;)</span></label>'
                  f'<input id="title" maxlength="100" value="{e(p.default_title)}">'
                  f'<label for="description">Descrição <span class="hint">(créditos, fontes e aviso de IA são acrescentados na publicação)</span></label>'
                  f'<textarea id="description" rows="5" maxlength="4000">{e(p.default_description)}</textarea>'
                  f'<label for="tags">Tags <span class="hint">(separadas por vírgula, até 15)</span></label><input id="tags" value="{e(", ".join(v.tags))}">'
                  f'<label for="publish_at">Agendar publicação <span class="hint">(opcional; o vídeo sobe privado e o YouTube publica no horário; '
                  f'mínimo 15 minutos à frente)</span></label><input id="publish_at" type="datetime-local">'
                  f'{override}<button type="button" id="approve">Aprovar</button>'
                  f'<label for="reject_reason">Motivo da rejeição <span class="hint">(opcional)</span></label><textarea id="reject_reason" rows="2" maxlength="500"></textarea>'
                  f'<button type="button" id="reject">Rejeitar</button><output id="result" role="status" aria-live="polite"></output></form>'
                  f'<script nonce="{nonce}">{JS}</script>')
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
        review = f"<h2>Decisão</h2>{who or '<p>Este vídeo não está em revisão.</p>'}"
    doc = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
           f"<title>Prévia: {e(p.default_title)}</title><style nonce=\"{nonce}\">{CSS}</style></head><body><main>{''.join(parts)}"
           f'<div class="layout"><section aria-label="Vídeo">{player}</section><section aria-label="Detalhes">{"".join(side)}{review}</section></div></main></body></html>')
    headers = {"Content-Security-Policy": f"default-src 'none'; media-src 'self'; img-src 'self'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
                                          "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
               "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}
    return doc, headers
