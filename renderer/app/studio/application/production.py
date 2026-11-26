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

import hashlib
import logging
import math
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Protocol

from ..domain.contracts import JobStatus, PublicationStatus, RenderJob, Video, VideoFormat, VideoStatus
from ..domain.effective_config import EffectiveConfig
from ..domain.ids import check_id
from ..domain.production_run import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    Checkpoint,
    CreateRunResult,
    OutboxEvent,
    ProductionRun,
    ProductionRunReferencedEntityNotFound,
    ProductionStage,
    RunCreation,
    RunOperation,
    RunState,
    RunTransition,
    RunTransitionResult,
    StageClaim,
    StageClaimResult,
    StageDag,
    StageExecution,
    StageState,
    StageTransitionResult,
    canonical_idempotency_key,
)
from ..domain.qa_report import (
    QaGateError,
    QaReport as VersionedQaReport,
    RenderVersion,
    approve as approve_qa,
    blocking_evidence,
)
from ..domain.run_config import RunConfigConflict, RunConfigStatus, StoredRunConfig
from ..domain.resilience import StageTimeoutError
from .budget import PaidOperationRepository, PaidOperationState
from .lease_heartbeat import LeaseHeartbeat, LeaseLost, StageLease
from .editorial import Editorial, SourceRefused, SourceUnavailable, StateConflict
from .media import Media
from .research import AutoResearch
from .publication_execution import PublicationResult, ReconcilePublication, RunPublication
from .ports import (
    ApprovalRepository,
    AssetRepository,
    ProductionRunConfigStore,
    PublicationQueueRepository,
    ProductionRunInFlightReader,
    ProductionRunRepository,
    ProductionRunStageReader,
    RenderJobRepository,
    VideoRepository,
)
from .render import RunRender, StartRender

logger = logging.getLogger("studio.production")

# S8: a seleção de provider congelada no snapshot do run em execução. O worker liga este contexto
# enquanto o handler roda; o roteador (composition) o consulta antes de qualquer re-roteamento.
# Fora de um run (ou em run legado sem `selection`) o valor é None e o comportamento é o de antes.
_FROZEN_PROVIDER_SELECTION: ContextVar[Mapping[str, str] | None] = ContextVar(
    "frozen_provider_selection", default=None)


def frozen_provider_selection() -> Mapping[str, str] | None:
    """Seleção congelada do run em execução, ou None quando não há snapshot com seleção."""
    return _FROZEN_PROVIDER_SELECTION.get()


@contextmanager
def use_frozen_provider_selection(selection: Mapping[str, str] | None):
    """Liga a seleção congelada só durante a execução do handler (isolamento por contexto)."""
    token = _FROZEN_PROVIDER_SELECTION.set(selection)
    try:
        yield
    finally:
        _FROZEN_PROVIDER_SELECTION.reset(token)


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


class RunConfigUnavailable(CoordinatorError, StateConflict):
    """A operação exige o snapshot congelado e o run é **legado** (não há entrada reproduzível).

    Política aprovada de F03.T04: o legado continua legível e aceita pause/resume/cancel, mas
    nenhuma operação que promete reproduzir as mesmas entradas (retry, por exemplo) é simulada.
    Herda `StateConflict` porque a API já mapeia esse conflito para 409 com a mensagem — nenhum
    caminho novo de erro HTTP precisa nascer para isso.
    """


# ---------------------------------------------------------------------------
# Chave da execução nova (regenerate) — F03.T04
# ---------------------------------------------------------------------------

REGENERATE_SUFFIX = ".regenerate"


