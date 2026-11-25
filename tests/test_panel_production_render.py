"""Render puro das telas de produção (F2-02..F2-05).

Sem banco: exercita `render_new_video`/`render_execution` diretamente e aplica o contrato de UX
canônico (`assert_ux_contract`) às duas telas novas.
"""
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.panel import CostBreakdown, MonthCost  # noqa: E402
from app.studio.application.ports import UsageInfo  # noqa: E402
from app.studio.api.panel_production import (  # noqa: E402
    ExecutionView,
    NewVideoView,
    PipelineStage,
    available_actions,
    artifact_available,
    elapsed_text,
    next_action_text,
    render_execution,
    render_new_video,
)
from app.studio.domain.production_run import (  # noqa: E402
    OutboxEvent,
    ProductionRun,
    ProductionStage,
    ProgressEventType,
    RunState,
    StageExecution,
    StageState,
)

from test_panel import _visible_text  # noqa: E402
from test_ux_contract import assert_ux_contract  # noqa: E402

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
RUN = "a" * 32
VIDEO = "b" * 32


def _month(calls=0) -> MonthCost:
    if calls == 0:
        return MonthCost(text="sem registro de uso", known_usd=0.0, cap_usd=15.0,
                         unknown_calls=0, percent=None, breakdown=CostBreakdown())
    return MonthCost(text="Real US$ 0,07 · Estimado US$ 0,05", known_usd=0.12, cap_usd=15.0,
                     unknown_calls=1, percent=0.8,
                     breakdown=CostBreakdown(real_usd=0.07, real_calls=1, estimate_usd=0.05,
                                             estimate_calls=1, free_calls=3, unknown_calls=1))


def _run(state=RunState.RUNNING, created=None, reason=None):
    return ProductionRun(run_id=RUN, video_id=VIDEO, idempotency_key="key", state=state,
                         reason=reason, created_at=created, updated_at=created)


def _stage(stage, state, *, error=None):
    lease = {}
    if state == "RUNNING":
        lease = {"lease_owner": "worker-1", "lease_expires_at": NOW + timedelta(minutes=5)}
    return StageExecution(run_id=RUN, stage_id=ProductionStage(stage), state=StageState(state),
                          error=error, **lease)


def _execution_view(**overrides) -> ExecutionView:
    defaults = dict(
        topic="Tópico real do operador",
        run=_run(),
        stages=(_stage("script", "SUCCEEDED"), _stage("factcheck", "RUNNING"),
                _stage("storyboard", "PENDING")),
        next_action="run",
        next_stage=ProductionStage.STORYBOARD,
        mode="INTERACTIVE",
        month=_month(),
        now=NOW,
    )
    defaults.update(overrides)
    return ExecutionView(**defaults)


def _new_video_view(**overrides) -> NewVideoView:
    defaults = dict(
        projects=[("p1", "Canal Real")],
        month=_month(),
        pipeline=(
            PipelineStage(ProductionStage.RESEARCH, "Fontes", False, "sem porta de pesquisa"),
            PipelineStage(ProductionStage.SCRIPT, "Roteiro", True),
            PipelineStage(ProductionStage.PUBLISH, "Publicação", False, "fatia F8"),
        ),
        selected_project_id="p1",
    )
    defaults.update(overrides)
    return NewVideoView(**defaults)


# -- contrato de UX ----------------------------------------------------------


def test_wizard_satisfies_the_ux_contract():
    page, _ = render_new_video(_new_video_view())
    assert_ux_contract(page, page="painel/novo-video")


def test_execution_satisfies_the_ux_contract():
    page, _ = render_execution(_execution_view())
    assert_ux_contract(page, page="painel/execução")


def test_execution_failed_state_satisfies_the_ux_contract():
    page, _ = render_execution(_execution_view(
        run=_run(RunState.FAILED, reason="gate humano ausente"),
        stages=(_stage("script", "SUCCEEDED"), _stage("factcheck", "FAILED", error="fonte não abriu")),
        next_action="retry", next_stage=ProductionStage.FACTCHECK,
    ))
    assert_ux_contract(page, page="painel/execução-falha")
    assert "Tentar novamente" in page


