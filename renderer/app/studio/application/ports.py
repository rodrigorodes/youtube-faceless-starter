"""Portas (interfaces) que os adaptadores implementam. Só dependem do domínio."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..domain.contracts import Project, Scene, UsageEntry, Video, VideoFormat, VideoStatus


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
