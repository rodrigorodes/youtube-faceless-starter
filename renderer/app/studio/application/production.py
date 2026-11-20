"""ProductionCoordinator, worker e handlers das etapas (D2 — F1-03/F1-04/F1-05/F1-07).

O coordenador é a jornada sob comando único: ele cria a execução idempotente, pega as etapas
prontas respeitando lease/fencing/checkpoint do repositório (fatia D) e as executa por handlers.
Ele **não** conhece adaptadores concretos: fala só com portas e com os casos de uso já existentes.

Regras que este módulo garante:

- **Nenhum efeito irreversível sem gate.** Etapas de capacidade inexistente (research, publish)
  são declaradas indisponíveis e recusadas; nunca fingem sucesso.
- **Pausa humana libera o worker.** A etapa `approval` (e, no modo interativo, o fim do roteiro)
  persiste `WAITING_HUMAN` e solta o lease: nenhum processo fica bloqueado esperando.
- **Publicação nunca auto-aprova.** O modo `BUDGET_GUARDED` pode dispensar a pausa do roteiro, mas
  a etapa `approval` continua exigindo decisão humana (gate F6) nos dois modos.
- **Idempotência.** `start` reusa a chave: chamada repetida não duplica run nem custo.

O modo controla só as pausas intermediárias. A projeção de custo é injetada (`ProductionBudget`);
sem projeção conhecida o modo guardado é conservador e pausa para humano em vez de presumir custo.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Protocol

from ..domain.contracts import JobStatus, RenderJob, Video, VideoStatus
from ..domain.ids import check_id
from ..domain.production_run import (
    Checkpoint,
    OutboxEvent,
    ProductionRun,
    ProductionStage,
    RunCreation,
    RunState,
    RunTransition,
    RunTransitionResult,
    StageClaim,
    StageClaimResult,
    StageDag,
    StageExecution,
    StageState,
    StageTransitionResult,
)
from ..domain.qa_report import (
    QaCoverage,
    QaFinding,
    QaGateError,
    QaReport as VersionedQaReport,
    RenderVersion,
    approve as approve_qa,
)
from .editorial import Editorial
from .media import Media
from .ports import (
    ApprovalRepository,
    AssetRepository,
    ProductionRunRepository,
    ProductionRunStageReader,
    RenderJobRepository,
    VideoRepository,
)
from .render import RunRender, StartRender

logger = logging.getLogger("studio.production")


# ---------------------------------------------------------------------------
# Erros de aplicação (mapeados para HTTP pela API; nunca viram 500)
# ---------------------------------------------------------------------------


class CoordinatorError(RuntimeError):
    """Base dos erros do coordenador (falha de negócio, não indisponibilidade)."""


class RunNotFound(CoordinatorError, LookupError):
    """Não existe execução para o `run_id` informado."""


class StageCapabilityUnavailable(CoordinatorError):
    """A etapa pedida não tem capacidade implementada: o coordenador se recusa a fingir sucesso."""

    def __init__(self, stage: ProductionStage, reason: str):
        label = stage.value if isinstance(stage, ProductionStage) else str(stage)
        super().__init__(f"stage {label} is unavailable: {reason}")
        self.stage = stage
        self.reason = reason


class StageExecutionFailed(CoordinatorError):
    """O handler recusou a etapa: a execução não terminou com sucesso."""


class MissingApprovalProof(CoordinatorError):
    """A retomada não traz prova de aprovação humana versionada (gate F6)."""


# ---------------------------------------------------------------------------
# Modo de produção (F1-03/F1-05)
# ---------------------------------------------------------------------------


class ProductionMode(str, Enum):
    """Como o coordenador trata as etapas intermediárias.

    `INTERACTIVE`: pausa humana obrigatória após o roteiro (e sempre antes da publicação).
    `BUDGET_GUARDED`: dispensa a pausa do roteiro quando a projeção não passa do teto do canal;
    se a projeção for desconhecida ou exceder o teto, volta a exigir humano. Publicação continua
    exigindo humano nos dois modos.
    """

    INTERACTIVE = "INTERACTIVE"
    BUDGET_GUARDED = "BUDGET_GUARDED"


@dataclass(frozen=True)
class BudgetProjection:
    """Projeção de custo do canal: gasto projetado comparado ao teto."""

    projected_usd: Decimal
    ceiling_usd: Decimal

    def exceeds(self) -> bool:
        return self.projected_usd > self.ceiling_usd


class ProductionBudget(Protocol):
    """Projeção de custo por etapa. `None` significa desconhecida (o chamador decide com cautela)."""

    def project(self, run: ProductionRun, next_stage: ProductionStage) -> BudgetProjection | None: ...


# ---------------------------------------------------------------------------
# Contrato dos handlers e do worker
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageContext:
    """Identidade e posse do dono atual da etapa, para o handler executar o efeito."""

    run: ProductionRun
    execution: StageExecution

    @property
    def checkpoint_version(self) -> int:
        # Monotônica por tentativa: retry nunca tenta regravar a versão anterior.
        return max(1, self.execution.attempt)


@dataclass(frozen=True)
class StageOutcome:
    """Resultado de um handler: checkpoint opcional e/ou pedido de pausa humana."""

    checkpoint: Checkpoint | None = None
    request_human: str | None = None


class StageHandler(Protocol):
    stage: ProductionStage
    available: bool

    def execute(self, context: StageContext) -> StageOutcome: ...


class WorkerStepResult(str, Enum):
    """Resultado de um passo do worker. Comparar explicitamente (nunca como booleano)."""

    COMPLETED = "COMPLETED"
    COMPLETED_PAUSED = "COMPLETED_PAUSED"  # etapa concluída e o run pausado para humano
    PAUSED = "PAUSED"                      # etapa pediu humano; não concluída
    FAILED = "FAILED"
    LOST = "LOST"
    NOTHING_READY = "NOTHING_READY"
    TERMINAL = "TERMINAL"

    def __bool__(self) -> bool:
        raise TypeError("compare the worker step result explicitly")


@dataclass(frozen=True)
class WorkerStep:
    result: WorkerStepResult
    run: ProductionRun | None = None
    stage: ProductionStage | None = None
    execution: StageExecution | None = None
    detail: str | None = None


# ---------------------------------------------------------------------------
# Handlers das etapas existentes
# ---------------------------------------------------------------------------


class _AvailableHandler:
    available = True

    def execute(self, context: StageContext) -> StageOutcome:  # pragma: no cover - interface
        raise NotImplementedError


class UnavailableStageHandler:
    """Etapa cuja capacidade ainda não existe. Nunca devolve sucesso."""

    available = False

    def __init__(self, stage: ProductionStage, reason: str):
        self.stage = stage
        self.reason = reason

    def execute(self, context: StageContext) -> StageOutcome:
        raise StageCapabilityUnavailable(self.stage, self.reason)


class ScriptHandler(_AvailableHandler):
    stage = ProductionStage.SCRIPT

    def __init__(self, editorial: Editorial):
        self.editorial = editorial

    def execute(self, context: StageContext) -> StageOutcome:
        script = self.editorial.generate.execute(context.run.video_id)
        return StageOutcome(checkpoint=Checkpoint(
            {"stage": self.stage.value, "script_version": script.version}, context.checkpoint_version))


class FactCheckHandler(_AvailableHandler):
    stage = ProductionStage.FACTCHECK

    def __init__(self, editorial: Editorial):
        self.editorial = editorial

    def execute(self, context: StageContext) -> StageOutcome:
        report = self.editorial.fact_check.execute(context.run.video_id)
        if not report.passed:
            flagged = ", ".join(str(scene.idx) for scene in report.scenes) or "unsupported claim"
            raise StageExecutionFailed(f"fact-check did not pass (scenes: {flagged})")
        return StageOutcome(checkpoint=Checkpoint({"stage": self.stage.value, "passed": True}, context.checkpoint_version))


class StoryboardHandler(_AvailableHandler):
    stage = ProductionStage.STORYBOARD

    def __init__(self, media: Media):
        self.media = media

    def execute(self, context: StageContext) -> StageOutcome:
        self.media.storyboard.execute(context.run.video_id)
        return StageOutcome(checkpoint=Checkpoint({"stage": self.stage.value}, context.checkpoint_version))


class AssetsHandler(_AvailableHandler):
    stage = ProductionStage.ASSETS

    def __init__(self, media: Media):
        self.media = media

    def execute(self, context: StageContext) -> StageOutcome:
        result = self.media.produce.execute(context.run.video_id)
        return StageOutcome(checkpoint=Checkpoint(
            {"stage": self.stage.value, "generated": result.generated, "reused": result.reused},
            context.checkpoint_version))


class RenderHandler(_AvailableHandler):
    stage = ProductionStage.RENDER

    def __init__(self, start: StartRender, run: RunRender, jobs: RenderJobRepository):
        self.start, self.run, self.jobs = start, run, jobs

    def execute(self, context: StageContext) -> StageOutcome:
        job = self.start.execute(context.run.video_id)
        self.run.execute(job.id)  # o worker do coordenador roda o render em linha
        finished = self.jobs.get(job.id)
        if finished is None or finished.status is not JobStatus.SUCCEEDED:
            raise StageExecutionFailed("the render did not finish successfully")
        return StageOutcome(checkpoint=Checkpoint(
            {"stage": self.stage.value, "render_job": job.id, "output_asset_id": finished.output_asset_id},
            context.checkpoint_version))


class QaHandler(_AvailableHandler):
    """Gate técnico da F6: exige render bem-sucedido com relatório de QA aprovado.

    Não recalcula nem inventa cobertura: só deixa passar quando o QA persistido pelo render passou.
    """

    stage = ProductionStage.QA

    def __init__(self, videos: VideoRepository, jobs: RenderJobRepository):
        self.videos, self.jobs = videos, jobs

    def execute(self, context: StageContext) -> StageOutcome:
        job = self.jobs.latest(context.run.video_id)
        if job is None or job.status is not JobStatus.SUCCEEDED:
            raise StageExecutionFailed("no successful render to verify")
        video = _require_video(self.videos, context.run.video_id)
        report = video.qa_report
        if report is None:
            raise StageExecutionFailed("the render has no QA report")
        if not report.passed:
            raise StageExecutionFailed("QA failed: " + "; ".join(report.failures))
        return StageOutcome(checkpoint=Checkpoint(
            {"stage": self.stage.value, "render_job": job.id, "qa_passed": True}, context.checkpoint_version))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _findings(suggestions: str, failures: Sequence[str]) -> tuple[QaFinding, ...]:
    return tuple(
        QaFinding(finding_id=f"qa-{index}", check_id="studio.render.qa", category="technical",
                  severity="blocking", evidence=failure, suggested_action=suggestions)
        for index, failure in enumerate(failures) if failure.strip()
    )


class RenderQaGate:
    """Monta o contrato versionado da F6 a partir do estado persistido (render + QA + aprovação).

    A identidade do render é declarada, não recalculada: o `render_id` é o job e o `checksum` é a
    chave do asset de saída (a mesma que a publicação usa). O gate recusa render superado e cobertura
    não verificada; sem render ou sem QA devolve `None` (nada a aprovar).
    """

    CHECK = "studio.render.qa"

    def __init__(self, videos: VideoRepository, jobs: RenderJobRepository, assets: AssetRepository,
                 clock: Callable[[], datetime] = _utc_now):
        self.videos, self.jobs, self.assets, self.clock = videos, jobs, assets, clock

    def _render_version(self, video_id: str) -> tuple[RenderJob, RenderVersion] | None:
        # `latest` é o render de saída mais recente (não a versão aprovada): se um render novo
        # surgiu depois da aprovação, `requested` (asset aprovado) diverge e o gate recusa.
        job = self.jobs.latest(video_id)
        asset = self.jobs.latest_output(video_id)
        if job is None or asset is None:
            return None
        return job, RenderVersion(render_id=job.id, checksum=asset.cache_key)

    def report(self, video_id: str, approved_asset_id: str | None = None
               ) -> tuple[VersionedQaReport, RenderVersion, RenderVersion] | None:
        version = self._render_version(video_id)
        if version is None:
            return None
        job, latest = version
        video = _require_video(self.videos, video_id)
        legacy = video.qa_report
        if legacy is None:
            return None
        approved = self.assets.get(approved_asset_id) if approved_asset_id else None
        requested = RenderVersion(render_id=job.id, checksum=approved.cache_key if approved else latest.checksum)
        report = VersionedQaReport(
            render_id=job.id, checksum=latest.checksum, generated_at=self.clock(),
            coverage=QaCoverage(status="verified"), checks_run=(self.CHECK,),
            findings=_findings("Regenerar o render ou corrigir a causa.", legacy.failures),
        )
        return report, latest, requested


class ApprovalHandler(_AvailableHandler):
    """Gate humano + F6. Sem aprovação humana persistida devolve pedido de pausa (não conclui).

    Com aprovação `approved`, valida o gate F6 pela versão exata do render aprovado e só então
    conclui, registrando no checkpoint a identidade que a publicação deve reutilizar.
    """

    stage = ProductionStage.APPROVAL

    def __init__(self, videos: VideoRepository, approvals: ApprovalRepository, gate: RenderQaGate):
        self.videos, self.approvals, self.gate = videos, approvals, gate

    def execute(self, context: StageContext) -> StageOutcome:
        video_id = context.run.video_id
        video = _require_video(self.videos, video_id)
        approval = self.approvals.get(video_id)
        if video.status is not VideoStatus.APPROVED or approval is None or approval.decision != "approved":
            return StageOutcome(request_human="aguardando a aprovação humana do render")
        evaluated = self.gate.report(video_id, approval.output_asset_id)
        if evaluated is None:
            raise StageExecutionFailed("cannot verify the QA gate: a render and a QA report are required")
        report, latest, requested = evaluated
        try:
            approved = approve_qa(report=report, latest=latest, requested=requested)
        except QaGateError as exc:
            raise StageExecutionFailed(f"QA gate refused approval: {exc}") from exc
        return StageOutcome(checkpoint=Checkpoint(
            {"stage": self.stage.value, "render_id": approved.render_id, "checksum": approved.checksum},
            context.checkpoint_version))


def _require_video(videos: VideoRepository, video_id: str) -> Video:
    video = videos.get_video(video_id)
    if video is None:
        raise StageExecutionFailed(f"video {video_id} does not exist")
    return video


RESEARCH_REASON = "research automático não existe (F3 pendente); adicione fontes ao vídeo antes de produzir"
PUBLISH_REASON = "publicação (F8) não é executada pelo coordenador; nunca auto-aprova e exige o fluxo de publicação"


def build_stage_handlers(*, editorial: Editorial, media: Media, start_render: StartRender, run_render: RunRender,
                         videos: VideoRepository, jobs: RenderJobRepository, assets: AssetRepository,
                         approvals: ApprovalRepository, clock: Callable[[], datetime] = _utc_now
                         ) -> dict[ProductionStage, StageHandler]:
    """Registra todos os nove estágios: os implementados por handler e os indisponíveis explícitos."""
    handlers: dict[ProductionStage, StageHandler] = {
        ProductionStage.SCRIPT: ScriptHandler(editorial),
        ProductionStage.FACTCHECK: FactCheckHandler(editorial),
        ProductionStage.STORYBOARD: StoryboardHandler(media),
        ProductionStage.ASSETS: AssetsHandler(media),
        ProductionStage.RENDER: RenderHandler(start_render, run_render, jobs),
        ProductionStage.QA: QaHandler(videos, jobs),
        ProductionStage.APPROVAL: ApprovalHandler(videos, approvals, RenderQaGate(videos, jobs, assets, clock)),
    }
    handlers[ProductionStage.RESEARCH] = UnavailableStageHandler(ProductionStage.RESEARCH, RESEARCH_REASON)
    handlers[ProductionStage.PUBLISH] = UnavailableStageHandler(ProductionStage.PUBLISH, PUBLISH_REASON)
    return handlers


# Pipeline do coordenador: começa no roteiro (a pesquisa é pré-condição, não etapa automática) e
# termina na aprovação (a publicação é fatia F, fora do coordenador).
COORDINATOR_DAG = StageDag({
    ProductionStage.SCRIPT: (),
    ProductionStage.FACTCHECK: (ProductionStage.SCRIPT,),
    ProductionStage.STORYBOARD: (ProductionStage.FACTCHECK,),
    ProductionStage.ASSETS: (ProductionStage.STORYBOARD,),
    ProductionStage.RENDER: (ProductionStage.ASSETS,),
    ProductionStage.QA: (ProductionStage.RENDER,),
    ProductionStage.APPROVAL: (ProductionStage.QA,),
})


# ---------------------------------------------------------------------------
# Projeção de status
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionProjection:
    """Visão somente-leitura de um run: run, etapas, próxima ação e capacidades."""

    run: ProductionRun
    stages: tuple[StageExecution, ...]
    next_stage: ProductionStage | None
    next_action: str | None  # "run" | "retry" | "resume" | "approve" | None
    mode: ProductionMode
    available_stages: tuple[ProductionStage, ...]
    unavailable_stages: tuple[tuple[ProductionStage, str], ...]


# ---------------------------------------------------------------------------
# Coordenador e worker
# ---------------------------------------------------------------------------


class ProductionCoordinator:
    """Orquestra um run pelas portas. Não importa nenhum adaptador concreto."""

    def __init__(self, runs: ProductionRunRepository & ProductionRunStageReader, *,
                 handlers: Mapping[ProductionStage, StageHandler], mode: ProductionMode = ProductionMode.INTERACTIVE,
                 lease_seconds: int = 300, budget: ProductionBudget | None = None,
                 pipeline: StageDag = COORDINATOR_DAG):
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 86_400:
            raise ValueError("lease_seconds must be an integer between 1 and 86400")
        missing = [stage for stage in pipeline.stages if stage not in handlers]
        if missing:
            raise ValueError("every pipeline stage needs a handler: " + ", ".join(stage.value for stage in missing))
        self.runs = runs
        self.handlers = dict(handlers)
        self.mode = mode
        self.lease_seconds = lease_seconds
        self.budget = budget
        self.pipeline = pipeline

    # -- criação e consulta ------------------------------------------------

    def default_pipeline(self) -> tuple[ProductionStage, ...]:
        return tuple(stage for stage in self.pipeline.topological_order() if self.handlers[stage].available)

    def available_stages(self) -> tuple[ProductionStage, ...]:
        return tuple(stage for stage in ProductionStage
                     if stage in self.handlers and self.handlers[stage].available)

    def unavailable_stages(self) -> tuple[tuple[ProductionStage, str], ...]:
        return tuple((stage, self.handlers[stage].reason) for stage in ProductionStage
                     if stage in self.handlers and not self.handlers[stage].available)

    def start(self, video_id: str, idempotency_key: str, *, channel_id: str | None = None,
              stages: Sequence[ProductionStage] | None = None) -> RunCreation:
        """Cria (ou reusa, pela chave) a execução. Não executa nada: o worker pega as etapas prontas."""
        video_id = check_id(video_id)
        if channel_id is not None:
            channel_id = check_id(channel_id)
        requested = self.default_pipeline() if stages is None else tuple(stages)
        self._require_available(requested)
        ordered = self.pipeline.validate_stages(requested)
        # `run_id` determinístico pela chave: o replay apresenta a mesma identidade, então o
        # repositório devolve EXISTING em vez de conflito — chamada repetida não duplica run.
        run_id = uuid.uuid5(uuid.NAMESPACE_URL, f"studio-production-run:{video_id}:{idempotency_key}").hex
        return self.runs.create_run(run_id, video_id, idempotency_key, channel_id=channel_id, stages=ordered)

    def get(self, run_id: str) -> ProductionProjection | None:
        run = self.runs.get_run(run_id)
        if run is None:
            return None
        stages = tuple(self.runs.list_stages(run_id))
        next_stage = self._next_stage(stages)
        return ProductionProjection(run=run, stages=stages, next_stage=next_stage,
                                    next_action=self._next_action(run, next_stage), mode=self.mode,
                                    available_stages=self.available_stages(),
                                    unavailable_stages=self.unavailable_stages())

    def events(self, run_id: str, limit: int = 100) -> list[OutboxEvent]:
        return self.runs.read_outbox(limit, run_id=run_id)

    # -- ciclo de vida -----------------------------------------------------

    def pause(self, run_id: str, reason: str) -> RunTransition:
        return self.runs.pause_run(run_id, reason)

    def resume(self, run_id: str, *, expected_state: RunState | None = None) -> RunTransition:
        run = self.runs.get_run(run_id)
        if run is None:
            raise RunNotFound(run_id)
        return self.runs.resume_run(run_id, expected_state or run.state)

    def cancel(self, run_id: str, reason: str) -> RunTransition:
        return self.runs.cancel_run(run_id, reason)

    def retry(self, run_id: str, *, expected_state: RunState = RunState.FAILED) -> RunTransition:
        run = self.runs.get_run(run_id)
        if run is None:
            raise RunNotFound(run_id)
        if run.state is not expected_state:
            return RunTransition(RunTransitionResult.NOT_ALLOWED, run)
        return self.runs.resume_run(run_id, expected_state)

    # -- laço do worker ----------------------------------------------------

    def step(self, run_id: str, *, owner: str) -> WorkerStep:
        """Um passo: pega a próxima etapa pronta e a executa; nunca bloqueia esperando humano."""
        run = self.runs.get_run(run_id)
        if run is None:
            return WorkerStep(WorkerStepResult.NOTHING_READY)
        if run.state in (RunState.SUCCEEDED, RunState.CANCELLED, RunState.FAILED, RunState.WAITING_HUMAN, RunState.PAUSED):
            return WorkerStep(WorkerStepResult.TERMINAL, run=run)
        claim = self._claim_ready(run_id, owner)
        if claim is None:
            return WorkerStep(WorkerStepResult.NOTHING_READY, run=run)
        execution = claim.execution
        assert execution is not None  # CLAIMED sempre traz a etapa
        return self._execute_claimed(run, execution, owner)

    def _claim_ready(self, run_id: str, owner: str) -> StageClaim | None:
        for stage in self.pipeline.topological_order():
            claim = self.runs.claim_stage(run_id, stage, owner, self.lease_seconds)
            if claim.result is StageClaimResult.CLAIMED:
                return claim
        return None

    def _execute_claimed(self, run: ProductionRun, execution: StageExecution, owner: str) -> WorkerStep:
        handler = self.handlers[execution.stage_id]
        try:
            outcome = handler.execute(StageContext(run=run, execution=execution))
        except StageExecutionFailed as exc:
            return self._fail(run, execution, owner, str(exc))
        except StageCapabilityUnavailable as exc:
            return self._fail(run, execution, owner, str(exc))
        except Exception as exc:  # o worker não pode derrubar o processo: a etapa vira FAILED com a causa
            logger.warning("stage %s failed: %s", execution.stage_id.value, type(exc).__name__)
            return self._fail(run, execution, owner, f"{type(exc).__name__}: {exc}")
        if outcome.request_human is not None:
            return self._pause(run, execution, owner, WorkerStepResult.PAUSED, outcome.request_human)
        transition = self.runs.complete_stage(run.run_id, execution.stage_id, owner, execution.fencing_token,
                                              checkpoint=outcome.checkpoint)
        if transition.result is not StageTransitionResult.APPLIED:
            return WorkerStep(self._lost_or_nothing(transition.result), run=run, stage=execution.stage_id,
                              execution=execution, detail=transition.result.value)
        reason = self._pause_after(execution.stage_id, run)
        if reason is not None:
            paused = self.runs.pause_run(run.run_id, reason)
            if paused.result is RunTransitionResult.APPLIED:
                return WorkerStep(WorkerStepResult.COMPLETED_PAUSED, run=paused.run or run,
                                  stage=execution.stage_id, execution=execution, detail=reason)
        return WorkerStep(WorkerStepResult.COMPLETED, run=run, stage=execution.stage_id, execution=execution)

    def _pause(self, run: ProductionRun, execution: StageExecution, owner: str,
               result: WorkerStepResult, reason: str) -> WorkerStep:
        paused = self.runs.pause_run(run.run_id, reason)
        if paused.result is RunTransitionResult.APPLIED:
            return WorkerStep(result, run=paused.run or run, stage=execution.stage_id, execution=execution,
                              detail=reason)
        # O run deixou de estar ativo (já terminal): a pausa não se aplica; reporta o desfecho real.
        return WorkerStep(self._lost_or_nothing(RunTransitionResult.NOT_ALLOWED), run=paused.run or run,
                          stage=execution.stage_id, execution=execution, detail=reason)

    def _fail(self, run: ProductionRun, execution: StageExecution, owner: str, error: str) -> WorkerStep:
        transition = self.runs.fail_stage(run.run_id, execution.stage_id, owner, execution.fencing_token,
                                          (error or "stage failed")[:2000])
        if transition.result is StageTransitionResult.APPLIED:
            return WorkerStep(WorkerStepResult.FAILED, run=run, stage=execution.stage_id,
                              execution=transition.execution, detail=error[:2000])
        return WorkerStep(self._lost_or_nothing(transition.result), run=run, stage=execution.stage_id,
                          execution=execution, detail=error[:2000])

    @staticmethod
    def _lost_or_nothing(result: StageTransitionResult | RunTransitionResult) -> WorkerStepResult:
        return WorkerStepResult.LOST if result is StageTransitionResult.LOST else WorkerStepResult.NOTHING_READY

    def _pause_after(self, stage: ProductionStage, run: ProductionRun) -> str | None:
        """Pausas humanas das etapas intermediárias. A etapa `approval` pausa pelo próprio handler."""
        if stage is not ProductionStage.SCRIPT:
            return None
        if self.mode is ProductionMode.INTERACTIVE:
            return "roteiro gerado: revisão humana obrigatória antes de continuar"
        projection = self.budget.project(run, ProductionStage.FACTCHECK) if self.budget is not None else None
        if projection is None:
            return "projeção de custo do canal desconhecida: revisão humana antes de continuar"
        if projection.exceeds():
            return "projeção de custo excede o teto do canal: revisão humana obrigatória"
        return None

    # -- projeção interna --------------------------------------------------

    def _require_available(self, stages: Sequence[ProductionStage]) -> None:
        for stage in stages:
            handler = self.handlers.get(stage)
            if handler is None:
                raise StageCapabilityUnavailable(stage, "unknown stage")
            if not handler.available:
                raise StageCapabilityUnavailable(stage, handler.reason)

    def _next_stage(self, stages: tuple[StageExecution, ...]) -> ProductionStage | None:
        by_id = {stage.stage_id: stage for stage in stages}
        for stage in self.pipeline.topological_order():
            execution = by_id.get(stage)
            if execution is not None and execution.state not in (StageState.SUCCEEDED, StageState.SKIPPED):
                return stage
        return None

    def _next_action(self, run: ProductionRun, next_stage: ProductionStage | None) -> str | None:
        if run.state in (RunState.SUCCEEDED, RunState.CANCELLED):
            return None
        if run.state is RunState.FAILED:
            return "retry"
        if run.state is RunState.WAITING_HUMAN:
            return "approve" if next_stage is ProductionStage.APPROVAL else "resume"
        if run.state is RunState.PAUSED:
            return "resume"
        return "run"


class ProductionWorker:
    """Laço que consome etapas prontas de um run até pausar, falhar ou não haver nada a fazer.

    Não bloqueia em etapa humana: quando o coordenador pausa, o laço encerra e libera a thread.
    """

    def __init__(self, coordinator: ProductionCoordinator, *, owner: str | None = None, max_steps: int = 64):
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.coordinator = coordinator
        self.owner = owner or f"worker-{uuid.uuid4().hex[:12]}"
        self.max_steps = max_steps

    def work(self, run_id: str) -> tuple[WorkerStep, ...]:
        steps: list[WorkerStep] = []
        for _ in range(self.max_steps):
            step = self.coordinator.step(run_id, owner=self.owner)
            steps.append(step)
            if step.result is not WorkerStepResult.COMPLETED:
                break
        return tuple(steps)


@dataclass(frozen=True)
class Production:
    """Serviço de produção exposto à API: coordenador, worker e o gatilho de execução."""

    coordinator: ProductionCoordinator
    worker: ProductionWorker
    submit: Callable[[str], None] | None = None

    def start(self, video_id: str, idempotency_key: str, *, channel_id: str | None = None,
              stages: Sequence[ProductionStage] | None = None) -> RunCreation:
        creation = self.coordinator.start(video_id, idempotency_key, channel_id=channel_id, stages=stages)
        if self.submit is not None:
            try:
                self.submit(creation.run.run_id)
            except Exception:  # fila indisponível: o run existe em CREATED e pode ser retomado
                logger.warning("could not enqueue production run %s", creation.run.run_id)
        return creation