# -- wizard: honestidade de campos -------------------------------------------


def test_wizard_disables_unsupported_fields_with_a_reason():
    import re

    page, _ = render_new_video(_new_video_view())
    for control in ("wiz-publico", "wiz-duracao", "wiz-estilo", "wiz-idioma", "wiz-teto"):
        match = re.search(rf'<[^>]*id="{control}"[^>]*>', page)
        assert match is not None, control
        assert "disabled" in match.group(0), control
    assert page.count("Motivo:") >= 5
    # O tema, o canal e o formato são as decisões reais e continuam habilitados.
    for control in ("wiz-tema", "wiz-canal", "wiz-formato"):
        match = re.search(rf'<[^>]*id="{control}"[^>]*>', page)
        assert match is not None and "disabled" not in match.group(0), control


def test_wizard_shows_the_default_duration_but_disabled():
    page, _ = render_new_video(_new_video_view())
    assert "480 s (8 min) — padrão" in page


def test_wizard_canal_is_disabled_when_no_project_exists():
    page, _ = render_new_video(_new_video_view(projects=[], selected_project_id=""))
    assert 'id="wiz-canal" name="project_id" disabled' in page


def test_wizard_has_aria_pressed_origin_chips_and_unavailable_series():
    page, _ = render_new_video(_new_video_view())
    assert 'aria-pressed="true"' in page and 'aria-pressed="false"' in page
    assert 'aria-disabled="true"' in page


def test_wizard_pipeline_marks_unavailable_stages_with_reason():
    page, _ = render_new_video(_new_video_view())
    assert "indisponível" in page
    assert "sem porta de pesquisa" in page and "fatia F8" in page


def test_wizard_never_projects_a_made_up_cost_estimate():
    page, _ = render_new_video(_new_video_view())
    assert "não projeta o custo antes de produzir" in page
    assert "US$ 0,00" not in page


# -- execução: stepper, próxima ação, sem barra ------------------------------


def test_execution_shows_stage_n_of_m_without_progress_bar():
    page, _ = render_execution(_execution_view())
    assert "Etapa <b>2 de 3</b>" in page
    # A barra `.prog` do protótipo é decorativa (aria-hidden): o progresso é dito em texto, por
    # etapas reais, e nunca como percentual.
    assert "<progress" not in page and 'role="progressbar"' not in page
    assert "1/3 etapas" in page and "%" not in _visible_text(page)


def test_execution_shows_next_action_and_current_stage_label():
    page, _ = render_execution(_execution_view())
    assert "Próxima ação:" in page
    assert "executar a próxima etapa (Cenas)" in page
    assert 'aria-current="step"' in page
    assert "Em execução" in page


def test_execution_keeps_ids_only_inside_closed_advanced():
    page, _ = render_execution(_execution_view())
    visible_main, advanced = _visible_text(page.split('id="advanced-diagnostics"', 1)[0]), \
        page.split('id="advanced-diagnostics"', 1)[1]
    assert RUN not in visible_main and VIDEO not in visible_main
    assert RUN in advanced and VIDEO in advanced
    assert '<details class="diag" id="advanced-diagnostics">' in page
    assert "<summary>Diagnóstico técnico</summary>" in page
    assert "<details open" not in page


def test_execution_empty_usage_is_explicit_not_zero():
    page, _ = render_execution(_execution_view())
    assert "Sem registro de uso de IA para este vídeo." in page
    assert "US$ 0,00" not in page


def test_execution_usage_rows_are_labeled_by_origin():
    usage = (
        UsageInfo(step="text", provider="opencode", model="gpt-5-mini", cost_usd=0.02,
                  created_at=NOW, cost_confirmation_kind="ESTIMATE"),
        UsageInfo(step="voice", provider="piper", model="pt-BR-faber-medium", cost_usd=0.0,
                  created_at=NOW, cost_confirmation_kind="FREE"),
        UsageInfo(step="image", provider="opencode", model="openai/gpt-4o-paid", cost_usd=0.0,
                  created_at=NOW),
    )
    page, _ = render_execution(_execution_view(usage=usage))
    assert "Estimado US$ 0,02" in page
    assert "Sem custo" in page
    assert "Desconhecido" in page


