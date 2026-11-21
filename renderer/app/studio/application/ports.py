"""Portas (interfaces) que os adaptadores implementam. Só dependem do domínio."""
from __future__ import annotations

import contextlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..domain.asset_resolver import AssetDescriptor
from ..domain.qa_report import QaReport as QualityReport
from ..domain.render import Cue
from ..domain.render_cache import CacheEntry, NodeId, PlanArtifact
from ..domain.render_plan import AssetReference, RenderPlan, StyleSnapshot
from ..domain.trends import TrendItem
from ..domain.categories import ProjectCategory
from ..domain.channel import ChannelProfile
from ..domain.channel_budget import BudgetLimits, CostSummary
from ..domain.provider import ProviderKind, ProviderProbeResult
from ..domain.youtube_channel import OAuthStatus, YouTubeChannel
from ..domain.youtube_identity import ChannelAuthorization, GoogleAccount, OAuthGrant, YouTubeChannelIdentity
from ..domain.saas import ByokKey, KeyAuditAction, MembershipStatus, Role
from ..domain.youtube_oauth import OAuthIdentity, OAuthTokenResponse
from ..domain.publication_policy import PublicationIntentEvidence
from ..domain.contracts import Approval, Publication, Asset, FactCheckReport, JobStatus, PublicationStatus, RenderJob, Project, Scene, Script, SourceSnapshot, UsageEntry, Video, VideoFormat, VideoStatus
from ..domain.production_run import (AckResult, Checkpoint, LeaseResult, OutboxEvent, ProductionRun, ProductionStage,
                                     RunCreation, RunState, RunTransition, StageClaim, StageExecution, StageTransition)
from ..domain.longform import ScriptApproval, ScriptPlan


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
    voice_id: str = ""            # identidade da voz (nome+modelo): entra no fingerprint da narração (RP-06c)
    # RP-016: identidade **versionada** de quem produziu o vídeo, resolvida a montante
    # (canal → estilo). ``None`` = não há canal/estilo a referenciar; o renderer usa o default.
    style: StyleSnapshot | None = None


@dataclass(frozen=True)
class RenderQaInputs:
    """Plano lógico + descriptors resolvidos que o renderer usou (entrada do QA versionado).

    O QA da F6 avalia o plano e a resolução dos assets; transportar isto do renderer para
    a porta de QA mantém o núcleo de render puro (sem I/O de mídia em ``domain``/
    ``application``) e garante que o relatório persistido descreve o render de verdade.
    """

    plan: RenderPlan
    descriptors: tuple[AssetDescriptor, ...] = ()


class ModelUnavailable(RuntimeError):
    """Provedor de modelo indisponível ou com resposta inutilizável (a API responde 502)."""


class VideoRepository(Protocol):
    def create_project(self, name: str, niche: str = "", language: str = "pt-BR") -> Project: ...
    def get_project(self, project_id: str) -> Project | None: ...
    def set_project_config(self, project_id: str, config: dict[str, str]) -> Project | None: ...
    def create_video(self, project_id: str, topic: str, fmt: VideoFormat) -> Video: ...
    def get_video(self, video_id: str) -> Video | None: ...
    def transition_video(self, video_id: str, expected: VideoStatus, new: VideoStatus) -> bool: ...


@runtime_checkable
class TextModel(Protocol):
    name: str
    def cost_estimate(self, prompt: str) -> float: ...
    def complete(self, prompt: str, *, json_schema: dict | None = None) -> TextResult: ...


@runtime_checkable
class ImageModel(Protocol):
    name: str
    model: str
    def cost_estimate(self, prompt: str) -> float: ...
    def generate(self, prompt: str, *, aspect: str = "9:16") -> ImageResult: ...


@runtime_checkable
class Voice(Protocol):
    name: str
    def speak(self, text: str, out_path: Path) -> float: ...  # devolve a duração em segundos


