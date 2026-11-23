"""Página do Roteiro — S5. Casca visual em `panel_shell`."""
import secrets

from ..application.script_view import ScriptPageView

from .panel_shell import _duration_text, _headers, e


def _fact_check_text(fact_check) -> str:
    if fact_check is None:
        return "sem fact-check"
    if not fact_check.current:
        return f"desatualizado (cobre a versão {fact_check.script_version})"
    if fact_check.passed:
        return "aprovado" + (" (override)" if fact_check.overridden else "")
    return "reprovado"


def render_script(view: ScriptPageView, *, video_channel: str = "") -> tuple[str, dict[str, str]]:
    """Página do Roteiro (mockup #roteiro) com dado real ou estado vazio explícito."""
    nonce = secrets.token_urlsafe(16)

    if not view.has_script:
        body_html = (
            '<article class="card empty" id="roteiro-vazio">'
            '<h2>Nenhum roteiro registrado para este vídeo</h2>'
            '<p class="section-sub">Gere um roteiro longo para ver capítulos, duração estimada e aprovação por versão.</p>'
            '</article>'
        )
        rail_html = (
            '<section class="card" aria-labelledby="h-duracao"><h2 id="h-duracao">Duração</h2>'
            '<p class="fine">Sem roteiro não há estimativa de duração. A duração real só existe depois do TTS.</p></section>'
        )
        approve_button = ""
    else:
        duration = _duration_text(view.estimated_seconds)
        chapter_items = "".join(
            f'<div class="kv"><span>{chapter.index + 1}. {e(chapter.title)} — {e(chapter.block_label)} · '
            f'{chapter.scene_count} cena(s)</span><span>{e(_duration_text(chapter.estimated_seconds))}</span></div>'
            for chapter in view.chapters
        )
        if not chapter_items:
            chapter_items = '<p class="empty">Capítulos não registrados para esta versão.</p>'

        badge = (
            '<span class="state s-done"><span class="state-icon" aria-hidden="true">✓</span> Versão aprovada</span>'
            if view.approved else
            '<span class="state s-act"><span class="state-icon" aria-hidden="true">!</span> Aguardando sua aprovação</span>'
        )
        fact_text = _fact_check_text(view.fact_check)
        hash_of_latest = next((v.content_hash for v in view.versions if v.current and v.content_hash), None)
        version_no = view.version or 0
        if view.approved:
            approve_button = (
                f'<button type="button" class="btn btn-primary" id="btn-approve-script" disabled '
                f'aria-disabled="true">Versão {version_no} aprovada</button>'
            )
        else:
            approve_button = (
                f'<button type="button" class="btn btn-primary" id="btn-approve-script" '
                f'data-video-id="{e(view.video_id)}" data-version="{version_no}" '
                f'data-hash="{e(hash_of_latest or "")}">Aprovar versão {version_no}</button>'
            )

        body_html = f"""
          <section class="card" aria-labelledby="roteiro-versao">
            <div class="spread">
              <div>
                <h2 id="roteiro-versao">Versão {version_no} · {e(duration)} estimados</h2>
                <p class="section-sub" style="margin:0">{view.chapter_count} capítulos · {view.scene_count} cenas · fact-check {e(fact_text)}</p>
              </div>
              {badge}
            </div>
            <div class="list" style="margin-top:12px">{chapter_items}</div>
            <div class="spread" style="margin-top:16px">
              <p class="fine" style="margin:0">Aprovar congela esta versão (<code>script_v{version_no}</code>). Editar cria a v{version_no + 1} e invalida só o que depende dela.</p>
              <div class="row">
                <a class="btn" href="/studio/panel/videos/{e(view.video_id)}/cenas">Editar cenas</a>
                {approve_button}
              </div>
            </div>
          </section>
          <details class="advanced" id="roteiro-versoes">
            <summary class="advanced-summary">Avançado — versões e fact-check</summary>
            <div class="advanced-body">
              {"".join(_version_row(v) for v in view.versions)}
              <p class="fine">Cada claim aponta para o snapshot da fonte que o sustenta.</p>
            </div>
          </details>
          <div id="approve-feedback" class="form-feedback" role="status"></div>
        """

        review_html = ""
        if view.review is not None:
            review_html = f"""
              <section class="card" aria-labelledby="h-revisao">
                <h2 id="h-revisao">Revisão do roteiro</h2>
                <div class="kv"><span>Estrutura (gancho→fechamento)</span><span>{_mark(view.review.structure_ok)}</span></div>
                <div class="kv"><span>Continuidade dos capítulos</span><span>{_mark(view.review.continuity_ok)}</span></div>
                <div class="kv"><span>Duração dentro do alvo</span><span>{_mark(view.review.duration_ok)}</span></div>
                <div class="kv"><span>Cenas redundantes</span><span>{view.review.redundant_count}</span></div>
                <div class="kv"><span>Cenas sem citação</span><span>{view.review.uncited_count}</span></div>
                <div class="kv"><span>Itens sem lastro nas fontes</span><span>{view.review.invented_count}</span></div>
              </section>
            """
        rail_html = f"""
          <section class="card" aria-labelledby="h-duracao">
            <h2 id="h-duracao">Duração</h2>
            <div class="kv"><span>Alvo</span><span>{e(f"{int(round(view.target_seconds))} s") if view.target_seconds else "não definido"}</span></div>
            <div class="kv"><span>Estimado</span><span>{e(duration) or "sem estimativa"}</span></div>
            <p class="fine">Estimativa por palavras/minuto. A duração real só existe depois do TTS — por isso a página não promete “exato”.</p>
          </section>
          {review_html}
        """

    side_card_html = (
        '<div class="side-card"><h2>Decisão de roteiro</h2>'
        '<p>A aprovação fica presa a uma versão: editar o roteiro cria outra, e a versão aprovada '
        'passa a constar como superada.</p></div>'
    )

    from . import shell_v3

    content_page = f"""      <section class="pagina" id="pagina-roteiro" aria-labelledby="roteiro-heading">
        <p class="crumb" style="margin:0 0 10px"><a href="/studio/panel/videos/{e(view.video_id)}">← Voltar ao vídeo</a> /
          <span>Roteiro</span></p>
        <div class="cab-video">
          <div>
            <p class="eyebrow">ROTEIRO DO VÍDEO</p>
            <h1 class="h1" id="roteiro-heading">Roteiro — {e(view.topic)}</h1>
            <p class="lead">Aprovação fica presa a uma versão; editar cria outra.</p>
          </div>
        </div>

        <div class="grade-video">
          <div>
            {body_html}
          </div>
          <div>
            {rail_html}
          </div>
        </div>
      </section>"""

    page_js = f"""
    const approveBtn = document.getElementById('btn-approve-script');
    if (approveBtn && !approveBtn.disabled) {{
      approveBtn.addEventListener('click', async () => {{
        const feedback = document.getElementById('approve-feedback');
        approveBtn.disabled = true;
        feedback.textContent = 'Registrando aprovação...';
        try {{
          const res = await fetch('/studio/videos/' + approveBtn.dataset.videoId + '/script/approve', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ version: Number(approveBtn.dataset.version), content_hash: approveBtn.dataset.hash }})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            feedback.textContent = 'Versão aprovada. Atualizando...';
            setTimeout(() => location.reload(), 800);
          }} else {{
            approveBtn.disabled = false;
            feedback.textContent = typeof data.detail === 'string' ? data.detail : 'Não foi possível aprovar a versão.';
          }}
        }} catch (err) {{
          approveBtn.disabled = false;
          feedback.textContent = 'Falha de rede: ' + err.message;
        }}
      }});
    }}
    """

    html_content = shell_v3.render_document(
        title="Faceless Studio — Roteiro",
        active="videos",
        crumb="Vídeos / Roteiro",
        body_html=content_page,
        nonce=nonce,
        projects=[],
        project_id="",
        cost_note="",
        page_js=page_js,
        video_channel=video_channel,
    )
    return html_content, _headers(nonce)


def _mark(ok: bool) -> str:
    return "✓ sem problema" if ok else "× atenção"


def _version_row(version) -> str:
    if version.current:
        label = f'atual · hash <code>{e(version.hash_short or "")}</code>'
    elif version.approved:
        label = "aprovada (superada)"
    elif version.rejected:
        label = "rejeitada"
    elif version.superseded:
        label = "substituída"
    else:
        label = "sem decisão"
    return f'<div class="kv"><span>script_v{version.version}</span><span>{label}</span></div>'
