"""Página de detalhe do vídeo (legado) e cartões Fontes/Execução — S5.

`render_video` monta a página do vídeo. `panel_video_workspace` reusa os cartões
`_video_sources_card`, `_video_run_card` e `_RUN_STATE_LABELS` via reexport em `panel.py`.
Casca visual em `panel_shell`.
"""
import secrets

from ..application.panel import CostKind, VideoDetailView, cost_kind
from ..domain.contracts import PublicationStatus, VideoStatus
from ..domain.panel import Stage

from .panel_shell import STAGE_LABELS, _cost_html, _headers, _state_badge, e
from .panel_video_nav import DEFAULT_AREA, video_area_nav


def _video_style_card(style_view) -> str:
    """Aparência do vídeo (VS-05b): herda do canal ou sobrepõe com um estilo da biblioteca.

    Deixa explícito **de quem** o vídeo herda hoje — o estilo do canal, ou nenhum. Sem a
    projeção (leitura indisponível) a seção não aparece: "o que não tem medição não aparece".
    """
    if style_view is None:
        return ""
    if style_view.inherits_from_channel:
        if style_view.inherited_style_name:
            situation = f"Este vídeo herda o estilo do canal: {style_view.inherited_style_name}."
        else:
            situation = "Este vídeo herda do canal, que não usa estilo — vale o padrão do estúdio."
    else:
        own = next((s.name for s in style_view.styles if s.id == style_view.override_style_id), None)
        inherited = style_view.inherited_style_name or "nenhum estilo no canal"
        situation = (f"Este vídeo sobrepõe o canal com {own or 'um estilo escolhido'} "
                     f"(o canal herda {inherited}).")
    inherit_label = (f"Herdar do canal ({style_view.inherited_style_name})"
                     if style_view.inherited_style_name else "Herdar do canal (nenhum estilo)")
    options = [
        f'<option value=""{" selected" if style_view.inherits_from_channel else ""}>'
        f"{e(inherit_label)}</option>"
    ]
    for style in style_view.styles:
        chosen = " selected" if style.id == style_view.override_style_id else ""
        options.append(f'<option value="{e(style.id)}"{chosen}>{e(style.name)}</option>')
    return f"""
      <div class="card painel" id="video-aparencia" style="margin-top:18px">
        <h3>Estilo deste vídeo</h3>
        <p class="muted" style="margin:4px 0 0">{e(situation)}</p>
        <form id="video-style-form" data-video-id="{e(style_view.video_id)}" style="margin-top:14px">
          <div class="campo field">
            <label for="video-estilo">Estilo visual</label>
            <select class="input campo" id="video-estilo" name="style_id" aria-describedby="video-estilo-hint">
              {''.join(options)}
            </select>
            <p class="dica hint" id="video-estilo-hint">Herdar mantém o estilo do canal; escolher um estilo aqui sobrepõe só este vídeo.</p>
          </div>
          <div class="acoes spread" style="margin-top:14px">
            <button class="btn btn-primario btn-primary" type="submit" id="btn-salvar-estilo-video">Salvar estilo</button>
            <div id="video-style-feedback" class="feedback form-feedback" role="status" aria-live="polite"></div>
          </div>
        </form>
      </div>
    """


# Rótulos das etapas de produção e dos estados do run: a página do vídeo mostra o motivo real
# sem reimplementar a execução (que vive em panel_production).
_PRODUCTION_STAGE_LABELS = {
    "research": "Fontes",
    "script": "Roteiro",
    "factcheck": "Fact-check",
    "storyboard": "Cenas",
    "assets": "Voz e imagens",
    "render": "Render",
    "qa": "QA",
    "approval": "Aprovação",
    "publish": "Publicação",
}
_RUN_STATE_LABELS = {
    "CREATED": "Criada (aguardando início)",
    "RUNNING": "Em execução",
    "WAITING_HUMAN": "Aguardando você",
    "PAUSED": "Pausada",
    "FAILED": "Falhou",
    "CANCELLED": "Cancelada",
    "SUCCEEDED": "Concluída",
}


