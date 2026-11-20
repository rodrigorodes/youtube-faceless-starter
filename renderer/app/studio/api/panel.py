"""Páginas HTML do painel do Studio (operacional e detalhe de vídeo).
Sem dependências externas; todo texto é escapado e a CSP é protegida por nonce.
"""
import html
import secrets

from ..application.panel import PanelView, VideoDetailView
from ..domain.panel import Stage, is_known_cost

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

CSS = """
:root {
  color-scheme: light dark;
  --bg: #0f141c;
  --surface: #18202c;
  --surface-hover: #1e2838;
  --border: #283548;
  --text: #e6edf3;
  --text-muted: #8b9baa;
  --primary: #2f81f7;
  --ok: #3fb950;
  --ok-bg: rgba(63, 185, 80, 0.15);
  --warn: #d29922;
  --warn-bg: rgba(210, 153, 34, 0.15);
  --bad: #f85149;
  --bad-bg: rgba(248, 81, 73, 0.15);
  --info: #58a6ff;
  --info-bg: rgba(88, 166, 255, 0.15);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f6f8fa;
    --surface: #ffffff;
    --surface-hover: #f3f4f6;
    --border: #d0d7de;
    --text: #1f2328;
    --text-muted: #656d76;
    --primary: #0969da;
    --ok: #1a7f37;
    --warn: #9a6700;
    --bad: #cf222e;
    --info: #0969da;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); padding: 1.25rem; }
.container { max-width: 75rem; margin: 0 auto; }
header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 1.5rem; }
h1 { font-size: 1.25rem; font-weight: 700; }
h2 { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.75rem; }
a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }
.btn {
  display: inline-block; padding: 0.4rem 0.8rem; font-size: 0.85rem; font-weight: 600;
  border-radius: 6px; border: 1px solid var(--border); background: var(--surface); color: var(--text);
  cursor: pointer; min-height: 44px; min-width: 44px; line-height: 1.8; text-align: center;
}
.btn-primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.btn:focus-visible { outline: 3px solid var(--primary); outline-offset: 2px; }

.grid-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
.card-label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; margin-bottom: 0.25rem; }
.card-value { font-size: 1.5rem; font-weight: 700; }
.card-sub { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; }

.filter-bar { display: flex; gap: 0.5rem; align-items: center; font-size: 0.85rem; }
.filter-link { padding: 0.2rem 0.6rem; border-radius: 4px; border: 1px solid var(--border); }
.filter-link.active { background: var(--primary); color: #fff; border-color: var(--primary); }

table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 1.5rem; }
th, td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); font-size: 0.875rem; }
th { background: rgba(0,0,0,0.05); color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--surface-hover); }

.pill { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
.pill-PENDING { background: var(--border); color: var(--text-muted); }
.pill-IN_PRODUCTION { background: var(--info-bg); color: var(--info); border: 1px solid var(--info); }
.pill-AWAITING_APPROVAL { background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn); }
.pill-APPROVED { background: var(--ok-bg); color: var(--ok); border: 1px solid var(--ok); }
.pill-COMPLETED { background: var(--ok-bg); color: var(--ok); }
.pill-FAILED { background: var(--bad-bg); color: var(--bad); border: 1px solid var(--bad); }
.pill-REJECTED { background: var(--bad-bg); color: var(--bad); }

.warning { background: var(--warn-bg); color: var(--warn); padding: 0.75rem; border-radius: 6px; margin-bottom: 1rem; font-size: 0.85rem; }
.empty { text-align: center; padding: 2rem; color: var(--text-muted); }

.timeline { list-style: none; padding-left: 1.5rem; position: relative; }
.timeline-item { position: relative; margin-bottom: 1.25rem; }
.timeline-dot { position: absolute; left: -1.5rem; top: 0.2rem; width: 10px; height: 10px; border-radius: 50%; background: var(--primary); }
.timeline-title { font-weight: 600; font-size: 0.875rem; }
.timeline-desc { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.15rem; }
.layout-detail { display: grid; grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr)); gap: 1.25rem; }
"""


