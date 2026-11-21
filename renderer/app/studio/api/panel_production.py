"""Páginas do fluxo único de produção do painel.

`Novo vídeo` (F2-02/F2-03) e `Execução` (F2-04/F2-05) renderizam **somente** dado real do
Studio ou estado vazio explícito. Nada do conteúdo ilustrativo do mockup vaza para o HTML:
IDs, eventos e uso de modelos ficam no `<details>` fechado; a área principal mostra etapa,
próxima ação, custo rotulado e o que fazer em caso de falha.

Sem barra de progresso e sem percentual: a produção não é linear — mostramos "etapa N de M".
A casca (tokens e sidebar em dois grupos) vem de `api/panel.py` (G1); este módulo só acrescenta
o layout das duas telas novas.
"""
import html
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from ..application.panel import CostBreakdown, CostKind, MonthCost, cost_kind, cost_label
from ..application.ports import UsageInfo
from ..application.production import has_live_lease
from ..domain.production_run import (
    OutboxEvent,
    ProductionRun,
    ProductionStage,
    RunState,
    StageExecution,
    StageState,
)
from . import panel as shell

e = lambda value: html.escape(str(value if value is not None else ""), quote=True)  # noqa: E731

# Rótulos humanos das etapas canônicas (F1-05). "Assets" cobre imagens e voz nesta versão.
STAGE_LABELS = {
    ProductionStage.RESEARCH: "Fontes",
    ProductionStage.SCRIPT: "Roteiro",
    ProductionStage.FACTCHECK: "Fact-check",
    ProductionStage.STORYBOARD: "Cenas",
    ProductionStage.ASSETS: "Voz e imagens",
    ProductionStage.RENDER: "Render",
    ProductionStage.QA: "QA",
    ProductionStage.APPROVAL: "Aprovação",
    ProductionStage.PUBLISH: "Publicação",
}

# Estado por etapa: sempre texto + ícone (nunca só cor). `state-icon` é o ícone da casca.
_STAGE_STATE = {
    StageState.SUCCEEDED: ("s-done", "✓", "Concluído"),
    StageState.RUNNING: ("s-run", "◐", "Em execução"),
    StageState.WAITING_HUMAN: ("s-act", "!", "Ação necessária"),
    StageState.FAILED: ("s-fail", "!", "Ação necessária"),
    StageState.CANCELLED: ("s-fail", "×", "Cancelado"),
    StageState.SKIPPED: ("state-idle", "·", "Pulado"),
    StageState.PENDING: ("state-idle", "○", "Sem execução ainda"),
}

_RUN_STATE = {
    RunState.CREATED: ("state-idle", "○", "Criada"),
    RunState.RUNNING: ("s-run", "◐", "Em execução"),
    RunState.WAITING_HUMAN: ("s-act", "!", "Ação necessária"),
    RunState.PAUSED: ("s-act", "!", "Pausada"),
    RunState.FAILED: ("s-fail", "!", "Falhou"),
    RunState.CANCELLED: ("s-fail", "×", "Cancelada"),
    RunState.SUCCEEDED: ("s-done", "✓", "Concluída"),
}

_MODE_LABELS = {"INTERACTIVE": "modo interativo", "BUDGET_GUARDED": "modo com teto"}

_NEXT_ACTION_LABELS = {
    "run": "executar a próxima etapa",
    "retry": "tentar novamente a etapa que falhou",
    "resume": "retomar a execução",
    "approve": "revisar e aprovar o artefato",
}

# Ações condicionadas ao estado — nunca renderizar ação inválida.
# RUN_TRANSITIONS (domain/production_run.py) é a fonte de verdade:
#   resume aceita WAITING_HUMAN/PAUSED/FAILED; retry só de FAILED; cancel de
#   CREATED/RUNNING/WAITING_HUMAN/PAUSED/FAILED.
_RESUMABLE_STATES = (RunState.WAITING_HUMAN, RunState.PAUSED, RunState.FAILED)
_CANCELLABLE_STATES = (RunState.CREATED, RunState.RUNNING, RunState.WAITING_HUMAN,
                       RunState.PAUSED, RunState.FAILED)

# Campos cuja capacidade real ainda não existe: desabilitados com motivo em texto,
# nunca um formulário que finge funcionar.
_NO_BACKEND = "Indisponível: este dado ainda não é persistido pelo Studio nesta versão."