def _video_sources_card(view: VideoDetailView) -> str:
    """Cartão Fontes: lista o que existe e registra fonte nova (texto colado ou busca na URL).

    PROD-04 (achado 3): quando o tema do vídeo casa com uma tendência do canal, o campo de URL
    já vem preenchido com o **vídeo base** — o humano só precisa colar o texto. Nada é
    registrado aqui: criar a fonte exige texto (sem texto, a busca pela URL é recusada pela
    allowlist de nicho e fonte sem texto não é evidência).
    """
    v = view.video
    if view.sources:
        items = "".join(
            f'<li><code>{e(s.url)}</code> — {s.chars} caractere{"" if s.chars == 1 else "s"}</li>'
            for s in view.sources
        )
        count_html = f'<p class="dim" style="font-size:12.5px;margin:6px 0 0">{len(view.sources)} fonte(s) registrada(s).</p>'
        list_html = f'<ul aria-label="Fontes registradas" style="margin:8px 0 0;padding-left:1.1rem">{items}</ul>'
    else:
        count_html = ""
        list_html = '<p class="empty" style="margin:8px 0 0">Nenhuma fonte registrada ainda.</p>'

    if view.base_video_url:
        url_value = f' value="{e(view.base_video_url)}"'
        origin = (f' · {e(view.base_video_source_name)}' if view.base_video_source_name else "")
        base_html = (
            '<p class="dim" style="font-size:12.5px;margin:6px 0 0">vídeo base: '
            f'<a href="{e(view.base_video_url)}" target="_blank" rel="noopener noreferrer">{e(view.base_video_url)}</a>'
            f'{origin}</p>'
        )
    else:
        url_value = ""
        base_html = ""
    return f"""
      <div class="card painel" id="video-fontes" style="margin-top:18px">
        <h3>Fontes</h3>
        <p class="muted" style="margin:4px 0 0">O roteiro só é escrito a partir de fatos das fontes. Sem fonte aproveitável, a produção para no primeiro passo.</p>
        {base_html}
        {count_html}
        {list_html}
        <form id="video-sources-form" class="campo" data-video-id="{e(v.id)}" style="margin-top:14px" novalidate>
          <div class="campo field">
            <label for="source-url">URL da fonte <span aria-hidden="true">*</span></label>
            <input type="url" id="source-url" name="url" class="input campo" required
                   data-error="source-url-error" placeholder="https://youtube.com/watch?v=..."
                   aria-describedby="source-rule"{url_value}>
            <p class="dica hint" id="source-rule">
              Com texto: o texto colado é a fonte e a URL é só referência.
              Sem texto: o servidor busca a URL, que precisa estar na lista permitida (STUDIO_SOURCE_ALLOWLIST);
              se a busca for recusada, a mensagem do servidor aparece aqui.
            </p>
            <p class="campo-erro error-msg" id="source-url-error"><span role="img" aria-label="Erro">&#9888;</span> Informe a URL da fonte.</p>
          </div>
          <div class="campo field" style="margin-top:12px">
            <label for="source-text">Texto da fonte <span class="micro">(opcional)</span></label>
            <textarea id="source-text" name="text" class="input campo" rows="4"
                      placeholder="Cole o conteúdo da página quando o site bloquear a leitura"></textarea>
          </div>
          <div class="acoes spread" style="margin-top:14px">
            <button class="btn btn-primario btn-primary" type="submit" id="btn-add-source">Adicionar fonte</button>
            <div id="video-sources-feedback" class="feedback form-feedback" role="status" aria-live="polite"></div>
          </div>
        </form>
      </div>
    """


# PROD-04 (achado 5): um run em estado terminal não impede uma produção nova — a API aceita
# `create_run` sem guarda de run ativo. Num run **vivo** (RUNNING/WAITING_HUMAN) a produção nova
# não cabe: o caminho é continuar/retomar pela execução.
_TERMINAL_RUN_STATES = ("FAILED", "CANCELLED", "SUCCEEDED")


def _new_production_button(video_id: str, *, primary: bool) -> str:
    cls = "btn btn-primary" if primary else "btn"
    return (
        f'<button class="{cls}" type="button" id="btn-new-production" '
        f'data-video-id="{e(video_id)}">Iniciar nova produção</button>'
    )