def test_execution_event_trace_is_only_in_advanced():
    event = OutboxEvent(id=1, run_id=RUN, event_type=ProgressEventType.STAGE_FAILED,
                        stage_id=ProductionStage.FACTCHECK, payload={"error": "fonte X não abriu"},
                        created_at=NOW)
    page, _ = render_execution(_execution_view(events=(event,)))
    main_area = page.split('id="advanced-diagnostics"', 1)[0]
    assert "fonte X não abriu" not in main_area
    advanced = page.split('id="advanced-diagnostics"', 1)[1]
    assert "production.stage.failed" in advanced and "fonte X não abriu" in advanced


# -- ações condicionadas ao estado -------------------------------------------


@pytest.mark.parametrize(("state", "keys"), [
    (RunState.CREATED, ["cancel"]),
    (RunState.RUNNING, ["pause", "cancel"]),
    (RunState.WAITING_HUMAN, ["resume", "cancel"]),
    (RunState.PAUSED, ["resume", "cancel"]),
    (RunState.FAILED, ["resume", "retry", "cancel"]),
    (RunState.SUCCEEDED, []),
    (RunState.CANCELLED, []),
])
def test_actions_are_conditioned_on_state(state, keys):
    assert [a.key for a in available_actions(state, None)] == keys


def test_execution_never_renders_invalid_actions():
    running, _ = render_execution(_execution_view(run=_run(RunState.RUNNING), next_action="run"))
    assert "Pausar" in running and "Cancelar" in running
    assert "Tentar novamente" not in running and "Continuar" not in running

    done, _ = render_execution(_execution_view(
        run=_run(RunState.SUCCEEDED), next_action=None, next_stage=None,
        stages=(_stage("script", "SUCCEEDED"),)))
    assert "Pausar" not in done and "Cancelar" not in done and "Tentar novamente" not in done
    assert "Nenhuma ação disponível neste estado" in done


def test_orphan_running_offers_continue_to_relaunch_the_worker():
    """RUNNING sem lease vivo: o worker morreu; "Continuar" é a única ação que destrava."""
    expired = StageExecution(run_id=RUN, stage_id=ProductionStage.FACTCHECK, state=StageState.RUNNING,
                             attempt=1, fencing_token=1, lease_owner="worker-1",
                             lease_expires_at=NOW - timedelta(minutes=1))
    assert [a.key for a in available_actions(RunState.RUNNING, "run", live_lease=False)] == \
        ["resume", "pause", "cancel"]

    page, _ = render_execution(_execution_view(run=_run(RunState.RUNNING),
                                               stages=(_stage("script", "SUCCEEDED"), expired)))
    actions = page.split('id="h-acoes"', 1)[1]
    assert "Continuar" in actions and "Pausar" in actions


def test_review_action_only_appears_with_an_artifact():
    assert artifact_available("approve") is True
    assert artifact_available("run") is False

    with_artifact, _ = render_execution(_execution_view(
        run=_run(RunState.WAITING_HUMAN), next_action="approve",
        next_stage=ProductionStage.APPROVAL))
    assert "Aprovação necessária antes de continuar" in with_artifact
    assert ">Revisar</a>" in with_artifact

    without, _ = render_execution(_execution_view(
        run=_run(RunState.WAITING_HUMAN), next_action="resume",
        next_stage=ProductionStage.FACTCHECK))
    assert ">Revisar</a>" not in without


def test_failure_card_shows_what_to_do_and_a_valid_retry_only_when_failed():
    failed, _ = render_execution(_execution_view(
        run=_run(RunState.FAILED, reason="fonte não abriu"),
        stages=(_stage("factcheck", "FAILED", error="relatório anual 2026 não abriu"),),
        next_action="retry", next_stage=ProductionStage.FACTCHECK))
    assert "Ação necessária" in failed
    assert "O que fazer:" in failed
    assert "Tentar novamente" in failed
    assert "relatório anual 2026 não abriu" in failed


