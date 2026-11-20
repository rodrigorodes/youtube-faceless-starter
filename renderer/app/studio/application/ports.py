"""Portas (interfaces) que os adaptadores implementam. Só dependem do domínio."""
from __future__ import annotations

import contextlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..domain.render import Cue
from ..domain.trends import TrendItem
from ..domain.categories import ProjectCategory
from ..domain.channel import ChannelProfile
from ..domain.contracts import Approval, Publication, Asset, FactCheckReport, JobStatus, PublicationStatus, QaReport, RenderJob, Project, Scene, Script, SourceSnapshot, UsageEntry, Video, VideoFormat, VideoStatus
from ..domain.production_run import (AckResult, Checkpoint, LeaseResult, OutboxEvent, ProductionRun, ProductionStage,
                                     RunCreation, RunState, RunTransition, StageClaim, StageTransition)


@dataclass(frozen=True)
class TextResult:
    text: str
    usage: UsageEntry


@dataclass(frozen=True)
class ImageResult:
    data: bytes
    mime: str
    usage: UsageEntry
    license: str = ""  # obrigatória: o caso de uso recusa imagem sem licença registrada
    attribution: str = ""
    source_url: str = ""


@dataclass(frozen=True)
class RenderSpec:
    scenes: list[Scene]
    images: list[Path]            # PNG de cada cena, na mesma ordem
    speech_wavs: list[Path]       # fala de cada cena
    scene_seconds: list[float]    # duração de cada cena (quadros inteiros)
    cues: list[Cue]               # legendas com tempo absoluto no vídeo
    format: VideoFormat = VideoFormat.short
    music: bool = True
    disclosure: str = "Ilustração gerada por IA"
    work_dir: Path | None = None  # onde o renderer grava intermediários


class ModelUnavailable(RuntimeError):
    """Provedor de modelo indisponível ou com resposta inutilizável (a API responde 502)."""


class VideoRepository(Protocol):
    def create_project(self, name: str, niche: str = "", language: str = "pt-BR") -> Project: ...
    def get_project(self, project_id: str) -> Project | None: ...
    def create_video(self, project_id: str, topic: str, fmt: VideoFormat) -> Video: ...
    def get_video(self, video_id: str) -> Video | None: ...
    def transition_video(self, video_id: str, expected: VideoStatus, new: VideoStatus) -> bool: ...


class TextModel(Protocol):
    name: str
    def cost_estimate(self, prompt: str) -> float: ...
    def complete(self, prompt: str, *, json_schema: dict | None = None) -> TextResult: ...


class ImageModel(Protocol):
    name: str
    model: str
    def cost_estimate(self, prompt: str) -> float: ...
    def generate(self, prompt: str, *, aspect: str = "9:16") -> ImageResult: ...


class Voice(Protocol):
    name: str
    def speak(self, text: str, out_path: Path) -> float: ...  # devolve a duração em segundos


class Renderer(Protocol):
    name: str
    def render(self, job: RenderSpec, out_path: Path) -> Path: ...


@dataclass(frozen=True)
class FetchedPage:
    text: str
    final_url: str


@dataclass(frozen=True)
class SceneDraft:
    narration: str
    caption: str
    label: str
    image_prompt: str
    claim_ids: list[str]


class SourceFetcher(Protocol):
    def fetch(self, url: str) -> FetchedPage: ...


class SnapshotRepository(Protocol):
    def add(self, video_id: str, url: str, text: str) -> SourceSnapshot: ...
    def list(self, video_id: str) -> list[SourceSnapshot]: ...


class ScriptRepository(Protocol):
    def save_and_advance(self, video_id: str, text: str, drafts: list[SceneDraft], claim_ids: list[str],
                         expected: VideoStatus, new: VideoStatus) -> Script | None:
        """Grava roteiro (versão +1) e cenas e move o estado numa transação; None se o estado não for o esperado."""
    def scenes(self, video_id: str) -> list[Scene]: ...
    def latest(self, video_id: str) -> Script | None: ...


class FactCheckRepository(Protocol):
    def save(self, video_id: str, report: FactCheckReport, advance: bool, script_version: int) -> bool:
        """Grava o relatório da versão do roteiro checada. Com advance, move SCRIPTED→FACT_CHECKED na mesma transação;
        False se o estado mudou ou se existe roteiro mais novo que o checado."""


