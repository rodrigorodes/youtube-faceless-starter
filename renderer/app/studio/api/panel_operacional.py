"""Telas operacionais do painel (Início, Produção e Tendências) — S5.

`render_panel` (Início) delega para `panel_home.render_home` (UX V3). `render_producao` e
`render_tendencias` usam a casca única `_render_panel_page`; a casca visual (CSS, sidebar,
selos, custo, cabeçalhos) vem de `panel_shell`.
"""
import secrets
from urllib.parse import quote

from ..application.panel import PanelView
from ..domain.contracts import VideoFormat
from ..domain.panel import Stage
from .panel_video_nav import area_href

from .erro_js import ERRO_JS
from .panel_shell import (
    ACTION_STAGES,
    CSS,
    STAGE_LABELS,
    _ICON_FLAME,
    _ICON_REFRESH,
    _ICON_SLIDERS,
    _cost_html,
    _headers,
    _state_badge,
    budget_side_card,
    cost_breakdown_rows,
    e,
    render_sidebar,
)

# IA-01: uma tela por rota de servidor. Cada caminho devolve **só** o HTML da sua seção.
_PANEL_PATHS = {
    "inicio": "/studio/panel",
    "producao": "/studio/panel/producao",
    "tendencias": "/studio/panel/tendencias",
}
_PANEL_TITLES = {
    "inicio": "Faceless Studio — Painel",
    "producao": "Faceless Studio — Produção",
    "tendencias": "Faceless Studio — Tendências",
}
_PANEL_SKIP_HREFS = {
    "inicio": "#inicio-section",
    "producao": "#producao-section",
    "tendencias": "#trending-section",
}


