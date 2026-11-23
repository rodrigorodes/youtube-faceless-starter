"""Páginas do fluxo único de produção do painel.

`Novo vídeo` (F2-02/F2-03) e `Execução` (F2-04/F2-05) renderizam **somente** dado real do
Studio ou estado vazio explícito. Nada do conteúdo ilustrativo do mockup vaza para o HTML:
IDs, eventos e uso de modelos ficam no `<details>` fechado; a área principal mostra etapa,
próxima ação, custo rotulado e o que fazer em caso de falha.

A página de execução porta a aba Produção e o `progressCard` do protótipo (`prototype-v4-v3`)
para o workspace do vídeo, na casca V3. O progresso é por etapas reais (concluídas/total), nunca
um percentual inventado; "etapa N de M" continua dito em texto. O wizard `Novo vídeo` ainda usa a
casca legada de `api/panel.py` e o `PRODUCTION_CSS` abaixo.
"""
import html
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from ..application.panel import CostBreakdown, CostKind, MonthCost, cost_breakdown, cost_kind, cost_label
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
from ..domain.panel import Stage
from . import panel as shell
from .erro_js import ERRO_JS
from .panel_video_nav import area_href, default_area, video_area_nav
from .panel_videos import _ESTADO

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

_RUN_LABEL = {
    RunState.CREATED: "Criada",
    RunState.RUNNING: "Em execução",
    RunState.WAITING_HUMAN: "Aguardando você",
    RunState.PAUSED: "Pausada",
    RunState.FAILED: "Falhou",
    RunState.CANCELLED: "Cancelada",
    RunState.SUCCEEDED: "Concluída",
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
    # F02.T02/G15: a biblioteca real de estilos (id, nome) — nunca nomes fixos no HTML.
    styles: tuple[tuple[str, str], ...] = ()
    # Nome do estilo que o canal selecionado herda (None = canal sem estilo definido).
    inherited_style_name: str | None = None
    # F02.T04: o que o canal realmente define (idioma/voz). None = canal sem perfil.
    channel_language: str | None = None
    channel_voice: str | None = None
    has_profile: bool = False
    channel_profile: Any = None
    channel_default_mode: str = "piloto"
    channel_default_format: str = "short"


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
    # `VideoDetailView` do vídeo (cabeçalho do workspace). Sem ele, o cabeçalho usa só o tema.
    detail: Any = None


# ---------------------------------------------------------------------------
# Utilitários de apresentação
# ---------------------------------------------------------------------------


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
  <meta name="color-scheme" content="dark light">
  <title>Faceless Studio — Novo vídeo</title>
  <style nonce="{nonce}">{shell.CSS}{PRODUCTION_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#novo-main">Ir para o conteúdo</a>
  <div class="app-layout">
    {shell.render_sidebar(active="producao", base_href="/studio/panel", side_card_html=side_card, channels_href="/studio/canais", nonce=nonce)}
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
    {ERRO_JS}
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
            feedback.textContent = 'Erro ao criar: ' + (window.StudioErro.texto(video, 'resposta inválida'));
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
            feedback.textContent = 'Erro ao iniciar: ' + (window.StudioErro.texto(run, 'resposta inválida'));
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
# Página de execução (F2-04/F2-05) — porta a aba Produção (`tabProd`) e o `progressCard`
# do protótipo para o workspace do vídeo, só com etapas reais da execução.
# ---------------------------------------------------------------------------

# Estado da etapa → (classe do `.ic`, glifo, texto, classe do pill). Sempre ícone + texto.
_STEP_VIEW = {
    StageState.SUCCEEDED: ("ok", "✓", "Concluída", "ok"),
    StageState.RUNNING: ("run", "…", "Em andamento", "accent"),
    StageState.WAITING_HUMAN: ("", "!", "Aguardando você", "warn"),
    StageState.FAILED: ("fail", "✕", "Falhou", "bad"),
    StageState.CANCELLED: ("fail", "×", "Cancelada", "bad"),
    StageState.SKIPPED: ("", "○", "Pulada", ""),
    StageState.PENDING: ("", "○", "Aguardando", ""),
}

_RUN_PILL = {
    RunState.CREATED: "",
    RunState.RUNNING: "accent",
    RunState.WAITING_HUMAN: "warn",
    RunState.PAUSED: "warn",
    RunState.FAILED: "bad",
    RunState.CANCELLED: "bad",
    RunState.SUCCEEDED: "ok",
}

ACTIVE_RUN_STATES = (RunState.CREATED, RunState.RUNNING, RunState.WAITING_HUMAN, RunState.PAUSED)
POLL_INTERVAL_MS = 2500

_STEP_ERR_STYLE = "color:var(--bad);font-size:12.5px"


def _usd(value: float) -> str:
    return "US$ " + f"{value:.2f}".replace(".", ",")


def _stage_cost_text(view: ExecutionView, stage: ProductionStage,
                     free_providers: frozenset[str]) -> tuple[str, bool]:
    """Custo da etapa e se ele foi realmente medido.

    O uso registrado só é atribuído a uma etapa quando o `step` do registro é o id dela; do
    contrário a etapa mostra "não medido" — nunca zero. Custo desconhecido nunca é somado.
    """
    rows = [(u.provider, u.model, u.cost_usd, u.cost_confirmation_kind)
            for u in view.usage if u.step == stage.value]
    breakdown = cost_breakdown(rows, free_providers)
    parts = []
    if breakdown.real_calls:
        parts.append(f"Real {_usd(breakdown.real_usd)}")
    if breakdown.estimate_calls:
        parts.append(f"Estimado {_usd(breakdown.estimate_usd)}")
    if breakdown.free_calls and not parts and not breakdown.unknown_calls:
        parts.append("Sem custo")
    measured = bool(parts) and not breakdown.unknown_calls
    if breakdown.unknown_calls and parts:
        parts.append("parte não medida")
    return (" · ".join(parts) if parts else "não medido"), measured


def _cost_headline(cost: CostBreakdown) -> str:
    if cost.calls == 0:
        return "sem registro de uso"
    parts = []
    if cost.real_calls:
        parts.append(f"Real {_usd(cost.real_usd)}")
    if cost.estimate_calls:
        parts.append(f"Estimado {_usd(cost.estimate_usd)}")
    if not parts:
        parts.append("sem custo" if not cost.unknown_calls else "não medido")
    return " · ".join(parts)


def _label_rows(rows: Sequence[tuple[str, str]]) -> str:
    return "".join(
        f'<div class="between sub" style="padding:2px 0"><span>{e(label)}</span><span>{e(value)}</span></div>'
        for label, value in rows
    )


def _cost_rows_html(cost: CostBreakdown) -> str:
    return _label_rows([
        ("Real", _usd(cost.real_usd) if cost.real_calls else "nenhum"),
        ("Estimado", _usd(cost.estimate_usd) if cost.estimate_calls else "nenhum"),
        ("Sem custo", f"{cost.free_calls} chamada(s)" if cost.free_calls else "nenhum"),
        ("Desconhecido", f"{cost.unknown_calls} chamada(s)" if cost.unknown_calls else "nenhum"),
    ])


def _position_html(view: ExecutionView) -> str:
    current = _current_stage(view.stages)
    index = _stage_index(view.stages, current)
    total = len(view.stages)
    position = f"Etapa <b>{index or total} de {total}</b>. " if total else ""
    current_label = STAGE_LABELS.get(current, current.value) if current is not None else "nenhuma"
    next_line = next_action_text(view.next_action, view.next_stage)
    return (f'{position}Etapa atual: <b>{e(current_label)}</b>. '
            f'Próxima ação: <b>{e(next_line)}</b>.')


def _step_rows_html(view: ExecutionView, free_providers: frozenset[str]) -> tuple[str, bool]:
    current = _current_stage(view.stages)
    rows, partial = [], False
    for execution in view.stages:
        ic_cls, glyph, text, _ = _STEP_VIEW.get(execution.state, _STEP_VIEW[StageState.PENDING])
        label = STAGE_LABELS.get(execution.stage_id, execution.stage_id.value)
        cost_text, measured = _stage_cost_text(view, execution.stage_id, free_providers)
        partial = partial or not measured
        err = (f'<p data-step-err style="{_STEP_ERR_STYLE}">{e(execution.error)}</p>'
               if execution.state is StageState.FAILED and execution.error else "")
        aria = ' aria-current="step"' if execution.stage_id is current else ""
        rows.append(
            f'<div class="step" data-step="{e(execution.stage_id.value)}"{aria}>'
            f'<span class="ic {ic_cls}" aria-hidden="true">{glyph}</span>'
            f'<div style="flex:1"><b>{e(label)}</b>{err}<p class="sample" data-step-text>{text}</p></div>'
            f'<span class="sample">{e(cost_text)}</span></div>')
    return "".join(rows), partial


def _action_button(view: ExecutionView, key: str, label: str, *, primary: bool = False,
                   small: bool = False) -> str:
    css = "btn" + (" primary" if primary else "") + (" small" if small else "")
    return (
        f'<button type="button" class="{css}" data-run-action="{e(key)}" '
        f'data-video-id="{e(view.run.video_id)}" data-run-id="{e(view.run.run_id)}">{e(label)}</button>'
    )


def _steps_card_html(view: ExecutionView, free_providers: frozenset[str]) -> tuple[str, bool]:
    rows, partial = _step_rows_html(view, free_providers)
    retry = (_action_button(view, "retry", "↻ Retomar de onde parou", primary=True, small=True)
             if view.run.state is RunState.FAILED else "")
    body = rows or '<p class="sub" style="margin-top:8px">Nenhuma etapa registrada nesta execução.</p>'
    position = (f'<p class="sample" id="exec-position" style="margin-top:12px">{_position_html(view)}</p>'
                if view.stages else "")
    return (f'<section class="card" aria-labelledby="h-etapas">'
            f'<div class="between"><h3 id="h-etapas">Etapas da produção</h3>{retry}</div>'
            f'<div style="margin-top:8px">{body}</div>{position}</section>'), partial


def _progress_card_html(view: ExecutionView) -> str:
    """`progressCard` do protótipo: só com a execução ativa, contando etapas reais concluídas."""
    if view.run.state not in ACTIVE_RUN_STATES:
        return ""
    total = len(view.stages)
    done = sum(1 for s in view.stages if s.state is StageState.SUCCEEDED)
    width = round(done / total * 100) if total else 0
    pills = "".join(
        '<span class="pill{cls}" data-pill="{stage}">{glyph} {label}</span>'.format(
            cls=(" " + pill_cls) if pill_cls else "", stage=e(s.stage_id.value), glyph=glyph,
            label=e(STAGE_LABELS.get(s.stage_id, s.stage_id.value)))
        for s in view.stages
        for _, glyph, _, pill_cls in [_STEP_VIEW.get(s.state, _STEP_VIEW[StageState.PENDING])]
    )
    route = " → ".join(STAGE_LABELS.get(s.stage_id, s.stage_id.value) for s in view.stages)
    sub = f"{route}." if route else "Nenhuma etapa registrada nesta execução."
    return (
        f'<section class="card" id="prod-card" aria-labelledby="h-andamento" style="border-color:var(--accent);'
        f'margin-bottom:18px" data-run-state="{e(view.run.state.value)}" '
        f'data-poll-url="/studio/videos/{e(view.run.video_id)}/production-runs/{e(view.run.run_id)}">'
        f'<div class="between"><div><h3 id="h-andamento">⚡ Produção em andamento</h3>'
        f'<p class="sub">{e(sub)}</p></div>'
        f'<span class="pill accent" id="prod-count">{done}/{total} etapas</span></div>'
        f'<div class="prog" aria-hidden="true" style="height:8px;margin-top:12px">'
        f'<b id="prod-bar" style="width:{width}%;transition:width .5s"></b></div>'
        f'<div class="row" style="margin-top:8px">{pills}</div></section>'
    )


def _act_card(title: str, what: str, detail_html: str, buttons: Sequence[str], *, tone: str = "bad") -> str:
    row = f'<div class="row" style="margin-top:12px">{"".join(buttons)}</div>' if buttons else ""
    return f"""
      <section class="card" style="border-color:var(--{tone})" aria-labelledby="h-acao-exec">
        <span class="pill {tone}"><span aria-hidden="true">!</span> Ação necessária</span>
        <h3 id="h-acao-exec" style="margin-top:8px">{e(title)}</h3>
        <div class="note" style="margin:10px 0 0">{e(what)}</div>
        {detail_html}
        {row}
        <p class="sample" style="margin-top:10px">Detalhe técnico (IDs, eventos, mensagem crua) em <b>Diagnóstico técnico</b>.</p>
      </section>
    """


def _revisar_link(view: ExecutionView, *, primary: bool = False) -> str:
    css = "btn primary" if primary else "btn"
    return f'<a class="{css}" href="{area_href(view.run.video_id, "qualidade")}">Revisar</a>'


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
        detail = f'<p class="sub" style="margin-top:10px">{e(raw)}</p>' if raw else ""
        buttons = []
        if state is RunState.FAILED:
            buttons.append(_action_button(view, "retry", "Tentar novamente", primary=True))
        buttons.append(_revisar_link(view))
        return _act_card(title, what, detail, buttons)
    if state is RunState.WAITING_HUMAN and view.next_action == "approve":
        title = "Aprovação necessária antes de continuar"
        what = ("O que fazer: revise o artefato renderizado e aprove no vídeo para seguir. "
                "A publicação nunca é automática.")
        return _act_card(title, what, "", [_revisar_link(view, primary=True)], tone="warn")
    if state in (RunState.WAITING_HUMAN, RunState.PAUSED):
        title = "A execução está aguardando você"
        what = "O que fazer: retome a execução para continuar de onde parou."
        return _act_card(title, what, "", [_action_button(view, "resume", "Continuar", primary=True)],
                         tone="warn")
    return ""


def _rail_actions_html(view: ExecutionView) -> str:
    live_lease = has_live_lease(view.stages, view.now)
    actions = available_actions(view.run.state, view.next_action, live_lease=live_lease)
    buttons = [_action_button(view, a.key, a.label, primary=a.primary) for a in actions]
    if artifact_available(view.next_action):
        buttons.append(_revisar_link(view))
    body = (
        f'<div class="row" style="margin-top:10px">{"".join(buttons)}</div>'
        if buttons else '<p class="sub" style="margin-top:8px">Nenhuma ação disponível neste estado.</p>'
    )
    return f"""
      <section class="card" aria-labelledby="h-acoes">
        <h3 id="h-acoes">Ações</h3>
        {body}
        <div id="run-action-feedback" class="sample" style="margin-top:8px" role="status" aria-live="polite"></div>
        <p class="sample" style="margin-top:8px">“Revisar” só aparece quando existe artefato para revisar.</p>
      </section>
    """


def _usage_rows_html(view: ExecutionView, free_providers: frozenset[str] = frozenset()) -> str:
    if not view.usage:
        return '<p class="sub">Sem registro de uso de modelos para este vídeo.</p>'
    rows = []
    for usage in view.usage:
        classified = cost_kind(usage.cost_confirmation_kind, usage.provider, usage.model,
                               usage.cost_usd, free_providers)
        rows.append((f"{usage.step} · {usage.provider}/{usage.model}",
                     _cost_cell(classified, usage.cost_usd)))
    return _label_rows(rows)


def _event_rows_html(view: ExecutionView) -> str:
    if not view.events:
        return '<p class="sub">Nenhum evento registrado para esta execução.</p>'
    rows = []
    for event in view.events:
        head = event.event_type.value
        if event.stage_id is not None:
            head += " · " + STAGE_LABELS.get(event.stage_id, event.stage_id.value)
        if isinstance(event.payload, dict) and event.payload.get("error"):
            head += " · " + str(event.payload["error"])
        when = event.created_at.strftime("%d/%m %H:%M:%S") if event.created_at else "sem horário"
        rows.append((head, when))
    return _label_rows(rows)


def _diag_html(view: ExecutionView, free_providers: frozenset[str] = frozenset()) -> str:
    """`details.diag` do protótipo + o diagnóstico avançado (IDs, eventos, uso de modelos)."""
    return f"""
      <details class="diag" id="advanced-diagnostics">
        <summary>Diagnóstico técnico</summary>
        <p class="mono" style="margin-top:8px">video_id={e(view.run.video_id)}<br>modo={e(view.mode)}<br>estado={e(view.run.state.value)}<br>execução={e(view.run.run_id)}</p>
        <p style="margin-top:12px"><b>Avançado — diagnóstico (IDs, eventos, uso de modelos)</b></p>
        <p class="sub" style="margin-top:6px">Modo declarado pelo servidor: <span class="mono">{e(view.mode)}</span>.</p>
        <p class="sub" style="margin:10px 0 2px"><b>Eventos da execução</b></p>
        {_event_rows_html(view)}
        <p class="sub" style="margin:10px 0 2px"><b>Registro de uso de modelos</b></p>
        {_usage_rows_html(view, free_providers)}
      </details>
    """


def _cost_card_html(view: ExecutionView, partial: bool) -> str:
    cost = view.cost
    rows = _cost_rows_html(cost) if cost.calls else ""
    if not cost.calls:
        first = "Sem registro de uso de IA para este vídeo."
    elif partial or cost.unknown_calls:
        first = "Etapas sem custo medido não são somadas como zero."
    else:
        first = "Custo registrado pelo uso real do vídeo."
    return (
        '<section class="card" aria-labelledby="h-custo-exec"><h3 id="h-custo-exec">Custo do vídeo</h3>'
        f'<p style="font-size:22px;font-weight:760;margin:6px 0">{e(_cost_headline(cost))}</p>'
        f'{rows}<p class="sample" style="margin-top:8px">{e(first)}</p>'
        '<p class="sample" style="margin-top:6px">O total é o custo registrado do vídeo: não há atribuição '
        'de custo por execução. Real e estimado nunca são somados num número só; ausência de custo '
        'não é zero.</p></section>'
    )


def _unavailable_card_html(view: ExecutionView) -> str:
    if not view.unavailable_stages:
        return ""
    rows = _label_rows([(STAGE_LABELS.get(stage, stage.value), reason)
                        for stage, reason in view.unavailable_stages])
    return (f'<section class="card" aria-labelledby="h-indisp"><h3 id="h-indisp">Indisponível nesta versão</h3>'
            f'<div style="margin-top:6px">{rows}</div></section>')


def _version_dialog(detail) -> str:
    if detail is not None and detail.stage in (Stage.AWAITING_APPROVAL, Stage.APPROVED, Stage.COMPLETED):
        body = ('<div class="between" style="padding:8px 0;border-bottom:1px solid var(--line)">'
                '<b>Versão atual</b><span class="sub">renderizada · as versões anteriores não são '
                "registradas nesta tela</span></div>")
    else:
        body = '<p class="sub">Nenhuma versão renderizada.</p>'
    return (
        '<dialog id="dlg-versoes" class="modal" aria-labelledby="t-versoes">'
        '<div class="modal-header"><h2 id="t-versoes">Histórico de versões</h2>'
        '<button class="modal-close" type="button" data-fechar-dialogo aria-label="Fechar">✕</button></div>'
        f'<div class="dialogo-corpo"><div style="margin:10px 0">{body}</div>'
        '<button class="btn small" type="button" data-fechar-dialogo>Fechar</button></div></dialog>'
    )


def _header_html(view: ExecutionView, video_channel: str) -> str:
    """Cabeçalho de `pgVideo` (igual ao do workspace): voltar + caminho, eyebrow, h1, pills, ações."""
    detail = view.detail
    video = getattr(detail, "video", None)
    video_id = view.run.video_id
    title = getattr(video, "title", None) or view.topic
    mode = getattr(video, "production_mode", None)
    mode_value = getattr(mode, "value", mode)
    if mode_value == "diretor":
        eyebrow = "🎬 Modo Diretor"
    elif mode_value:
        eyebrow = "⚡ Criado no piloto automático"
    else:
        eyebrow = "Execução da produção"
    pills = []
    if detail is not None:
        label, tone = _ESTADO.get(detail.stage, (detail.stage.value, ""))
        pills.append(f'<span class="pill {tone}">{e(label)}</span>')
    run_label = _RUN_LABEL.get(view.run.state, "Estado desconhecido")
    run_tone = _RUN_PILL.get(view.run.state, "")
    pills.append(f'<span class="pill {run_tone}">Execução: {e(run_label)}</span>')
    fmt = getattr(getattr(video, "format", None), "value", getattr(video, "format", None))
    if fmt:
        pills.append(f'<span class="pill">{"Short 9:16" if fmt == "short" else "Vídeo 16:9"}</span>')
    pills.append(f'<span class="pill">{e(_MODE_LABELS.get(view.mode, view.mode))}</span>')
    editar = ""
    if detail is not None and mode_value != "diretor" and detail.stage != Stage.PENDING:
        editar = f'<a class="btn small" href="{area_href(video_id, "cenas")}">Editar no Modo Diretor</a>'
    caminho = f"{e(video_channel)} / {e(title)}" if video_channel else e(title)
    started = f"Execução iniciada {elapsed_text(view.run.created_at, view.now)}"
    return f"""        <p class="sub" style="margin-bottom:8px"><a class="btn ghost small" href="/studio/panel/videos">← Vídeos</a> &nbsp; {caminho}</p>
        <div class="head"><div><p class="eyebrow">{eyebrow}</p><h1 id="t-video">{e(title)}</h1>
          <div class="row" style="margin-top:6px">{"".join(pills)}</div>
          <p class="sub" style="margin-top:6px">{e(started)}</p></div>
          <div class="row">{editar}<button class="btn small" type="button" id="btn-versoes">Histórico de versões</button></div>
          <a class="btn ghost small" href="{area_href(video_id, "producao")}">Ver progresso / Diagnóstico</a></div>
        {_version_dialog(detail)}"""


_ACTION_JS = """
    document.querySelectorAll('[data-run-action]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const action = btn.getAttribute('data-run-action');
        const videoId = btn.getAttribute('data-video-id');
        const runId = btn.getAttribute('data-run-id');
        const feedback = document.getElementById('run-action-feedback');
        const url = '/studio/videos/' + encodeURIComponent(videoId) +
          '/production-runs/' + encodeURIComponent(runId) + '/' + action;
        btn.disabled = true;
        btn.classList.add('carregando');
        if (window.StudioLoading) window.StudioLoading.start();
        if (feedback) feedback.textContent = 'Aplicando...';
        try {
          const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
          });
          const data = await res.json().catch(() => ({}));
          if (res.ok) {
            if (feedback) feedback.textContent = 'Feito. Atualizando...';
            location.reload();
          } else {
            btn.disabled = false;
            btn.classList.remove('carregando');
            if (window.StudioLoading) window.StudioLoading.done();
            if (feedback) feedback.textContent = 'Não foi possível: ' +
              (window.StudioErro.texto(data, 'o estado atual não permite esta ação'));
          }
        } catch (err) {
          btn.disabled = false;
          btn.classList.remove('carregando');
          if (window.StudioLoading) window.StudioLoading.done();
          if (feedback) feedback.textContent = 'Falha de rede: ' + err.message;
        }
      });
    });
    (function () {
      var dlg = document.getElementById('dlg-versoes');
      var btn = document.getElementById('btn-versoes');
      if (!dlg || !btn) return;
      btn.addEventListener('click', function () {
        if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
      });
      dlg.addEventListener('click', function (ev) {
        if (ev.target === dlg || (ev.target.closest && ev.target.closest('[data-fechar-dialogo]'))) dlg.close();
      });
    })();
"""

# Polling leve do estado real da execução. Atualiza etapas/contagem sem recarregar a página;
# qualquer mudança do estado da execução (terminal ou não) recarrega uma única vez, porque as
# ações válidas dependem dele. Pausa com a aba oculta e nunca dispara uma operação (só GET).
_POLL_JS = """
    (function () {
      var card = document.getElementById('prod-card');
      if (!card) return;
      var CFG = __CONFIG__;
      var url = card.getAttribute('data-poll-url');
      var initial = card.getAttribute('data-run-state');
      var timer = null, busy = false, stopped = false;

      function fill(node, parts) {
        while (node.firstChild) node.removeChild(node.firstChild);
        parts.forEach(function (p) {
          if (p.b) { var b = document.createElement('b'); b.textContent = p.b; node.appendChild(b); }
          else node.appendChild(document.createTextNode(p));
        });
      }
      function nextText(data) {
        if (!data.next_action) return CFG.terminal;
        var t = CFG.next[data.next_action] || data.next_action;
        if (data.next_action === 'run' && data.next_stage) t += ' (' + (CFG.labels[data.next_stage] || data.next_stage) + ')';
        return t;
      }
      function apply(data) {
        var stages = data.stages || [];
        var done = 0, current = -1;
        stages.forEach(function (s, i) {
          if (s.state === 'SUCCEEDED') done++;
          if (current < 0 && (s.state === 'RUNNING' || s.state === 'WAITING_HUMAN' || s.state === 'FAILED')) current = i;
        });
        if (current < 0) current = stages.findIndex(function (s) { return s.state === 'PENDING'; });
        stages.forEach(function (s, i) {
          var v = CFG.steps[s.state] || CFG.steps.PENDING;
          var row = document.querySelector('[data-step="' + s.stage + '"]');
          if (row) {
            var ic = row.querySelector('.ic');
            ic.className = 'ic' + (v[0] ? ' ' + v[0] : '');
            ic.textContent = v[1];
            row.querySelector('[data-step-text]').textContent = v[2];
            var err = row.querySelector('[data-step-err]');
            if (s.state === 'FAILED' && s.error) {
              if (!err) {
                err = document.createElement('p');
                err.setAttribute('data-step-err', '');
                err.setAttribute('style', CFG.errStyle);
                row.querySelector('b').insertAdjacentElement('afterend', err);
              }
              err.textContent = s.error;
            } else if (err) err.remove();
            if (i === current) row.setAttribute('aria-current', 'step'); else row.removeAttribute('aria-current');
          }
          var pill = document.querySelector('[data-pill="' + s.stage + '"]');
          if (pill) {
            pill.className = 'pill' + (v[3] ? ' ' + v[3] : '');
            pill.textContent = v[1] + ' ' + (CFG.labels[s.stage] || s.stage);
          }
        });
        var count = document.getElementById('prod-count');
        if (count) count.textContent = done + '/' + stages.length + ' etapas';
        var bar = document.getElementById('prod-bar');
        if (bar) bar.style.width = (stages.length ? Math.round(done / stages.length * 100) : 0) + '%';
        var pos = document.getElementById('exec-position');
        if (pos) {
          var cur = current >= 0 ? stages[current].stage : null;
          var parts = [];
          if (current >= 0) parts.push('Etapa ', { b: (current + 1) + ' de ' + stages.length }, '. ');
          parts.push('Etapa atual: ', { b: cur ? (CFG.labels[cur] || cur) : 'nenhuma' }, '. ',
                     'Próxima ação: ', { b: nextText(data) }, '.');
          fill(pos, parts);
        }
      }
      function schedule() {
        clearTimeout(timer);
        if (!stopped && !document.hidden) timer = setTimeout(tick, CFG.interval);
      }
      async function tick() {
        if (busy || stopped || document.hidden) return;
        busy = true;
        try {
          var res = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store', credentials: 'same-origin' });
          if (res.ok) {
            var data = await res.json();
            if (data.state !== initial) { stopped = true; location.reload(); return; }
            apply(data);
          } else if (res.status >= 400 && res.status < 500) { stopped = true; return; }
        } catch (err) { /* rede instável: tenta de novo no próximo ciclo */ }
        busy = false;
        schedule();
      }
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) clearTimeout(timer); else tick();
      });
      schedule();
    })();
"""


def _poll_js() -> str:
    config = {
        "interval": POLL_INTERVAL_MS,
        "steps": {s.value: [v[0], v[1], v[2], v[3]] for s, v in _STEP_VIEW.items()},
        "labels": {s.value: label for s, label in STAGE_LABELS.items()},
        "next": _NEXT_ACTION_LABELS,
        "terminal": next_action_text(None, None),
        "errStyle": _STEP_ERR_STYLE,
    }
    return _POLL_JS.replace("__CONFIG__", json.dumps(config, ensure_ascii=False))


def render_execution(view: ExecutionView, *, video_channel: str = "",
                     free_providers: frozenset[str] = frozenset()) -> tuple[str, dict[str, str]]:
    from . import shell_v3

    nonce = secrets.token_urlsafe(16)
    video_id = view.run.video_id
    dots = {}
    if view.detail is not None and view.detail.stage == Stage.AWAITING_APPROVAL:
        dots["qualidade"] = "Aguardando você"
    steps_card, partial = _steps_card_html(view, free_providers)

    body_html = f"""      <section class="pagina" id="pagina-execucao" aria-labelledby="t-video">
{_header_html(view, video_channel)}
        {video_area_nav(video_id, "", dots)}
        {_progress_card_html(view)}
        <div class="two">
          <div class="stack">
            {steps_card}
            {_action_card_html(view)}
            {_rail_actions_html(view)}
          </div>
          <aside class="stack" aria-label="Custo e diagnóstico">
            {_cost_card_html(view, partial)}
            {_unavailable_card_html(view)}
            {_diag_html(view, free_providers)}
          </aside>
        </div>
      </section>"""

    page_js = _ACTION_JS + (_poll_js() if view.run.state in ACTIVE_RUN_STATES else "")
    page = shell_v3.render_document(
        title=f"Faceless Studio — Execução: {view.topic}",
        active="videos",
        crumb=f"{video_channel} / {view.topic}" if video_channel else f"Vídeos / {view.topic}",
        body_html=body_html,
        nonce=nonce,
        projects=[],
        project_id="",
        cost_note="",
        page_js=page_js,
        video_channel=video_channel,
    )
    return page, shell._headers(nonce)


def render_production_page(view) -> tuple[str, dict[str, str]]:
    """Produção (FS31-A3): quadro de execução na **casca V3**, só com dado real.

    Cada vídeo mostra o estado da produção, a etapa atual e o custo **rotulado** (sem registro
    de uso não é zero). A casca antiga (sidebar V2, links de API/n8n) não é mais renderizada.
    """
    import secrets

    from ..application.panel import PanelView, Stage  # noqa: F401  (tipo só para leitura)
    from . import panel as legacy
    from . import panel_home
    from . import shell_v3

    nonce = secrets.token_urlsafe(16)
    project_id = view.project_id or (view.projects[0][0] if view.projects else "")
    videos = [video for topic in view.topics for video in topic.videos]
    videos.sort(key=lambda item: item.updated_at, reverse=True)

    if videos:
        cards = "".join(_production_card(video, panel_home) for video in videos)
        empty = ""
    else:
        cards = ""
        empty = ('<p class="vazio" id="producao-vazio">Nenhum vídeo em produção neste canal ainda. '
                 'Comece por <a href="/studio/panel/novo-video">Novo vídeo</a>.</p>')

    body = f"""      <section class="pagina" id="pagina-producao" aria-labelledby="t-producao">
        <div class="secao-cab">
          <div>
            <p class="eyebrow">EXECUÇÃO DO CANAL</p>
            <h1 class="h1" id="t-producao">Produção</h1>
            <p class="lead">Onde cada vídeo está e quanto custou — estado real, sem estimativa inventada.</p>
          </div>
          <a class="btn btn-primario" href="/studio/panel/novo-video">＋ Novo vídeo</a>
        </div>
        <div class="grade" id="lista-producao">{cards}</div>
        {empty}
      </section>"""

    html = shell_v3.render_document(
        title="Faceless Studio — Produção",
        active="producao",
        crumb="Produção",
        body_html=body,
        nonce=nonce,
        projects=list(view.projects),
        project_id=project_id,
        cost_note=panel_home.cost_note(view),
    )
    return html, legacy._headers(nonce)


def _production_card(video, panel_home) -> str:
    label, css, step = panel_home._SITUACAO.get(video.stage, (video.stage.value, "parado", ""))
    title = video.title or video.topic
    return f"""<article class="cartao-projeto" data-situacao="{e(css)}">
            <a href="{area_href(video.id, default_area(video.stage))}" aria-label="Abrir o vídeo {e(title)}">
              <div class="miniatura"><b>{e(panel_home._format_label(video))}</b></div>
              <div class="cartao-corpo">
                <h3>{e(title)}</h3>
                <p class="linha-meta"><span class="situacao {e(css)}"><i aria-hidden="true"></i>{e(label)}</span></p>
                <p class="etapa-atual">{e(step)}</p>
                <p class="linha-meta">Custo: {e(video.cost_text)}</p>
              </div>
            </a>
          </article>"""
