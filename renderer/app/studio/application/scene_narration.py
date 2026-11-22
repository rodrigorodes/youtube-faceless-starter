"""W4.3 (EDIT-02) — pré-escuta e regeneração da narração de UMA cena.

Duas operações, ambas explícitas (nada aqui roda em autosave):

* ``SceneNarration.find`` — localiza o WAV já medido de uma cena, sem sintetizar. Lê primeiro o
  caminho durável gravado pela regeneração/render; se não houver, cai no índice de cache do último
  render. Devolve ``None`` quando não existe artefato físico íntegro — nunca inventa áudio.
* ``RegenerateSceneNarration.execute`` — sintetiza de novo a narração de uma cena, com a mesma
  guarda de orçamento do render: estimativa antes, reserva antes do efeito, custo confirmado
  depois. Grava o WAV no caminho durável e a duração **real** na cena.

A cena é identificada pelo ``id`` estável (W4.0), não pelo índice. O vídeo precisa estar em
``IDEA``/``SCRIPTED``: regenerar narração de um vídeo já aprovado/publicado exigiria reabrir o
fluxo, o que é decisão de outra frente (W4.2).
"""
from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ..domain.contracts import Scene, Video, VideoStatus
from ..domain.ids import check_id
from .editorial import StateConflict, _require_video
from .errors import InvalidInput
from .ports import (RenderPlanRepository, SceneDurationStore, SceneNarrationStore, ScriptRepository,
                    VideoRepository, Voice)
from .render import _sha256_file, _voice_settlement, _wav_seconds


@dataclass(frozen=True)
class SceneNarrationArtifact:
    """WAV de narração de uma cena, com a duração real e a identidade do conteúdo."""

    video_id: str
    scene_id: str
    path: Path
    duration_s: float
    sha256: str
    voice_id: str = ""


def _scene(scripts: ScriptRepository, video_id: str, scene_id: str) -> Scene:
    for scene in scripts.scenes(check_id(video_id)):
        if scene.id == scene_id:
            return scene
    raise InvalidInput(f"scene {scene_id} does not belong to this video")


def _require_editable(video: Video) -> None:
    if video.status not in (VideoStatus.IDEA, VideoStatus.SCRIPTED):
        raise StateConflict(
            f"narration regeneration is only available in IDEA/SCRIPTED, got {video.status.value}; "
            "reopen the video before changing its script")


class SceneNarration:
    """Leitura da pré-escuta: encontra o WAV de uma cena já sintetizado."""

    def __init__(self, videos: VideoRepository, scripts: ScriptRepository,
                 store: SceneNarrationStore, plans: RenderPlanRepository | None = None,
                 durations: SceneDurationStore | None = None):
        self.videos, self.scripts, self.store = videos, scripts, store
        self.plans, self.durations = plans, durations

    def find(self, video_id: str, scene_id: str) -> SceneNarrationArtifact | None:
        video = _require_video(self.videos, video_id)
        scene = _scene(self.scripts, video_id, scene_id)
        path = self.store.narration_path(video.project_id, video.id, scene.id)
        if not path.is_file():
            path = self._cached_path(video, scene)
        if path is None or not path.is_file():
            return None
        measured = self.durations.durations(video.id).get(scene.id) if self.durations is not None else None
        duration = float(measured) if measured is not None else _wav_seconds(path)
        return SceneNarrationArtifact(video_id=video.id, scene_id=scene.id, path=path,
                                      duration_s=duration, sha256=_sha256_file(path))

    def _cached_path(self, video: Video, scene: Scene) -> Path | None:
        if self.plans is None:
            return None
        from ..domain.render_cache import NodeId

        entry = self.plans.entries(f"plan:{video.id}").get(NodeId("narration", scene.id))
        if entry is None:
            return None
        path = Path(entry.artifact_uri)
        if not path.is_file() or _sha256_file(path) != entry.artifact_sha256:
            return None
        return path


class RegenerateSceneNarration:
    """Sintetiza de novo a narração de UMA cena, com estimativa e reserva antes do efeito."""

    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, voice_for: Callable[[Video], Voice],
                 store: SceneNarrationStore, durations: SceneDurationStore, paid=None):
        self.videos, self.scripts, self.voice_for = videos, scripts, voice_for
        self.store, self.durations, self.paid = store, durations, paid

    def execute(self, video_id: str, scene_id: str) -> SceneNarrationArtifact:
        video = _require_video(self.videos, video_id)
        _require_editable(video)
        scene = _scene(self.scripts, video_id, scene_id)
        voice = self.voice_for(video)
        destination = self.store.narration_path(video.project_id, video.id, scene.id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp.wav")
        try:
            seconds = self._synthesize(video, scene, voice, temporary)
            shutil.move(str(temporary), str(destination))
        finally:
            temporary.unlink(missing_ok=True)
        self.durations.save_durations(video.id, {scene.id: float(seconds)})
        return SceneNarrationArtifact(video_id=video.id, scene_id=scene.id, path=destination,
                                      duration_s=float(seconds), sha256=_sha256_file(destination),
                                      voice_id=_voice_identity(voice))

    def _synthesize(self, video: Video, scene: Scene, voice: Voice, destination: Path) -> float:
        estimate = getattr(voice, "cost_estimate", None)
        amount = Decimal(str(estimate(scene.narration))) if callable(estimate) else Decimal("0")
        if self.paid is None:
            return float(voice.speak(scene.narration, destination))
        key = f"narration:{video.id}:{scene.id}"
        return float(self.paid.run(
            key, video.id, amount,
            call=lambda: voice.speak(scene.narration, destination),
            settle=lambda seconds: _voice_settlement(voice, scene.narration, seconds),
            allow_free_replay=True))


def _voice_identity(voice: Voice) -> str:
    name = getattr(voice, "name", "voice")
    model = getattr(voice, "model", "") or ""
    return f"{name}:{model}" if model else str(name)