_START_OVER_HINT = (
    '<p class="dim" style="font-size:12.5px;margin:0.6rem 0 0">'
    '«Iniciar nova produção» recomeça do zero: cria um novo run e reprograma as etapas. '
    'Não é o retry desta execução.</p>'
)


def _video_run_card(view: VideoDetailView) -> str:
    """Iniciar/retomar a produção a partir do vídeo, sempre com o motivo real do servidor.

    Sem run: "Iniciar produção". Run em falha: mostra a etapa e o motivo e oferece "Tentar
    novamente" **e** "Iniciar nova produção" (run novo, não o retry da etapa). Run termina
    (SUCCEEDED/CANCELLED) também oferece "Iniciar nova produção". Com run vivo
    (RUNNING/WAITING_HUMAN) não há produção nova: o caminho é continuar pela execução — e a
    própria tela explica por quê, sem botão inerte.
    """
    v = view.video
    run = view.latest_run
    feedback = '<div id="video-run-feedback" class="form-feedback" role="status" aria-live="polite"></div>'
    if run is None:
        return f"""
          <div class="card painel" id="video-producao">
            <h3>Produção</h3>
            <p class="muted" style="margin:4px 0 0">Nenhuma produção iniciada para este vídeo.</p>
            <div class="acoes spread" style="margin-top:14px">
              <button class="btn btn-primario btn-primary" type="button" id="btn-start-production"
                      data-video-id="{e(v.id)}">Iniciar produção</button>
              {feedback}
            </div>
          </div>
        """
    exec_url = f'/studio/panel/videos/{e(v.id)}/production-runs/{e(run.run_id)}'
    if run.state == "FAILED":
        stage_label = _PRODUCTION_STAGE_LABELS.get(run.failed_stage, run.failed_stage or "etapa desconhecida")
        if run.failure_reason:
            reason_html = f'<p class="muted" style="margin:0.5rem 0 0">Motivo: <strong>{e(run.failure_reason)}</strong></p>'
        else:
            reason_html = '<p class="muted" style="margin:0.5rem 0 0">O motivo não foi registrado; abra a execução para ver o detalhe.</p>'
        return f"""
          <div class="card painel" id="video-producao">
            <span class="state s-fail" data-state="action"><span class="state-icon" aria-hidden="true">!</span> <span>Ação necessária</span></span>
            <h3 style="margin-top:0.6rem">A produção parou</h3>
            <p class="muted" style="margin:0.5rem 0 0">Parou na etapa <strong>{e(stage_label)}</strong>.</p>
            {reason_html}
            <div class="acoes-linha spread" style="margin-top:14px">
              <button class="btn btn-primario btn-primary" type="button" id="btn-retry-production"
                      data-video-id="{e(v.id)}" data-run-id="{e(run.run_id)}">Tentar novamente</button>
              {_new_production_button(v.id, primary=False)}
              <a class="btn" href="{exec_url}">Abrir execução</a>
              {feedback}
            </div>
            {_START_OVER_HINT}
          </div>
        """
    if run.state in ("SUCCEEDED", "CANCELLED"):
        state_label = _RUN_STATE_LABELS.get(run.state, run.state)
        return f"""
          <div class="card painel" id="video-producao">
            <h3>Produção</h3>
            <p class="muted" style="margin:0.5rem 0 0">A execução atual terminou: <strong>{e(state_label)}</strong>.</p>
            <div class="acoes-linha spread" style="margin-top:14px">
              {_new_production_button(v.id, primary=True)}
              <a class="btn" href="{exec_url}">Abrir execução</a>
              {feedback}
            </div>
            {_START_OVER_HINT}
          </div>
        """
    state_label = _RUN_STATE_LABELS.get(run.state, run.state)
    return f"""
      <div class="card painel" id="video-producao">
        <h3>Produção</h3>
        <p class="muted" style="margin:0.5rem 0 0">Execução atual: <strong>{e(state_label)}</strong>.</p>
        <p class="micro" style="margin:4px 0 0">Nova tentativa só é válida quando a execução está em falha; aqui o caminho é continuar pela execução.</p>
        <div class="acoes spread" style="margin-top:14px">
          <a class="btn btn-primario btn-primary" href="{exec_url}">Abrir execução</a>
          {feedback}
        </div>
      </div>
    """