def _render_panel_page(view: PanelView, *, mode: str = "inicio",
                       topic: str = "") -> tuple[str, dict[str, str]]:
    """Casca única das telas operacionais; `mode` decide **o que** entra em `<main>`.

    Início, Produção e Tendências compartilham a casca (sidebar, topbar, rail e o mesmo script
    guardado por presença de elemento), mas cada modo renderiza apenas as suas seções — o HTML de
    uma tela nunca aparece dentro da outra (critério de aceite da IA-01).
    """
    nonce = secrets.token_urlsafe(16)
    days = view.days
    panel_path = _PANEL_PATHS[mode]
    current_project_id = view.project_id or (view.projects[0][0] if view.projects else "")
    new_video_href = "#new-video-section" if mode == "inicio" else "/studio/panel#new-video-section"

    filters_html = "".join(
        f'<a class="filter-link {"active" if d == days else ""}" href="{panel_path}?project_id={e(current_project_id)}&days={d}">{d} dias</a>'
        if current_project_id
        else f'<a class="filter-link {"active" if d == days else ""}" href="{panel_path}?days={d}">{d} dias</a>'
        for d in (7, 14, 30)
    )

    warning_html = (
        '<div class="warning">Aviso: exibindo os 500 vídeos mais recentes do período selecionado.</div>'
        if view.truncated else ""
    )

    project_options = "".join(
        f'<option value="{e(p[0])}"{" selected" if p[0] == current_project_id else ""}>{e(p[1])}</option>'
        for p in view.projects
    )
    global_project_options = project_options
    create_form_html = f"""
      <details class="new-video-section" id="new-video-section">
        <summary class="new-video-summary">
          <div class="new-video-summary-inner">
            <div style="display: flex; align-items: center; gap: 0.6rem;">
              <span class="btn btn-primary btn-compact">+ Novo Vídeo</span>
              <span style="font-size: 0.85rem; color: var(--text-muted);">Criar vídeo a partir de tema ou tendência</span>
            </div>
            <span style="font-size: 0.8rem; color: var(--text-muted);">Clique para expandir</span>
          </div>
        </summary>
        <form id="create-video-form" class="new-video-form">
          <div class="form-grid-2">
            <div>
              <label for="new-video-project">Canal</label>
              <select id="new-video-project" name="project_id" required>
                {project_options}
              </select>
            </div>
            <div>
              <label for="new-video-format">Formato</label>
              <select id="new-video-format" name="format">
                <option value="short">Short (vertical 1080x1920)</option>
                <option value="long">Long (horizontal 1920x1080)</option>
              </select>
            </div>
          </div>
          <div>
            <label for="topic">Tema <span style="font-weight: 400; opacity: 0.75;">(3 a 300 caracteres)</span></label>
            <input type="text" id="topic" name="topic" class="new-video-topic" minlength="3" maxlength="300" placeholder="Ex: ADE Lineup 2026 Revelado" required>
          </div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary" id="btn-create-video">Criar Vídeo</button>
            <div id="create-video-feedback" class="form-feedback"></div>
          </div>
        </form>
      </details>
    """

    total_trends = len(view.trends)
    pills = [
        f'<button type="button" class="cat-pill active" data-filter-type="all" aria-pressed="true">Todas ({total_trends})</button>',
    ]
    region_labels = {"BR": "Em Alta Brasil", "US": "Em Alta EUA", "UNKNOWN": "Origem desconhecida"}
    regions = ["BR", "US"] + sorted({t.region for t in view.trends if t.region and t.region not in ("BR", "US")})
    for region in regions:
        count = sum(1 for t in view.trends if t.region == region)
        label = region_labels.get(region, f"Em Alta {region}")
        pills.append(
            f'<button type="button" class="cat-pill" data-filter-type="region" data-region-code="{e(region)}" aria-pressed="false">{e(label)} ({count})</button>'
        )
    for cat in view.categories:
        cat_count = sum(1 for t in view.trends if t.category_id == cat.id)
        pills.append(
            f'<button type="button" class="cat-pill" data-filter-type="category" data-cat-id="{e(cat.id)}" data-category-id="{e(cat.id)}" aria-pressed="false">🏷️ {e(cat.name)} ({cat_count})</button>'
        )
    pills.append('<button type="button" class="cat-pill cat-pill-btn" id="btn-open-categories-modal">+ Novo pilar</button>')
    cat_pills_html = f'<search class="cat-pills-bar" aria-label="Filtros de tendências">{"".join(pills)}</search>'

    action_buttons_html = f"""
      <div class="trends-actions">
        <button type="button" class="btn btn-compact" id="btn-refresh-trends" data-project-id="{e(current_project_id)}">{_ICON_REFRESH}Buscar agora</button>
        <button type="button" class="btn btn-compact" id="btn-manage-categories" data-project-id="{e(current_project_id)}">{_ICON_SLIDERS}Gerenciar pilares ({len(view.categories)})</button>
      </div>
    """

    if view.trends_status == "never_collected" or not view.trends:
        trends_html = f"""
          <div class="card trends-card" style="margin-bottom: 1.75rem;">
            <div class="trends-header">
              <div class="trends-title">
                <span>{_ICON_FLAME}Temas em alta nos últimos {days} dias</span>
              </div>
              {action_buttons_html}
            </div>
            {cat_pills_html}
            <div id="trends-refresh-feedback" class="form-feedback" style="margin-bottom: 0.5rem;"></div>
            <div class="empty" style="padding: 1.5rem 1rem;">Ainda não há coleta de tendências registrada para o período selecionado. Clique em <strong>Buscar agora</strong> para atualizar.</div>
          </div>
        """
    else:
        last_dt_str = view.last_collected_at.strftime("%d/%m %H:%M") if view.last_collected_at else ""
        stale_badge = ' <span class="pill pill-FAILED" style="margin-left: 0.5rem;">Desatualizado</span>' if view.trends_status == "stale" else ""
        items_html = []
        for idx, t in enumerate(view.trends):
            extra_class = " trend-item-extra" if idx >= 6 else ""
            extra_style = ' style="display: none;"' if idx >= 6 else ""
            ev_list = []
            for ev in t.evidence:
                ev_title = e(ev.get("title", ""))
                ev_chan = e(ev.get("channel", ""))
                ev_views = f"{int(ev['views']):,} views".replace(",", ".") if ev.get("views") is not None else ""
                ev_list.append(
                    f"<div role='listitem' class='evidence-item'>"
                    f"<div class='evidence-title'><span style='color: var(--primary); font-size: 0.75rem; flex-shrink: 0;'>▶</span> <strong style='color: var(--text);'>{ev_title}</strong> <span style='color: var(--text-muted);'>· {ev_chan}</span></div>"
                    f"<div class='evidence-views'>{ev_views}</div>"
                    f"</div>"
                )
            ev_html = f'<div role="list" class="evidence-list">{"".join(ev_list)}</div>' if ev_list else ""

            # Thumbnail markup
            if t.thumbnail_url:
                thumb_inner = f'<img src="{e(t.thumbnail_url)}" alt="{e(t.topic)}" loading="lazy" class="trend-thumb-img" /><span class="thumb-play-overlay">▶</span>'
            else:
                thumb_inner = (
                    '<div class="trend-thumb-placeholder">'
                    '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                    '<rect x="2" y="4" width="20" height="16" rx="4"></rect>'
                    '<polygon points="10 8 16 12 10 16 10 8" fill="currentColor"></polygon>'
                    '</svg>'
                    '</div>'
                )

            if t.video_url:
                thumb_html = (
                    f'<a href="{e(t.video_url)}" target="_blank" rel="noopener noreferrer" class="trend-thumb-link" aria-label="Assistir {e(t.topic)} no YouTube">'
                    f'<div class="trend-thumb">{thumb_inner}</div>'
                    f'</a>'
                )
            else:
                thumb_html = f'<div class="trend-thumb">{thumb_inner}</div>'

            # Badges row
            badges_parts = []
            if t.region:
                label = region_labels.get(t.region, f"Em Alta {t.region}")
                badge_class = "badge-region-br" if t.region == "BR" else "badge-region-global"
                badges_parts.append(f'<span class="chip-metric {badge_class}">{e(label)}</span>')

            if t.category_name:
                badges_parts.append(f'<span class="chip-metric chip-category badge-pillar">🏷️ {e(t.category_name)}</span>')

            if t.metric_text:
                badges_parts.append(f'<span class="chip-metric" style="color: var(--info); font-weight: 600;">📊 {e(t.metric_text)}</span>')

            completed_count = t.counts.get(Stage.COMPLETED, 0)
            in_prod_count = t.counts.get(Stage.IN_PRODUCTION, 0)
            trend_action_count = sum(t.counts.get(stage, 0) for stage in ACTION_STAGES)
            trend_idle_count = t.counts.get(Stage.PENDING, 0)
            if completed_count + in_prod_count + trend_action_count + trend_idle_count == 0:
                badges_parts.append(_state_badge(Stage.PENDING))
            else:
                badges_parts.append(_state_badge(Stage.COMPLETED, completed_count))
                badges_parts.append(_state_badge(Stage.IN_PRODUCTION, in_prod_count))
                badges_parts.append(_state_badge(Stage.AWAITING_APPROVAL, trend_action_count))
            badges_parts.append(f'<span class="chip-metric">💰 {_cost_html(t.cost_text)}</span>')

            badges_html = f'<div class="trend-badges">{"".join(badges_parts)}</div>'

            # Title
            if t.video_url:
                title_html = (
                    f'<a href="{e(t.video_url)}" target="_blank" rel="noopener noreferrer" class="trend-title-link">'
                    f'<span class="trend-topic-name">{e(t.topic)}</span>'
                    f'<span class="trend-external-icon">↗</span>'
                    f'</a>'
                )
            else:
                title_html = f'<div class="trend-topic-name">{e(t.topic)}</div>'

            # Channel & metadata
            views_str = None
            if t.evidence and t.evidence[0].get("views") is not None:
                views_str = f"{int(t.evidence[0]['views']):,} views".replace(",", ".")
            elif t.metric_text:
                views_str = t.metric_text

            meta_parts = [f'<span class="trend-meta-item">📺 {e(t.channel_title or "Canal")}</span>']
            if views_str:
                meta_parts.append(f'<span class="trend-meta-item">👁️ {e(views_str)}</span>')
            if t.published_text:
                meta_parts.append(f'<span class="trend-meta-item">⏱️ {e(t.published_text)}</span>')
            meta_html = f'<div class="trend-meta-row">{" · ".join(meta_parts)}</div>'

            # Action buttons
            action_buttons = []
            if t.video_url:
                action_buttons.append(
                    f'<a href="{e(t.video_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-compact btn-watch-yt">▶️ Assistir no YouTube</a>'
                )
            if t.create_action:
                # IA-01: o formulário vive no Início. O botão é um destino real que leva o tema
                # pré-preenchido por parâmetro tratado pela rota do Início (sem JS cross-page).
                create_params = [f"topic={quote(t.topic)}"]
                if current_project_id:
                    create_params.append(f"project_id={quote(current_project_id)}")
                create_params.append(f"days={days}")
                create_href = "/studio/panel?" + "&".join(create_params)
                action_buttons.append(
                    f'<a class="btn btn-primary btn-create-from-trend" data-topic="{e(t.topic)}" href="{e(create_href)}" style="white-space: nowrap;">✨ Criar Vídeo deste Tema</a>'
                )
            actions_html = f'<div class="trend-actions-row">{"".join(action_buttons)}</div>' if action_buttons else ""

            items_html.append(f"""
              <div class="trend-item{extra_class}"{extra_style} data-category-id="{e(t.category_id or '')}" data-region="{e(t.region or '')}">
                {thumb_html}
                <div class="trend-content">
                  {badges_html}
                  {title_html}
                  {meta_html}
                  {actions_html}
                  {ev_html}
                </div>
              </div>
            """)

        expansion_bar_html = ""
        if len(view.trends) > 6:
            extra_count = len(view.trends) - 6
            expansion_bar_html = f"""
              <div class="trends-expansion-bar" style="text-align: center; margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid var(--border);">
                <button type="button" class="btn btn-compact" id="btn-toggle-more-trends" data-expanded="false" data-total="{len(view.trends)}" aria-expanded="false">
                  Ver Mais Tendências (+{extra_count}) ▼
                </button>
              </div>
            """

        sources = dict.fromkeys(
            ("YouTube (origem desconhecida)" if t.source_name == "YouTube Global (Em Alta)" else t.source_name,
             t.source_url)
            for t in view.trends
        )
        sources_html = " · ".join(
            f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">{e(name)}</a>'
            for name, url in sources
        )
        trends_html = f"""
          <div class="card trends-card">
            <div class="trends-header">
              <div class="trends-title">
                <span>{_ICON_FLAME}Temas em alta nos últimos {days} dias</span>{stale_badge}
              </div>
              <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;">
                <div class="trends-source">
                  Fontes (todas as tendências): {sources_html} · Consulta: {last_dt_str}
                </div>
                {action_buttons_html}
              </div>
            </div>
            {cat_pills_html}
            <div id="trends-refresh-feedback" class="form-feedback" style="margin-bottom: 0.5rem;"></div>
            {''.join(items_html)}
            {expansion_bar_html}
          </div>
        """

    if not view.topics:
        body_html = '<div class="card empty">Nenhum vídeo no período selecionado.</div>'
    else:
        topic_blocks = []
        for g in view.topics:
            cards = []
            for v in g.videos:
                actions_html = []
                if "preview" in v.actions:
                    actions_html.append(f'<a class="btn btn-primary btn-compact" href="/studio/videos/{e(v.id)}/preview">Ver Prévia</a>')
                if "progress" in v.actions:
                    actions_html.append(f'<a class="btn btn-compact" href="{area_href(v.id, "producao")}">Ver Progresso</a>')

                fmt_label = "Short" if getattr(v, "format", VideoFormat.short) == VideoFormat.short else "Long"
                date_str = v.updated_at.strftime("%d/%m %H:%M")
                stage_label = STAGE_LABELS.get(v.stage, v.stage.value)

                cards.append(f"""
                  <div class="video-sample-card">
                    <div class="video-thumb-sample">
                      <div class="video-thumb-placeholder">
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                          <rect x="2" y="4" width="20" height="16" rx="4"></rect>
                          <polygon points="10 8 16 12 10 16 10 8" fill="currentColor"></polygon>
                        </svg>
                      </div>
                    </div>
                    <div class="video-sample-body">
                      <div class="video-state">
                        {_state_badge(v.stage)}
                        <span class="pill pill-{e(v.stage.value)}">{e(stage_label)}</span>
                      </div>
                      <div class="video-sample-title">{e(v.topic)}</div>
                      <div class="video-sample-meta">
                        <span>{e(fmt_label)}</span>
                        <span>·</span>
                        <span>{date_str}</span>
                        <span>·</span>
                        <span style="font-variant-numeric: tabular-nums;">{_cost_html(v.cost_text)}</span>
                      </div>
                    </div>
                    <div class="video-sample-actions">
                      {' '.join(actions_html)}
                    </div>
                  </div>
                """)

            topic_blocks.append(f"""
              <details open class="card topic-group-card" style="margin-bottom: 1.25rem;">
                <summary class="topic-group-summary" style="cursor: pointer; padding: 0.85rem 1rem; border-bottom: 1px solid var(--border); margin-bottom: 0.85rem;">
                  <div class="topic-group-summary-inner" style="display: flex; justify-content: space-between; align-items: center;">
                    <div class="topic-group-title" style="display: flex; align-items: center; gap: 0.6rem;">
                      <span class="topic-group-label" style="font-weight: 700; font-size: 1rem;">{e(g.label)}</span>
                      <span class="chip-metric" style="font-size: 0.72rem;">{len(g.videos)} vídeo{'s' if len(g.videos) > 1 else ''}</span>
                    </div>
                    <span class="topic-group-cost" style="font-weight: 600; font-size: 0.85rem; color: var(--text-muted);">{_cost_html(g.cost_text)}</span>
                  </div>
                </summary>
                <div class="topic-group-videos" style="display: flex; flex-direction: column; gap: 0.5rem;">
                  {''.join(cards)}
                </div>
              </details>
            """)
        body_html = "".join(topic_blocks)

    cat_items = []
    if not view.categories:
        categories_list_html = '<div class="empty" style="padding: 1rem; font-size: 0.85rem;" id="empty-cat-msg">Nenhum pilar cadastrado ainda. Preencha o formulário abaixo para adicionar o primeiro.</div>'
    else:
        for c in view.categories:
            queries_str = ", ".join(c.queries)
            queries_disp = e(queries_str) if c.queries else "Nenhum termo definido"
            cat_items.append(f"""
              <div class="cat-list-item" data-category-id="{e(c.id)}">
                <div class="cat-item-info">
                  <strong style="color: var(--text);">{e(c.name)}</strong>
                  <span style="color: var(--text-muted); font-size: 0.78rem;">Termos: {queries_disp}</span>
                </div>
                <div class="cat-item-actions">
                  <button type="button" class="btn btn-compact btn-edit-category" data-id="{e(c.id)}" data-name="{e(c.name)}" data-queries="{e(queries_str)}">Editar</button>
                  <button type="button" class="btn btn-compact btn-delete-category" data-id="{e(c.id)}" data-name="{e(c.name)}" style="color: var(--bad); border-color: var(--bad);">Excluir</button>
                </div>
              </div>
            """)
        categories_list_html = "".join(cat_items)

    modal_html = f"""
      <div class="modal-overlay" id="categories-modal" role="dialog" aria-modal="true" aria-labelledby="modal-categories-title">
        <div class="modal-content">
          <div class="modal-header">
            <div class="modal-title" id="modal-categories-title">Gerenciar pilares de conteúdo</div>
            <button type="button" class="modal-close" id="btn-close-modal" aria-label="Fechar">&times;</button>
          </div>
          <div class="modal-body">
            <div>
              <div style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.5rem;">Pilares Cadastrados</div>
              <div class="cat-list" id="modal-categories-list">
                {categories_list_html}
              </div>
            </div>

            <div style="border-top: 1px solid var(--border); padding-top: 1rem;">
              <div style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.65rem;" id="category-form-title">Novo Pilar de Conteúdo</div>
              <form id="form-category" style="display: flex; flex-direction: column; gap: 0.85rem;">
                <input type="hidden" id="category-id" name="id" value="">
                <div>
                  <label for="category-name">Nome do Pilar</label>
                  <input type="text" id="category-name" name="name" minlength="1" maxlength="100" placeholder="Ex: Tecnologia e IA" required>
                </div>
                <div>
                  <label for="category-queries">Termos de Busca <span style="font-weight: 400; opacity: 0.75;">(separados por vírgula, máx 10)</span></label>
                  <input type="text" id="category-queries" name="queries" placeholder="Ex: IA, inteligência artificial, ChatGPT">
                </div>
                <div class="form-actions">
                  <button type="submit" class="btn btn-primary" id="btn-save-category">Salvar Pilar</button>
                  <button type="button" class="btn btn-compact" id="btn-cancel-edit-category" style="display: none;">Cancelar</button>
                  <div id="category-form-feedback" class="form-feedback"></div>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    """

    project_modal_html = f"""
      <div class="modal-overlay" id="project-modal" role="dialog" aria-modal="true" aria-labelledby="modal-project-title">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <div class="modal-title" id="modal-project-title">Novo Canal</div>
            <button type="button" class="modal-close" id="btn-close-project-modal" aria-label="Fechar">&times;</button>
          </div>
          <div class="modal-body">
            <form id="form-project" style="display: flex; flex-direction: column; gap: 0.85rem;">
              <div>
                <label for="project-name">Nome do Canal <span style="color: var(--primary);">*</span></label>
                <input type="text" id="project-name" name="name" minlength="1" maxlength="120" placeholder="Ex: Canal de Curiosidades" required>
              </div>
              <div>
                <label for="project-niche">Nicho Editorial <span style="font-weight: 400; opacity: 0.75;">(opcional)</span></label>
                <input type="text" id="project-niche" name="niche" maxlength="200" placeholder="Ex: Música, Mistérios, Curiosidades">
              </div>
              <div>
                <label for="project-language">Idioma</label>
                <select id="project-language" name="language">
                  <option value="pt-BR" selected>Português Brasil (pt-BR)</option>
                  <option value="en-US">English US (en-US)</option>
                  <option value="es-ES">Español (es-ES)</option>
                </select>
              </div>
              <div class="form-actions" style="margin-top: 0.5rem;">
                <button type="submit" class="btn btn-primary" id="btn-save-project">Cadastrar Canal</button>
                <button type="button" class="btn btn-compact" id="btn-cancel-project">Cancelar</button>
                <div id="project-form-feedback" class="form-feedback"></div>
              </div>
            </form>
          </div>
        </div>
      </div>
    """

    month_breakdown = view.month.breakdown
    if month_breakdown.calls == 0:
        month_display = "Sem registro de uso"
        month_origin = "Nenhuma chamada de IA registrada no mês."
    else:
        month_display = view.month.text
        month_origin = (
            "Real é cobrança confirmada; estimado aguarda reconciliação. "
            "“Sem custo” nunca vira valor e “desconhecido” não é zero."
        )

    budget_bar_html = ""
    if view.month.percent is not None and view.month.known_usd > 0:
        pct_width = min(100.0, max(0.0, view.month.percent))
        budget_bar_html = (
            f'<div class="budget-bar" aria-hidden="true">'
            f'<div class="budget-fill" style="width: {pct_width:.1f}%;"></div></div>'
        )

    done_count = view.totals.get(Stage.COMPLETED, 0)
    running_count = view.totals.get(Stage.IN_PRODUCTION, 0)
    action_count = sum(view.totals.get(stage, 0) for stage in ACTION_STAGES)
    idle_count = view.totals.get(Stage.PENDING, 0)
    total_videos = done_count + running_count + action_count + idle_count

    state_legend_html = (
        '<div class="state-legend" aria-label="Legenda de estados">'
        + _state_badge(Stage.COMPLETED, done_count)
        + _state_badge(Stage.IN_PRODUCTION, running_count)
        + _state_badge(Stage.AWAITING_APPROVAL, action_count)
        + '</div>'
    )

    steps_chips_html = """
      <ol class="steps" aria-label="Etapas da produção">
        <li><span class="n">1</span> Roteiro</li>
        <li><span class="n">2</span> Fontes</li>
        <li><span class="n">3</span> Fact-check</li>
        <li><span class="n">4</span> Cenas</li>
        <li><span class="n">5</span> Voz</li>
        <li><span class="n">6</span> Render</li>
        <li><span class="n">7</span> QA</li>
        <li><span class="n">8</span> Publicação</li>
      </ol>
    """

    if total_videos == 0:
        producao_body_html = f"""
          <article class="card empty" id="producao-vazia">
            <h3>Nenhuma execução registrada</h3>
            <p class="muted">Quando você produzir um vídeo, o andamento aparece aqui com etapa atual, próxima ação e custo.</p>
            {steps_chips_html}
            <p class="fine">Etapas exibidas sem estado: nenhuma foi iniciada. Não há percentual porque não existe execução registrada.</p>
          </article>
        """
    else:
        status_items = "".join(
            f'<li class="status-item" data-stage="{stage.value}">'
            f'<span class="status-label">{e(STAGE_LABELS[stage])}</span>'
            f'<span class="status-count">{view.totals.get(stage, 0)}</span></li>'
            for stage in Stage
        )
        producao_body_html = f"""
          <div class="grid-summary">
            <div class="card" style="border-left: 4px solid var(--info);">
              <div class="card-label">Em Produção</div>
              <div class="card-value" style="color: var(--info);">{running_count}</div>
              <div class="card-sub">Jobs de render/áudio ativos</div>
            </div>
            <div class="card" style="border-left: 4px solid var(--warn);">
              <div class="card-label">Aguardando Aprovação</div>
              <div class="card-value" style="color: var(--warn);">{view.totals.get(Stage.AWAITING_APPROVAL, 0)}</div>
              <div class="card-sub">Exigem revisão humana</div>
            </div>
            <div class="card" style="border-left: 4px solid var(--ok);">
              <div class="card-label">Concluídos / Publicados</div>
              <div class="card-value" style="color: var(--ok);">{done_count}</div>
              <div class="card-sub">No período selecionado</div>
            </div>
            <div class="card" style="border-left: 4px solid var(--accent);">
              <div class="card-label">Gasto no Mês vs Teto</div>
              <div class="card-value">{e(month_display)}</div>
              <div class="card-sub">Teto mensal: US$ {view.month.cap_usd:.2f}</div>
              <div class="card-sub">{e(month_origin)}</div>
            </div>
          </div>
          <div class="section-block">
            <h3>Status por fase</h3>
            <ul class="status-list">{status_items}</ul>
          </div>
          <p class="cost-note">Custos rotulados por tipo: <strong>Real</strong> (cobrança confirmada), <strong>Estimado</strong> (ainda sem confirmação), <strong>Sem custo</strong> e <strong>Desconhecido</strong>. Real e estimado nunca são fundidos num único número; ausência de uso é “sem registro de uso” e nunca vira zero.</p>
        """

    action_videos = [
        item
        for group in view.topics
        for item in group.videos
        if item.stage in ACTION_STAGES
    ]
    action_videos.sort(key=lambda item: item.updated_at, reverse=True)
    if not action_videos:
        precisa_body_html = (
            '<div class="card empty">Nada exige sua ação no período selecionado.</div>'
        )
    else:
        cards = []
        for item in action_videos[:6]:
            buttons = []
            if "preview" in item.actions:
                buttons.append(
                    f'<a class="btn btn-primary" href="/studio/videos/{e(item.id)}/preview">Abrir Prévia</a>'
                )
            if "progress" in item.actions:
                progress_label = "Ver correção" if item.stage in (Stage.FAILED, Stage.REJECTED) else "Ver Progresso"
                button_class = "btn btn-ghost" if "preview" in item.actions else "btn btn-primary"
                buttons.append(
                    f'<a class="{button_class}" href="{area_href(item.id, "producao")}">{progress_label}</a>'
                )
            if not buttons:
                buttons.append('<span class="dim">Sem ação disponível nesta versão.</span>')
            hints = {
                Stage.AWAITING_APPROVAL: "Aprovar ou editar antes de seguir para publicação.",
                Stage.APPROVED: "Aprovado; a publicação ainda não foi registrada.",
                Stage.FAILED: "Revisar o passo que falhou e reexecutar a produção.",
                Stage.REJECTED: "Rejeitado; revisar antes de retomar.",
            }
            cards.append(f"""
              <article class="card">
                <div class="spread">
                  <h3>{e(item.topic)}</h3>
                  {_state_badge(item.stage)}
                </div>
                <p class="muted">{_cost_html(item.cost_text)}</p>
                <p class="dim">{hints.get(item.stage, "Ação necessária para continuar.")}</p>
                <div class="row">{''.join(buttons)}</div>
              </article>
            """)
        remaining = len(action_videos) - 6
        remaining_html = (
            f'<p class="fine">E mais {remaining} item(ns) com ação necessária na seção Vídeos.</p>'
            if remaining > 0 else ""
        )
        precisa_body_html = f'<div class="next">{"".join(cards)}</div>{remaining_html}'

    latest_failure = next(
        (
            item
            for group in view.topics
            for item in group.videos
            if item.stage == Stage.FAILED
        ),
        None,
    )
    if latest_failure is None:
        ultima_falha_html = (
            '<p class="muted">Nenhuma falha registrada no período selecionado.</p>'
        )
    else:
        ultima_falha_html = f"""
          <p><strong>Falha registrada no vídeo «{e(latest_failure.topic)}».</strong></p>
          <p class="muted">O que fazer: abra o vídeo para ver o passo de correção. O botão de nova tentativa aparece no detalhe quando o estado permite.</p>
          <p class="dim">Detalhe técnico disponível em Avançado — diagnóstico.</p>
          <a class="btn btn-primary" style="width: 100%;" href="{area_href(latest_failure.id, "producao")}">Ver correção</a>
        """

    rail_cost_html = cost_breakdown_rows(view.month.breakdown)

    fases_html = """
      <div class="kv"><span>F0 Segurança e docs</span><span class="state s-done"><span class="state-icon" aria-hidden="true">✓</span> concluído</span></div>
      <div class="kv"><span>F1 Reservas e execução</span><span class="state s-act"><span class="state-icon" aria-hidden="true">!</span> parcial</span></div>
      <div class="kv"><span>F5 Audiovisual</span><span class="state s-act"><span class="state-icon" aria-hidden="true">!</span> domínio</span></div>
      <div class="kv"><span>F6 QA</span><span class="state s-act"><span class="state-icon" aria-hidden="true">!</span> contrato</span></div>
      <div class="kv"><span>F8 Publicação</span><span class="state s-fail"><span class="state-icon" aria-hidden="true">×</span> não iniciada</span></div>
      <div class="kv"><span>F11 SaaS</span><span class="state s-fail"><span class="state-icon" aria-hidden="true">×</span> adiada</span></div>
      <p class="fine">Rótulos do plano de implementação do repositório; não são estado de execução do Studio.</p>
    """

    side_card_html = budget_side_card(view.month, budget_bar_html)

    # --- IA-01: cada modo monta só as suas seções; nada de "cinco telas numa página". ---
    inicio_producao_body_html = (
        f"""
          <article class="card empty" id="inicio-producao-vazia">
            <h3>Nenhuma execução registrada</h3>
            <p class="muted">Quando você produzir um vídeo, o andamento aparece aqui com etapa atual, próxima ação e custo.</p>
            {steps_chips_html}
            <p class="fine">Etapas exibidas sem estado: nenhuma foi iniciada. Não há percentual porque não existe execução registrada.</p>
            <div class="row"><a class="btn" href="/studio/panel/producao">Abrir Produção</a></div>
          </article>
        """
        if total_videos == 0
        else f"""
          <div class="card">
            <div class="spread">
              <h3>Em produção agora</h3>
              <span class="dim">Em execução: {running_count} · Ação necessária: {action_count} · Concluídos: {done_count}</span>
            </div>
            <p class="muted">O quadro completo — status por fase e custo — fica na tela Produção.</p>
            <div class="row"><a class="btn btn-primary" href="/studio/panel/producao">Ver Produção</a></div>
          </div>
        """
    )
    inicio_producao_html = f"""
      <section class="block panel-section" id="inicio-producao-section" aria-labelledby="inicio-producao-heading">
        <div class="block-head">
          <h2 id="inicio-producao-heading">Produção</h2>
          {state_legend_html}
        </div>
        {inicio_producao_body_html}
      </section>
    """

    trends_count = len(view.trends)
    last_trends_text = view.last_collected_at.strftime("%d/%m %H:%M") if view.last_collected_at else ""
    if trends_count == 0:
        trends_resumo_body = (
            '<div class="card empty">Ainda não há tendências coletadas no período selecionado. '
            'Abra a tela Tendências para buscar agora.</div>'
        )
    else:
        trends_resumo_body = (
            f'<div class="card"><p class="muted">{trends_count} tema(s) coletado(s) no período'
            + (f' · última coleta: {e(last_trends_text)}' if last_trends_text else '')
            + '.</p><div class="row"><a class="btn btn-primary" href="/studio/panel/tendencias">'
            'Ver todas as tendências</a></div></div>'
        )
    inicio_tendencias_html = f"""
      <section class="block panel-section" id="inicio-tendencias-section" aria-labelledby="inicio-tendencias-heading">
        <div class="block-head">
          <h2 id="inicio-tendencias-heading">Tendências</h2>
        </div>
        <p class="section-sub">Resumo do período. Filtros por região e pilar, evidências e o botão «Criar Vídeo deste Tema» ficam na tela Tendências.</p>
        {trends_resumo_body}
      </section>
    """
    producao_section_html = f"""
      <section class="block panel-section" id="producao-section" aria-labelledby="producao-heading">
        <div class="block-head">
          <h1 id="producao-heading" tabindex="-1">Produção</h1>
          {state_legend_html}
        </div>
        {producao_body_html}
      </section>
    """
    tendencias_section_html = f"""
      <section class="block panel-section" id="trending-section" aria-labelledby="trending-heading">
        <div class="block-head">
          <h1 id="trending-heading" tabindex="-1">Tendências</h1>
        </div>
        <p class="section-sub">Temas coletados com evidências, região e origem. Origem não identificada aparece como desconhecida.</p>
        {trends_html}
      </section>
    """

    rail_cost_section = f"""
      <section class="card" aria-labelledby="h-custo">
        <h2 id="h-custo">Custo do mês</h2>
        {rail_cost_html}
        <p class="fine">Real é cobrança confirmada; estimado aguarda reconciliação e consome o teto até lá. “Sem custo” nunca vira valor e “desconhecido” não é zero.</p>
      </section>"""
    rail_fases_section = f"""
      <section class="card" aria-labelledby="h-fase">
        <h2 id="h-fase">Estado das fases</h2>
        {fases_html}
      </section>"""
    rail_inicio_html = f"""<aside class="rail" aria-label="Resumo">{rail_cost_section}
      <section class="card" aria-labelledby="h-falha">
        <h2 id="h-falha">Última falha</h2>
        {ultima_falha_html}
      </section>{rail_fases_section}
    </aside>"""
    rail_producao_html = f"""<aside class="rail" aria-label="Resumo">{rail_cost_section}{rail_fases_section}
    </aside>"""
    trend_stale_note = (
        "A coleta mais recente é anterior ao período selecionado; os dados aparecem marcados como desatualizados."
        if view.trends_status == "stale" else
        "Cada tema traz a origem e a data da coleta."
    )
    rail_tendencias_html = f"""<aside class="rail" aria-label="Resumo">
      <section class="card" aria-labelledby="h-frescor">
        <h2 id="h-frescor">Frescor</h2>
        <div class="kv"><span>Última coleta</span><span>{e(last_trends_text) or "sem registro"}</span></div>
        <div class="kv"><span>Temas no período</span><span>{trends_count}</span></div>
        <div class="kv"><span>Situação</span><span>{e("Desatualizado" if view.trends_status == "stale" else ("Coleta registrada" if trends_count else "Sem coleta"))}</span></div>
        <p class="fine">{e(trend_stale_note)} A coleta é dado real da API; “views” vem da lista de tendências e é aproximado.</p>
      </section>
    </aside>"""

    # O modal de pilares pertence à tela Tendências; o modal de canal é casca e vale para todas.
    overlays_html = project_modal_html + (modal_html if mode == "tendencias" else "")

    create_form_html = f"""
        <form id="create-video-form" class="idea-row">
          <div>
            <label class="sr-only" for="topic">Tema do vídeo</label>
            <input type="text" id="topic" name="topic" class="new-video-topic input" minlength="3" maxlength="300" placeholder="Ex: ADE Lineup 2026 Revelado" value="{e(topic)}" required>
          </div>
          <div>
            <label class="sr-only" for="new-video-project">Canal</label>
            <select id="new-video-project" name="project_id" class="input" style="width: auto;" required>
              {project_options}
            </select>
          </div>
          <div>
            <label class="sr-only" for="new-video-format">Formato</label>
            <select id="new-video-format" name="format" class="input" style="width: auto;">
              <option value="short">Short (1080x1920)</option>
              <option value="long">Long (1920x1080)</option>
            </select>
          </div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary" id="btn-create-video">✦ Produzir vídeo</button>
            <div id="create-video-feedback" class="form-feedback"></div>
          </div>
        </form>
        <p class="note">Ao criar, o vídeo abre para você <strong>pesquisar as fontes</strong>; a produção só começa quando você clicar em «Iniciar produção», já com a fonte registrada.</p>
    """

    hero_html = f"""
        <section class="hero" id="inicio-section" aria-labelledby="hero-heading" tabindex="-1">
          <p class="eyebrow"><span class="dot" aria-hidden="true"></span> Um comando, do briefing à publicação</p>
          <h1 id="hero-heading">Transforme uma ideia em um vídeo <span class="accent-word">publicado</span></h1>
          <p class="lede">Produção assistida com aprovação humana e teto de custo. Esta visão mostra apenas o que está registrado no Studio.</p>
          <div class="tabs" role="tablist" aria-label="Origem do vídeo">
            <button type="button" class="tab" role="tab" id="tab-ideia" aria-selected="true" aria-controls="p-ideia">Minha ideia</button>
            <button type="button" class="tab" role="tab" id="tab-tend" aria-selected="false" aria-controls="p-tend" tabindex="-1">Tendência</button>
            <button type="button" class="tab" role="tab" id="tab-serie" aria-selected="false" aria-controls="p-serie" aria-disabled="true" tabindex="-1">Série / Playlist</button>
          </div>
          <div id="p-ideia" role="tabpanel" aria-labelledby="tab-ideia">
            <div id="new-video-section">{create_form_html}</div>
          </div>
          <div id="p-tend" role="tabpanel" aria-labelledby="tab-tend" hidden>
            <p class="note">Use a tela <a href="/studio/panel/tendencias">Tendências</a>; o botão «Criar Vídeo deste Tema» abre este Início com o tema já preenchido.</p>
          </div>
          <div id="p-serie" role="tabpanel" aria-labelledby="tab-serie" hidden>
            <p class="note">Séries e playlists ainda não têm backend nesta versão; por isso a aba está indisponível.</p>
          </div>
        </section>
    """

    advanced_panel_html = f"""
      <details class="advanced" id="advanced-diagnostics">
        <summary class="advanced-summary">Avançado — diagnóstico (IDs, traces, uso de modelos)</summary>
        <div class="advanced-body">
          <p>Canal: <code>{e(current_project_id) or "não selecionado"}</code></p>
          <p>Visão gerada em {view.generated_at.strftime("%d/%m/%Y %H:%M")}.</p>
          <p>Identificadores técnicos apenas. Logs e traces por vídeo ficam no detalhe do vídeo, na mesma seção avançada.</p>
        </div>
      </details>
    """

    if mode == "producao":
        main_html = f"""
      {producao_section_html}
      {warning_html}
      {advanced_panel_html}
        """
        rail_html = rail_producao_html
    elif mode == "tendencias":
        main_html = f"""
      {tendencias_section_html}
      {advanced_panel_html}
        """
        rail_html = rail_tendencias_html
    else:
        main_html = f"""
      {hero_html}
      {inicio_producao_html}
      <section class="block panel-section" id="precisa-section" aria-labelledby="precisa-heading">
        <h2 id="precisa-heading">Precisa de você</h2>
        {precisa_body_html}
      </section>
      {inicio_tendencias_html}
      {warning_html}
      <section class="block panel-section" id="videos" aria-labelledby="videos-heading">
        <h2 id="videos-heading">Vídeos</h2>
        {body_html}
      </section>
      {advanced_panel_html}
        """
        rail_html = rail_inicio_html

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark light">
  <title>{_PANEL_TITLES[mode]}</title>
  <style nonce="{nonce}">{CSS}</style>