PRODUCTION_CSS = """
.wizard-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.9rem 1.1rem;
  margin-top: 1rem;
}
.wizard-grid .field-full { grid-column: 1 / -1; }
.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field .hint { color: var(--text-dim); font-size: 0.72rem; line-height: 1.4; }
.field .why { color: var(--warn); font-size: 0.72rem; line-height: 1.4; }
.field input[disabled], .field select[disabled] {
  background: #0b111d; color: var(--text-dim); cursor: not-allowed; opacity: 0.85;
}
.origin-chips { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.75rem 0 0.25rem; }
.page-goal { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.35rem; }
.page-goal b { color: var(--text); }
.act-card { border-color: #7a2436; }
.act-card h2 { margin-top: 0.5rem; }
.exec-meta { color: var(--text-dim); font-size: 0.78rem; margin-top: 0.25rem; }
@media (max-width: 820px) {
  .wizard-grid { grid-template-columns: minmax(0, 1fr); }
}
"""


@dataclass(frozen=True)
class PipelineStage:
    """Etapa canônica do pipeline com a disponibilidade real declarada pelo coordenador."""

    stage: ProductionStage
    label: str
    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class NewVideoView:
    """Dados reais do wizard. Onde não há capacidade, o controle entra desabilitado."""

    projects: list[tuple[str, str]]
    month: MonthCost
    pipeline: tuple[PipelineStage, ...]
    selected_project_id: str = ""


@dataclass(frozen=True)
class ExecutionView:
    """Projeção real de uma execução (D2) + uso de modelos do vídeo para o diagnóstico."""

    topic: str
    run: ProductionRun
    stages: tuple[StageExecution, ...]
    next_action: str | None
    next_stage: ProductionStage | None
    mode: str
    month: MonthCost
    unavailable_stages: tuple[tuple[ProductionStage, str], ...] = ()
    cost: CostBreakdown = field(default_factory=CostBreakdown)
    usage: tuple[UsageInfo, ...] = ()
    events: tuple[OutboxEvent, ...] = ()
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Utilitários de apresentação
# ---------------------------------------------------------------------------


def _badge(kind: str, icon: str, label: str) -> str:
    return (
        f'<span class="state {e(kind)}"><span class="state-icon" aria-hidden="true">{e(icon)}</span> '
        f'<span>{e(label)}</span></span>'
    )


def stage_badge(state: StageState) -> str:
    kind, icon, label = _STAGE_STATE.get(state, ("state-idle", "○", "Sem execução ainda"))
    return _badge(kind, icon, label)


def run_badge(state: RunState) -> str:
    kind, icon, label = _RUN_STATE.get(state, ("state-idle", "○", "Estado desconhecido"))
    return _badge(kind, icon, label)


def elapsed_text(created_at: datetime | None, now: datetime) -> str:
    """Tempo decorrido honesto. Sem criação registrada, diz que falta o registro."""
    if created_at is None:
        return "sem horário de início registrado"
    seconds = int((now - created_at).total_seconds())
    if seconds < 0:
        return "horário de início no futuro (relógio divergente)"
    if seconds < 60:
        return "há menos de 1 min"
    minutes = seconds // 60
    if minutes < 60:
        return f"há {minutes} min"
    hours, rest = divmod(minutes, 60)
    if rest == 0:
        return f"há {hours} h"
    return f"há {hours} h {rest} min"


def _current_stage(stages: Sequence[StageExecution]) -> ProductionStage | None:
    for execution in stages:
        if execution.state in (StageState.RUNNING, StageState.WAITING_HUMAN, StageState.FAILED):
            return execution.stage_id
    for execution in stages:
        if execution.state is StageState.PENDING:
            return execution.stage_id
    return None


def _stage_index(stages: Sequence[StageExecution], stage: ProductionStage | None) -> int | None:
    if stage is None:
        return None
    for index, execution in enumerate(stages, start=1):
        if execution.stage_id is stage:
            return index
    return None


def next_action_text(action: str | None, next_stage: ProductionStage | None) -> str:
    if action is None:
        return "Nada a fazer: a execução está em estado terminal."
    text = _NEXT_ACTION_LABELS.get(action, action)
    if action == "run" and next_stage is not None:
        text = f"{text} ({STAGE_LABELS.get(next_stage, next_stage.value)})"
    return text