class UsageRepository(Protocol):
    def record(self, video_id: str | None, entry: UsageEntry) -> None: ...
    def spent_video(self, video_id: str) -> float: ...
    def spent_month(self) -> float: ...


class AssetRepository(Protocol):
    def find(self, cache_key: str) -> Asset | None: ...
    def get(self, asset_id: str) -> Asset | None: ...
    def add(self, asset: Asset) -> Asset:
        """Insere; se a chave de cache já existir (corrida), devolve o asset existente."""
    def link_scene(self, video_id: str, idx: int, asset_id: str, image_prompt: str) -> bool:
        """Vincula só se o vídeo ainda está STORYBOARDED e a cena idx continua com este prompt; False caso contrário."""


class AssetStore(Protocol):
    def put(self, cache_key: str, data: bytes, aspect: str) -> str:
        """Valida e grava a imagem; devolve o caminho relativo à raiz de storage."""


class ProductionLock(Protocol):
    def hold(self, video_id: str) -> "contextlib.AbstractContextManager[bool]":
        """Exclusão mútua da produção de um vídeo; entra com False se outra execução já a detém (não espera)."""


class QaAnalyzer(Protocol):
    def analyze(self, path: Path, narration: Path | None = None) -> dict:
        """Métricas do arquivo: duration_s, width, height, has_audio, integrated_lufs, silence_ratio, black_ratio e,
        se `narration` (WAV só com a voz) for dado, narration_lufs e narration_silence_ratio."""


class RenderJobRepository(Protocol):
    def enqueue(self, video_id: str, input_hash: str) -> tuple[RenderJob, bool]:
        """Cria job QUEUED; se já existe um QUEUED/RUNNING recente para o vídeo, devolve esse (False). Job ativo há
        horas sem progresso é encerrado como FAILED (stale) antes."""
    def get(self, job_id: str) -> RenderJob | None: ...
    def latest(self, video_id: str) -> RenderJob | None: ...
    def latest_output(self, video_id: str) -> Asset | None:
        """Asset do vídeo final do job SUCCEEDED mais recente (é ele que a API serve)."""
    def output(self, video_id: str, asset_id: str) -> Asset | None: ...
    def approved_output(self, video_id: str) -> Asset | None: ...
    def start(self, job_id: str) -> bool:
        """QUEUED → RUNNING numa operação só; False se outro executor pegou."""
    def alive(self, job_id: str) -> bool:
        """O job ainda está RUNNING e o vídeo ainda pode receber render (conferir antes de publicar arquivos)."""
    def fail(self, job_id: str, error: str) -> None: ...
    def complete(self, job_id: str, asset: Asset, qa: QaReport) -> bool:
        """Numa transação: job SUCCEEDED, qa_report no vídeo e estado → RENDERED (→ AWAITING_APPROVAL se qa.passed).
        False se o estado do vídeo mudou."""


class RenderStorage(Protocol):
    def image_path(self, relative: str) -> Path: ...
    def work_dir(self, project_id: str, video_id: str, job_id: str) -> Path: ...
    def publish(self, project_id: str, video_id: str, job_id: str, mp4: Path, srt: str) -> str:
        """Grava `final-<job>.mp4/.srt` (arquivo próprio do job: um render novo nunca sobrescreve o servido);
        devolve o caminho relativo do MP4."""
    def resolve(self, relative: str, kind: str) -> Path | None:
        """Caminho do MP4 ou do .srt de um asset de vídeo, se existir e estiver dentro dos arquivos finais."""
    def prune(self, project_id: str, video_id: str, keep: str) -> None:
        """Apaga os finais de renders anteriores, mantendo só `keep`."""
    def cleanup(self, work_dir: Path) -> None: ...


class ApprovalRepository(Protocol):
    def decide(self, video_id: str, expected: VideoStatus, decision: str, *, title: str, description: str, tags: list[str],
               publish_at: "datetime | None", reason: str, qa_override: bool, output_asset_id: str | None = None) -> bool:
        """Numa transação: estado expected → APPROVED/REJECTED (se expected é RENDERED, passa por AWAITING_APPROVAL), grava os
        metadados do vídeo e a linha de `approvals`. False se o estado já não é `expected`."""
    def get(self, video_id: str) -> Approval | None: ...