</head>
<body>
  <a class="skip-link" href="{_PANEL_SKIP_HREFS[mode]}">Ir para o conteúdo</a>
  <div class="app-layout">
    {render_sidebar(active=mode, side_card_html=side_card_html, channels_href="/studio/canais", nonce=nonce)}

    <main class="main-content">
      <header class="topbar">
        <div class="topbar-actions" style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
          <a class="btn btn-primary btn-compact" href="{new_video_href}" id="nav-btn-new-video">+ Novo Vídeo</a>
          <div class="project-switcher">
            <label for="global-project-select" style="font-weight: 600; font-size: 0.85rem; color: var(--text-muted);">Canal Ativo:</label>
            <select id="global-project-select" class="form-select-compact">
              {global_project_options}
            </select>
            <button type="button" class="btn btn-compact" id="btn-open-project-modal">+ Novo Canal</button>
          </div>
          <div class="filter-bar">
            <span style="padding-left: 0.4rem; color: var(--text-muted);">Período:</span>
            {filters_html}
          </div>
        </div>
      </header>

      {main_html}
    </main>

    {rail_html}
  </div>
  {overlays_html}
  <script nonce="{nonce}">
    {ERRO_JS}
    const form = document.getElementById('create-video-form');
    if (form) {{
      form.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const btn = document.getElementById('btn-create-video');
        const feedback = document.getElementById('create-video-feedback');
        const project_id = document.getElementById('new-video-project').value;
        const topicInput = document.getElementById('topic') || document.getElementById('new-video-topic');
        const topic = topicInput ? topicInput.value.trim() : '';
        const format = document.getElementById('new-video-format').value;
        if (!topic) return;
        if (btn) btn.disabled = true;
        feedback.textContent = 'Criando vídeo...';
        try {{
          const res = await fetch('/studio/videos', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ project_id, topic, format }})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (!res.ok || !data.id) {{
            const why = window.StudioErro.texto(data, 'tente novamente.');
            feedback.textContent = '';
            const msg = document.createElement('span');
            msg.textContent = 'Erro ao criar: ' + why + ' ';
            const link = document.createElement('a');
            link.href = '#videos';
            link.textContent = 'Ver meus vídeos';
            feedback.append(msg, link);
            if (btn) btn.disabled = false;
            return;
          }}
          // PROD-04 (achado 4): o fluxo aprovado é Produzir vídeo → Pesquisar fontes → Roteiro.
          // A produção **não** começa aqui: sem fonte, a 1ª etapa do DAG (script) falharia na hora
          // (SourceRefused). O vídeo abre na página onde vivem Fontes e «Iniciar produção».
          feedback.textContent = 'Vídeo criado. Abrindo para você pesquisar as fontes...';
          location.href = '/studio/panel/videos/' + encodeURIComponent(data.id);
        }} catch (err) {{
          feedback.textContent = 'Falha de rede: ' + err.message;
          if (btn) btn.disabled = false;
        }}
      }});
    }}
    document.querySelectorAll('.btn-create-from-trend').forEach((btn) => {{
      btn.addEventListener('click', () => {{
        const topic = btn.getAttribute('data-topic') || btn.dataset.topic || '';
        const details = document.getElementById('new-video-section');
        const form = document.getElementById('create-video-form');
        const input = document.getElementById('topic') || document.getElementById('new-video-topic');
        if (details && 'open' in details) details.open = true;
        if (input) {{
          input.value = topic;
          input.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
          input.classList.remove('topic-pulse');
          void input.offsetWidth;
          input.classList.add('topic-pulse');
          setTimeout(() => input.focus(), 100);
          setTimeout(() => input.classList.remove('topic-pulse'), 1500);
        }} else if (form) {{
          form.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        }}
      }});
    }});
    const navBtnNew = document.getElementById('nav-btn-new-video');
    if (navBtnNew) {{
      navBtnNew.addEventListener('click', (ev) => {{
        // Fora do Início o formulário não existe nesta página: o href do servidor manda para
        // /studio/panel#new-video-section — não interceptamos (nada de preventDefault órfão).
        const details = document.getElementById('new-video-section');
        if (!details) return;
        ev.preventDefault();
        const input = document.getElementById('topic') || document.getElementById('new-video-topic');
        if ('open' in details) details.open = true;
        details.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        if (input) {{
          setTimeout(() => input.focus(), 200);
        }}
      }});
    }}

    // Abas de origem: só alterna entre painéis reais; a aba sem backend fica indisponível.
    const originTabs = Array.from(document.querySelectorAll('.tab[role="tab"]'));
    if (originTabs.length > 0) {{
      const selectTab = (selectedTab) => {{
        if (selectedTab.getAttribute('aria-disabled') === 'true') return;
        originTabs.forEach((tab) => {{
          const isSelected = tab === selectedTab;
          tab.setAttribute('aria-selected', isSelected ? 'true' : 'false');
          tab.tabIndex = isSelected ? 0 : -1;
          const panel = document.getElementById(tab.getAttribute('aria-controls'));
          if (panel) panel.hidden = !isSelected;
        }});
      }};
      originTabs.forEach((tab) => {{
        if (tab.getAttribute('aria-disabled') === 'true') return;
        tab.addEventListener('click', () => selectTab(tab));
      }});
    }}

    // Navegação por seções: aria-current acompanha a seção visível.
    const primaryNav = document.querySelector('nav[aria-label="Principal"]');
    if (primaryNav) {{
      const sectionLinks = Array.from(primaryNav.querySelectorAll('a.nav-item[href^="#"]'));
      const sectionTargets = sectionLinks
        .map((link) => document.querySelector(link.getAttribute('href')))
        .filter(Boolean);
      const markCurrentSection = (id) => {{
        sectionLinks.forEach((link) => {{
          const isCurrent = link.getAttribute('href') === '#' + id;
          link.classList.toggle('active', isCurrent);
          if (isCurrent) link.setAttribute('aria-current', 'page');
          else link.removeAttribute('aria-current');
        }});
      }};
      if ('IntersectionObserver' in window && sectionTargets.length > 0) {{
        const observer = new IntersectionObserver((entries) => {{
          entries.forEach((entry) => {{
            if (entry.isIntersecting) markCurrentSection(entry.target.id);
          }});
        }}, {{ rootMargin: '-30% 0px -55% 0px', threshold: 0 }});
        sectionTargets.forEach((target) => observer.observe(target));
      }}
      sectionLinks.forEach((link) => {{
        link.addEventListener('click', () => markCurrentSection(link.getAttribute('href').slice(1)));
      }});
    }}

    // Pill Filtering (Region, Category & All) & Compact Trends Expansion
    const filterPills = document.querySelectorAll('.cat-pill[data-filter-type]');
    const trendItems = document.querySelectorAll('.trend-item');
    const btnToggleTrends = document.getElementById('btn-toggle-more-trends');

    function applyTrendsFilter() {{
      const activePill = document.querySelector('.cat-pill.active[data-filter-type]');
      const filterType = activePill ? activePill.getAttribute('data-filter-type') : 'all';
      const isExpanded = btnToggleTrends ? btnToggleTrends.getAttribute('data-expanded') === 'true' : true;
      let shown = 0;

      trendItems.forEach((item) => {{
        let matches = false;
        if (filterType === 'all') {{
          matches = true;
        }} else if (filterType === 'region') {{
          const regCode = activePill ? activePill.getAttribute('data-region-code') : null;
          matches = (item.getAttribute('data-region') === regCode);
        }} else if (filterType === 'category') {{
          const catId = activePill ? (activePill.getAttribute('data-cat-id') || activePill.getAttribute('data-category-id')) : null;
          matches = (item.getAttribute('data-category-id') === catId);
        }}

        if (!matches) {{
          item.style.display = 'none';
        }} else {{
          if (!isExpanded && shown >= 6) {{
            item.style.display = 'none';
          }} else {{
            item.style.display = '';
          }}
          shown++;
        }}
      }});
      if (btnToggleTrends) {{
        const hidden = shown <= 6;
        btnToggleTrends.hidden = hidden;
        btnToggleTrends.parentElement.hidden = hidden;
        btnToggleTrends.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
        btnToggleTrends.textContent = isExpanded
          ? 'Recolher Tendências ▲'
          : 'Ver Mais Tendências (+' + Math.max(0, shown - 6) + ') ▼';
      }}
    }}

    filterPills.forEach((pill) => {{
      pill.addEventListener('click', () => {{
        filterPills.forEach((p) => {{
          p.classList.remove('active');
          p.setAttribute('aria-pressed', 'false');
        }});
        pill.classList.add('active');
        pill.setAttribute('aria-pressed', 'true');
        if (btnToggleTrends) btnToggleTrends.setAttribute('data-expanded', 'false');
        applyTrendsFilter();
      }});
    }});

    if (btnToggleTrends) {{
      btnToggleTrends.addEventListener('click', () => {{
        const isCurrentlyExpanded = btnToggleTrends.getAttribute('data-expanded') === 'true';
        if (!isCurrentlyExpanded) {{
          btnToggleTrends.setAttribute('data-expanded', 'true');
          applyTrendsFilter();
        }} else {{
          btnToggleTrends.setAttribute('data-expanded', 'false');
          applyTrendsFilter();
          const trendSection = document.getElementById('trending-section');
          if (trendSection) {{
            trendSection.scrollIntoView({{ behavior: 'smooth' }});
          }}
        }}
      }});
    }}

    // Modal Open & Close
    const modal = document.getElementById('categories-modal');
    const btnManage = document.getElementById('btn-manage-categories');
    const btnAddPillarPill = document.getElementById('btn-open-categories-modal') || document.getElementById('btn-add-pillar-pill');
    const btnCloseModal = document.getElementById('btn-close-modal');

    function openCatModal() {{
      if (modal) {{
        modal.style.display = 'flex';
        resetCategoryForm();
      }}
    }}
    function closeCatModal() {{
      if (modal) modal.style.display = 'none';
    }}

    if (btnManage) btnManage.addEventListener('click', openCatModal);
    if (btnAddPillarPill) btnAddPillarPill.addEventListener('click', openCatModal);
    if (btnCloseModal) btnCloseModal.addEventListener('click', closeCatModal);
    if (modal) {{
      modal.addEventListener('click', (ev) => {{
        if (ev.target === modal) closeCatModal();
      }});
    }}
    document.addEventListener('keydown', (ev) => {{
      if (ev.key === 'Escape') {{
        if (modal && modal.style.display === 'flex') closeCatModal();
        if (projectModal && projectModal.style.display === 'flex') closeProjectModal();
      }}
    }});

    // Global Project Switcher Change
    const globalProjectSelect = document.getElementById('global-project-select');
    if (globalProjectSelect) {{
      globalProjectSelect.addEventListener('change', () => {{
        const val = globalProjectSelect.value;
        const urlParams = new URLSearchParams(window.location.search);
        const days = urlParams.get('days') || '{days}';
        window.location.href = '{panel_path}?project_id=' + encodeURIComponent(val) + '&days=' + encodeURIComponent(days);
      }});
    }}

    // Project Creation Modal Open & Close
    const projectModal = document.getElementById('project-modal');
    const btnOpenProjectModal = document.getElementById('btn-open-project-modal');
    const btnCloseProjectModal = document.getElementById('btn-close-project-modal');
    const btnCancelProject = document.getElementById('btn-cancel-project');
    const projectForm = document.getElementById('form-project');
    const projectFeedback = document.getElementById('project-form-feedback');
    const btnSaveProject = document.getElementById('btn-save-project');

    function openProjectModal() {{
      if (projectModal) {{
        projectModal.style.display = 'flex';
        if (projectForm) projectForm.reset();
        if (projectFeedback) projectFeedback.textContent = '';
        if (btnSaveProject) btnSaveProject.disabled = false;
        const nameInput = document.getElementById('project-name');
        if (nameInput) nameInput.focus();
      }}
    }}
    function closeProjectModal() {{
      if (projectModal) projectModal.style.display = 'none';
    }}

    if (btnOpenProjectModal) btnOpenProjectModal.addEventListener('click', openProjectModal);
    if (btnCloseProjectModal) btnCloseProjectModal.addEventListener('click', closeProjectModal);
    if (btnCancelProject) btnCancelProject.addEventListener('click', closeProjectModal);
    if (projectModal) {{
      projectModal.addEventListener('click', (ev) => {{
        if (ev.target === projectModal) closeProjectModal();
      }});
    }}

    // Project Form Submit
    if (projectForm) {{
      projectForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const nameInput = document.getElementById('project-name');
        const nicheInput = document.getElementById('project-niche');
        const langInput = document.getElementById('project-language');
        const name = nameInput ? nameInput.value.trim() : '';
        const niche = nicheInput ? nicheInput.value.trim() : '';
        const language = langInput ? langInput.value : 'pt-BR';

        if (!name) return;
        if (btnSaveProject) btnSaveProject.disabled = true;
        if (projectFeedback) projectFeedback.textContent = 'Cadastrando canal...';

        try {{
          const res = await fetch('/studio/projects', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ name, niche, language }})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok && data.id) {{
            if (projectFeedback) projectFeedback.textContent = 'Canal criado com sucesso! Redirecionando...';
            const urlParams = new URLSearchParams(window.location.search);
            const days = urlParams.get('days') || '{days}';
            window.location.href = '{panel_path}?project_id=' + encodeURIComponent(data.id) + '&days=' + encodeURIComponent(days);
          }} else {{
            const errMsg = window.StudioErro.texto(data, 'tente novamente.');
            if (projectFeedback) projectFeedback.textContent = 'Erro ao cadastrar: ' + errMsg;
            if (btnSaveProject) btnSaveProject.disabled = false;
          }}
        }} catch (err) {{
          if (projectFeedback) projectFeedback.textContent = 'Falha de rede: ' + err.message;
          if (btnSaveProject) btnSaveProject.disabled = false;
        }}
      }});
    }}

    // Category Form Reset & Edit
    const catForm = document.getElementById('form-category');
    const catFormTitle = document.getElementById('category-form-title');
    const catIdInput = document.getElementById('category-id');
    const catNameInput = document.getElementById('category-name');
    const catQueriesInput = document.getElementById('category-queries');
    const btnSaveCat = document.getElementById('btn-save-category');
    const btnCancelEdit = document.getElementById('btn-cancel-edit-category');
    const catFeedback = document.getElementById('category-form-feedback');

    function resetCategoryForm() {{
      if (catIdInput) catIdInput.value = '';
      if (catNameInput) catNameInput.value = '';
      if (catQueriesInput) catQueriesInput.value = '';
      if (catFormTitle) catFormTitle.textContent = 'Novo Pilar de Conteúdo';
      if (btnSaveCat) {{
        btnSaveCat.textContent = 'Salvar Pilar';
        btnSaveCat.disabled = false;
      }}
      if (btnCancelEdit) btnCancelEdit.style.display = 'none';
      if (catFeedback) catFeedback.textContent = '';
    }}

    if (btnCancelEdit) {{
      btnCancelEdit.addEventListener('click', resetCategoryForm);
    }}

    document.querySelectorAll('.btn-edit-category').forEach((btn) => {{
      btn.addEventListener('click', () => {{
        const id = btn.dataset.id || '';
        const name = btn.dataset.name || '';
        const queries = btn.dataset.queries || '';
        if (catIdInput) catIdInput.value = id;
        if (catNameInput) {{
          catNameInput.value = name;
          catNameInput.focus();
        }}
        if (catQueriesInput) catQueriesInput.value = queries;
        if (catFormTitle) catFormTitle.textContent = 'Editar Pilar: ' + name;
        if (btnSaveCat) btnSaveCat.textContent = 'Atualizar Pilar';
        if (btnCancelEdit) btnCancelEdit.style.display = '';
        if (catFeedback) catFeedback.textContent = '';
      }});
    }});

    // Category Form Submit
    const activeProjectId = "{e(current_project_id)}";
    if (catForm) {{
      catForm.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const id = (catIdInput && catIdInput.value.trim()) || null;
        const name = catNameInput ? catNameInput.value.trim() : '';
        if (!name) return;

        const rawQueries = catQueriesInput ? catQueriesInput.value : '';
        const queries = rawQueries
          .split(',')
          .map((q) => q.trim())
          .filter((q) => q.length > 0);

        if (btnSaveCat) btnSaveCat.disabled = true;
        if (catFeedback) catFeedback.textContent = 'Salvando pilar...';

        try {{
          const payload = {{ name: name, queries: queries }};
          if (id) payload.id = id;

          const res = await fetch('/studio/projects/' + encodeURIComponent(activeProjectId) + '/categories', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload)
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            if (catFeedback) catFeedback.textContent = 'Pilar salvo com sucesso! Atualizando...';
            setTimeout(() => location.reload(), 600);
          }} else if (res.status === 409) {{
            if (catFeedback) catFeedback.textContent = 'Já existe um pilar com este nome no canal.';
            if (btnSaveCat) btnSaveCat.disabled = false;
          }} else {{
            const errMsg = window.StudioErro.texto(data, 'tente novamente.');
            if (catFeedback) catFeedback.textContent = 'Erro: ' + errMsg;
            if (btnSaveCat) btnSaveCat.disabled = false;
          }}
        }} catch (err) {{
          if (catFeedback) catFeedback.textContent = 'Falha de rede: ' + err.message;
          if (btnSaveCat) btnSaveCat.disabled = false;
        }}
      }});
    }}

    // Category Delete
    document.querySelectorAll('.btn-delete-category').forEach((btn) => {{
      btn.addEventListener('click', async () => {{
        const catId = btn.dataset.id;
        const catName = btn.dataset.name || 'este pilar';
        if (!catId) return;
        if (!confirm('Deseja excluir o pilar "' + catName + '"?')) return;

        btn.disabled = true;
        if (catFeedback) catFeedback.textContent = 'Excluindo pilar...';

        try {{
          const res = await fetch('/studio/projects/' + encodeURIComponent(activeProjectId) + '/categories/' + encodeURIComponent(catId), {{
            method: 'DELETE'
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            if (catFeedback) catFeedback.textContent = 'Pilar excluído com sucesso! Atualizando...';
            setTimeout(() => location.reload(), 600);
          }} else {{
            const errMsg = window.StudioErro.texto(data, 'tente novamente.');
            if (catFeedback) catFeedback.textContent = 'Erro ao excluir: ' + errMsg;
            btn.disabled = false;
          }}
        }} catch (err) {{
          if (catFeedback) catFeedback.textContent = 'Falha de rede: ' + err.message;
          btn.disabled = false;
        }}
      }});
    }});

    // Refresh Trends
    const btnRefresh = document.getElementById('btn-refresh-trends');
    const refreshFeedback = document.getElementById('trends-refresh-feedback');
    if (btnRefresh) {{
      btnRefresh.addEventListener('click', async () => {{
        btnRefresh.disabled = true;
        const origHtml = btnRefresh.innerHTML;
        btnRefresh.textContent = ' Consultando YouTube...';
        const spinner = document.createElement('span');
        spinner.className = 'spinner-inline';
        btnRefresh.prepend(spinner);
        if (refreshFeedback) refreshFeedback.textContent = 'Consultando YouTube Data API com seus pilares de conteúdo...';

        try {{
          const res = await fetch('/studio/projects/' + encodeURIComponent(activeProjectId) + '/trends/refresh', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{}})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            const count = typeof data.stored === 'number' ? data.stored : 0;
            if (refreshFeedback) refreshFeedback.textContent = 'Coleta concluída (' + count + ' temas encontrados)! Atualizando...';
            setTimeout(() => location.reload(), 500);
          }} else {{
            const msg = window.StudioErro.texto(data, 'tente novamente.');
            if (refreshFeedback) refreshFeedback.textContent = 'Erro na coleta: ' + msg;
            btnRefresh.disabled = false;
            btnRefresh.innerHTML = origHtml;
          }}
        }} catch (err) {{
          if (refreshFeedback) refreshFeedback.textContent = 'Falha de rede: ' + err.message;
          btnRefresh.disabled = false;
          btnRefresh.innerHTML = origHtml;
        }}
      }});
    }}
  </script>
</body>
</html>"""
    return html_content, _headers(nonce)


def render_panel(view: PanelView, *, topic: str = "") -> tuple[str, dict[str, str]]:
    """Início: hero + criar vídeo + produção em andamento + precisa de atenção + resumo de
    tendências + bloco Vídeos. `topic` pré-preenche o tema (usado pelo «Criar Vídeo deste Tema»
    vindo da tela Tendências)."""
    from .panel_home import render_home  # UX V3: o Início segue a proposta aprovada

    return render_home(view, topic=topic)


def render_producao(view: PanelView) -> tuple[str, dict[str, str]]:
    """Produção: quadro completo de execução (status por fase e custo), sem as outras telas."""
    return _render_panel_page(view, mode="producao")


def render_tendencias(view: PanelView) -> tuple[str, dict[str, str]]:
    """Tendências: lista completa com filtros por região/pilar, evidências e «Criar Vídeo deste Tema»."""
    return _render_panel_page(view, mode="tendencias")