@runtime_checkable
class Renderer(Protocol):
    name: str
    def render(self, job: RenderSpec, out_path: Path) -> Path: ...
    def qa_inputs(self, job: RenderSpec) -> "RenderQaInputs":
        """Plano + descriptors que este render usa (mesma entrada do ``render``).

        O renderer é o único ponto com I/O de leitura dos assets: é ele quem constrói o
        Render Plan e resolve os descriptors. A porta de QA (``QualityEvaluator``) recebe
        exatamente esse plano e esses descriptors — sem reconstruir mídia no núcleo puro.
        """


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


@dataclass(frozen=True)
class FactCheckRecord:
    """Relatório de fact-check com a versão do roteiro que ele cobre."""

    report: FactCheckReport
    script_version: int


class FactCheckReader(Protocol):
    """Leitura do último fact-check do vídeo (porta separada da escrita da F4)."""

    def latest(self, video_id: str) -> FactCheckRecord | None: ...


@dataclass(frozen=True)
class ScriptRecord:
    """Uma versão de roteiro com seu plano long-form, hash e aprovação humanos (se houver)."""

    script: Script
    plan: ScriptPlan | None
    content_hash: str | None
    approval: ScriptApproval | None


class LongFormScriptRepository(Protocol):
    """Persistência versionada do roteiro longo: plano, hash e aprovação presa à versão.

    O mesmo objeto que satisfaz `ScriptRepository` pode satisfazer esta porta. `save_planned_version`
    grava roteiro, cenas, plano e hash **na mesma transação**: nunca existe versão sem hash ou hash sem
    versão. `approve` vincula a decisão à versão lida; False se essa versão já não é a mais recente.
    """

    def save_planned_version(self, video_id: str, text: str, drafts: list[SceneDraft], claim_ids: list[str],
                             plan: ScriptPlan, content_hash: str, expected: VideoStatus, new: VideoStatus) -> Script | None:
        """Grava roteiro (versão +1), cenas e plano/hash atomicamente; None se o estado não for o esperado."""

    def list_script_records(self, video_id: str) -> list[ScriptRecord]:
        """Versões do roteiro em ordem crescente, com plano, hash e aprovação de cada uma."""

    def approve(self, video_id: str, version: int, content_hash: str, decision: str, reason: str,
                approved_by: str, approved_at: datetime | None = None) -> bool:
        """Grava a decisão presa à (versão, hash). False se a versão não existe ou já não é a mais recente."""


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


class AssetResolver(Protocol):
    """RP-019: resolve um ``AssetReference`` do manifesto em um ``AssetDescriptor``.

    Recebe a entrada do manifesto (URI, versão, ``content_sha256`` e licença) e devolve
    a visão resolvida — disponibilidade comprovada, hash do **conteúdo** conferido e
    metadado técnico (codec, resolução, duração) — validada por
    ``domain.asset_resolver``. O resolver concreto (toca disco/rede) mora em
    ``adapters/``; o núcleo de render não importa mídia (RP-022 é política pura).
    """

    def resolve(self, reference: AssetReference) -> AssetDescriptor: ...


class ProductionLock(Protocol):
    def hold(self, video_id: str) -> "contextlib.AbstractContextManager[bool]":
        """Exclusão mútua da produção de um vídeo; entra com False se outra execução já a detém (não espera)."""


class QaAnalyzer(Protocol):
    def analyze(self, path: Path, narration: Path | None = None) -> dict:
        """Métricas do arquivo: duration_s, width, height, has_audio, integrated_lufs, silence_ratio, black_ratio e,
        se `narration` (WAV só com a voz) for dado, narration_lufs e narration_silence_ratio."""