def _headers(nonce: str) -> dict[str, str]:
    return {
        "Content-Security-Policy": (
            f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        ),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


def render_panel(view: PanelView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    days = view.days

    filters_html = "".join(
        f'<a class="filter-link {"active" if d == days else ""}" href="/studio/panel?days={d}">{d} dias</a>'
        for d in (7, 14, 30)
    )

    warning_html = (
        '<div class="warning">Aviso: exibindo os 500 vídeos mais recentes do período selecionado.</div>'
        if view.truncated else ""
    )

    project_options = "".join(f'<option value="{e(p[0])}">{e(p[1])}</option>' for p in view.projects)
    create_form_html = f"""
      <details style="margin-bottom: 1.5rem;" id="new-video-section">
        <summary class="btn btn-primary" style="display: inline-block; list-style: none; margin-bottom: 0.75rem;">+ Novo Vídeo</summary>
        <form id="create-video-form" class="card" style="margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.75rem; max-width: 32rem;">
          <div>
            <label for="new-video-project" style="font-size: 0.8rem; font-weight: 600; display: block; margin-bottom: 0.25rem;">Projeto</label>
            <select id="new-video-project" name="project_id" style="width: 100%; padding: 0.4rem;" required>
              {project_options}
            </select>
          </div>
          <div>
            <label for="new-video-topic" style="font-size: 0.8rem; font-weight: 600; display: block; margin-bottom: 0.25rem;">Tema (3 a 300 caracteres)</label>
            <input id="new-video-topic" name="topic" minlength="3" maxlength="300" style="width: 100%; padding: 0.4rem; font: inherit;" placeholder="Ex: ADE Lineup 2026 Revelado" required>
          </div>
          <div>
            <label for="new-video-format" style="font-size: 0.8rem; font-weight: 600; display: block; margin-bottom: 0.25rem;">Formato</label>
            <select id="new-video-format" name="format" style="width: 100%; padding: 0.4rem;">
              <option value="short">Short (vertical 1080x1920)</option>
              <option value="long">Long (horizontal 1920x1080)</option>
            </select>
          </div>
          <button type="submit" class="btn btn-primary" id="btn-create-video" style="align-self: flex-start;">Criar Vídeo</button>
          <div id="create-video-feedback" style="font-size: 0.85rem;"></div>
        </form>
      </details>
    """

    if view.trends_status == "never_collected" or not view.trends:
        trends_html = f"""
          <div class="card" style="margin-bottom: 1.5rem;">
            <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem;">🔥 Temas em Alta nos Últimos {days} Dias</div>
            <div style="font-size: 0.85rem; color: var(--text-muted);">Ainda não há coleta de tendências registrada para o período selecionado.</div>
          </div>
        """
    else:
        last_dt_str = view.last_collected_at.strftime("%d/%m %H:%M") if view.last_collected_at else ""
        stale_badge = ' <span class="pill pill-FAILED" style="margin-left: 0.5rem;">Desatualizado</span>' if view.trends_status == "stale" else ""
        items_html = []
        for t in view.trends:
            ev_list = []
            for ev in t.evidence:
                ev_title = e(ev.get("title", ""))
                ev_chan = e(ev.get("channel", ""))
                ev_views = f"{int(ev['views']):,} views".replace(",", ".") if ev.get("views") is not None else ""
                ev_list.append(f"<li>{ev_title} ({ev_chan}) — {ev_views}</li>")
            ev_html = f'<ul style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; padding-left: 1.25rem;">{"".join(ev_list)}</ul>' if ev_list else ""

            btn_create = (
                f'<button type="button" class="btn btn-primary btn-create-from-trend" data-topic="{e(t.topic)}">Criar Vídeo deste Tema</button>'
                if t.create_action else ""
            )

            metric_badge = f'<span style="font-weight: 600; color: var(--info);">{e(t.metric_text)}</span>' if t.metric_text else ""
            completed_count = t.counts.get(Stage.COMPLETED, 0)
            in_prod_count = t.counts.get(Stage.IN_PRODUCTION, 0)

            items_html.append(f"""
              <div style="display: flex; justify-content: space-between; align-items: flex-start; padding: 0.75rem 0; border-bottom: 1px solid var(--border);">
                <div>
                  <div style="font-weight: 600; font-size: 1rem;">{e(t.topic)}</div>
                  <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem; display: flex; gap: 0.75rem; flex-wrap: wrap;">
                    <span>📊 {metric_badge}</span>
                    <span>🎬 {completed_count} concluídos · {in_prod_count} em produção</span>
                    <span>💰 Custo: {e(t.cost_text)}</span>
                  </div>
                  {ev_html}
                </div>
                <div>{btn_create}</div>
              </div>
            """)

        trends_html = f"""
          <div class="card" style="margin-bottom: 1.5rem; background: linear-gradient(180deg, rgba(47, 129, 247, 0.05) 0%, var(--surface) 100%);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <div style="font-weight: 600; font-size: 1rem; display: flex; align-items: center;">
                <span>🔥 Temas em Alta nos Últimos {days} Dias</span>{stale_badge}
              </div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">
                Fonte: <a href="{e(view.trends[0].source_url)}" target="_blank" rel="noopener noreferrer">{e(view.trends[0].source_name)}</a> · Consulta: {last_dt_str}
              </div>
            </div>
            {''.join(items_html)}
          </div>
        """

    if not view.topics:
        body_html = '<div class="card empty">Nenhum vídeo no período selecionado.</div>'
    else:
        topic_blocks = []
        for g in view.topics:
            rows = []
            for v in g.videos:
                actions_html = []
                if "preview" in v.actions:
                    actions_html.append(f'<a class="btn btn-primary" href="/studio/videos/{e(v.id)}/preview">Ver Prévia</a>')
                if "progress" in v.actions:
                    actions_html.append(f'<a class="btn" href="/studio/panel/videos/{e(v.id)}">Ver Progresso</a>')

                date_str = v.updated_at.strftime("%d/%m %H:%M")
                rows.append(f"""
                  <tr>
                    <td><strong>{e(v.topic)}</strong></td>
                    <td><span class="pill pill-{e(v.stage.value)}">{e(v.stage.value)}</span></td>
                    <td>{e(v.cost_text)}</td>
                    <td>{date_str}</td>
                    <td>{' '.join(actions_html)}</td>
                  </tr>
                """)

            table_html = f"""
              <table>
                <thead>
                  <tr>
                    <th scope="col">Tema</th>
                    <th scope="col">Etapa</th>
                    <th scope="col">Custo</th>
                    <th scope="col">Atualizado</th>
                    <th scope="col">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(rows)}
                </tbody>
              </table>
            """
            topic_blocks.append(f"""
              <details open class="card" style="margin-bottom: 1rem;">
                <summary style="cursor: pointer; display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; font-weight: 600;">
                  <span>{e(g.label)} <span style="font-size: 0.8rem; color: var(--text-muted); font-weight: 400;">({len(g.videos)} vídeo{'s' if len(g.videos) > 1 else ''})</span></span>
                  <span style="font-size: 0.85rem; color: var(--text-muted);">{e(g.cost_text)}</span>
                </summary>
                {table_html}
              </details>
            """)
        body_html = "".join(topic_blocks)

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Faceless Studio — Painel</title>
  <style nonce="{nonce}">{CSS}</style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>FACELESS STUDIO</h1>
        <div style="font-size: 0.8rem; color: var(--text-muted);">Painel Operacional de Produção</div>
      </div>
      <div class="filter-bar">
        <span>Período:</span>
        {filters_html}
      </div>
    </header>

    <div class="grid-summary">
      <div class="card">
        <div class="card-label">Em Produção</div>
        <div class="card-value" style="color: var(--info);">{view.totals.get(Stage.IN_PRODUCTION, 0)}</div>
        <div class="card-sub">Jobs de render/mídia ativos</div>
      </div>
      <div class="card">
        <div class="card-label">Aguardando Aprovação</div>
        <div class="card-value" style="color: var(--warn);">{view.totals.get(Stage.AWAITING_APPROVAL, 0)}</div>
        <div class="card-sub">Exigem revisão humana</div>
      </div>
      <div class="card">
        <div class="card-label">Concluídos</div>
        <div class="card-value" style="color: var(--ok);">{view.totals.get(Stage.COMPLETED, 0)}</div>
        <div class="card-sub">No período selecionado</div>
      </div>
      <div class="card">
        <div class="card-label">Gasto no Mês vs Teto</div>
        <div class="card-value">{e(view.month.text)}</div>
        <div class="card-sub">Teto mensal: US$ {view.month.cap_usd:.2f}</div>
      </div>
    </div>

    {create_form_html}

    {trends_html}

    {warning_html}

    <h2>Vídeos</h2>
    {body_html}
  </div>
  <script nonce="{nonce}">
    const form = document.getElementById('create-video-form');
    if (form) {{
      form.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const btn = document.getElementById('btn-create-video');
        const feedback = document.getElementById('create-video-feedback');
        const project_id = document.getElementById('new-video-project').value;
        const topic = document.getElementById('new-video-topic').value.trim();
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
          if (res.ok) {{
            feedback.textContent = 'Vídeo criado com sucesso! Atualizando...';
            setTimeout(() => location.reload(), 800);
          }} else {{
            feedback.textContent = 'Erro ao criar: ' + (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
            if (btn) btn.disabled = false;
          }}
        }} catch (err) {{
          feedback.textContent = 'Falha de rede: ' + err.message;
          if (btn) btn.disabled = false;
        }}
      }});
    }}
    document.querySelectorAll('.btn-create-from-trend').forEach((btn) => {{
      btn.addEventListener('click', () => {{
        const topic = btn.dataset.topic || '';
        const details = document.getElementById('new-video-section');
        const input = document.getElementById('new-video-topic');
        if (details) details.open = true;
        if (input) {{
          input.value = topic;
          input.focus();
        }}
      }});
    }});
  </script>
