"""Portas (interfaces) que os adaptadores implementam. Só dependem do domínio."""
import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..domain.render import Cue
from ..domain.contracts import Asset, FactCheckReport, QaReport, RenderJob, Project, Scene, Script, SourceSnapshot, UsageEntry, Video, VideoFormat, VideoStatus


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
