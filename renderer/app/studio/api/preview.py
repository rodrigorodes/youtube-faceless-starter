"""Página de prévia e aprovação. HTML estático e sem dependências; todo texto vem escapado e a CSP só libera o script/estilo desta página.

A página usa a **casca compartilhada** (`api.panel.render_sidebar`): a navegação lateral e o
design system têm uma única fonte de verdade. Nada de paleta, `.sidebar` ou `.nav-menu` aqui.
"""
import html
import secrets

from . import approval_form
from . import panel as shell
from . import shell_v3
from ..application.publishing import Preview

e = lambda value: html.escape(str(value), quote=True)  # noqa: E731


def render_preview(p: Preview, *, video_channel: str = "") -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    v = p.video
    base = f"/studio/videos/{v.id}"
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
    review = approval_form.render_approval_decision(p, base=base)

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
        page_js=approval_form.APPROVAL_JS,
        video_channel=video_channel,
    )
    headers = {"Content-Security-Policy": f"default-src 'none'; media-src 'self'; img-src 'self'; style-src 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; script-src 'nonce-{nonce}'; "
                                          "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
               "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    return doc, headers
