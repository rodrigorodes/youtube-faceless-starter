"""Página de prévia e aprovação. HTML estático e sem dependências; todo texto vem escapado e a CSP só libera o script/estilo desta página.

A página usa a **casca compartilhada** (`api.panel.render_sidebar`): a navegação lateral e o
design system têm uma única fonte de verdade. Nada de paleta, `.sidebar` ou `.nav-menu` aqui.
"""
import html
import secrets

from . import approval_form
from . import panel as shell
from . import shell_v3
from .panel_video_nav import area_href, video_area_nav
from ..application.publishing import Preview
from ..domain.contracts import VideoStatus

e = lambda value: html.escape(str(value), quote=True)  # noqa: E731


# Rótulo e tom do estado no vocabulário do produto (o enum cru nunca aparece na tela).
_ESTADO = {
    VideoStatus.IDEA: ("Rascunho", "accent"), VideoStatus.SCRIPTED: ("Em produção", "accent"),
    VideoStatus.FACT_CHECKED: ("Em produção", "accent"), VideoStatus.STORYBOARDED: ("Em produção", "accent"),
    VideoStatus.ASSETS_READY: ("Em produção", "accent"), VideoStatus.RENDERED: ("Renderizado", "accent"),
    VideoStatus.AWAITING_APPROVAL: ("Aguardando aprovação", "warn"), VideoStatus.APPROVED: ("Aprovado", "ok"),
    VideoStatus.PUBLISHED: ("Publicado", "ok"), VideoStatus.REJECTED: ("Rejeitado", "bad"),
    VideoStatus.FAILED: ("Falhou na produção", "bad"),
}
_KIND = {"FATO": "Fato", "OPINIAO": "Opinião", "OPINION": "Opinião", "TRANSICAO": "Transição"}


def render_preview(p: Preview, *, video_channel: str = "", projects=(), project_id: str = "",
                   ) -> tuple[str, dict[str, str]]:
    """Prévia e aprovação no padrão do workspace do vídeo (`pgVideo` do protótipo v4/v3):
    cabeçalho com voltar + caminho, pills de estado, abas de área e `.two` com cartões `.card`."""
    nonce = secrets.token_urlsafe(16)
    v = p.video
    base = f"/studio/videos/{v.id}"
    short = v.format.value == "short"
    if p.has_file:
        player = (
            f'<div class="frame {"r916" if short else "r169"}" style="max-width:{"230px" if short else "560px"}">'
            f'<video controls preload="metadata" poster="{base}/thumbnail" '
            f'src="{base}/file?output_asset_id={e(p.output_asset_id)}" '
            'style="width:100%;height:100%;object-fit:contain;display:block;background:#000">'
            f'<track kind="captions" srclang="pt-BR" label="Português" src="{base}/subtitles.vtt" default></video></div>')
    else:
        player = '<p class="sub" role="alert">Sem arquivo de vídeo renderizado.</p>'

    qa = '<p class="sub">Sem relatório de QA.</p>'
    if p.qa is not None:
        counts = p.qa.severity_counts
        selo = ('<span class="pill ok">✓ QA aprovado</span>' if p.qa.is_publishable
                else '<span class="pill bad">✕ QA reprovado</span>')
        findings = "".join(
            f'<p class="sub" style="margin-top:8px">{e(f.check_id)} · {e(f.evidence)} '
            f'<span class="pill {"bad" if f.severity == "blocking" else "warn"}">{e(f.severity)}</span></p>'
            for f in p.qa.findings)
        resumo = (f"{counts['blocking']} bloqueante(s), {counts['warning']} aviso(s), {counts['info']} "
                  f"informativo(s) · cobertura {e(p.qa.coverage.status)}")
        qa = f'<div class="row">{selo}</div>{findings}<p class="sample" style="margin-top:8px">{resumo}</p>'

    scenes = "".join(
        '<div class="step"><span class="ic">' + str(i + 1) + '</span><div style="flex:1">'
        + (f'<b>{e(_KIND.get(s.label.upper(), s.label))}</b>' if s.label else f'<b>Cena {i + 1}</b>')
        + f'<p class="sub">{e(s.narration)}</p></div></div>'
        for i, s in enumerate(p.scenes)) or '<p class="sub">Nenhuma cena registrada.</p>'
    sources = "".join(f'<li><a href="{e(u)}" rel="noopener noreferrer" target="_blank">{e(u)}</a></li>'
                      for u in p.sources if u.startswith(("https://", "http://")))
    credits = "".join(f"<li>{e(c)}</li>" for c in p.credits)

    aside = [
        f'<div class="card"><h3>Qualidade (QA)</h3><div style="margin-top:8px">{qa}</div></div>',
        f'<div class="card"><h3>Roteiro narrado</h3><div style="margin-top:8px">{scenes}</div></div>',
        '<div class="card"><h3>Fontes</h3><ul style="margin:8px 0 0;padding-left:18px">'
        f'{sources or "<li>Nenhuma registrada.</li>"}</ul></div>',
    ]
    if credits:
        aside.append(f'<div class="card"><h3>Créditos de imagem</h3><ul style="margin:8px 0 0;padding-left:18px">'
                     f'{credits}</ul></div>')
    review = approval_form.render_approval_decision(p, base=base, bare=True)

    label, tone = _ESTADO.get(v.status, (v.status.value, ""))
    caminho = f"{e(video_channel)} / {e(p.default_title)}" if video_channel else e(p.default_title)
    body_html = f"""      <section class="pagina" id="pagina-previa" aria-labelledby="previa-heading">
        <p class="sub" style="margin-bottom:8px"><a class="btn ghost small" href="/studio/panel/videos">← Vídeos</a> &nbsp; {caminho}</p>
        <div class="head"><div><p class="eyebrow">Prévia e aprovação</p><h1 id="previa-heading">{e(p.default_title)}</h1>
          <div class="row" style="margin-top:6px"><span class="pill {tone}">{e(label)}</span>
            <span class="pill">{"Short 9:16" if short else "Vídeo 16:9"}</span></div>
          <p class="sub" style="margin-top:6px">Tema: {e(v.topic)}</p></div>
          <a class="btn ghost small" href="{area_href(v.id, "qualidade")}">← Voltar à Qualidade &amp; Aprovação</a></div>
        {video_area_nav(v.id, "")}
        <div class="two">
          <div class="stack">
            <div class="card card-preview-destaque"><h3 style="margin-bottom:10px">Prévia da versão</h3>{player}</div>
            <div class="card"><h3>Decisão de aprovação</h3><div style="margin-top:10px">{review}</div></div>
          </div>
          <aside class="stack">{"".join(aside)}</aside>
        </div>
      </section>"""

    doc = shell_v3.render_document(
        title=f"Faceless Studio — Prévia: {p.default_title}",
        active="videos",
        crumb=f"{video_channel} / {p.default_title}" if video_channel else "Vídeos / Prévia",
        body_html=body_html,
        nonce=nonce,
        projects=list(projects),
        project_id=project_id,
        cost_note="",
        page_js=approval_form.APPROVAL_JS,
        video_channel=video_channel,
    )
    headers = {"Content-Security-Policy": f"default-src 'none'; media-src 'self'; img-src 'self'; style-src 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; script-src 'nonce-{nonce}'; "
                                          "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
               "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    return doc, headers