</body>
</html>"""
    return html_content, _headers(nonce)


def render_video(view: VideoDetailView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    v = view.video

    steps_html = []
    if not view.steps:
        steps_html.append('<li class="timeline-item"><div class="timeline-desc">Nenhum passo executado ainda.</div></li>')
    else:
        for s in view.steps:
            err_html = f'<div style="color: var(--bad); font-size: 0.8rem; margin-top: 0.2rem;">{e(s.error_message)}</div>' if s.error_message else ""
            steps_html.append(f"""
              <li class="timeline-item">
                <div class="timeline-dot"></div>
                <div class="timeline-title">{e(s.step)} (tentativa {s.attempt}): {e(s.status)}</div>
                <div class="timeline-desc">{s.started_at.strftime("%d/%m %H:%M:%S")}{err_html}</div>
              </li>
            """)

    usage_html = []
    if not view.usage:
        usage_html.append('<tr><td colspan="4" class="empty">Sem registro de uso de IA para este vídeo.</td></tr>')
    else:
        for u in view.usage:
            if is_known_cost(u.provider, u.model, u.cost_usd):
                cost_str = "US$ 0,00 (gratuito)" if u.cost_usd == 0.0 else f"US$ {u.cost_usd:.4f}"
            else:
                cost_str = '<span style="color: var(--warn);">Não informado</span>'
            usage_html.append(f"""
              <tr>
                <td>{e(u.step)}</td>
                <td>{e(u.provider)}</td>
                <td>{e(u.model)}</td>
                <td>{cost_str}</td>
              </tr>
            """)

    render_err_html = f'<div class="warning" style="margin-top: 1rem;"><strong>Erro de Renderização:</strong> {e(view.render_error)}</div>' if view.render_error else ""

    pub_status_html = ""
    if view.publication:
        pub_err = f'<div style="color: var(--bad);">{e(view.publication.error)}</div>' if view.publication.error else ""
        pub_status_html = f"""
          <div class="card" style="margin-top: 1rem;">
            <div class="card-label">Publicação</div>
            <div>Status: <span class="pill pill-{e(view.publication.status.value)}">{e(view.publication.status.value)}</span> (tentativa {view.publication.attempt})</div>
            {pub_err}
          </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Faceless Studio — Detalhe do Vídeo</title>
  <style nonce="{nonce}">{CSS}</style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <div style="font-size: 0.85rem;"><a href="/studio/panel">&larr; Voltar ao Painel</a></div>
        <h1>{e(v.topic)}</h1>
        <div style="margin-top: 0.25rem;">
          <span class="pill pill-{e(view.stage.value)}">{e(view.stage.value)}</span>
          <span style="font-size: 0.85rem; color: var(--text-muted); margin-left: 0.5rem;">Custo: {e(view.cost_text)}</span>
        </div>
      </div>
      <div>
        <a class="btn btn-primary" href="/studio/videos/{e(v.id)}/preview">Abrir Prévia e Aprovar</a>
      </div>
    </header>

    <div class="layout-detail">
      <div class="card">
        <h2>Linha do Tempo dos Passos</h2>
        <ul class="timeline">
          {''.join(steps_html)}
        </ul>
        {render_err_html}
        {pub_status_html}
      </div>

      <div class="card">
        <h2>Registro de Uso de Modelos</h2>
        <table>
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
    </div>
  </div>
</body>
</html>"""
    return html_content, _headers(nonce)
