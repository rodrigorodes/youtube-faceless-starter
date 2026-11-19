"""Portas (interfaces) que os adaptadores implementam. Só dependem do domínio."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..domain.contracts import FactCheckReport, Project, Scene, Script, SourceSnapshot, UsageEntry, Video, VideoFormat, VideoStatus


@dataclass(frozen=True)
class TextResult:
    text: str
    usage: UsageEntry


@dataclass(frozen=True)
class ImageResult:
    data: bytes
    mime: str
    usage: UsageEntry


@dataclass(frozen=True)
class RenderSpec:
    scenes: list[Scene]
    narration_wav: Path
    music_wav: Path | None
    format: VideoFormat = VideoFormat.short
    options: dict = field(default_factory=dict)


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