class QualityEvaluator(Protocol):
    """Porta do QA do render (RP-030, design §6/§7.5): plano + evidências → QualityReport.

    O ``QualityReport`` é o contrato versionado da F6 (``domain.qa_report.QaReport``):
    achados com severidade ``blocking``/``warning``/``info`` e cobertura
    ``verified``/``not_verified``. A porta decide sobre a evidência disponível de forma
    determinística — **não** avalia semântica multimodal (sem provedor) nem inventa score
    visual; a falta de evidência vira cobertura ``not_verified``.

    A implementação concreta mora em ``adapters/`` (ffprobe/ebur128 + resolução dos
    assets) e é montada **só** em ``composition.py``; a política de severidade é pura
    (``domain.quality``). O plano e os descriptors vêm do ``Renderer`` (``qa_inputs``) —
    o QA mede o **mesmo** render, com a identidade real (``render_id``/``checksum``).
    """

    def evaluate(self, plan: RenderPlan, *, media_path: Path, narration_path: Path | None = None,
                 descriptors: Sequence[AssetDescriptor] = (), render_id: str, checksum: str) -> QualityReport: ...


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
    def complete(self, job_id: str, asset: Asset, qa: QualityReport) -> bool:
        """Numa transação: job SUCCEEDED, qa_report no vídeo e estado → RENDERED (→ AWAITING_APPROVAL se o relatório
        for publicável). False se o estado do vídeo mudou."""


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


class RenderPlanRepository(Protocol):
    """Persistência versionada do Render Plan e do índice de cache (RP-027/RP-029).

    Guarda o plano por revisão (identidade lógica) e, à parte, o artefato físico produzido por
    nó (hash + localização) — as duas identidades não se confundem.
    """

    def save_plan(self, plan: RenderPlan) -> None:
        """Grava o documento do plano na sua revisão (idempotente por `(plan_id, revision)`) e
        registra os artefatos físicos referenciados no manifesto."""
    def get_plan(self, plan_id: str, revision: int) -> RenderPlan | None: ...
    def latest_plan(self, plan_id: str) -> RenderPlan | None:
        """Revisão mais recente do plano lógico, ou None se ainda não há nenhuma."""
    def revisions(self, plan_id: str) -> list[int]:
        """Revisões persistidas, em ordem crescente."""
    def record_entry(self, entry: CacheEntry) -> None:
        """Registra (ou atualiza) o artefato físico produzido por um nó numa revisão."""
    def record_entries(self, entries: "Sequence[CacheEntry]") -> None:
        """Registra, numa transação só, os artefatos produzidos por vários nós (RP-06b).

        O executor que reusa segmentos registra todos os nós de uma revisão de uma vez: sem
        isto, um plano de N cenas faria N conexões só para gravar o índice de cache.
        """
    def record_artifacts(self, artifacts: "Sequence[PlanArtifact]") -> None:
        """Registra, numa transação só, os artefatos **físicos** produzidos (hash/codec/localização).

        Separado de ``record_entries`` porque a identidade física (hash+localização) não carrega a
        revisão do plano: o mesmo conteúdo reaproveitado por outra revisão é o mesmo registro.
        """
    def entries(self, plan_id: str) -> dict[NodeId, CacheEntry]:
        """Último artefato conhecido por nó lógico (para decidir acerto de cache)."""
    def artifact(self, content_sha256: str, location: str) -> PlanArtifact | None:
        """Registro físico por hash/codec/localização, sem depender da revisão do plano."""


class ApprovalRepository(Protocol):
    def decide(self, video_id: str, expected: VideoStatus, decision: str, *, title: str, description: str, tags: list[str],
               publish_at: "datetime | None", reason: str, qa_override: bool, output_asset_id: str | None = None,
               visibility: str = "private", public_confirmed: bool = False) -> bool:
        """Numa transação: estado expected → APPROVED/REJECTED (se expected é RENDERED, passa por AWAITING_APPROVAL), grava os
        metadados do vídeo, a linha de `approvals` e (se aprovado) a `publication_intents` imutável com render/checksum.
        False se o estado já não é `expected`."""
    def get(self, video_id: str) -> Approval | None: ...