def render_video(view: VideoDetailView, *, style_view=None,
                 video_channel: str = "",
                 free_providers: frozenset[str] = frozenset()) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    v = view.video

    step_state_labels = {
        "SUCCEEDED": ("done", "✓", "Concluído"),
        "FAILED": ("action", "!", "Ação necessária"),
        "RUNNING": ("running", "▶", "Em execução"),
    }

    steps_html = []
    if not view.steps:
        steps_html.append(
            '<li class="timeline-item"><div class="timeline-desc">'
            'Nenhum passo executado ainda. Sem execução registrada.</div></li>'
        )
    else:
        for step in view.steps:
            kind, icon, label = step_state_labels.get(
                step.status, ("idle", "·", "Sem execução registrada")
            )
            steps_html.append(f"""
              <li class="timeline-item">
                <div class="timeline-dot"></div>
                <div class="timeline-title">{e(step.step)} (tentativa {step.attempt})</div>
                <div class="timeline-desc">
                  <span class="state s-{kind}" data-state="{kind}">
                    <span class="state-icon" aria-hidden="true">{icon}</span> <span>{label}</span>
                  </span>
                  <span style="margin-left: 0.4rem;">{step.started_at.strftime("%d/%m %H:%M:%S")}</span>
                </div>
              </li>
            """)

    usage_html = []
    if not view.usage:
        usage_html.append('<tr><td colspan="4" class="empty">Sem registro de uso de IA para este vídeo.</td></tr>')
    else:
        for usage in view.usage:
            kind = cost_kind(usage.cost_confirmation_kind, usage.provider, usage.model,
                             usage.cost_usd, free_providers)
            if kind is CostKind.REAL:
                cost_str = f"Real: US$ {usage.cost_usd:.2f}".replace(".", ",")
            elif kind is CostKind.ESTIMATE:
                cost_str = f"Estimado: US$ {usage.cost_usd:.2f}".replace(".", ",")
            elif kind is CostKind.FREE:
                cost_str = "Sem custo"
            else:
                cost_str = '<span style="color: var(--warn);">Desconhecido</span>'
            usage_html.append(f"""
              <tr>
                <td>{e(usage.step)}</td>
                <td>{e(usage.provider)}</td>
                <td>{e(usage.model)}</td>
                <td>{cost_str}</td>
              </tr>
            """)

    failed_steps = [step for step in view.steps if step.status == "FAILED"]
    has_render_failure = bool(view.render_error or failed_steps)
    has_publication_failure = bool(
        view.publication and view.publication.status == PublicationStatus.FAILED
    )

    failure_paragraphs = []
    retry_buttons = []
    if has_render_failure:
        failed_step_name = failed_steps[-1].step if failed_steps else "render"
        failure_paragraphs.append(f"<p><strong>Falha na etapa {e(failed_step_name)}.</strong></p>")
        failure_paragraphs.append(
            f"<p>Passo de correção: revise a etapa {e(failed_step_name)} e reexecute a produção.</p>"
        )
        if view.render_error and v.status == VideoStatus.ASSETS_READY:
            retry_buttons.append(
                f'<button type="button" class="btn btn-primary btn-compact" '
                f'id="btn-retry-render" data-video-id="{e(v.id)}">Tentar render novamente</button>'
            )
        else:
            failure_paragraphs.append(
                "<p>Nova tentativa de render só é válida quando o vídeo está pronto para renderizar. "
                "Corrija o passo no painel para voltar a esse estado.</p>"
            )
    if has_publication_failure:
        failure_paragraphs.append("<p><strong>Falha na publicação.</strong></p>")
        failure_paragraphs.append(
            "<p>Passo de correção: confira os dados da publicação e tente novamente.</p>"
        )
        retry_buttons.append(
            f'<button type="button" class="btn btn-primary btn-compact" '
            f'id="btn-retry-publication" data-video-id="{e(v.id)}">Tentar publicar novamente</button>'
        )

    failure_html = ""
    if failure_paragraphs:
        actions = (
            f'<div class="form-actions" style="margin-top: 0.6rem;">{"".join(retry_buttons)}</div>'
            if retry_buttons else ""
        )
        failure_html = f'<div class="failure-summary">{"".join(failure_paragraphs)}{actions}</div>'

    publication_summary_html = ""
    if view.publication:
        publication_summary_html = f"""
          <div class="section-block" style="margin-top: 1rem;">
            <h3>Publicação</h3>
            <p>Status: <span class="pill pill-{e(view.publication.status.value)}">{e(view.publication.status.value)}</span>
            (tentativa {view.publication.attempt})</p>
          </div>
        """

    render_err_html = (
        f'<div class="warning"><strong>Erro de renderização (bruto):</strong> '
        f'<code>{e(view.render_error)}</code></div>'
        if view.render_error else ""
    )
    step_errors_html = "".join(
        f'<div class="warning"><strong>Passo {e(step.step)} (tentativa {step.attempt}) — erro bruto:</strong> '
        f'<code>{e(step.error_message)}</code></div>'
        for step in view.steps
        if step.error_message
    )
    pub_err_html = ""
    if view.publication and view.publication.error:
        pub_err_html = (
            f'<div class="warning"><strong>Publicação (erro bruto):</strong> '
            f'<code>{e(view.publication.error)}</code></div>'
        )

    preview_nav_html = ""
    preview_stages = (Stage.AWAITING_APPROVAL, Stage.APPROVED, Stage.COMPLETED)
    if view.stage in preview_stages:
        preview_nav_html = f"""
          <li>
            <a class="nav-item" href="/studio/videos/{e(v.id)}/preview">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
              <span>Ver Prévia</span>
            </a>
          </li>
        """
    else:
        preview_nav_html = """
          <li>
            <span class="nav-item nav-item-unavailable" aria-disabled="true" tabindex="-1">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
              <span>Prévia após render</span><span class="nav-tag">indisponível</span>
            </span>
          </li>
        """

    if view.stage == Stage.AWAITING_APPROVAL:
        header_action_html = (
            f'<a class="btn btn-primary" href="/studio/videos/{e(v.id)}/preview">Abrir Prévia e Aprovar</a>'
        )
    elif view.stage in (Stage.APPROVED, Stage.COMPLETED):
        header_action_html = (
            f'<a class="btn btn-primary" href="/studio/videos/{e(v.id)}/preview">Abrir Prévia</a>'
        )
    else:
        header_action_html = (
            '<span class="section-sub" style="margin: 0;">Prévia e aprovação ficam disponíveis após a renderização.</span>'
        )

    # A casca aprovada exige o card lateral. A view do detalhe não traz orçamento do mês:
    # nada é inventado — o card só repete onde fica o diagnóstico técnico.
    side_card_html = (
        '<div class="side-card">'
        '<h2>Diagnóstico</h2>'
        '<p>ID, erros brutos e uso de modelos ficam em Avançado — diagnóstico.</p>'
        '</div>'
    )
    style_card_html = _video_style_card(style_view)
    sources_card_html = _video_sources_card(view)
    run_card_html = _video_run_card(view)

    from . import shell_v3

    body_html = f"""      <section class="pagina" id="pagina-video" aria-labelledby="detalhe-heading">
        <p class="crumb" style="margin:0 0 10px"><a href="/studio/panel/videos">← Vídeos</a> /
          <span id="video-situacao">{e(STAGE_LABELS.get(view.stage, view.stage.value))}</span></p>
        <div class="cab-video">
          <div>
            <p class="eyebrow">ESPAÇO DO VÍDEO</p>
            <h1 class="h1" id="detalhe-heading">{e(v.topic)}</h1>
            <p class="lead" id="video-resumo" style="margin-top: 0.25rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
              {_state_badge(view.stage)}
              <span class="pill pill-{e(view.stage.value)}">{e(STAGE_LABELS.get(view.stage, view.stage.value))}</span>
              <span style="font-size: 0.85rem; color: var(--text-muted);">Custo do vídeo: {_cost_html(view.cost_text)}</span>
            </p>
          </div>
          <div class="pilha" id="video-acoes">{header_action_html}</div>
        </div>

        {video_area_nav(v.id, DEFAULT_AREA)}

        <div class="grade-video">
          <div>
            <div class="player">
              <p style="margin:0;font-size:15px;font-weight:700">Prévia do corte final</p>
              <p class="micro" style="margin:0;color:inherit">Acompanhe a produção e assista ao corte renderizado.</p>
            </div>

            <div class="card painel" style="margin-top:18px">
              <h2>Linha do Tempo dos Passos</h2>
              <ul class="timeline">
                {''.join(steps_html)}
              </ul>
              {failure_html}
              {publication_summary_html}
            </div>

            {run_card_html}
            {sources_card_html}
            {style_card_html}

            <details class="card painel advanced" id="advanced-diagnostics" style="margin-top:18px">
              <summary class="advanced-summary" style="cursor:pointer;font-weight:700">Avançado — diagnóstico</summary>
              <div class="advanced-body">
                <p>ID do vídeo: <code>{e(v.id)}</code></p>
                <div>
                  <h3>Registro de Uso de Modelos</h3>
                  <p class="cost-note">Cada chamada vem rotulada: “Real”, “Estimado”, “Sem custo” ou “Desconhecido”. Real e estimado nunca são fundidos.</p>
                  <table class="tabela-kv">
                    <thead>
                      <tr>
                        <th scope="col">Passo</th>
                        <th scope="col">Provedor</th>
                        <th scope="col">Modelo</th>
                        <th scope="col">Custo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {''.join(usage_html)}
                    </tbody>
                  </table>
                </div>
                {render_err_html}
                {step_errors_html}
                {pub_err_html}
              </div>
            </details>
          </div>

          <div>
            <div class="card painel">
              <h2>Neste vídeo</h2>
              <nav class="nav-menu" aria-label="Navegação do vídeo">
                <ul class="nav-list">
                  <li>
                    <a class="nav-item" href="/studio/videos/{e(v.id)}/roteiro">
                      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 4h16v16H4z"></path><line x1="8" y1="9" x2="16" y2="9"></line><line x1="8" y1="13" x2="14" y2="13"></line></svg>
                      <span>Roteiro</span>
                    </a>
                  </li>
                  {preview_nav_html}
                </ul>
              </nav>
            </div>

            <div class="card painel" style="margin-top:18px">
              <h2>Detalhes do vídeo</h2>
              <table class="tabela-kv">
                <caption class="sr-only">Detalhes do vídeo</caption>
                <tr><th scope="row">Situação</th><td><span class="pill pill-{e(view.stage.value)}">{e(STAGE_LABELS.get(view.stage, view.stage.value))}</span></td></tr>
                <tr><th scope="row">Custo total</th><td>{_cost_html(view.cost_text)}</td></tr>
              </table>
            </div>
          </div>
        </div>
      </section>"""

    page_js = f"""
    function wireRetry(buttonId, url) {{
      const button = document.getElementById(buttonId);
      if (!button) return;
      button.addEventListener('click', async () => {{
        button.disabled = true;
        const original = button.textContent;
        button.textContent = 'Enviando...';
        try {{
          const response = await fetch(url, {{ method: 'POST' }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok) {{
            button.textContent = 'Solicitado. Atualizando...';
            setTimeout(() => location.reload(), 800);
          }} else {{
            button.disabled = false;
            button.textContent = original;
            const message = typeof data.detail === 'string' ? data.detail : 'Não foi possível repetir a operação.';
            window.alert(message);
          }}
        }} catch (error) {{
          button.disabled = false;
          button.textContent = original;
          window.alert('Falha de rede: ' + error.message);
        }}
      }});
    }}
    wireRetry('btn-retry-render', '/studio/videos/{e(v.id)}/resume');
    wireRetry('btn-retry-publication', '/studio/videos/{e(v.id)}/publication/retry');

    const styleForm = document.getElementById('video-style-form');
    if (styleForm) {{
      styleForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const feedback = document.getElementById('video-style-feedback');
        const button = document.getElementById('btn-salvar-estilo-video');
        const select = document.getElementById('video-estilo');
        const videoId = styleForm.getAttribute('data-video-id') || '';
        const value = select ? select.value : '';
        if (button) {{ button.disabled = true; button.classList.add('carregando'); }}
        if (window.StudioLoading) window.StudioLoading.start();
        if (feedback) feedback.textContent = 'Salvando estilo...';
        try {{
          const response = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/style', {{
            method: 'PATCH',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ style_id: value || null }})
          }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok) {{
            if (feedback) feedback.textContent = 'Estilo salvo. Atualizando...';
            setTimeout(() => location.reload(), 500);
          }} else if (response.status === 404) {{
            if (feedback) feedback.textContent = 'Não foi possível salvar: o vídeo não foi encontrado.';
            if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
            if (window.StudioLoading) window.StudioLoading.done();
          }} else {{
            if (feedback) feedback.textContent = 'Não foi possível salvar o estilo: '
              + (typeof data.detail === 'string' ? data.detail : 'verifique o estilo e tente novamente.');
            if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
            if (window.StudioLoading) window.StudioLoading.done();
          }}
        }} catch (error) {{
          if (feedback) feedback.textContent = 'Falha de rede ao salvar o estilo. Tente novamente.';
          if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
          if (window.StudioLoading) window.StudioLoading.done();
        }}
      }});
    }}

    const sourcesForm = document.getElementById('video-sources-form');
    if (sourcesForm) {{
      sourcesForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const feedback = document.getElementById('video-sources-feedback');
        const button = document.getElementById('btn-add-source');
        const videoId = sourcesForm.getAttribute('data-video-id') || '';
        const urlInput = document.getElementById('source-url');
        const textInput = document.getElementById('source-text');
        const url = urlInput ? urlInput.value.trim() : '';
        const text = textInput ? textInput.value : '';
        if (!url) {{ feedback.textContent = 'Informe a URL da fonte.'; return; }}
        if (button) {{ button.disabled = true; button.classList.add('carregando'); }}
        if (window.StudioLoading) window.StudioLoading.start();
        feedback.textContent = 'Registrando a fonte...';
        try {{
          const payload = {{ url: url }};
          if (text.trim()) payload.text = text;
          const response = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/sources', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload)
          }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok) {{
            feedback.textContent = 'Fonte registrada. Atualizando...';
            setTimeout(() => location.reload(), 600);
          }} else {{
            feedback.textContent = 'Não foi possível registrar a fonte: '
              + (typeof data.detail === 'string' ? data.detail : 'verifique a URL e tente novamente.');
            if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
            if (window.StudioLoading) window.StudioLoading.done();
          }}
        }} catch (error) {{
          feedback.textContent = 'Falha de rede ao registrar a fonte. Tente novamente.';
          if (button) {{ button.disabled = false; button.classList.remove('carregando'); }}
          if (window.StudioLoading) window.StudioLoading.done();
        }}
      }});
    }}

    const runFeedback = document.getElementById('video-run-feedback');
    document.querySelectorAll('#btn-start-production, #btn-new-production').forEach((startBtn) => {{
      startBtn.addEventListener('click', async () => {{
        const videoId = startBtn.getAttribute('data-video-id') || '';
        startBtn.disabled = true;
        startBtn.classList.add('carregando');
        if (window.StudioLoading) window.StudioLoading.start();
        if (runFeedback) runFeedback.textContent = 'Iniciando a produção...';
        try {{
          const key = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
          const response = await fetch('/studio/videos/' + encodeURIComponent(videoId) + '/production-runs', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'Idempotency-Key': key }},
            body: JSON.stringify({{}})
          }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok && data.run_id) {{
            if (runFeedback) runFeedback.textContent = 'Produção iniciada. Abrindo a execução...';
            location.href = '/studio/panel/videos/' + encodeURIComponent(videoId) +
              '/production-runs/' + encodeURIComponent(data.run_id);
          }} else {{
            if (runFeedback) runFeedback.textContent = 'Não foi possível iniciar: '
              + (typeof data.detail === 'string' ? data.detail : 'resposta inválida do servidor.');
            startBtn.disabled = false;
            startBtn.classList.remove('carregando');
            if (window.StudioLoading) window.StudioLoading.done();
          }}
        }} catch (error) {{
          if (runFeedback) runFeedback.textContent = 'Falha de rede ao iniciar a produção. Tente novamente.';
          startBtn.disabled = false;
          startBtn.classList.remove('carregando');
          if (window.StudioLoading) window.StudioLoading.done();
        }}
      }});
    }});
    const retryProductionBtn = document.getElementById('btn-retry-production');
    if (retryProductionBtn) {{
      retryProductionBtn.addEventListener('click', async () => {{
        const videoId = retryProductionBtn.getAttribute('data-video-id') || '';
        const runId = retryProductionBtn.getAttribute('data-run-id') || '';
        retryProductionBtn.disabled = true;
        retryProductionBtn.classList.add('carregando');
        if (window.StudioLoading) window.StudioLoading.start();
        if (runFeedback) runFeedback.textContent = 'Retomando a produção...';
        try {{
          const response = await fetch('/studio/videos/' + encodeURIComponent(videoId) +
            '/production-runs/' + encodeURIComponent(runId) + '/retry', {{ method: 'POST' }});
          const data = await response.json().catch(() => ({{}}));
          if (response.ok) {{
            if (runFeedback) runFeedback.textContent = 'Produção retomada. Abrindo a execução...';
            location.href = '/studio/panel/videos/' + encodeURIComponent(videoId) +
              '/production-runs/' + encodeURIComponent(runId);
          }} else {{
            if (runFeedback) runFeedback.textContent = 'Não foi possível retomar: '
              + (typeof data.detail === 'string' ? data.detail : 'o estado atual não permite nova tentativa.');
            retryProductionBtn.disabled = false;
            retryProductionBtn.classList.remove('carregando');
            if (window.StudioLoading) window.StudioLoading.done();
          }}
        }} catch (error) {{
          if (runFeedback) runFeedback.textContent = 'Falha de rede ao retomar a produção. Tente novamente.';
          retryProductionBtn.disabled = false;
          retryProductionBtn.classList.remove('carregando');
          if (window.StudioLoading) window.StudioLoading.done();
        }}
      }});
    }}

    const flagged = new WeakSet();
    const linkError = (el, shown) => {{
      const errorId = el.dataset ? el.dataset.error : null;
      if (!errorId) return;
      const ids = (el.getAttribute('aria-describedby') || '').split(/\\s+/).filter((id) => id && id !== errorId);
      if (shown) ids.push(errorId);
      if (ids.length) el.setAttribute('aria-describedby', ids.join(' '));
      else el.removeAttribute('aria-describedby');
    }};
    const syncAria = (el) => {{
      if (!el.matches || !el.matches('input, select, textarea')) return;
      const invalid = el.matches(':user-invalid');
      if (invalid) {{
        el.setAttribute('aria-invalid', 'true');
        linkError(el, true);
        flagged.add(el);
      }} else if (flagged.has(el) || el.getAttribute('aria-invalid') !== 'true') {{
        el.setAttribute('aria-invalid', 'false');
        linkError(el, false);
        flagged.delete(el);
      }}
    }};
    document.querySelectorAll('input, select, textarea').forEach((el) => syncAria(el));
    document.addEventListener('blur', (ev) => syncAria(ev.target), true);
    document.addEventListener('input', (ev) => {{ if (ev.target.hasAttribute && ev.target.hasAttribute('aria-invalid')) syncAria(ev.target); }});
    document.addEventListener('change', (ev) => syncAria(ev.target), true);
    document.addEventListener('invalid', (ev) => syncAria(ev.target), true);
    """

    html_content = shell_v3.render_document(
        title="Faceless Studio — Detalhe do Vídeo",
        active="videos",
        crumb="Vídeos / Detalhe",
        body_html=body_html,
        nonce=nonce,
        projects=[],
        project_id="",
        cost_note="",
        page_js=page_js,
        video_channel=video_channel,
    )
    return html_content, _headers(nonce)