class PublicationRepository(Protocol):
    def claim(self, lease_seconds: int, max_attempts: int) -> Publication | None:
        """Reivindica atomicamente um vídeo APPROVED sem publicação prévia; nunca retoma tentativa ambígua."""
    def get(self, video_id: str) -> Publication | None: ...
    def get_by_id(self, publication_id: str) -> Publication | None: ...
    def abort_before_delivery(self, publication_id: str, attempt: int) -> bool:
        """Somente antes de entregar o claim: remove tentativa sem sessão ou resultado externo."""
    def set_upload_uri(self, publication_id: str, attempt: int, uri: str, replace: bool) -> Publication | None:
        """Só na tentativa atual, UPLOADING e sem URI (ou com replace). None caso contrário."""
    def mark_uploaded(self, publication_id: str, youtube_video_id: str) -> Publication | None:
        """Numa transação: publicação UPLOADED com o ID e vídeo APPROVED → PUBLISHED. Mesmo ID de novo é no-op;
        ID diferente levanta PublicationConflict. None se a publicação não existe."""
    def mark_thumbnail(self, publication_id: str) -> bool: ...
    def release(self, publication_id: str, attempt: int, error: str) -> bool:
        """Falha transitória: solta o lease para a próxima reivindicação repetir."""
    def fail(self, publication_id: str, attempt: int, error: str) -> bool:
        """Registra falha; não prova que não houve efeito externo."""
    def retry(self, video_id: str) -> Publication | None:
        """FAILED → PENDING, preservando sessão e número monotônico de tentativas."""


class ThumbnailMaker(Protocol):
    def make(self, image: Path) -> bytes:
        """JPEG 1280x720 de até 2 MB a partir da imagem da cena."""


@dataclass(frozen=True)
class VideoRow:
    id: str
    project_id: str
    topic: str
    format: VideoFormat
    status: VideoStatus
    title: str
    updated_at: datetime
    job_status: JobStatus | None
    step_running: bool
    publication_status: PublicationStatus | None
    error: str | None
    # (provider, model, cost_usd, cost_confirmation_kind); kind ∈ ACTUAL/ESTIMATE/FREE/None.
    cost_rows: list[tuple[str, str, float, str | None]]


@dataclass(frozen=True)
class StepInfo:
    step: str
    attempt: int
    status: str
    error_class: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class UsageInfo:
    step: str
    provider: str
    model: str
    cost_usd: float
    created_at: datetime
    cost_confirmation_kind: str | None = None


@dataclass(frozen=True)
class PubInfo:
    status: PublicationStatus
    attempt: int
    error: str | None


@dataclass(frozen=True)
class VideoDetail:
    video: VideoRow
    steps: list[StepInfo]
    usage: list[UsageInfo]
    render_error: str | None
    publication: PubInfo | None


class PanelRepository(Protocol):
    def projects(self) -> list[tuple[str, str]]: ...
    def videos(self, since: datetime | None, project_id: str | None, limit: int) -> list[VideoRow]: ...
    def video_detail(self, video_id: str) -> VideoDetail | None: ...
    def month_usage(self) -> list[tuple[str, str, float, str | None]]:
        """Lançamentos do mês corrente: (provider, model, cost_usd, cost_confirmation_kind)."""
    def unattributed_usage(self) -> list[tuple[str, str, float]]: ...


@dataclass(frozen=True)
class TrendRecord:
    id: str
    project_id: str
    topic: str
    topic_key: str
    source_name: str
    source_url: str
    observed_at: datetime
    window_start: datetime
    window_end: datetime
    metric_name: str | None
    metric_value: float | None
    evidence: list[dict]


class TrendRepository(Protocol):
    def upsert(self, project_id: str, items: list[TrendItem]) -> int: ...
    def list(self, project_id: str | None, since: datetime) -> list[TrendRecord]: ...
    def last_collected_at(self, project_id: str | None) -> datetime | None: ...


class CategoryRepository(Protocol):
    def list(self, project_id: str) -> list[ProjectCategory]: ...
    def get(self, category_id: str) -> ProjectCategory | None: ...
    def save(self, project_id: str, name: str, queries: list[str], category_id: str | None = None) -> ProjectCategory: ...
    def delete(self, category_id: str) -> bool: ...