class PublicationRepository(Protocol):
    def claim(self, lease_seconds: int, max_attempts: int, video_id: str | None = None) -> Publication | None:
        """Reivindica atomicamente um vídeo APPROVED sem publicação prévia; nunca retoma tentativa ambígua.
        `video_id` restringe ao dono do run do coordenador."""
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


class VisualStyleRepository(Protocol):
    """Biblioteca de estilos visuais (compartilhada). Versionada por snapshot (VS-01).

    Um estilo é definido uma vez e vários canais apontam para ele; por isso a biblioteca não
    pertence ao canal. `update` é otimista: devolve None se o estilo não existe e levanta
    `VisualStyleVersionConflict` se a versão divergiu de outra atualização.
    """

    def create(self, name: str, **options: object) -> "VisualStyle": ...
    def get(self, style_id: str) -> "VisualStyle | None": ...
    def list(self, include_archived: bool = False) -> "list[VisualStyle]": ...
    def update(self, style_id: str, expected_version: int, changes: dict[str, object]) -> "VisualStyle | None": ...


class ChannelBudgetRepository(Protocol):
    def get(self, project_id: str) -> "BudgetLimits | None": ...
    def upsert(self, limits: "BudgetLimits") -> "BudgetLimits": ...


class ChannelUsageRepository(Protocol):
    def month_summary(self, project_id: str) -> "CostSummary":
        """Custo do mês corrente só dos vídeos do canal, classificado de forma honesta."""


class YouTubeChannelRepository(Protocol):
    def get(self, project_id: str) -> "YouTubeChannel | None": ...
    def upsert(self, channel: "YouTubeChannel") -> "YouTubeChannel": ...
    def delete(self, project_id: str) -> bool: ...


class GoogleAccountRepository(Protocol):
    """Conta Google (YT-01). Uma por e-mail, sem distinguir caixa: reconectar atualiza, não duplica."""

    def upsert(self, account: GoogleAccount) -> GoogleAccount: ...
    def get(self, account_id: str) -> GoogleAccount | None: ...
    def get_by_email(self, email: str) -> GoogleAccount | None: ...
    def list(self) -> list[GoogleAccount]: ...


class OAuthGrantRepository(Protocol):
    """Autorização independente da conta: escopos, status e vencimento próprios (tokens no vault)."""

    def create(self, grant: OAuthGrant) -> OAuthGrant: ...
    def get(self, grant_id: str) -> OAuthGrant | None: ...
    def list_for_account(self, account_id: str) -> list[OAuthGrant]: ...
    def update_status(self, grant_id: str, status: OAuthStatus, *,
                      token_expires_at: datetime | None = ...) -> OAuthGrant | None: ...


class YouTubeChannelIdentityRepository(Protocol):
    """Identidade oficial do canal (`UC...`): global e independente da conta."""

    def upsert(self, channel: YouTubeChannelIdentity) -> YouTubeChannelIdentity: ...
    def get(self, youtube_channel_id: str) -> YouTubeChannelIdentity | None: ...
    def list(self) -> list[YouTubeChannelIdentity]: ...


class ChannelAuthorizationRepository(Protocol):
    """Vínculo **validado** entre autorização e canal; existir já afirma que houve conferência."""

    def link(self, authorization: ChannelAuthorization) -> ChannelAuthorization: ...
    def get(self, grant_id: str, youtube_channel_id: str) -> ChannelAuthorization | None: ...
    def authorizations_for_channel(self, youtube_channel_id: str) -> list[ChannelAuthorization]: ...
    def revoke(self, grant_id: str, youtube_channel_id: str) -> bool: ...


class SecretStore(Protocol):
    """Cofre de segredos: só o valor por (escopo, chave). `names` nunca devolve valores."""

    def get(self, scope: str, key: str) -> str | None: ...
    def set(self, scope: str, key: str, value: str) -> None: ...
    def delete(self, scope: str, key: str) -> None: ...
    def names(self, scope: str) -> tuple[str, ...]: ...