def _cost_cell(kind: CostKind, cost_usd: float) -> str:
    if kind in (CostKind.FREE, CostKind.UNKNOWN):
        return cost_label(kind)
    return f"{cost_label(kind)} US$ {cost_usd:.2f}".replace(".", ",")


# ---------------------------------------------------------------------------
# Matriz de ações por estado (F2-05)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunAction:
    key: str          # pause | resume | cancel | retry
    label: str
    primary: bool = False


def available_actions(state: RunState, next_action: str | None, *, live_lease: bool = True) -> tuple[RunAction, ...]:
    """Ações válidas para o estado atual do run, na ordem do mockup. Nunca habilitar inválida.

    `live_lease` só importa em `RUNNING`: sem lease vivo o run está órfão (o worker morreu) e
    "Continuar" re-lança o worker sem escrever estado. Com lease vivo permanece só "Pausar" —
    re-lançar criaria um worker duplicado sobre a mesma etapa.
    """
    actions: list[RunAction] = []
    if state is RunState.RUNNING:
        if not live_lease:
            actions.append(RunAction("resume", "Continuar", primary=True))
        actions.append(RunAction("pause", "Pausar"))
    if state in _RESUMABLE_STATES:
        actions.append(RunAction("resume", "Continuar"))
    if state is RunState.FAILED:
        actions.append(RunAction("retry", "Tentar novamente", primary=True))
    if state in _CANCELLABLE_STATES:
        actions.append(RunAction("cancel", "Cancelar"))
    return tuple(actions)


def artifact_available(next_action: str | None) -> bool:
    """`Revisar` só existe quando há artefato: a próxima ação é aprovar o render."""
    return next_action == "approve"


# ---------------------------------------------------------------------------
# Wizard `Novo vídeo` (F2-02/F2-03)
# ---------------------------------------------------------------------------


def _wizard_field(label: str, field_id: str, control_html: str, *, hint: str | None = None,
                  why: str | None = None, full: bool = False) -> str:
    classes = "field field-full" if full else "field"
    hint_html = f'<span class="hint">{e(hint)}</span>' if hint else ""
    if why:
        hint_html += f'<span class="why" role="note">Motivo: {e(why)}</span>'
    return (
        f'<div class="{classes}"><label for="{e(field_id)}">{e(label)}</label>'
        f'{control_html}{hint_html}</div>'
    )


def _pipeline_rail_html(pipeline: Sequence[PipelineStage]) -> str:
    items = []
    for index, entry in enumerate(pipeline, start=1):
        tag = "" if entry.available else ' <span class="tag">indisponível</span>'
        probe = ""
        if not entry.available and entry.reason:
            probe = f'<span class="hint">Motivo: {e(entry.reason)}</span>'
        items.append(f'<li><span class="n">{index}</span> {e(entry.label)}{tag}{probe}</li>')
    if not items:
        return '<p class="muted">Nenhuma etapa declarada pelo coordenador.</p>'
    return f'<ol class="steps" aria-label="Etapas da produção">{"".join(items)}</ol>'