def test_elapsed_text_is_honest_about_missing_start():
    assert elapsed_text(None, NOW) == "sem horário de início registrado"
    assert elapsed_text(NOW - timedelta(seconds=30), NOW) == "há menos de 1 min"
    assert elapsed_text(NOW - timedelta(minutes=6), NOW) == "há 6 min"
    assert elapsed_text(NOW - timedelta(hours=2, minutes=5), NOW) == "há 2 h 5 min"
    assert "futuro" in elapsed_text(NOW + timedelta(minutes=1), NOW)


def test_next_action_text_covers_terminal_state():
    assert next_action_text(None, None).startswith("Nada a fazer")
    assert next_action_text("approve", ProductionStage.APPROVAL) == "revisar e aprovar o artefato"


# -- página de execução: aparência da aba Produção do protótipo --------------


def _failed_view(**overrides):
    defaults = dict(
        run=_run(RunState.FAILED, reason="gate humano ausente"),
        stages=(_stage("research", "SUCCEEDED"),
                _stage("script", "FAILED", error="SourceRefused: no sources with checkable claims"),
                _stage("factcheck", "PENDING")),
        next_action="retry", next_stage=ProductionStage.SCRIPT,
    )
    defaults.update(overrides)
    return _execution_view(**defaults)


def test_execution_uses_prototype_classes_and_no_legacy_ones():
    for view in (_execution_view(), _failed_view()):
        page, _ = render_execution(view)
        markup = re.sub(r"<(style|script)\b.*?</\1>", "", page, flags=re.S)
        for legacy in ("grade-video", "cab-video", 'class="steps"', "advanced-summary", "act-card",
                       "btn-primary", "form-feedback", 'class="kv"', 'class="muted"', 'class="fine"'):
            assert legacy not in markup, legacy
        for proto in ('class="head"', 'class="eyebrow"', 'class="two"', 'class="stack"',
                      '<aside class="stack"', 'class="step"', "details class=\"diag\"",
                      'class="abas-video"'):
            assert proto in page, proto


def test_execution_steps_are_prototype_step_rows_with_real_state():
    page, _ = render_execution(_failed_view())
    assert page.count('<div class="step"') == 3
    assert 'class="ic ok"' in page and 'class="ic fail"' in page and 'class="ic "' in page
    assert "Concluída" in page and "Falhou" in page and "Aguardando" in page
    # Mensagem real da etapa na cor/tamanho do protótipo; custo sem medição nunca vira zero.
    assert '<p data-step-err style="color:var(--bad);font-size:12.5px">O roteiro só é escrito a partir de fatos' in page
    assert "SourceRefused: no sources with checkable claims" in page  # o motivo técnico segue visível no cartão
    assert page.count('<span class="sample">não medido</span>') == 3
    assert "US$ 0,00" not in page


def test_execution_header_matches_workspace_with_no_active_tab():
    page, _ = render_execution(_execution_view(), video_channel="Canal Real")
    assert "← Vídeos" in page and "Canal Real / Tópico real do operador" in page
    assert '<h1 id="t-video">Tópico real do operador</h1>' in page
    assert f'href="/studio/panel/videos/{VIDEO}/producao">Ver progresso / Diagnóstico</a>' in page
    nav = page.split('aria-label="Áreas do vídeo"', 1)[1].split("</nav>", 1)[0]
    assert nav.count("<a ") == 6 and "aria-current" not in nav


def test_progress_card_only_while_active_and_counts_real_stages():
    for state in (RunState.CREATED, RunState.RUNNING, RunState.WAITING_HUMAN, RunState.PAUSED):
        page, _ = render_execution(_execution_view(run=_run(state)))
        assert "⚡ Produção em andamento" in page, state
    page, _ = render_execution(_execution_view())
    assert 'id="prod-count">1/3 etapas</span>' in page
    assert '<b id="prod-bar" style="width:33%;transition:width .5s"></b>' in page
    assert 'class="prog" aria-hidden="true" style="height:8px' in page
    assert '<span class="pill ok" data-pill="script">✓ Roteiro</span>' in page
    assert '<span class="pill accent" data-pill="factcheck">… Fact-check</span>' in page
    assert '<span class="pill" data-pill="storyboard">○ Cenas</span>' in page

    for state in (RunState.FAILED, RunState.CANCELLED, RunState.SUCCEEDED):
        page, _ = render_execution(_execution_view(run=_run(state), next_action=None, next_stage=None))
        assert "Produção em andamento" not in page and "prod-card" not in page, state
        assert "ReadableStream" not in page and "data-poll-url" not in page