class OAuthClient(Protocol):
    """Cliente OAuth do Google/YouTube (F8-05). O adaptador concreto injeta o HTTP.

    Nenhum método devolve erro com corpo cru: a aplicação recebe uma exceção de domínio
    (`OAuthReconnectRequired`/`OAuthTransientError`) sem token nem client secret na mensagem.
    """

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> OAuthTokenResponse: ...
    def refresh(self, refresh_token: str) -> OAuthTokenResponse: ...
    def revoke(self, token: str) -> None: ...
    def identity(self, access_token: str) -> OAuthIdentity: ...


@dataclass(frozen=True)
class PublicationIntentRecord:
    """Linha de `publication_intents` lida do banco (evidência imutável de F8-02)."""

    evidence: PublicationIntentEvidence
    approved_at: datetime | None = None


class PublicationIntentRepository(Protocol):
    def get(self, video_id: str) -> PublicationIntentEvidence | None:
        """Intenção gravada na mesma transação da aprovação; None se o vídeo não foi aprovado."""


class UploadOutcome(str, Enum):
    UPLOADED = "UPLOADED"          # há um id do YouTube confirmado
    INCOMPLETE = "INCOMPLETE"      # 308: sessão viva, continuar do offset
    RETRYABLE = "RETRYABLE"        # rede/5xx: pode repetir, preservando a sessão quando existe
    PERMANENT = "PERMANENT"        # metadado inválido/quota/token inválido: não repetir sozinho
    AMBIGUOUS = "AMBIGUOUS"        # timeout/404/410: não presumir sucesso; reconciliar


@dataclass(frozen=True)
class UploadRequest:
    """Tudo que o executor precisa para um upload resumable idempotente."""

    idempotency_key: str
    file_path: Path
    file_size: int
    content_type: str
    youtube_body: dict
    upload_uri: str | None = None
    offset: int = 0


@dataclass(frozen=True)
class UploadResult:
    outcome: UploadOutcome
    youtube_video_id: str | None = None
    upload_uri: str | None = None
    offset: int = 0
    error: str | None = None


class YouTubeUploader(Protocol):
    """Porta do upload nativo: nenhuma mídia/SDK entra no núcleo; o adaptador faz o HTTP."""

    def upload(self, request: UploadRequest, access_token: str) -> UploadResult: ...
    def reconcile(self, request: UploadRequest, access_token: str) -> UploadResult:
        """Pergunta ao YouTube se a sessão produziu vídeo; NUNCA inventa sucesso."""


class PublicationQueueRepository(Protocol):
    """Fila resiliente: retry com backoff, DLQ e reconciliação (F8-03/F8-04).

    Separada de `PublicationRepository` para o caminho legado (n8n) continuar estrito: o
    `claim` antigo nunca retoma tentativa ambígua; só esta porta reivindica devido-para-retry.
    """

    def claim_retry(self, lease_seconds: int, max_attempts: int, video_id: str | None = None) -> Publication | None:
        """Reivindica publicação PENDING/FAILED não-DLQ, sem id confirmado e sem ambiguidade."""

    def record_session(self, publication_id: str, attempt: int, upload_uri: str, offset: int) -> bool:
        """Grava a sessão resumable e o offset já aceito, na tentativa atual."""

    def retry_later(self, publication_id: str, attempt: int, error: str, delay_seconds: int,
                    failure_class: str) -> bool:
        """Falha transiente: solta o lease e agenda a próxima tentativa com backoff."""

    def dead_letter(self, publication_id: str, attempt: int, error: str, failure_class: str) -> bool:
        """Falha permanente/ambígua esgotada: DLQ explícita; nunca vira sucesso."""

    def mark_ambiguous(self, publication_id: str, attempt: int, error: str) -> bool:
        """Resultado externo desconhecido: marca UNKNOWN; exige reconciliação antes de retry."""

    def resolve_ambiguous(self, publication_id: str, *, retry: bool, error: str, failure_class: str) -> bool:
        """Reconciliação: `retry=True` só quando provou que não há vídeo; senão DLQ/humano."""