def _wizard_fields_html(view: NewVideoView) -> str:
    if view.projects:
        options = "".join(
            f'<option value="{e(pid)}"{" selected" if pid == view.selected_project_id else ""}>{e(name)}</option>'
            for pid, name in view.projects
        )
        canal_html = f'<select id="wiz-canal" name="project_id">{options}</select>'
        canal_hint = "Define voz, identidade e orçamento."
        canal_why = None
    else:
        canal_html = '<select id="wiz-canal" name="project_id" disabled><option value="">Nenhum canal cadastrado</option></select>'
        canal_hint = None
        canal_why = "Nenhum canal cadastrado neste Studio."

    fields = [
        _wizard_field(
            "Tema", "wiz-tema",
            '<input type="text" id="wiz-tema" name="topic" minlength="3" maxlength="300" '
            'placeholder="Uma frase basta" required>',
            hint="Uma frase basta. O roteiro é seu; a pesquisa confirma.", full=True,
        ),
        _wizard_field(
            "Canal", "wiz-canal", canal_html, hint=canal_hint, why=canal_why,
        ),
        _wizard_field(
            "Formato", "wiz-formato",
            '<select id="wiz-formato" name="format">'
            '<option value="short">Short (vertical 1080x1920)</option>'
            '<option value="long">Long (horizontal 1920x1080)</option></select>',
            hint="Define a proporção do vídeo entregue.",
        ),
        _wizard_field(
            "Público", "wiz-publico",
            '<input type="text" id="wiz-publico" name="audience" disabled value="">',
            why=_NO_BACKEND,
        ),
        _wizard_field(
            "Duração alvo", "wiz-duracao",
            '<select id="wiz-duracao" name="duration_s" disabled>'
            '<option selected>480 s (8 min) — padrão</option>'
            '<option>60 s (Short)</option><option>1200 s (20 min)</option></select>',
            why="A duração alvo não é persistida; fica no briefing (fatia de briefing).",
        ),
        _wizard_field(
            "Estilo de edição", "wiz-estilo",
            '<select id="wiz-estilo" name="style" disabled>'
            '<option selected>Preset do canal</option></select>',
            why="Preset estruturado só na fatia de estilo; ainda não é escolha por vídeo.",
        ),
        _wizard_field(
            "Idioma", "wiz-idioma",
            '<select id="wiz-idioma" name="language" disabled>'
            '<option selected>Português (Brasil)</option><option>Inglês (EUA)</option></select>',
            why="O idioma é definido pelo canal; ainda não é escolha por vídeo.",
        ),
        _wizard_field(
            "Teto de custo deste vídeo", "wiz-teto",
            '<input type="text" id="wiz-teto" name="budget_cap" disabled value="" '
            'placeholder="Configurado no servidor">',
            why="O teto por vídeo é configuração do servidor (MAX_COST_USD_PER_VIDEO); não é editável por vídeo.",
        ),
    ]
    return "".join(fields)


def _wizard_cost_line(view: NewVideoView) -> str:
    budget = (
        "Sem registro de uso neste mês."
        if view.month.breakdown.calls == 0
        else f"Registrado no mês: {view.month.text}."
    )
    return (
        f"{e(budget)} O Studio não projeta o custo antes de produzir; "
        "custo desconhecido não é tratado como zero."
    )


def render_new_video(view: NewVideoView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    side_card = shell.budget_side_card(view.month)
    pipeline_rail = _pipeline_rail_html(view.pipeline)
    unavailable = [entry for entry in view.pipeline if not entry.available]
    unavailable_note = (
        '<p class="fine">Etapas indisponíveis nesta versão: '
        + "; ".join(f"{e(entry.label)} — {e(entry.reason or 'sem backend')}" for entry in unavailable)
        + ".</p>"
        if unavailable else ""
    )

    page = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>Faceless Studio — Novo vídeo</title>
  <style nonce="{nonce}">{shell.CSS}{PRODUCTION_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#novo-main">Ir para o conteúdo</a>
  <div class="app-layout">
    {shell.render_sidebar(active="producao", base_href="/studio/panel", side_card_html=side_card, channels_href="/studio/canais")}
    <main class="main-content" id="novo-main">
      <div class="card">
        <div class="spread">
          <div>
            <h1 id="novo-heading">Novo vídeo</h1>
            <p class="page-goal">Ação primária: <b>produzir vídeo</b>. Nada é cobrado antes do teto ser confirmado.</p>
          </div>
        </div>

        <h2 style="margin-top:1rem">Transforme uma ideia em um vídeo publicado</h2>
        <p class="dim">Quatro decisões. O resto o Studio resolve por você.</p>

        <div class="origin-chips" role="tablist" aria-label="Origem do vídeo">
          <button class="cat-pill active" role="tab" aria-selected="true" aria-pressed="true" type="button">Minha ideia</button>
          <a class="cat-pill" role="tab" aria-selected="false" aria-pressed="false" href="/studio/panel/tendencias">Tendência</a>
          <button class="cat-pill" role="tab" aria-selected="false" aria-pressed="false" type="button" aria-disabled="true" tabindex="-1" disabled>Série</button>
        </div>

        <form id="new-video-wizard">
          <div class="wizard-grid">
            {_wizard_fields_html(view)}
          </div>
          <div class="spread" style="margin-top:1.1rem">
            <p class="fine" style="margin:0">{_wizard_cost_line(view)}</p>
            <button class="btn btn-primary" type="submit" id="btn-produzir-video">Produzir vídeo</button>
          </div>
          <div id="wizard-feedback" class="form-feedback" role="status" aria-live="polite"></div>
        </form>
      </div>

      <div class="card empty">
        <h2>Modo de execução</h2>
        <p class="muted" style="margin-top:0.4rem">
          <b>Interativo</b> (você aprova o roteiro) ou <b>com teto</b> (o Studio segue sozinho até o teto).
          Publicar nunca é automático.
        </p>
      </div>
    </main>

    <aside class="rail" aria-label="Resumo">
      <section class="card" aria-labelledby="h-acontece">
        <h2 id="h-acontece">O que acontece ao produzir</h2>
        {pipeline_rail}
        <p class="fine">Pausas humanas: após o roteiro (modo interativo) e antes da aprovação.</p>
        {unavailable_note}
      </section>
    </aside>
  </div>
  <script nonce="{nonce}">
    const wizard = document.getElementById('new-video-wizard');
    if (wizard) {{
      wizard.addEventListener('submit', async (ev) => {{
        ev.preventDefault();
        const btn = document.getElementById('btn-produzir-video');
        const feedback = document.getElementById('wizard-feedback');
        const topic = (document.getElementById('wiz-tema').value || '').trim();
        const project_id = document.getElementById('wiz-canal').value;
        const format = document.getElementById('wiz-formato').value;
        if (!topic) {{ feedback.textContent = 'Informe o tema.'; return; }}
        if (!project_id) {{ feedback.textContent = 'Selecione um canal.'; return; }}
        if (btn) btn.disabled = true;
        feedback.textContent = 'Criando o vídeo...';
        try {{
          const created = await fetch('/studio/videos', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ project_id, topic, format }})
          }});
          const video = await created.json().catch(() => ({{}}));
          if (!created.ok || !video.id) {{
            feedback.textContent = 'Erro ao criar: ' + (typeof video.detail === 'string' ? video.detail : 'resposta inválida');
            if (btn) btn.disabled = false;
            return;
          }}
          const key = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
          feedback.textContent = 'Iniciando a produção...';
          const started = await fetch('/studio/videos/' + encodeURIComponent(video.id) + '/production-runs', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'Idempotency-Key': key }},
            body: JSON.stringify({{}})
          }});
          const run = await started.json().catch(() => ({{}}));
          if (!started.ok || !run.run_id) {{
            feedback.textContent = 'Erro ao iniciar: ' + (typeof run.detail === 'string' ? run.detail : 'resposta inválida');
            if (btn) btn.disabled = false;
            return;
          }}
          location.href = '/studio/panel/videos/' + encodeURIComponent(video.id) +
            '/production-runs/' + encodeURIComponent(run.run_id);
        }} catch (err) {{
          feedback.textContent = 'Falha de rede: ' + err.message;
          if (btn) btn.disabled = false;
        }}
      }});
    }}
  </script>
