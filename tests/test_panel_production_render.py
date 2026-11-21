"""Render puro das telas de produção (F2-02..F2-05).

Sem banco: exercita `render_new_video`/`render_execution` diretamente e aplica o contrato de UX
canônico (`assert_ux_contract`) às duas telas novas.
"""
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
    assert "Não há barra de progresso nem percentual" in page
    assert "<progress" not in page and 'role="progressbar"' not in page


def test_execution_shows_next_action_and_current_stage_label():
    page, _ = render_execution(_execution_view())
    assert "Próxima ação:" in page
    assert "executar a próxima etapa (Cenas)" in page
    assert 'aria-current="step"' in page
    assert "Em execução" in page


def test_execution_keeps_ids_only_inside_closed_advanced():
    page, _ = render_execution(_execution_view())
    main_area, advanced = page.split('id="advanced-diagnostics"', 1)
    assert RUN not in main_area and VIDEO not in main_area
    assert RUN in advanced and VIDEO in advanced
    assert "<details class=\"advanced\" id=\"advanced-diagnostics\">" in page
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