def _regeneration_key(source_key: str, revision: int = 1) -> str:
    """Chave idempotente **nova e determinística** derivada do run de origem.

    `regenerate` é uma execução nova: a chave difere da origem e um duplo clique reusa a mesma
    execução (idempotência) — nunca devolve o run de origem. `revision > 1` pede outra execução
    (uma revisão seguinte) sem que o chamador invente chave: o sufixo numérico é canônico.
    A forma canônica (`[a-z0-9._:-]`) admite o ponto; chaves longas caem para um digest estável.
    """
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError("regeneration revision must be an integer >= 1")
    suffix = REGENERATE_SUFFIX if revision == 1 else f"{REGENERATE_SUFFIX}.{revision}"
    candidate = f"{source_key}{suffix}"
    if len(candidate) <= MAX_IDEMPOTENCY_KEY_LENGTH:
        return canonical_idempotency_key(candidate)
    digest = hashlib.sha256(f"{source_key}{suffix}".encode("utf-8")).hexdigest()[:32]
    return canonical_idempotency_key(f"regen.{digest}")


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
    lease: StageLease | None = None
    cancel_event: threading.Event | None = None
    deadline_monotonic: float | None = None
    clock: Callable[[], float] = time.monotonic

    @property
    def checkpoint_version(self) -> int:
        # Monotônica por tentativa: retry nunca tenta regravar a versão anterior.
        return max(1, self.execution.attempt)

    def is_cancelled(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()

    def ensure_active(self, clock: Callable[[], float] | None = None) -> None:
        now_fn = clock or self.clock
        if self.is_cancelled() or (self.deadline_monotonic is not None and now_fn() >= self.deadline_monotonic):
            raise StageTimeoutError("stage cancelled or deadline exceeded")
        if self.lease is not None:
            self.lease.ensure_held()


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


class ResearchHandler(_AvailableHandler):
    """Pesquisa automática do tema (F3 mínimo). Fontes já registradas pelo humano são respeitadas."""

    stage = ProductionStage.RESEARCH

    def __init__(self, research: AutoResearch):
        self.research = research

    def execute(self, context: StageContext) -> StageOutcome:
        try:
            result = self.research.execute(context.run.video_id)
        except SourceUnavailable as exc:
            raise StageExecutionFailed(
                "a pesquisa automática não conseguiu acessar a fonte de referência agora; tente de novo "
                f"ou adicione uma fonte manualmente ({exc})") from exc
        except SourceRefused as exc:
            raise StageExecutionFailed(
                "a pesquisa automática não achou uma fonte com fatos verificáveis para este tema; "
                "adicione uma fonte manualmente em Fontes e inicie de novo") from exc
        return StageOutcome(checkpoint=Checkpoint(
            {"stage": self.stage.value, "sources": len(result.snapshots), "reused": result.reused,
             "urls": [snap.url for snap in result.snapshots]}, context.checkpoint_version))


class ScriptHandler(_AvailableHandler):
    stage = ProductionStage.SCRIPT

    def __init__(self, editorial: Editorial, videos: VideoRepository | None = None):
        self.editorial, self.videos = editorial, videos

    def execute(self, context: StageContext) -> StageOutcome:
        video = self.videos.get_video(context.run.video_id) if self.videos is not None else None
        if video is not None and video.status is VideoStatus.SCRIPTED:
            # Roteiro já escrito (Diretor, ou vídeo reaberto por "Pedir ajustes"): produzir de novo NÃO o reescreve,
            # senão as edições do operador seriam descartadas. Reescrever é a ação explícita "Gerar roteiro".
            found = self.editorial.get_script.execute(context.run.video_id)
            if found is not None:
                return StageOutcome(checkpoint=Checkpoint(
                    {"stage": self.stage.value, "script_version": found[0].version, "reused": True},
                    context.checkpoint_version))
        if video is not None and video.format is VideoFormat.long and self.editorial.long_generate is not None:
            script = self.editorial.long_generate.execute(context.run.video_id)  # F4: duas passagens
        else:
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
        # F03.T03: o job do run lê a configuração **congelada** do run (nunca re-resolve).
        self.run.execute(job.id, context.run.run_id)  # o worker do coordenador roda o render em linha
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
        if not report.is_publishable:
            raise StageExecutionFailed("QA failed: " + "; ".join(blocking_evidence(report)))
        return StageOutcome(checkpoint=Checkpoint(
            {"stage": self.stage.value, "render_job": job.id, "qa_passed": True}, context.checkpoint_version))


class RenderQaGate:
    """Liga o relatório de QA **persistido** ao gate de aprovação por versão (F6).

    Fonte única: o relatório é o que o loop de render produziu e gravou em ``videos.qa_report``
    (F6), não uma segunda medição. A identidade do render é declarada, não recalculada: o
    ``render_id`` é o job e o ``checksum`` é a chave do asset de saída (a mesma que a publicação
    usa). O gate recusa render superado e cobertura não verificada; sem render ou sem QA devolve
    ``None`` (nada a aprovar).
    """

    def __init__(self, videos: VideoRepository, jobs: RenderJobRepository, assets: AssetRepository):
        self.videos, self.jobs, self.assets = videos, jobs, assets

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
        report = video.qa_report
        if report is None:
            return None
        approved = self.assets.get(approved_asset_id) if approved_asset_id else None
        requested = RenderVersion(render_id=job.id, checksum=approved.cache_key if approved else latest.checksum)
        # O relatório persistido é o mesmo que o loop produziu; só a identidade é reamarrada ao
        # render que se pretende aprovar (o gate da F6 é sobre a versão aprovada). Os achados e a
        # cobertura são os do relatório — nada é remedido aqui.
        bound = report.model_copy(update={"render_id": job.id, "checksum": latest.checksum})
        return bound, latest, requested


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


RESEARCH_REASON = "research automático não está configurado; adicione fontes ao vídeo antes de produzir"
PUBLISH_REASON = "publication executor is not configured (F8); nothing is uploaded and success is never simulated"


class PublishHandler(_AvailableHandler):
    """Estágio `publish` real (F8): executa o caminho nativo e nunca finge sucesso.

    O executor já reivindica a publicação do vídeo deste run, aplica o gate de QA/render e decide
    retry/DLQ/reconciliação. Aqui só traduzimos o desfecho para o coordenador: só `UPLOADED`
    conclui a etapa; o resto falha com o motivo real (sem autoaprovação e sem retry cego).
    """

    stage = ProductionStage.PUBLISH

    def __init__(self, publish: RunPublication, reconcile: ReconcilePublication | None = None,
                 pubs: PublicationQueueRepository | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.publish, self.reconcile, self.pubs, self.clock = publish, reconcile, pubs, clock

    def _done(self, context: StageContext, youtube_video_id: str | None, publication_id: str | None) -> StageOutcome:
        return StageOutcome(checkpoint=Checkpoint(
            {"stage": self.stage.value, "youtube_video_id": youtube_video_id, "publication_id": publication_id},
            context.checkpoint_version))

    def _confirmed_id(self, pub, state) -> str | None:
        return (pub.youtube_video_id if pub else None) or (state.youtube_video_id if state else None) or None

    def _reconcile_first(self, context: StageContext) -> StageOutcome | None:
        """D8: nunca reenvia sobre uma publicação ambígua/obsoleta; o CAS do banco decide a obsolescência."""
        video_id = context.run.video_id
        pub = self.pubs.get(video_id)
        if pub is None:
            return None
        state = self.pubs.lease_state(video_id)
        confirmed = self._confirmed_id(pub, state)
        if confirmed:
            return self._done(context, confirmed, pub.id)
        if state is not None and state.dead_letter:
            raise StageExecutionFailed("publication is in the dead-letter queue; resolve it manually")
        if pub.status is PublicationStatus.UPLOADING:
            for _ in range(2):
                until = state.lease_until if state else None
                if until is not None and until > self.clock():
                    raise StageExecutionFailed("a previous upload attempt is still active; wait for its lease or reconcile")
                if self.pubs.mark_stale_ambiguous(
                        pub.id, pub.attempt,
                        "stage re-claimed after the previous executor stopped; upload outcome unknown"):
                    break
                pub = self.pubs.get(video_id) or pub
                state = self.pubs.lease_state(video_id)
                confirmed = self._confirmed_id(pub, state)
                if confirmed:
                    return self._done(context, confirmed, pub.id)
            else:
                raise StageExecutionFailed("could not settle the previous upload attempt; try again later")
            state = self.pubs.lease_state(video_id)
        if state is not None and state.remote_state == "UNKNOWN":
            if self.reconcile is None:
                raise StageExecutionFailed("publication outcome is ambiguous; reconcile before retrying")
            run = self.reconcile.execute(pub.id)
            if run.result is PublicationResult.UPLOADED:
                confirmed = (run.youtube_video_id or (run.publication.youtube_video_id if run.publication else None)
                             or pub.youtube_video_id)
                if not confirmed:
                    raise StageExecutionFailed("reconcile reported UPLOADED without a confirmed YouTube video id")
                return self._done(context, confirmed, pub.id)
            if run.result is not PublicationResult.RETRY:
                raise StageExecutionFailed(
                    f"publication did not complete ({run.result.value}): {run.detail or 'no detail'}")
        return None

    def execute(self, context: StageContext) -> StageOutcome:
        if context.lease is not None:
            context.lease.ensure_held()
        if self.pubs is not None:
            done = self._reconcile_first(context)
            if done is not None:
                return done
            if context.lease is not None:
                context.lease.ensure_held()
        outcome = self.publish.execute(video_id=context.run.video_id)
        if outcome.result is PublicationResult.UPLOADED:
            return self._done(context, outcome.youtube_video_id, outcome.publication.id if outcome.publication else None)
        if outcome.result is PublicationResult.IDLE:
            raise StageExecutionFailed("no approved publication is pending for this video")
        raise StageExecutionFailed(f"publication did not complete ({outcome.result.value}): {outcome.detail or 'no detail'}")


def build_stage_handlers(*, editorial: Editorial, media: Media, start_render: StartRender, run_render: RunRender,
                         videos: VideoRepository, jobs: RenderJobRepository, assets: AssetRepository,
                         approvals: ApprovalRepository, publish: RunPublication | None = None,
                         research: AutoResearch | None = None, reconcile: ReconcilePublication | None = None,
                         publications: PublicationQueueRepository | None = None
                         ) -> dict[ProductionStage, StageHandler]:
    """Registra todos os nove estágios: os implementados por handler e os indisponíveis explícitos."""
    if reconcile is not None and publications is None:
        raise ValueError("`reconcile` requires `publications`: it would be silently ignored")
    handlers: dict[ProductionStage, StageHandler] = {
        ProductionStage.SCRIPT: ScriptHandler(editorial, videos),
        ProductionStage.FACTCHECK: FactCheckHandler(editorial),
        ProductionStage.STORYBOARD: StoryboardHandler(media),
        ProductionStage.ASSETS: AssetsHandler(media),
        ProductionStage.RENDER: RenderHandler(start_render, run_render, jobs),
        ProductionStage.QA: QaHandler(videos, jobs),
        ProductionStage.APPROVAL: ApprovalHandler(videos, approvals, RenderQaGate(videos, jobs, assets)),
    }
    handlers[ProductionStage.RESEARCH] = (ResearchHandler(research) if research is not None
                                          else UnavailableStageHandler(ProductionStage.RESEARCH, RESEARCH_REASON))
    handlers[ProductionStage.PUBLISH] = (PublishHandler(publish, reconcile, publications) if publish is not None
                                         else UnavailableStageHandler(ProductionStage.PUBLISH, PUBLISH_REASON))
    return handlers


# Pipeline do coordenador: a pesquisa só entra na execução quando há provedor (handler disponível).
# F8: a publicação passa a ser a última etapa executável — somente depois da aprovação humana/QA.
COORDINATOR_DAG = StageDag({
    ProductionStage.SCRIPT: (),
    ProductionStage.FACTCHECK: (ProductionStage.SCRIPT,),
    ProductionStage.STORYBOARD: (ProductionStage.FACTCHECK,),
    ProductionStage.ASSETS: (ProductionStage.STORYBOARD,),
    ProductionStage.RENDER: (ProductionStage.ASSETS,),
    ProductionStage.QA: (ProductionStage.RENDER,),
    ProductionStage.APPROVAL: (ProductionStage.QA,),
    ProductionStage.PUBLISH: (ProductionStage.APPROVAL,),
})


# Com pesquisa automática configurada, a pesquisa é a primeira etapa e o roteiro depende dela.
COORDINATOR_DAG_WITH_RESEARCH = StageDag({
    ProductionStage.RESEARCH: (),
    ProductionStage.SCRIPT: (ProductionStage.RESEARCH,),
    ProductionStage.FACTCHECK: (ProductionStage.SCRIPT,),
    ProductionStage.STORYBOARD: (ProductionStage.FACTCHECK,),
    ProductionStage.ASSETS: (ProductionStage.STORYBOARD,),
    ProductionStage.RENDER: (ProductionStage.ASSETS,),
    ProductionStage.QA: (ProductionStage.RENDER,),
    ProductionStage.APPROVAL: (ProductionStage.QA,),
    ProductionStage.PUBLISH: (ProductionStage.APPROVAL,),
})


# ---------------------------------------------------------------------------
# Projeção de status
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionProjection:
    """Visão somente-leitura de um run: run, etapas, próxima ação e capacidades.

    F03.T04: a configuração aparece só como **referência** (`status` + `hash`) — o documento do
    snapshot nunca entra na projeção, então nenhum payload carrega token nem campo com credencial.
    `None`/`None` significa "sem porta de leitura" (deployment sem snapshot), não "legado".
    """

    run: ProductionRun
    stages: tuple[StageExecution, ...]
    next_stage: ProductionStage | None
    next_action: str | None  # "run" | "retry" | "resume" | "approve" | None
    mode: ProductionMode
    available_stages: tuple[ProductionStage, ...]
    unavailable_stages: tuple[tuple[ProductionStage, str], ...]
    config_status: RunConfigStatus | None = None
    config_hash: str | None = None


def has_live_lease(stages: Sequence[StageExecution], now: datetime) -> bool:
    """Alguma etapa tem lease vivo em `now`?

    Lease ausente ou expirado não conta: o dono anterior já não pode escrever, então o run está
    órfão e pode ser re-lançado. Sem esse predicado, um run `RUNNING` cuja thread morreu ficaria
    preso para sempre — a UI só oferecia `Pausar`, que não devolve worker.
    """
    for execution in stages:
        expires = execution.lease_expires_at
        if execution.lease_owner and expires is not None and expires > now:
            return True
    return False


def _latest_activity(run: ProductionRun, stages: Sequence[StageExecution]) -> datetime | None:
    moments = [m for m in (run.updated_at, run.created_at, *(stage.updated_at for stage in stages)) if m is not None]
    return max(moments) if moments else None


def orphan_in_flight(
    in_flight: Iterable[tuple[ProductionRun, Sequence[StageExecution]]], now: datetime,
    grace: timedelta = timedelta(0),
) -> tuple[str, ...]:
    """Run ids **órfãos** entre os runs em voo: os que a recuperação deve re-dirigir.

    Regra pura (sem I/O, `now` é parâmetro): um run é órfão quando nada o dirige agora.

    - `CREATED`: nunca passou pelo `submit` (a fila estava indisponível no `start`), então é
      recuperável por definição — o worker o levará a `RUNNING` ao reivindicar a primeira etapa.
    - `RUNNING`: só é órfão se **nenhuma** etapa tem lease vivo (`has_live_lease`). Com lease vivo
      o dono ainda pode escrever e re-dirigir criaria worker ocioso/duplicado: fica de fora.
    - Qualquer outro estado (`FAILED`/`SUCCEEDED`/`CANCELLED`/`WAITING_HUMAN`/`PAUSED`) nunca entra,
      ainda que a leitura os traga: recuperar não é retomar nem retentar.

    `grace` (recuperação periódica): além do acima, a última atividade conhecida (run e etapas,
    ignorando `None`) precisa ser `<= now - grace`; sem nenhuma atividade conhecida o run é elegível.
    Com `grace=0` (boot) o comportamento é o original.

    Devolve os ids na ordem de `in_flight` (ordem estável da porta), sem duplicar.
    """
    orphans: list[str] = []
    for run, stages in in_flight:
        if run.state is RunState.CREATED:
            eligible = True
        elif run.state is RunState.RUNNING:
            eligible = not has_live_lease(stages, now)
        else:
            eligible = False
        if eligible and grace > timedelta(0):
            latest = _latest_activity(run, stages)
            eligible = latest is None or latest <= now - grace
        if eligible:
            orphans.append(run.run_id)
    return tuple(orphans)


class CapacityExceeded(RuntimeError):
    """Limite de capacidade de execuções simultâneas atingido no processo local."""


class ActiveRuns:
    """Runs despachados neste processo e ainda não terminados (contador por `run_id`, thread-safe).

    Evita que a recuperação periódica re-despache um run que está na fila do executor (sem lease
    ainda) ou entre duas etapas do worker. Entre réplicas a segurança vem do CAS de `claim_stage`.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}

    def acquire(self, run_id: str) -> None:
        with self._lock:
            self._counts[run_id] = self._counts.get(run_id, 0) + 1

    def release(self, run_id: str) -> None:
        with self._lock:
            remaining = self._counts.get(run_id, 0) - 1
            if remaining > 0:
                self._counts[run_id] = remaining
            else:
                self._counts.pop(run_id, None)

    def snapshot(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._counts)

    def count(self) -> int:
        with self._lock:
            return len(self._counts)


# ---------------------------------------------------------------------------
# Coordenador e worker
# ---------------------------------------------------------------------------


class ProductionCoordinator:
    """Orquestra um run pelas portas. Não importa nenhum adaptador concreto."""

    def __init__(self, runs: ProductionRunRepository & ProductionRunStageReader, *,
                 handlers: Mapping[ProductionStage, StageHandler], mode: ProductionMode = ProductionMode.INTERACTIVE,
                 lease_seconds: int = 300, budget: ProductionBudget | None = None,
                 pipeline: StageDag = COORDINATOR_DAG, videos: VideoRepository | None = None,
                 config_store: ProductionRunConfigStore | None = None,
                 paid_ops: PaidOperationRepository | None = None,
                 operation_key_for: Callable[[ProductionRun, StageExecution], str | None] | None = None,
                 reconcile_operation: Callable[[str, ProductionRun, StageExecution], bool] | None = None,
                 stage_timeouts: Mapping[ProductionStage, float] | None = None,
                 default_stage_timeout_seconds: float | None = None,
                 clock: Callable[[], float] = time.monotonic):
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
        # F03.T02: leitura do snapshot congelado (a escrita é do `create_run`, na mesma transação
        # do run) e leitura do vídeo para entregar o agregado ao resolvedor.
        self.videos = videos
        self.config_store = config_store
        self.paid_ops = paid_ops
        self.operation_key_for = operation_key_for
        self.reconcile_operation = reconcile_operation
        self._stage_timeouts: dict[ProductionStage, float] = {}
        if stage_timeouts is not None:
            for stage, val in stage_timeouts.items():
                fval = float(val)
                if not math.isfinite(fval) or fval <= 0:
                    raise ValueError(f"stage timeout for {stage.value} must be a positive finite number")
                self._stage_timeouts[stage] = fval
        if default_stage_timeout_seconds is not None:
            fdef = float(default_stage_timeout_seconds)
            if not math.isfinite(fdef) or fdef <= 0:
                raise ValueError("default_stage_timeout_seconds must be a positive finite number")
            self._default_stage_timeout_seconds: float | None = fdef
        else:
            self._default_stage_timeout_seconds = None
        self._clock = clock

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
              stages: Sequence[ProductionStage] | None = None,
              effective_config_for: Callable[[Video], EffectiveConfig] | None = None,
              config_store: ProductionRunConfigStore | None = None,
              provider_selection_for: Callable[[Video, EffectiveConfig], Mapping[str, str] | None] | None = None
              ) -> RunCreation:
        """Cria (ou reusa, pela chave) a execução. Não executa nada: o worker pega as etapas prontas.

        F03.T02: com `effective_config_for`, a configuração efetiva é resolvida **antes** de gravar
        o run e o snapshot vai para o mesmo INSERT (`create_run` grava run + etapas + snapshot ou
        nada). Sem resolvedor, o comportamento anterior é preservado e o run nasce `legacy` de
        forma explícita — nunca re-resolvido depois. O replay devolve o run existente com a config
        que ele já tinha; um snapshot divergente é `RunConfigConflict`, não sobrescrita.

        S8: com `provider_selection_for`, a seleção efetiva por capacidade é resolvida junto com a
        configuração e congelada no mesmo snapshot. Sem ela, o snapshot continua sem `selection`
        (run legado) e o roteamento vivo segue como antes.
        """
        video_id = check_id(video_id)
        if channel_id is not None:
            channel_id = check_id(channel_id)
        requested = self.default_pipeline() if stages is None else tuple(stages)
        self._require_available(requested)
        ordered = self.pipeline.validate_stages(requested)
        store = config_store if config_store is not None else self.config_store
        config = self._resolve_config(video_id, effective_config_for, provider_selection_for)
        # `run_id` determinístico pela chave: o replay apresenta a mesma identidade, então o
        # repositório devolve EXISTING em vez de conflito — chamada repetida não duplica run.
        run_id = uuid.uuid5(uuid.NAMESPACE_URL, f"studio-production-run:{video_id}:{idempotency_key}").hex
        creation = self.runs.create_run(run_id, video_id, idempotency_key, channel_id=channel_id,
                                        stages=ordered, config=config)
        # O repositório real já recusa divergência dentro da transação; aqui conferimos a referência
        # devolvida para que um repositório sem a coluna não devolva "sucesso" com outro snapshot.
        if store is not None and config is not None:
            persisted = store.run_config(creation.run.run_id)
            if persisted is None or persisted.config is None \
                    or persisted.config.content_hash != config.content_hash:
                raise RunConfigConflict(
                    "the stored run config does not match the requested effective config")
        return creation

    def _resolve_config(self, video_id: str,
                        effective_config_for: Callable[[Video], EffectiveConfig] | None,
                        provider_selection_for: Callable[[Video, EffectiveConfig],
                                                         Mapping[str, str] | None] | None = None
                        ) -> EffectiveConfig | None:
        """Resolve antes do INSERT: erro aqui não cria run nem deixa efeito pela metade."""
        if effective_config_for is None:
            return None
        if not callable(effective_config_for):
            raise TypeError("effective_config_for must be callable or None")
        if self.videos is None:
            raise ValueError("resolving the effective config requires a video repository")
        video = self.videos.get_video(video_id)
        if video is None:
            raise ProductionRunReferencedEntityNotFound(f"video {video_id} does not exist")
        config = effective_config_for(video)
        if not isinstance(config, EffectiveConfig):
            raise TypeError("effective_config_for must return an EffectiveConfig")
        if config.video_id != video_id:
            raise ValueError("the effective config belongs to another video")
        if provider_selection_for is not None:
            if not callable(provider_selection_for):
                raise TypeError("provider_selection_for must be callable or None")
            selection = provider_selection_for(video, config)
            if selection:
                config = replace(config, provider_selection=selection)
        return config

    def config_for(self, run_id: str) -> StoredRunConfig | None:
        """Lê a configuração congelada do run; nunca resolve de novo.

        `None` sem porta de leitura ou para run inexistente; run legado vem com o marcador
        explícito (`status=LEGACY`, `config=None`).
        """
        if self.config_store is None:
            return None
        return self.config_store.run_config(check_id(run_id))

    def _frozen_selection(self, run_id: str) -> Mapping[str, str] | None:
        """Seleção congelada do snapshot do run; None em run legado ou config sem `selection`."""
        stored = self.config_for(run_id)
        if stored is None or stored.status is not RunConfigStatus.RESOLVED or stored.config is None:
            return None
        return stored.config.provider_selection

    def get(self, run_id: str) -> ProductionProjection | None:
        run = self.runs.get_run(run_id)
        if run is None:
            return None
        stages = tuple(self.runs.list_stages(run_id))
        next_stage = self._next_stage(stages)
        stored = self.config_for(run_id)
        return ProductionProjection(run=run, stages=stages, next_stage=next_stage,
                                    next_action=self._next_action(run, next_stage), mode=self.mode,
                                    available_stages=self.available_stages(),
                                    unavailable_stages=self.unavailable_stages(),
                                    config_status=stored.status if stored is not None else None,
                                    config_hash=stored.content_hash if stored is not None else None)

    def events(self, run_id: str, limit: int = 100) -> list[OutboxEvent]:
        return self.runs.read_outbox(limit, run_id=run_id)

    # -- ciclo de vida -----------------------------------------------------

    def pause(self, run_id: str, reason: str) -> RunTransition:
        transition = self.runs.pause_run(run_id, reason)
        if transition.result is RunTransitionResult.APPLIED:
            self.record_operation(run_id, RunOperation.PAUSE, reason=reason)
        return transition

    def resume(self, run_id: str, *, expected_state: RunState | None = None,
               reason: str | None = None) -> RunTransition:
        """Retoma sem re-resolver: a decisão é registrada na outbox com o snapshot já persistido.

        Reiniciar um run `FAILED` **é** retry (mesmo efeito), então a operação é derivada do estado
        persistido — não do endpoint — e um run legado é recusado para não fingir reprodução.
        """
        run = self.runs.get_run(run_id)
        if run is None:
            raise RunNotFound(run_id)
        operation = RunOperation.RETRY if run.state is RunState.FAILED else RunOperation.RESUME
        stored = self._require_frozen_config(run_id) if operation.requires_frozen_config \
            else self.config_for(run_id)
        transition = self.runs.resume_run(run_id, expected_state or run.state)
        if transition.result is RunTransitionResult.APPLIED:
            self.record_operation(run_id, operation, config=stored,
                                  reason=self._restart_reason(operation, reason, stored))
        return transition

    def cancel(self, run_id: str, reason: str) -> RunTransition:
        return self.runs.cancel_run(run_id, reason)

    def retry(self, run_id: str, *, expected_state: RunState = RunState.FAILED,
              reason: str | None = None) -> RunTransition:
        """Reinicia um run `FAILED` com as **mesmas** entradas congeladas; legado é recusado."""
        run = self.runs.get_run(run_id)
        if run is None:
            raise RunNotFound(run_id)
        if run.state is not expected_state:
            return RunTransition(RunTransitionResult.NOT_ALLOWED, run)
        stored = self._require_frozen_config(run_id)
        transition = self.runs.resume_run(run_id, expected_state)
        if transition.result is RunTransitionResult.APPLIED:
            self.record_operation(run_id, RunOperation.RETRY, config=stored,
                                  reason=self._restart_reason(RunOperation.RETRY, reason, stored))
        return transition

    # -- decisão de lifecycle (F03.T04) ------------------------------------

    def record_operation(self, run_id: str, operation: RunOperation, *, reason: str,
                         config: StoredRunConfig | None = None,
                         source_run_id: str | None = None) -> OutboxEvent | None:
        """Grava a decisão na outbox existente; falha de evento não desfaz o estado já aplicado."""
        if not isinstance(operation, RunOperation):
            raise TypeError("operation must be a RunOperation")
        stored = config if config is not None else self.config_for(run_id)
        try:
            return self.runs.record_operation(run_id, operation, reason=reason, config=stored,
                                              source_run_id=source_run_id)
        except (TypeError, ValueError):
            raise  # erro de programação (id/razão inválidos) não pode virar trilha "silenciosa"
        except Exception:  # a transição já foi aplicada: registrar é trilha, não pré-condição
            logger.warning("could not record %s for production run %s", operation.value, run_id)
            return None

    def _require_frozen_config(self, run_id: str) -> StoredRunConfig | None:
        """Recusa explícita (não silenciosa) quando a operação promete reproduzir as entradas.

        Devolve o snapshot lido (uma única leitura, reusada pela decisão) para não reler nem
        re-resolver. Sem porta de leitura (`config_store` ausente) o comportamento anterior é
        preservado: não há como afirmar que o run é legado, então a política não inventa a recusa.
        """
        stored = self.config_for(run_id)
        if stored is not None and stored.status is RunConfigStatus.LEGACY:
            raise RunConfigUnavailable(
                "this operation needs the frozen run config, but the run was created without a "
                "snapshot (legacy): its inputs cannot be reproduced. Start a new run to adopt a "
                "new revision.")
        return stored

    @staticmethod
    def _restart_reason(operation: RunOperation, reason: str | None,
                        stored: StoredRunConfig | None) -> str:
        """Motivo + decisão: o run legado diz explicitamente que **não** reproduz as entradas."""
        base = (reason or "").strip() or ("retry pelo operador" if operation is RunOperation.RETRY
                                          else "retomada pelo operador")
        if stored is None:
            return f"{base}; sem snapshot legível (configuração não reproduzida)"
        if stored.status is RunConfigStatus.LEGACY:
            return f"{base}; run legado sem snapshot: as entradas NÃO são reproduzidas"
        return (f"{base}; configuração congelada {str(stored.content_hash)[:12]} relida do snapshot "
                f"(sem re-resolver)")

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

    def _timeout_for(self, stage: ProductionStage) -> float | None:
        if stage in self._stage_timeouts:
            return self._stage_timeouts[stage]
        return self._default_stage_timeout_seconds

    def _reconcile_key(self, op_key: str, op_state: PaidOperationState,
                       run: ProductionRun, execution: StageExecution) -> bool:
        if self.reconcile_operation is None:
            return False
        if not self.reconcile_operation(op_key, run, execution):
            return False
        current = self.paid_ops.state(op_key) if self.paid_ops is not None else None
        return current not in (PaidOperationState.RESERVED, PaidOperationState.UNCERTAIN)

    def _check_pre_retry_reconciliation(self, run: ProductionRun, execution: StageExecution) -> str | None:
        """Verifica se há operação paga pendente/incerta antes de reexecutar efeito externo.

        Retorna uma mensagem de bloqueio (fail-closed) caso exista operação não reconciliada,
        ou None quando a execução pode prosseguir.
        """
        if self.paid_ops is None:
            return None
        if self.operation_key_for is not None:
            op_key = self.operation_key_for(run, execution)
            if op_key is not None:
                op_state = self.paid_ops.state(op_key)
                if op_state in (PaidOperationState.RESERVED, PaidOperationState.UNCERTAIN):
                    if not self._reconcile_key(op_key, op_state, run, execution):
                        return (
                            f"blocked before retry: paid operation {op_key} is {op_state.value} "
                            "and requires reconciliation"
                        )
        if execution.attempt > 1:
            pending = self.paid_ops.pending_reconciliation(stale_after=timedelta(0))
            for item in pending:
                if item.video_id != run.video_id:
                    continue
                if item.reason == "uncertain_operation":
                    op_state = PaidOperationState.UNCERTAIN
                elif item.reason == "stale_reservation":
                    cur = self.paid_ops.state(item.idempotency_key)
                    if cur not in (PaidOperationState.RESERVED, PaidOperationState.UNCERTAIN):
                        continue
                    op_state = cur
                else:
                    continue
                if not self._reconcile_key(item.idempotency_key, op_state, run, execution):
                    return (
                        f"blocked before retry: {op_state.value} paid operation {item.idempotency_key} "
                        f"for video {run.video_id} requires reconciliation"
                    )
        return None

    def _execute_claimed(self, run: ProductionRun, execution: StageExecution, owner: str) -> WorkerStep:
        handler = self.handlers[execution.stage_id]
        # S8: a seleção congelada é ligada só durante o handler. Em run legado (sem snapshot) ou
        # sem `selection`, o contexto fica None e o roteador segue o caminho vivo de antes.
        try:
            selection = self._frozen_selection(run.run_id)
        except Exception as exc:  # leitura do snapshot não pode derrubar o worker
            logger.warning("frozen selection read failed for %s: %s", run.run_id, type(exc).__name__)
            return self._fail(run, execution, owner, f"{type(exc).__name__}: {exc}")
        reconcile_block = self._check_pre_retry_reconciliation(run, execution)
        if reconcile_block is not None:
            return self._fail(run, execution, owner, reconcile_block)
        heartbeat = LeaseHeartbeat(
            renew=lambda: self.runs.renew_lease(run.run_id, execution.stage_id, owner, execution.fencing_token,
                                                self.lease_seconds),
            lease_seconds=self.lease_seconds)
        timeout_s = self._timeout_for(execution.stage_id)
        cancel_event = threading.Event()
        deadline = (self._clock() + timeout_s) if timeout_s is not None else None
        failure: Exception | None = None
        outcome = None
        # `lost` deriva com o relógio mesmo depois do stop: captura-se logo após o handler e só ele decide.
        with heartbeat as lease, use_frozen_provider_selection(selection):
            ctx = StageContext(
                run=run,
                execution=execution,
                lease=lease,
                cancel_event=cancel_event,
                deadline_monotonic=deadline,
                clock=self._clock,
            )
            try:
                if timeout_s is None:
                    outcome = handler.execute(ctx)
                else:
                    done = threading.Event()
                    box: dict[str, object] = {}

                    def _run_stage() -> None:
                        with use_frozen_provider_selection(selection):
                            try:
                                box["outcome"] = handler.execute(ctx)
                            except Exception as exc:  # noqa: BLE001
                                box["failure"] = exc
                            finally:
                                done.set()

                    worker_thread = threading.Thread(
                        target=_run_stage,
                        name=f"stage-{execution.stage_id.value}",
                        daemon=True,
                    )
                    worker_thread.start()
                    if not done.wait(timeout=timeout_s):
                        cancel_event.set()
                        failure = StageTimeoutError(
                            f"stage {execution.stage_id.value} exceeded timeout of {timeout_s}s"
                        )
                    elif "failure" in box:
                        failure = box["failure"]  # type: ignore[assignment]
                    else:
                        outcome = box.get("outcome")
            except Exception as exc:
                failure = exc
            finally:
                cancel_event.set()
            lost = lease.lost
            if failure is not None or lost:
                lease.revoke("stage execution failed or timed out")
        if lost or isinstance(failure, LeaseLost):
            return WorkerStep(WorkerStepResult.LOST, run=run, stage=execution.stage_id, execution=execution,
                              detail="lease lost during stage execution")
        if failure is not None:
            if isinstance(failure, (StageExecutionFailed, StageCapabilityUnavailable)):
                return self._fail(run, execution, owner, str(failure))
            logger.warning("stage %s failed: %s", execution.stage_id.value, type(failure).__name__)
            return self._fail(run, execution, owner, f"{type(failure).__name__}: {failure}")
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
    """Serviço de produção exposto à API: coordenador, worker e o gatilho de execução.

    `in_flight` é a porta de leitura dos runs em voo usada só na recuperação de boot (PROD-03);
    sem ela (ou com fila indisponível) a recuperação é no-op — o app sobe de qualquer forma.
    """

    coordinator: ProductionCoordinator
    worker: ProductionWorker
    submit: Callable[[str], None] | None = None
    in_flight: ProductionRunInFlightReader | None = None
    # F03.T02: resolvedor e leitura do snapshot. Ausentes = caminho legado explícito (sem snapshot).
    effective_config_for: Callable[[Video], EffectiveConfig] | None = None
    config_store: ProductionRunConfigStore | None = None
    # S8: seleção efetiva por capacidade, congelada junto com a configuração no mesmo snapshot.
    provider_selection_for: Callable[[Video, EffectiveConfig], Mapping[str, str] | None] | None = None

    def start(self, video_id: str, idempotency_key: str, *, channel_id: str | None = None,
              stages: Sequence[ProductionStage] | None = None) -> RunCreation:
        return self._create(video_id, idempotency_key, channel_id=channel_id, stages=stages,
                            operation=RunOperation.NEW_RUN)

    def new_run(self, video_id: str, idempotency_key: str, *, channel_id: str | None = None,
                stages: Sequence[ProductionStage] | None = None) -> RunCreation:
        """Nova execução explícita (mesmo caminho do `start`): chave nova → snapshot novo.

        A trilha grava a decisão `new_run` na criação real; replay da mesma chave não duplica.
        """
        return self._create(video_id, idempotency_key, channel_id=channel_id, stages=stages,
                            operation=RunOperation.NEW_RUN)

    def regenerate(self, run_id: str, *, revision: int = 1,
                   reason: str | None = None) -> RunCreation:
        """Gera de novo a partir de um run existente: **execução nova**, nunca um resume disfarçado.

        Chave nova derivada do run de origem (`<origem>.regenerate[.<revisão>]`), mesmas
        etapas/canal e a configuração efetiva **atual** resolvida antes do INSERT. O snapshot da
        origem não muda e o novo run nasce resolvido — sem resolvedor a operação é recusada, porque
        um run legado novo não teria entradas reproduzíveis.
        """
        run_id = check_id(run_id)
        source = self.coordinator.get(run_id)
        if source is None:
            raise RunNotFound(run_id)
        if self.effective_config_for is None or self.config_store is None:
            raise RunConfigUnavailable(
                "regenerate needs an effective config resolver: the new run would be created "
                "without a snapshot (legacy) and its inputs could not be reproduced")
        key = _regeneration_key(source.run.idempotency_key, revision)
        stages = tuple(stage.stage_id for stage in source.stages) or None
        return self._create(source.run.video_id, key, channel_id=source.run.channel_id, stages=stages,
                            operation=RunOperation.REGENERATE, source_run_id=run_id, reason=reason)

    def _create(self, video_id: str, idempotency_key: str, *, channel_id: str | None,
                stages: Sequence[ProductionStage] | None, operation: RunOperation,
                source_run_id: str | None = None, reason: str | None = None) -> RunCreation:
        options = {"effective_config_for": self.effective_config_for,
                   "config_store": self.config_store}
        if self.provider_selection_for is not None:
            # S8: o resolvedor só é encaminhado quando existe; sem ele o caminho legado e os
            # dublês de teste que não conhecem o parâmetro continuam valendo.
            options["provider_selection_for"] = self.provider_selection_for
        creation = self.coordinator.start(
            video_id, idempotency_key, channel_id=channel_id, stages=stages, **options)
        self._enqueue(creation.run.run_id)
        if creation.result is CreateRunResult.CREATED:
            self._record_creation(creation, operation, source_run_id=source_run_id, reason=reason)
        return creation

    def _record_creation(self, creation: RunCreation, operation: RunOperation, *,
                         source_run_id: str | None, reason: str | None) -> None:
        base = (reason or "").strip()
        if operation is RunOperation.REGENERATE:
            decision = (f"{base or 'regenerate'}; execução nova a partir do run {source_run_id} com a "
                        f"revisão atual congelada — nunca um resume")
        else:
            decision = base or "nova execução com chave idempotente nova; revisão atual congelada"
        self.coordinator.record_operation(creation.run.run_id, operation, reason=decision,
                                          source_run_id=source_run_id)

    def config_for(self, run_id: str) -> StoredRunConfig | None:
        """Configuração congelada do run (retomada, retry e painel leem; nunca re-resolvem)."""
        if self.config_store is None:
            return None
        return self.config_store.run_config(check_id(run_id))

    def resume(self, run_id: str, *, expected_state: RunState | None = None) -> RunTransition:
        """Transpõe um gate humano: retoma o run e **relança o worker**.

        Sem o `submit` o `Continuar` só trocava o estado para `RUNNING` e o run morria parado —
        o laço do worker encerra na pausa e nada o reativava. Além da retomada normal, um run
        `RUNNING` **órfão** (nenhuma etapa com lease vivo) é re-lançado sem escrever estado.
        """
        transition = self.coordinator.resume(run_id, expected_state=expected_state)
        if transition.result is RunTransitionResult.APPLIED:
            self._enqueue(run_id)
            return transition
        redrive = self._orphan_running(run_id)
        if redrive is not None:
            self._enqueue(run_id)
            return redrive
        return transition

    def retry(self, run_id: str) -> RunTransition:
        """Reinicia um run `FAILED` e **relança o worker** (mesmo defeito do resume)."""
        transition = self.coordinator.retry(run_id, expected_state=RunState.FAILED)
        if transition.result is RunTransitionResult.APPLIED:
            self._enqueue(run_id)
        return transition

    def recover_in_flight(self, *, now: datetime | None = None) -> tuple[str, ...]:
        """Religa no boot os runs em voo que ficaram órfãos (sem lease vivo) e devolve seus ids.

        Lê os runs em voo pela porta (`list_in_flight`), filtra os órfãos pela regra pura
        `orphan_in_flight` e usa o **mesmo** `submit` do `start` para cada um — nenhum caminho novo
        de execução. Idempotente: o `step` reivindica etapa com lease/fencing, então repetir o
        re-drive não executa a mesma etapa duas vezes (o perdedor recebe `BUSY`/`LOST`).
        Sem porta (ou com a fila indisponível) é no-op; falha de um `submit` não impede os outros
        nem propaga (`_enqueue`). Não escreve estado: só relança o worker.
        """
        if self.in_flight is None:
            return ()
        moment = now or datetime.now(timezone.utc)
        orphans = orphan_in_flight(self.in_flight.list_in_flight(), moment)
        for run_id in orphans:
            self._enqueue(run_id)
        return orphans

    def recover_orphans(self, *, now: datetime | None = None, grace_seconds: int = 30, limit: int = 50,
                        active: ActiveRuns | None = None) -> tuple[str, ...]:
        """Recuperação periódica: re-despacha órfãos com inatividade >= `grace_seconds`.

        Pede à porta só os candidatos (limitados, sem os ids ativos neste processo), reaplica a
        regra pura e usa o mesmo `submit`. Erro de leitura propaga (o laço chamador captura);
        falha de `submit` fica isolada em `_enqueue`. Não escreve estado.
        """
        if self.in_flight is None:
            return ()
        moment = now or datetime.now(timezone.utc)
        candidates = self.in_flight.list_orphan_candidates(
            grace_seconds=grace_seconds, limit=limit,
            exclude_run_ids=active.snapshot() if active is not None else frozenset())
        orphans = orphan_in_flight(candidates, moment, timedelta(seconds=grace_seconds))
        for run_id in orphans:
            self._enqueue(run_id)
        return orphans

    def _orphan_running(self, run_id: str) -> RunTransition | None:
        """Re-drive de um `RUNNING` sem lease vivo: devolve APPLIED sem escrever estado.

        Com lease vivo não re-lança (seria worker duplicado); devolve `None` para o chamador
        preservar o `NOT_ALLOWED`.
        """
        projection = self.coordinator.get(run_id)
        if projection is None or projection.run.state is not RunState.RUNNING:
            return None
        if has_live_lease(projection.stages, datetime.now(timezone.utc)):
            return None
        return RunTransition(RunTransitionResult.APPLIED, projection.run)

    def _enqueue(self, run_id: str) -> None:
        """Gatilho do worker: fila indisponível não pode perder o run nem derrubar a requisição."""
        if self.submit is None:
            return
        try:
            self.submit(run_id)
        except Exception:
            logger.warning("could not enqueue production run %s", run_id)
