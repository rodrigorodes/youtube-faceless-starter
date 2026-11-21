"""Tela de Analytics (F9-01/02/03/05/06) na casca aprovada.

Fonte visual: `produto/tela-analytics.html` (aprovado em 2026-11-20). O mockup é ilustrativo;
esta página só renderiza medição real do Studio ou estado vazio explícito. Onde não há número,
aparece "Ainda não disponível" com o motivo — nunca 0, nunca estimativa disfarçada, nunca
"Global" como origem.
"""
import html
import json
import secrets
from urllib.parse import urlencode

from ..application.analytics_dashboard import (
    AnalyticsDashboardView,
    Cell,
    ExperimentView,
    InsightView,
    PillarMetricsView,
    RecommendationView,
    Tile,
    VideoMetricsView,
)
from ..application.panel import MonthCost
from . import panel as shell

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

ANALYTICS_CSS = """
.page-goal { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.35rem; max-width: 70ch; }
.page-goal b { color: var(--text); }
.filter-form { display: flex; flex-wrap: wrap; gap: 0.65rem; align-items: flex-end; margin-top: 1rem; }
.filter-form .field { min-width: 190px; flex: 1 1 190px; }
.filter-form select { min-height: 40px; }
.chip-row { display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.65rem; align-items: center; }
.chip {
  display: inline-flex; align-items: center; min-height: 40px; padding: 0.35rem 0.75rem;
  border-radius: 999px; border: 1px solid var(--border); background: var(--surface);
  color: var(--text-muted); font-size: 0.78rem; text-decoration: none;
}
.chip:hover { color: var(--text); border-color: var(--border-hover); }
.chip[aria-current="true"] { background: var(--accent-soft); border-color: var(--accent); color: var(--text); font-weight: 600; }
.chip-static { cursor: default; }
.tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.75rem; margin-top: 1rem; }
.tile {
  border: 1px solid var(--border); background: var(--surface-raised); border-radius: 14px;
  padding: 0.9rem; display: flex; flex-direction: column; gap: 0.4rem; min-height: 152px;
}
.tile.na { border-style: dashed; background: #0e1524; }
.tile .tile-label { font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.06em; }
.tile .metric { font-size: 1.45rem; font-weight: 700; line-height: 1.15; }
.tile .label { font-size: 0.76rem; color: var(--text-muted); }
.tile .why { font-size: 0.72rem; color: var(--text-dim); line-height: 1.45; }
.tile-group + .tile-group { border-top: 1px dashed var(--border-soft); padding-top: 0.55rem; }
.s-idle { color: var(--text-muted); background: var(--surface-raised); border-color: var(--border); }
.ins { border: 1px solid var(--border-soft); border-radius: 12px; padding: 0.9rem; background: var(--surface); }
.ins + .ins { margin-top: 0.6rem; }
.ins p { margin: 0.45rem 0 0; }
.ins .ev { font-size: 0.75rem; color: var(--text-dim); border-left: 2px solid var(--border); padding-left: 0.65rem; margin-top: 0.5rem; }
.subblock { margin-top: 0.65rem; }
.subblock > .label { display: block; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim); margin-bottom: 0.25rem; }
.subblock ul { margin: 0; padding-left: 1.1rem; color: var(--text-muted); font-size: 0.8rem; line-height: 1.5; }
.exp-list { list-style: none; padding: 0; margin: 0; }
.table-scroll { overflow-x: auto; margin-top: 1rem; }
.metrics-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; min-width: 760px; }
.metrics-table th, .metrics-table td { text-align: left; padding: 0.55rem 0.5rem; border-bottom: 1px solid var(--border-soft); vertical-align: top; }
.metrics-table th { color: var(--text-dim); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }
.metrics-table .cell-num { font-variant-numeric: tabular-nums; font-weight: 600; }
.metrics-table .cell-why { color: var(--text-dim); font-size: 0.7rem; line-height: 1.4; display: block; margin-top: 0.2rem; }
.metrics-table .cell-origin { color: var(--text-dim); font-size: 0.68rem; display: block; margin-top: 0.2rem; }
.status-line { margin-top: 0.6rem; font-size: 0.78rem; color: var(--text-muted); }
.recommendation-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.7rem; }
.recommendation-note { font-size: 0.72rem; color: var(--text-dim); margin-top: 0.5rem; }
@media (max-width: 1180px) {
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 820px) {
  .tiles { grid-template-columns: minmax(0, 1fr); }
  .filter-form .field { flex: 1 1 100%; }
  .metrics-table { min-width: 640px; }
}
"""