def test_progress_card_shows_failed_stage_pill_with_x():
    page, _ = render_execution(_execution_view(
        run=_run(RunState.WAITING_HUMAN),
        stages=(_stage("script", "SUCCEEDED"), _stage("factcheck", "FAILED", error="x"))))
    assert '<span class="pill bad" data-pill="factcheck">✕ Fact-check</span>' in page


def test_polling_script_only_for_active_runs_and_is_read_only():
    import re

    page, _ = render_execution(_execution_view())
    assert f'data-poll-url="/studio/videos/{VIDEO}/production-runs/{RUN}"' in page
    script = re.findall(r"<script nonce=\"[^\"]+\">(.*?)</script>", page, re.S)[-1]
    assert "setTimeout(tick, CFG.interval)" in script and '"interval": 2500' in script
    assert "document.hidden" in script and "visibilitychange" in script
    assert "location.reload()" in script and "data.state !== initial" in script
    assert "no-store" in script
    # O polling só lê (GET); nunca declara método de escrita.
    poll = script.split("var card = document.getElementById('prod-card')", 1)[1]
    assert "method:" not in poll and "POST" not in poll

    for state in (RunState.FAILED, RunState.SUCCEEDED, RunState.CANCELLED):
        quiet, _ = render_execution(_execution_view(run=_run(state), next_action=None, next_stage=None))
        assert "visibilitychange" not in quiet


def test_no_inline_event_handlers_and_script_has_nonce():
    import re

    page, headers = render_execution(_failed_view())
    assert not re.search(r"\son[a-z]+=", page)
    nonce = re.search(r"nonce-([\w-]+)", headers["Content-Security-Policy"]).group(1)
    assert page.count(f'<script nonce="{nonce}">') >= 2


def test_failed_run_keeps_retry_in_header_card_and_action_card():
    page, _ = render_execution(_failed_view())
    assert "↻ Retomar de onde parou" in page
    assert page.count('data-run-action="retry"') == 3  # cabeçalho, cartão de ação, ações
    assert "A execução falhou na etapa Roteiro" in page
    assert "O que fazer:" in page and ">Revisar</a>" in page
    assert 'data-run-action="cancel"' in page and 'data-run-action="resume"' in page
    assert 'id="run-action-feedback"' in page and 'aria-live="polite"' in page

    running, _ = render_execution(_execution_view())
    assert "Retomar de onde parou" not in running
    assert 'data-run-action="retry"' not in running


def test_cost_card_is_honest_about_unmeasured_stages():
    page, _ = render_execution(_failed_view())
    aside = page.split('<aside class="stack"', 1)[1]
    assert "Custo do vídeo" in aside
    assert "sem registro de uso" in aside
    assert "Sem registro de uso de IA para este vídeo." in aside
    usage = (UsageInfo(step="script", provider="opencode", model="m", cost_usd=0.02, created_at=NOW,
                       cost_confirmation_kind="ESTIMATE"),
             UsageInfo(step="text", provider="opencode", model="m", cost_usd=0.01, created_at=NOW,
                       cost_confirmation_kind="ACTUAL"))
    from app.studio.application.panel import cost_breakdown
    cost = cost_breakdown([(u.provider, u.model, u.cost_usd, u.cost_confirmation_kind) for u in usage])
    page, _ = render_execution(_failed_view(usage=usage, cost=cost))
    aside = page.split('<aside class="stack"', 1)[1]
    assert "Etapas sem custo medido não são somadas como zero." in aside
    assert "Real US$ 0,01 · Estimado US$ 0,02" in aside
    # Só o uso cujo `step` é o id da etapa é atribuído a ela; o resto continua "não medido".
    assert '<span class="sample">Estimado US$ 0,02</span>' in page
    assert page.count('<span class="sample">não medido</span>') == 2
