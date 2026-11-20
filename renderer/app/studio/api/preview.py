"""Página de prévia e aprovação. HTML estático e sem dependências; todo texto vem escapado e a CSP só libera o script/estilo desta página."""
import html
import secrets

from ..application.publishing import Preview
from ..domain.contracts import VideoStatus

e = lambda value: html.escape(str(value), quote=True)  # noqa: E731

CSS = """
:root {
  color-scheme: light dark;
  --bg: #0f0f0f;
  --surface: #181818;
  --surface-alt: #212121;
  --surface-hover: #212121;
  --border: #282828;
  --border-hover: #383838;
  --text: #f1f1f1;
  --text-muted: #aaaaaa;
  --primary: #cc0000;
  --primary-hover: #ff0000;
  --primary-focus: rgba(204, 0, 0, 0.28);
  --input-bg: #121212;
  --input-focus-bg: #181818;
  --ok: #2ba640;
  --ok-bg: rgba(43, 166, 64, 0.14);
  --bad: #ff4e45;
  --bad-bg: rgba(255, 78, 69, 0.14);
  --warn: #fbc02d;
  --warn-bg: rgba(251, 192, 45, 0.14);
  --gap: 1.5rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f5f7fb;
    --surface: #ffffff;
    --surface-alt: #f0f0f0;
    --surface-hover: #f7fafc;
    --border: #dbe2ec;
    --border-hover: #cbd5e1;
    --text: #1a202c;
    --text-muted: #64748b;
    --primary: #cc0000;
    --primary-hover: #b30000;
    --primary-focus: rgba(204, 0, 0, 0.22);
    --input-bg: #ffffff;
    --input-focus-bg: #ffffff;
    --ok: #1a7f37;
    --ok-bg: rgba(26, 127, 55, 0.12);
    --bad: #cf222e;
    --bad-bg: rgba(207, 34, 46, 0.12);
    --warn: #9a6700;
    --warn-bg: rgba(154, 103, 0, 0.12);
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); padding: 1.5rem; margin: 0 auto; max-width: 80rem; }
header { margin-bottom: 1.25rem; }
h1 { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.01em; margin-bottom: 0.35rem; }
h2 { font-size: 1.05rem; font-weight: 600; margin: 1.25rem 0 0.5rem; color: var(--text); }
a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }

.layout { display: grid; gap: var(--gap); grid-template-columns: minmax(18rem, 26rem) 1fr; align-items: start; }
@media (max-width: 860px) {
  .layout { grid-template-columns: 1fr; }
}

video { width: 100%; max-height: 80vh; background: #000; border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 4px 12px rgba(0,0,0,0.25); }

.badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; background: var(--surface); border: 1px solid var(--border); margin-right: 0.35rem; }
.ok { color: var(--ok); }
.bad { color: var(--bad); }

label { display: block; font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-top: 0.85rem; margin-bottom: 0.25rem; }
.hint { font-weight: 400; font-size: 0.78rem; opacity: 0.8; }

input, textarea {
  width: 100%;
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.6rem 0.85rem;
  font: inherit;
  font-size: 0.875rem;
  color: var(--text);
  transition: border-color 0.15s, box-shadow 0.15s, background-color 0.15s;
}
input:hover, textarea:hover { border-color: var(--border-hover); }
input:focus-visible, textarea:focus-visible {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-focus);
  background: var(--input-focus-bg);
}

button {
  font: inherit;
  font-size: 0.875rem;
  font-weight: 600;
  padding: 0.55rem 1.25rem;
  border-radius: 8px;
  border: 1px solid transparent;
  cursor: pointer;
  min-height: 42px;
  margin-top: 0.85rem;
  margin-right: 0.5rem;
  transition: all 0.15s ease;
}
button#approve {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
  box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}
button#approve:hover {
  background: var(--primary-hover);
  box-shadow: 0 2px 6px var(--primary-focus);
}
button#reject {
  background: var(--surface);
  color: var(--bad);
  border-color: var(--border);
}
button#reject:hover {
  background: var(--bad-bg);
  border-color: var(--bad);
}
button:focus-visible { outline: 3px solid var(--primary); outline-offset: 2px; }

table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-top: 0.5rem; }
th, td { text-align: start; padding: 0.45rem 0.85rem; font-size: 0.82rem; border-bottom: 1px solid var(--border); }
th { color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; font-weight: 600; }
tr:last-child th, tr:last-child td { border-bottom: none; }

ol, ul { padding-left: 1.25rem; font-size: 0.875rem; color: var(--text); }
li { margin-bottom: 0.35rem; }

section[aria-label="Detalhes"] { display: flex; flex-direction: column; gap: 1rem; }
section[aria-label="Detalhes"] .card-panel { margin-top: 0 !important; }
.card-panel { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; }
"""

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
    qa_failed = p.qa is not None and not p.qa.passed
    header_parts = [
        '<div style="font-size: 0.82rem; margin-bottom: 0.35rem;"><a href="/studio/panel">&larr; Voltar ao Painel</a></div>',
        f"<h1>{e(p.default_title)}</h1>",
        f'<p><span class="badge">{e(v.status.value)}</span> <span class="badge">{e(v.format.value)}</span> <span style="font-size: 0.85rem; color: var(--text-muted);">Tema: {e(v.topic)}</span></p>'
    ]
    player = (f'<video controls preload="metadata" poster="{base}/thumbnail" src="{base}/file?output_asset_id={e(p.output_asset_id)}"><track kind="captions" srclang="pt-BR" label="Português" '
              f'src="{base}/subtitles.vtt" default></video>') if p.has_file else '<p class="bad" role="alert" style="padding: 2rem; background: var(--surface); border-radius: 8px; text-align: center;">Sem arquivo de vídeo renderizado.</p>'
    qa = "<p style='color: var(--text-muted); font-size: 0.85rem;'>Sem relatório de QA.</p>"
    if p.qa is not None:
        rows = "".join(f"<tr><th scope='row'>{e(k)}</th><td>{e(val)}</td></tr>" for k, val in sorted(p.qa.metrics.items()))
        fails = "".join(f"<li>{e(f)}</li>" for f in p.qa.failures)
        qa = (f'<p class="{"ok" if p.qa.passed else "bad"}" style="font-weight: 600; font-size: 0.9rem;">QA {"aprovado" if p.qa.passed else "REPROVADO"}</p>'
              f"{f'<ul style=\"color: var(--bad); margin: 0.35rem 0;\">{fails}</ul>' if fails else ''}<table><caption class='hint' style='display:none;'>Métricas medidas</caption>{rows}</table>")
    scenes = "".join(f"<li>{('<strong>' + e(s.label) + '</strong> ') if s.label else ''}{e(s.narration)}</li>" for s in p.scenes)
    sources = "".join(f'<li><a href="{e(u)}" rel="noopener noreferrer" target="_blank">{e(u)}</a></li>' for u in p.sources if u.startswith(("https://", "http://")))
    credits = "".join(f"<li>{e(c)}</li>" for c in p.credits)
    side = [
        f"<div class='card-panel'><h2>Qualidade (QA)</h2>{qa}</div>",
        f"<div class='card-panel' style='margin-top: 1rem;'><h2>Roteiro narrado</h2><ol>{scenes}</ol></div>",
        f"<div class='card-panel' style='margin-top: 1rem;'><h2>Fontes</h2><ul>{sources or '<li>Nenhuma registrada.</li>'}</ul></div>"
    ]
    if credits:
        side.append(f"<div class='card-panel' style='margin-top: 1rem;'><h2>Créditos de imagem</h2><ul>{credits}</ul></div>")
    review = ""
    if reviewable:
        override = ""
        if qa_failed:
            override = ('<label for="override_reason">O QA reprovou. Para aprovar mesmo assim, explique o motivo '
                        '<span class="hint">(obrigatório e fica registrado)</span></label><textarea id="override_reason" rows="2" maxlength="500"></textarea>')
        review = (f"<div class='card-panel' style='margin-top: 1rem;'><h2>Decisão de Aprovação</h2><form id=\"review\" data-base=\"{base}\" data-output-asset-id=\"{e(p.output_asset_id or '')}\" onsubmit=\"return false\">"
                  f'<label for="title">Título <span class="hint">(até 100 caracteres, sem &lt; ou &gt;)</span></label>'
                  f'<input id="title" maxlength="100" value="{e(p.default_title)}">'
                  f'<label for="description">Descrição <span class="hint">(créditos, fontes e aviso de IA são acrescentados na publicação)</span></label>'
                  f'<textarea id="description" rows="5" maxlength="4000">{e(p.default_description)}</textarea>'
                  f'<label for="tags">Tags <span class="hint">(separadas por vírgula, até 15)</span></label><input id="tags" value="{e(", ".join(v.tags))}">'
                  f'<label for="publish_at">Agendar publicação <span class="hint">(opcional; o vídeo sobe privado e o YouTube publica no horário; '
                  f'mínimo 15 minutos à frente)</span></label><input id="publish_at" type="datetime-local">'
                  f'{override}<div style="margin-top: 0.5rem;"><button type="button" id="approve">Aprovar Vídeo</button></div>'
                  f'<label for="reject_reason" style="margin-top: 1.25rem;">Motivo da rejeição <span class="hint">(opcional)</span></label><textarea id="reject_reason" rows="2" maxlength="500"></textarea>'
                  f'<div><button type="button" id="reject">Rejeitar</button></div><output id="result" role="status" aria-live="polite" style="display: block; margin-top: 0.75rem; font-weight: 600; font-size: 0.85rem;"></output></form>'
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
        review = f"<div class='card-panel' style='margin-top: 1rem;'><h2>Decisão</h2>{who or '<p>Este vídeo não está em revisão.</p>'}</div>"
    doc = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
           f"<title>Prévia: {e(p.default_title)}</title><style nonce=\"{nonce}\">{CSS}</style></head><body><main><header>{''.join(header_parts)}</header>"
           f'<div class="layout"><section aria-label="Vídeo">{player}</section><section aria-label="Detalhes">{"".join(side)}{review}</section></div></main></body></html>')
    headers = {"Content-Security-Policy": f"default-src 'none'; media-src 'self'; img-src 'self'; style-src 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; script-src 'nonce-{nonce}'; "
                                          "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
               "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    return doc, headers