def _badge(kind: str, icon: str, label: str) -> str:
    return (
        f'<span class="state {e(kind)}"><span class="state-icon" aria-hidden="true">{e(icon)}</span> '
        f'<span>{e(label)}</span></span>'
    )


def _measured_badge() -> str:
    return _badge("s-done", "✓", "Medido")


def _unavailable_badge() -> str:
    return _badge("s-idle", "○", "Ainda não disponível")


def _cell_html(cell: Cell) -> str:
    if cell.state == "measured" and cell.text is not None:
        return (
            f'<span class="cell-num">{e(cell.text)}</span>'
            f'<span class="cell-origin">Origem: {e(cell.origin_label)}</span>'
        )
    return f'{_unavailable_badge()}<span class="cell-why">{e(cell.why)}</span>'


def _tile_html(tile: Tile) -> str:
    if not tile.groups:
        return f"""
        <div class="tile na">
          <span class="tile-label">{e(tile.label)}</span>
          {_unavailable_badge()}
          <span class="why">{e(tile.why)}</span>
        </div>"""
    groups = []
    for group in tile.groups:
        if group.state == "measured" and group.text is not None:
            body = (
                f'<span class="metric num">{e(group.text)}</span>'
                f'<span class="label">{e(group.label)} · {e(group.coverage_text)}</span>'
                f'<span class="why">Origem: {e(group.origin_label)} · {e(group.why)}</span>'
            )
        else:
            body = (
                f'{_unavailable_badge()}'
                f'<span class="label">{e(group.label)} · {e(group.coverage_text)}</span>'
                f'<span class="why">{e(group.why)} — origem: {e(group.origin_label)}</span>'
            )
        groups.append(f'<div class="tile-group">{body}</div>')
    return (
        f'<div class="tile"><span class="tile-label">{e(tile.label)}</span>'
        f'{"".join(groups)}</div>'
    )


def _video_table_html(rows: tuple[VideoMetricsView, ...]) -> str:
    if not rows:
        return ('<p class="muted">Nenhuma medição por vídeo nesta janela. '
                'A tabela só existe quando há publicação coletada com o escopo de leitura.</p>')
    body = []
    for row in rows:
        cells = "".join(f"<td>{_cell_html(cell)}</td>" for cell in row.cells)
        body.append(
            f'<tr><td><b>{e(row.topic)}</b><span class="cell-why">{e(row.format_label)} · '
            f'{e(row.pillar_text)}</span></td>{cells}'
            f'<td>{e(row.attribution_text)}<span class="cell-origin">Origem: {e(row.origin_label)}</span></td></tr>'
        )
    header = "".join(f"<th scope=\"col\">{e(c.label)}</th>" for c in rows[0].cells)
    return f"""
      <div class="table-scroll">
        <table class="metrics-table">
          <caption class="fine">Medição por vídeo, com as versões que a produziram.</caption>
          <thead><tr><th scope="col">Vídeo</th>{header}<th scope="col">Versões</th></tr></thead>
          <tbody>{''.join(body)}</tbody>
        </table>
      </div>"""


def _pillar_table_html(rows: tuple[PillarMetricsView, ...]) -> str:
    if not rows:
        return ('<p class="muted">Nenhuma medição atribuída a pilar e formato nesta janela. '
                'Pilar não registrado não é inventado a partir do tema.</p>')
    body = []
    for row in rows:
        body.append(
            f'<tr><td><b>{e(row.pillar_text)}</b><span class="cell-why">{e(row.format_label)}</span></td>'
            f'<td>{_cell_html(row.views)}</td><td>{_cell_html(row.ctr)}</td>'
            f'<td>{_cell_html(row.retention)}</td><td>{_cell_html(row.watch)}</td>'
            f'<td>{e(row.coverage_text)}</td></tr>'
        )
    return f"""
      <div class="table-scroll">
        <table class="metrics-table">
          <caption class="fine">Pilar e formato separados: Short e long-form não entram na mesma média.</caption>
          <thead><tr><th scope="col">Pilar · formato</th><th scope="col">Views</th><th scope="col">CTR</th>
            <th scope="col">Retenção média</th><th scope="col">Tempo assistido</th><th scope="col">Cobertura</th></tr></thead>
          <tbody>{''.join(body)}</tbody>
        </table>
      </div>"""