</body>
</html>"""
    return page, shell._headers(nonce)


# ---------------------------------------------------------------------------
# Página de execução (F2-04/F2-05)
# ---------------------------------------------------------------------------


def _steps_html(view: ExecutionView) -> tuple[str, int, int]:
    current = _current_stage(view.stages)
    index = _stage_index(view.stages, current)
    items = []
    for execution in view.stages:
        aria = ' aria-current="step"' if execution.stage_id is current else ""
        label = STAGE_LABELS.get(execution.stage_id, execution.stage_id.value)
        items.append(f'<li{aria}>{stage_badge(execution.state)} <span>{e(label)}</span></li>')
    if not items:
        return '<p class="muted">Nenhuma etapa registrada nesta execução.</p>', 0, 0
    total = len(view.stages)
    return f'<ol class="steps" aria-label="Etapas da produção">{"".join(items)}</ol>', index or total, total


def _act_card(title: str, what: str, detail_html: str, buttons: Sequence[str]) -> str:
    row = f'<div class="row" style="margin-top:0.75rem">{"".join(buttons)}</div>' if buttons else ""
    return f"""
      <div class="card act-card">
        <span class="state s-fail"><span class="state-icon" aria-hidden="true">!</span> <span>Ação necessária</span></span>
        <h2 style="margin-top:0.6rem">{e(title)}</h2>
        <p class="muted" style="margin:0.5rem 0 0">{e(what)}</p>
        {detail_html}
        {row}
        <p class="fine">Detalhe técnico (IDs, eventos, mensagem crua) em <b>Avançado</b>, no fim da página — não aqui.</p>
      </div>
    """


def _action_button(view: ExecutionView, key: str, label: str, *, primary: bool = False) -> str:
    css = "btn btn-primary" if primary else "btn"
    return (
        f'<button type="button" class="{css}" data-run-action="{e(key)}" '
        f'data-video-id="{e(view.run.video_id)}" data-run-id="{e(view.run.run_id)}">{e(label)}</button>'
    )


def _action_card_html(view: ExecutionView) -> str:
    """Card de ação necessária: o que fazer + retry, nunca aqui o detalhe técnico."""
    state = view.run.state
    failed = [s for s in view.stages if s.state is StageState.FAILED]
    if state is RunState.FAILED or failed:
        stage = failed[-1] if failed else None
        stage_label = STAGE_LABELS.get(stage.stage_id, stage.stage_id.value) if stage else None
        title = f"A execução falhou na etapa {stage_label}" if stage_label else "A execução falhou"
        raw = (stage.error if stage and stage.error else None) or view.run.reason
        what = ("O que fazer: revise a etapa que falhou e use «Tentar novamente». "
                "Nada foi publicado.")
        detail = f'<p class="muted" style="margin:0.5rem 0 0">{e(raw)}</p>' if raw else ""
        buttons = []
        if state is RunState.FAILED:
            buttons.append(_action_button(view, "retry", "Tentar novamente", primary=True))
        buttons.append(
            f'<a class="btn" href="/studio/panel/videos/{e(view.run.video_id)}">Revisar</a>'
        )
        return _act_card(title, what, detail, buttons)
    if state is RunState.WAITING_HUMAN and view.next_action == "approve":
        title = "Aprovação necessária antes de continuar"
        what = ("O que fazer: revise o artefato renderizado e aprove no vídeo para seguir. "
                "A publicação nunca é automática.")
        buttons = [f'<a class="btn btn-primary" href="/studio/panel/videos/{e(view.run.video_id)}">Revisar</a>']
        return _act_card(title, what, "", buttons)
    if state in (RunState.WAITING_HUMAN, RunState.PAUSED):
        title = "A execução está aguardando você"
        what = "O que fazer: retome a execução para continuar de onde parou."
        buttons = [_action_button(view, "resume", "Continuar", primary=True)]
        return _act_card(title, what, "", buttons)
    return ""


def _usage_rows_html(view: ExecutionView) -> str:
    if not view.usage:
        return '<p class="muted">Sem registro de uso de modelos para este vídeo.</p>'
    rows = []
    for usage in view.usage:
        classified = cost_kind(usage.cost_confirmation_kind, usage.provider, usage.model, usage.cost_usd)
        rows.append(
            f'<div class="kv"><span>{e(usage.step)} · {e(usage.provider)}/{e(usage.model)}</span>'
            f'<span>{e(_cost_cell(classified, usage.cost_usd))}</span></div>'
        )
    return "".join(rows)


def _event_rows_html(view: ExecutionView) -> str:
    if not view.events:
        return '<p class="muted">Nenhum evento registrado para esta execução.</p>'
    rows = []
    for event in view.events:
        head = event.event_type.value
        if event.stage_id is not None:
            head += " · " + STAGE_LABELS.get(event.stage_id, event.stage_id.value)
        if isinstance(event.payload, dict) and event.payload.get("error"):
            head += " · " + str(event.payload["error"])
        when = event.created_at.strftime("%d/%m %H:%M:%S") if event.created_at else "sem horário"
        rows.append(f'<div class="kv"><span>{e(head)}</span><span>{e(when)}</span></div>')
    return "".join(rows)


def _advanced_html(view: ExecutionView) -> str:
    return f"""
      <details class="advanced" id="advanced-diagnostics">
        <summary class="advanced-summary">Avançado — diagnóstico (IDs, eventos, uso de modelos)</summary>
        <div class="advanced-body">
          <p>Execução <code>{e(view.run.run_id)}</code> · vídeo <code>{e(view.run.video_id)}</code></p>
          <p>Modo declarado pelo servidor: <code>{e(view.mode)}</code>.</p>
          <p><b>Eventos da execução</b></p>
          {_event_rows_html(view)}
          <p><b>Registro de uso de modelos</b></p>
          {_usage_rows_html(view)}
        </div>
      </details>
    """


def _rail_actions_html(view: ExecutionView) -> str:
    live_lease = has_live_lease(view.stages, view.now)
    actions = available_actions(view.run.state, view.next_action, live_lease=live_lease)
    buttons = [_action_button(view, a.key, a.label, primary=a.primary) for a in actions]
    if artifact_available(view.next_action):
        buttons.append(f'<a class="btn" href="/studio/panel/videos/{e(view.run.video_id)}">Revisar</a>')
    body = (
        f'<div class="row" style="margin-top:0.5rem">{"".join(buttons)}</div>'
        if buttons else '<p class="muted">Nenhuma ação disponível neste estado.</p>'
    )
    return f"""
      <section class="card" aria-labelledby="h-acoes">
        <h2 id="h-acoes">Ações</h2>
        {body}
        <div id="run-action-feedback" class="form-feedback" role="status" aria-live="polite"></div>
        <p class="fine">“Revisar” só aparece quando existe artefato para revisar.</p>
      </section>
    """


def render_execution(view: ExecutionView) -> tuple[str, dict[str, str]]:
    nonce = secrets.token_urlsafe(16)
    steps_html, index, total = _steps_html(view)
    position = f'Etapa <b>{index} de {total}</b>. ' if total else ""
    current = _current_stage(view.stages)
    current_label = (
        STAGE_LABELS.get(current, current.value) if current is not None else "nenhuma"
    )
    next_line = next_action_text(view.next_action, view.next_stage)
    mode_label = _MODE_LABELS.get(view.mode, view.mode)
    action_card = _action_card_html(view)

    unavailable = "".join(
        f'<div class="kv"><span>{e(STAGE_LABELS.get(stage, stage.value))}</span><span>{e(reason)}</span></div>'
        for stage, reason in view.unavailable_stages
    )
    unavailable_card = (
        f'<section class="card" aria-labelledby="h-indisp"><h2 id="h-indisp">Indisponível nesta versão</h2>'
        f'{unavailable}</section>'
        if unavailable else ""
    )

    page = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>Faceless Studio — Execução</title>
  <style nonce="{nonce}">{shell.CSS}{PRODUCTION_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#exec-main">Ir para o conteúdo</a>
  <div class="app-layout">
    {shell.render_sidebar(active="producao", base_href="/studio/panel", side_card_html=shell.budget_side_card(view.month), channels_href="/studio/canais")}
    <main class="main-content" id="exec-main">
      <div class="card">
        <div class="spread">
          <div>
            <h1 id="exec-heading">{e(view.topic)}</h1>
            <p class="exec-meta">Execução iniciada {e(elapsed_text(view.run.created_at, view.now))} · {e(mode_label)}</p>
          </div>
          {run_badge(view.run.state)}
        </div>

        {steps_html}
        <p class="fine">{position}Etapa atual: <b>{e(current_label)}</b>. Próxima ação: <b>{e(next_line)}</b>.
        Não há barra de progresso nem percentual: o trabalho não é linear e etapas podem ser refeitas.</p>
      </div>

      {action_card}

      {_advanced_html(view)}
    </main>

    <aside class="rail" aria-label="Resumo">
      <section class="card" aria-labelledby="h-custo-exec">
        <h2 id="h-custo-exec">Custo desta execução</h2>
        {shell.cost_breakdown_rows(view.cost) if view.cost.calls else '<p class="muted">Sem registro de uso de IA para este vídeo.</p>'}
        <p class="fine">O total é o custo registrado do vídeo: não há atribuição de custo por execução.
        Real e estimado nunca são somados num número só; ausência de custo não é zero.</p>
      </section>
      {_rail_actions_html(view)}
      {unavailable_card}
    </aside>
  </div>
  <script nonce="{nonce}">
    document.querySelectorAll('[data-run-action]').forEach((btn) => {{
      btn.addEventListener('click', async () => {{
        const action = btn.getAttribute('data-run-action');
        const videoId = btn.getAttribute('data-video-id');
        const runId = btn.getAttribute('data-run-id');
        const feedback = document.getElementById('run-action-feedback');
        const url = '/studio/videos/' + encodeURIComponent(videoId) +
          '/production-runs/' + encodeURIComponent(runId) + '/' + action;
        btn.disabled = true;
        if (feedback) feedback.textContent = 'Aplicando...';
        try {{
          const res = await fetch(url, {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{}})
          }});
          const data = await res.json().catch(() => ({{}}));
          if (res.ok) {{
            if (feedback) feedback.textContent = 'Feito. Atualizando...';
            location.reload();
          }} else {{
            btn.disabled = false;
            if (feedback) feedback.textContent = 'Não foi possível: ' +
              (typeof data.detail === 'string' ? data.detail : 'o estado atual não permite esta ação');
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