class ProviderProbe(Protocol):
    """Sonda de conexão de um provider; roda no adaptador (nunca no core)."""

    def probe(self, kind: "ProviderKind", spec: str) -> "ProviderProbeResult": ...



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


class ProductionRunStageReader(Protocol):
    """Leitura das etapas de um run para a projeção de status (D2).

    Porta separada de `ProductionRunRepository` para o coordenador montar a projeção sem acrescentar
    métodos de escrita à porta D. O mesmo objeto do repositório satisfaz as duas portas; um run
    inexistente devolve tupla vazia.
    """

    def list_stages(self, run_id: str) -> tuple[StageExecution, ...]:
        """Etapas do run na ordem estável do DAG (topológica); vazio se o run não existe."""


@dataclass(frozen=True)
class MemberRecord:
    """Membro com dados de usuário (join leitura). Sem valor de segredo."""

    membership_id: str
    organization_id: str
    user_id: str
    display_name: str
    email: str
    role: "Role"
    status: "MembershipStatus"
    created_at: datetime | None = None


class SaasRepository(Protocol):
    """Tenancy e BYOK (F11-01/04 / L2). Toda leitura/escrita recebe o `organization_id` do ator.

    A fronteira de tenant é aplicada pelo filtro obrigatório por organização: um recurso de outra
    organização simplesmente não é encontrado. O runtime deriva o tenant do vínculo do operador
    autenticado (o login por SSO/OIDC ainda não é a fonte de identidade); as mutações de equipe
    são expostas pela rota e auditam o ator. O schema modela o caminho de tenancy dos registros.
    """

    def organizations(self) -> list[tuple[str, str]]: ...
    def organization(self, organization_id: str) -> str | None: ...
    def workspace(self, organization_id: str) -> str | None: ...

    def members(self, organization_id: str) -> list[MemberRecord]: ...
    def member(self, organization_id: str, membership_id: str) -> MemberRecord | None: ...
    def member_by_user(self, organization_id: str, user_id: str) -> MemberRecord | None: ...
    def owner_count(self, organization_id: str) -> int: ...
    def find_user(self, email: str) -> tuple[str, str] | None: ...
    def insert_user(self, user_id: str, email: str, display_name: str) -> None: ...
    def insert_membership(self, membership_id: str, organization_id: str, user_id: str,
                          role: "Role", status: "MembershipStatus") -> None: ...
    def update_membership_role(self, organization_id: str, membership_id: str, role: "Role") -> bool: ...
    def delete_membership(self, organization_id: str, membership_id: str) -> bool: ...
    def audit_membership(self, organization_id: str, membership_id: str, actor_user_id: str | None,
                         action: "MembershipAuditAction", role: "Role | None" = None) -> None: ...

    def keys(self, organization_id: str) -> list["ByokKey"]: ...
    def key(self, organization_id: str, key_id: str) -> "ByokKey" | None: ...
    def insert_key(self, key: "ByokKey") -> None: ...
    def update_key_rotation(self, organization_id: str, key_id: str, mask: str, fingerprint: str,
                            secret_name: str, rotated_at: datetime) -> bool: ...
    def revoke_key(self, organization_id: str, key_id: str, revoked_at: datetime) -> bool: ...
    def mark_key_used(self, organization_id: str, key_id: str, used_at: datetime) -> None: ...
    def audit_key(self, organization_id: str, key_id: str, actor_user_id: str | None,
                  action: "KeyAuditAction") -> None: ...

    def usage_rows(self, organization_id: str) -> list[tuple[str | None, str, str, float, str | None]]:
        """Consumo já atribuído ao tenant: (membro, provider, model, custo, confirmação)."""