def _insights_html(insights: tuple[InsightView, ...]) -> str:
    if not insights:
        return ('<p class="muted">Nenhum insight registrado ainda. Observação e hipótese só aparecem '
                'com métrica, janela e origem — e a amostra mínima é de 3 vídeos comparáveis.</p>')
    blocks = []
    for insight in insights:
        observations = "".join(
            f"<li><b>{e(item.label)}</b>: {e(item.value_text)} · {e(item.source_label)} · "
            f"{e(item.window_text)}</li>"
            for item in insight.observations
        )
        hypotheses = []
        for hypothesis in insight.hypotheses:
            hypotheses.append(
                f'<li>{_badge("s-act", "!", "Hipótese · não verificada")} '
                f'<span>{e(hypothesis.statement)}</span>'
                f'<span class="cell-why">Evidência: {e(hypothesis.evidence_text)}</span></li>'
            )
        blocks.append(f"""
        <div class="ins">
          <div class="spread">
            {_badge("s-done", "✓", "Observação")}
            <span class="dim">confiança {e(insight.confidence_label)}</span>
          </div>
          <p><b>{e(insight.title)}</b></p>
          <div class="subblock"><span class="label">Observação — o que o dado mostra</span>
            <ul>{observations}</ul></div>
          <div class="subblock"><span class="label">Hipótese — o que ainda não foi comprovado</span>
            <ul>{''.join(hypotheses) or '<li>Nenhuma hipótese registrada.</li>'}</ul></div>
          <p class="fine">Confiança declarada por {e(insight.declared_by)}: {e(insight.confidence_basis)}.</p>
        </div>""")
    return "".join(blocks)


def _recommendations_html(view: AnalyticsDashboardView) -> str:
    if not view.recommendations:
        notes = " ".join(view.notes)
        return f'<p class="muted">Nenhuma recomendação gerada. {e(notes)}</p>'
    blocks = []
    for item in view.recommendations:
        blocks.append(_recommendation_html(item))
    return "".join(blocks)


def _recommendation_html(item: RecommendationView) -> str:
    if item.status == "proposed":
        badge = _badge("s-act", "!", "Requer revisão humana")
        actions = f"""
          <div class="recommendation-actions">
            <button class="btn btn-sm" type="button" data-recommendation-id="{e(item.recommendation_id)}"
              data-decision="rejected">Recusar</button>
            <button class="btn btn-sm btn-ghost" type="button" data-recommendation-id="{e(item.recommendation_id)}"
              data-decision="accepted_for_review">Aceitar para revisão</button>
          </div>
          <p class="recommendation-note">Aceitar registra a revisão; não altera o canal. Aplicar exige
          edição manual em Canais (tela ainda não disponível).</p>"""
    else:
        badge = _badge("s-done" if item.status == "accepted_for_review" else "s-idle",
                       "✓" if item.status == "accepted_for_review" else "○",
                       item.status_label)
        decided = f" por {e(item.decided_by)}" if item.decided_by else ""
        actions = f'<p class="status-line">Decisão registrada: {e(item.status_label)}{decided}.</p>'
    return f"""
    <div class="ins">
      <div class="spread">
        {badge}
        <span class="dim">{e(item.kind_label)} · confiança {e(item.confidence_label)}</span>
      </div>
      <p><b>{e(item.statement)}</b></p>
      <p class="why">{e(item.rationale)}</p>
      <div class="ev">Evidência: {e(item.evidence_text)} · {e(item.confidence_basis)}</div>
      {actions}
    </div>"""