class ChannelProfileRepository(Protocol):
    def create(self, project_id: str, name: str, **options: object) -> ChannelProfile: ...
    def get(self, profile_id: str) -> ChannelProfile | None: ...
    def get_by_project(self, project_id: str) -> ChannelProfile | None: ...
    def list(self, include_archived: bool = False) -> list[ChannelProfile]: ...
    def update(self, profile_id: str, expected_version: int, changes: dict[str, object]) -> ChannelProfile | None:
        """Atualiza de forma otimista: None se o perfil não existe; `ChannelVersionConflict` se a versão divergiu."""


class ProductionRunRepository(Protocol):
    """Execução persistida de produção: toda transição condiciona no estado atual (CAS).

    Os retornos são enums explícitos (nunca booleano ambíguo). A outbox é gravada na mesma
    transação da mudança de estado; o chamador só executa efeito externo após `CLAIMED`.

    Erros com significado próprio (nunca 500 genérico): `InvalidIdempotencyKey` (chave fora da forma
    canônica), `ProductionIdempotencyConflict` (replay divergente),
    `ProductionRunReferencedEntityNotFound` (vídeo/canal inexistente) e `ProductionRunLockTimeout`
    (contenção de lock: repetir).
    """

    def create_run(self, run_id: str, video_id: str, idempotency_key: str, *,
                   channel_id: str | None = None,
                   stages: Sequence[ProductionStage] | None = None) -> RunCreation:
        """Cria o run e as etapas PENDING numa transação; replay da chave devolve `EXISTING`.

        A chave é identidade byte-a-byte canônica: ASCII minúsculo em `[a-z0-9._:-]`. Variantes
        (caixa, Unicode/NFC, espaço ou invisível) são recusadas, nunca normalizadas. A mesma chave
        com outra solicitação (vídeo, canal ou conjunto de estágios) é conflito.
        """

    def get_run(self, run_id: str) -> ProductionRun | None: ...

    def claim_stage(self, run_id: str, stage_id: ProductionStage, owner: str, lease_seconds: int) -> StageClaim:
        """Reivindica a etapa se as dependências concluíram e o lease não está com outro dono.

        Etapa órfã (lease vencido) é retomável; o claim incrementa tentativa e fencing token.
        """

    def renew_lease(self, run_id: str, stage_id: ProductionStage, owner: str, fencing_token: int,
                    lease_seconds: int) -> LeaseResult:
        """Heartbeat: só o dono do token atual, com lease ainda válido, estende a expiração."""

    def complete_stage(self, run_id: str, stage_id: ProductionStage, owner: str, fencing_token: int, *,
                       checkpoint: Checkpoint | None = None) -> StageTransition:
        """SUCCEEDED via CAS de dono/token/lease; grava checkpoint monotônico e evento na mesma transação."""

    def fail_stage(self, run_id: str, stage_id: ProductionStage, owner: str, fencing_token: int,
                   error: str, *, checkpoint: Checkpoint | None = None) -> StageTransition:
        """FAILED via o mesmo CAS; persiste o erro, libera o lease e marca o run como FAILED."""

    def pause_run(self, run_id: str, reason: str) -> RunTransition:
        """Pausa humana persistida: run e etapa em execução viram WAITING_HUMAN, sem lease ativo."""

    def resume_run(self, run_id: str, expected_state: RunState) -> RunTransition:
        """Retoma somente se o estado persistido for `expected_state`; divergência é recusada.

        Revoga leases e incrementa o `fencing_token` das etapas abertas: a geração anterior não
        escreve mais. Cada etapa revogada emite `stage.revoked` na mesma transação. A prova de
        aprovação humana versionada (gate de QA) é D2 e entrará como referência do checkpoint da
        etapa `approval`.
        """

    def cancel_run(self, run_id: str, reason: str) -> RunTransition:
        """Cancela o run e as etapas abertas numa transação; estados terminais recusam."""

    def read_outbox(self, limit: int = 100, *, run_id: str | None = None) -> list[OutboxEvent]:
        """Eventos de progresso ainda não confirmados, em ordem de gravação."""

    def ack_outbox(self, event_id: int) -> AckResult:
        """Confirma um evento; repetir não falha e não apaga histórico."""