def _experiments_html(experiments: tuple[ExperimentView, ...]) -> str:
    if not experiments:
        return ('<p class="muted">Nenhum experimento registrado. A API do YouTube Analytics não expõe '
                'A/B de thumbnail/título; a rotação é manual e precisa de aprovação humana.</p>')
    items = []
    for item in experiments:
        kind = {"Planejado": "s-idle", "Em andamento": "s-run", "Concluído": "s-done",
                "Abandonado": "s-idle"}.get(item.status_label, "s-idle")
        confidence = (f' · confiança {e(item.confidence_label)}' if item.confidence_label else "")
        items.append(f"""
        <li class="ins">
          <div class="spread">
            {_badge(kind, "◐" if item.status_label == "Em andamento" else "·", item.status_label)}
            <span class="dim">{e(item.kind_label)}</span>
          </div>
          <p><b>Variantes:</b> {e(item.variants_text)}</p>
          <div class="kv"><span>Janela</span><span>{e(item.window_text)}</span></div>
          <div class="kv"><span>Conclusão</span><span>{e(item.conclusion_text)}{confidence}</span></div>
          <p class="fine">Aprovado por {e(item.approved_by)}. {e(item.platform_note)}</p>
        </li>""")
    return f'<ul class="exp-list">{"".join(items)}</ul>'


def _advanced_html(view: AnalyticsDashboardView) -> str:
    observations = "".join(
        f'<div class="kv"><span><code>{e(observation_id)}</code></span><span>observação</span></div>'
        for observation_id in view.observation_ids
    ) or '<p class="muted">Nenhuma observação persistida.</p>'
    experiments = "".join(
        f'<div class="kv"><span><code>{e(experiment_id)}</code></span><span>experimento</span></div>'
        for experiment_id in view.experiment_ids
    ) or '<p class="muted">Nenhum experimento persistido.</p>'
    return f"""
    <details class="advanced" id="analytics-advanced">
      <summary class="advanced-summary">Avançado — IDs, janela e origem das medições</summary>
      <div class="advanced-body">
        <p>Canal <code>{e(view.project_id)}</code> · janela {e(view.period_label)} ·
        gerado em {e(view.generated_at.strftime("%d/%m/%Y %H:%M"))}.</p>
        <p><b>Observações</b></p>{observations}
        <p><b>Experimentos</b></p>{experiments}
        <p class="fine">A tela não exibe trace, token nem credencial. A coleta exige o escopo
        <code>yt-analytics.readonly</code>; sem ele, o estado é "ainda não disponível".</p>
      </div>
    </details>"""


def _filter_url(view: AnalyticsDashboardView, **changes) -> str:
    params = {"project": view.project_id, "days": view.period.days}
    if view.selected_video_id:
        params["video"] = view.selected_video_id
    if view.selected_pillar_id:
        params["pillar"] = view.selected_pillar_id
    params.update({key: value for key, value in changes.items() if value is not None})
    return "/studio/panel/analytics?" + urlencode(params)


def _filters_html(view: AnalyticsDashboardView) -> str:
    project_options = "".join(
        f'<option value="{e(item.id)}"{" selected" if item.id == view.project_id else ""}>'
        f'{e(item.label)}</option>'
        for item in view.projects
    )
    video_options = '<option value="">Todos os vídeos</option>' + "".join(
        f'<option value="{e(item.id)}"{" selected" if item.id == view.selected_video_id else ""}>'
        f'{e(item.label)}</option>'
        for item in view.videos
    )
    pillar_options = '<option value="">Todos os pilares</option>' + "".join(
        f'<option value="{e(item.id)}"{" selected" if item.id == view.selected_pillar_id else ""}>'
        f'{e(item.label)}</option>'
        for item in view.pillars
    )
    chips = []
    for days, label in ((7, "7 dias"), (28, "28 dias"), (90, "90 dias")):
        current = ' aria-current="true"' if days == view.period.days else ""
        chips.append(f'<a class="chip"{current} href="{e(_filter_url(view, days=days))}">{label}</a>')
    return f"""
      <form class="filter-form" method="get" action="/studio/panel/analytics" aria-label="Filtrar o dashboard">
        <input type="hidden" name="days" value="{view.period.days}">
        <div class="field"><label for="analytics-project">Canal</label>
          <select id="analytics-project" name="project">{project_options}</select></div>
        <div class="field"><label for="analytics-video">Vídeo</label>
          <select id="analytics-video" name="video">{video_options}</select></div>
        <div class="field"><label for="analytics-pillar">Pilar</label>
          <select id="analytics-pillar" name="pillar">{pillar_options}</select></div>
        <button class="btn btn-sm" type="submit">Aplicar filtros</button>
      </form>
      <div class="chip-row" role="group" aria-label="Filtrar por período">
        <span class="chip chip-static" aria-current="true">Canal: {e(view.project_name)}</span>
        {''.join(chips)}
        <a class="btn btn-sm btn-ghost" href="{e(_filter_url(view))}">Atualizar dados salvos</a>
      </div>"""


def render_analytics(view: AnalyticsDashboardView,
                     month: MonthCost | None = None) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    side_card = (
        shell.budget_side_card(month) if month is not None
        else '<div class="side-card"><h2>Orçamento do mês</h2>'
             '<p>Consulte o painel Início para o custo registrado.</p></div>'
    )
    tiles = "".join(_tile_html(tile) for tile in view.tiles)
    period_state = (
        _measured_badge() if view.has_measurements
        else _badge("s-idle", "○", "Ainda não disponível")
    )
    if view.has_measurements:
        subtitle = f"Recorte de {e(view.period_label)} · última coleta: {e(view.last_collected_text)}."
    elif not view.readiness.publication_available:
        subtitle = "Nenhuma publicação coletada ainda neste canal."
    elif not view.readiness.scope_granted:
        subtitle = "Escopo yt-analytics.readonly não concedido; nenhuma métrica pode ser lida."
    elif view.last_collected_at is not None:
        subtitle = (f"Há coleta registrada em {e(view.last_collected_text)}, mas nenhuma "
                    f"observação cobre exatamente a janela de {view.period.days} dias.")
    else:
        subtitle = "Nenhuma medição coletada nesta janela."
    page = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>Faceless Studio — Analytics</title>
  <style nonce="{nonce}">{shell.CSS}{ANALYTICS_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#analytics-main">Ir para o conteúdo</a>
  <div class="app-layout">
    {shell.render_sidebar(active="analytics", base_href="/studio/panel", side_card_html=side_card)}
    <main class="main-content" id="analytics-main">
      <div class="card">
        <div class="spread">
          <div>
            <h1 id="analytics-heading">Analytics</h1>
            <p class="page-goal">Ação primária: <b>aprender</b>. CTR e retenção aparecem só quando a
            API entrega e a permissão existe — fora disso, “ainda não disponível”.</p>
          </div>
          <span class="dim">Canal: {e(view.project_name)} · {e(view.period_label)}</span>
        </div>
        {_filters_html(view)}
      </div>

      <div class="card">
        <div class="spread">
          <div><h2>Métricas do período</h2><p class="dim" style="margin:0.25rem 0 0">{subtitle}</p></div>
          {period_state}
        </div>
        <div class="tiles">{tiles}</div>
        <p class="fine">Zero não é o mesmo que “sem dado”: quando a API não devolve o valor, o estado é
        <b>ainda não disponível</b> — nunca 0% nem estimativa apresentada como medição. Taxa não é
        somada entre vídeos; Short e long-form não entram na mesma média.</p>
      </div>

      <details class="advanced">
        <summary class="advanced-summary">Como a tela fica quando houver dado</summary>
        <div class="advanced-body">
          <p>A estrutura é a mesma desta página: um bloco por formato comparável, com o valor medido,
          a origem e a cobertura de vídeos. Quando a coleta existir, ela preenche estes blocos; até
          então, o estado vazio acima é o dado real.</p>
          <p>Taxas aparecem por vídeo, ou por um único vídeo comparável — nunca como média de médias.
          Vídeos de duração muito diferente não são agrupados.</p>
        </div>
      </details>

      <div class="card">
        <h2>Desempenho por vídeo</h2>
        <p class="dim" style="margin:0.25rem 0 0">Cada número diz de onde vem — ou por que não existe.</p>
        {_video_table_html(view.video_rows)}
      </div>

      <div class="card">
        <h2>Por pilar e formato</h2>
        <p class="dim" style="margin:0.25rem 0 0">Recorte por pilar dentro do formato; pilar não
        registrado aparece como tal, não é deduzido do tema.</p>
        {_pillar_table_html(view.pillar_rows)}
      </div>

      <div class="card">
        <h2>Insights</h2>
        <p class="dim" style="margin:0.25rem 0 0.6rem"><b>Observação</b> é o que o dado mostra;
        <b>hipótese</b> é o que ainda não foi comprovado. Os dois têm rótulos diferentes, com
        evidência e nível de confiança.</p>
        {_insights_html(view.insights)}
      </div>

      <div class="card">
        <h2>Recomendações</h2>
        <p class="dim" style="margin:0.25rem 0 0.6rem">Uma recomendação sugere, não decide.
        <b>Nada é reconfigurado sozinho</b>: aplicar exige edição manual do perfil do canal e
        aprovação humana.</p>
        {_recommendations_html(view)}
        <div id="analytics-feedback" class="form-feedback" role="status" aria-live="polite"></div>
      </div>

      <div class="card">
        <h2>Histórico de experimentos</h2>
        <p class="dim" style="margin:0.25rem 0 0.6rem">Thumbnail e título, conforme o que o YouTube
        realmente oferece. O histórico registra rotação manual; não declara A/B da plataforma.</p>
        {_experiments_html(view.experiments)}
      </div>

      {_advanced_html(view)}
    </main>

    <aside class="rail" aria-label="Resumo">
      <section class="card" aria-labelledby="h-honest">
        <h2 id="h-honest">Honestidade do dado</h2>
        <p class="fine">CTR e retenção dependem de escopos e permissão da API do canal. Quando o dado
        não vem, mostramos <b>ainda não disponível</b>; nunca preenchemos com 0 nem com estimativa
        disfarçada de medição.</p>
      </section>
      <section class="card" aria-labelledby="h-fresh">
        <h2 id="h-fresh">Frescor e origem</h2>
        <div class="kv"><span>Última coleta</span><span>{e(view.last_collected_text)}</span></div>
        <div class="kv"><span>Escopo de leitura</span><span>{e(view.scope_text)}</span></div>
        <div class="kv"><span>Canal</span><span>{e(view.channel_text)}</span></div>
        <div class="kv"><span>Publicação</span><span>{e("disponível" if view.readiness.publication_available else "nenhuma registrada")}</span></div>
        <p class="fine">A coleta só começa após a primeira publicação e com
        <code>yt-analytics.readonly</code> autorizado no canal.</p>
      </section>
      <section class="card" aria-labelledby="h-not-does">
        <h2 id="h-not-does">O que esta tela não faz</h2>
        <p class="fine">Não muda configuração, não promete métrica que a API não entrega e não junta
        vídeos não comparáveis numa média só. Origem não confiável aparece como
        <b>origem desconhecida</b>.</p>
      </section>
    </aside>
  </div>
  <script nonce="{nonce}">
    const PROJECT = {json.dumps(view.project_id)};
    document.querySelectorAll('[data-recommendation-id]').forEach((btn) => {{
      btn.addEventListener('click', async () => {{
        const feedback = document.getElementById('analytics-feedback');
        const recommendationId = btn.getAttribute('data-recommendation-id');
        const decision = btn.getAttribute('data-decision');
        btn.disabled = true;
        if (feedback) feedback.textContent = 'Registrando a revisão...';
        try {{
          const res = await fetch('/studio/panel/analytics/recommendations/' +
            encodeURIComponent(recommendationId) + '/decision', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ project_id: PROJECT, decision }})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            if (feedback) feedback.textContent = 'Revisão registrada. Nada foi reconfigurado.';
            location.reload();
          }} else {{
            btn.disabled = false;
            if (feedback) feedback.textContent = 'Não foi possível: ' +
              (typeof data.detail === 'string' ? data.detail : 'tente novamente');
          }}
        }} catch (err) {{
          btn.disabled = false;
          if (feedback) feedback.textContent = 'Falha de rede: ' + err.message;
        }}
      }});
    }});
  </script>
</body>
</html>"""
    return page, shell._headers(nonce)