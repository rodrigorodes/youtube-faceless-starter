"""Casos de uso de renderização: enfileirar (idempotente), executar (voz → vídeo → QA → publicar) e consultar."""
import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from ..domain.contracts import Asset, AssetKind, QaReport, RenderJob, VideoStatus
from ..domain.render import MAX_SECONDS, NARRATION_FILE, Cue, evaluate_qa, make_cues, scene_length, to_srt
from .editorial import StateConflict, _require_video
from .errors import ServiceUnavailable
from .observability import run_step
from .ports import (AssetRepository, QaAnalyzer, RenderJobRepository, Renderer, RenderSpec, RenderStorage, ScriptRepository,
                    VideoRepository, Voice)


class RenderRefused(ValueError):
    """O vídeo não pode ser renderizado (ex.: passaria do limite de duração do formato)."""


def _scenes_with_assets(videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, video_id: str):
    scenes = scripts.scenes(video_id)
    if not scenes:
        raise StateConflict("no scenes to render")
    found = []
    for scene in scenes:
        asset = assets.get(scene.asset_id) if scene.asset_id else None
        if asset is None:
            raise StateConflict(f"scene {scene.idx} has no asset: produce the assets first")
        found.append((scene, asset))
    return found


class StartRender:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository,
                 jobs: RenderJobRepository, enqueue: Callable[[str], None]):
        self.videos, self.scripts, self.assets, self.jobs, self.enqueue = videos, scripts, assets, jobs, enqueue

    def execute(self, video_id: str) -> RenderJob:
        video = _require_video(self.videos, video_id)
        if video.status not in (VideoStatus.ASSETS_READY, VideoStatus.RENDERED):
            raise StateConflict(f"render needs state ASSETS_READY (or RENDERED to render again), got {video.status.value}")
        pairs = _scenes_with_assets(self.videos, self.scripts, self.assets, video_id)
        payload = json.dumps([video.format.value, [[s.narration, s.label, a.cache_key] for s, a in pairs]], ensure_ascii=False)
        job, created = self.jobs.enqueue(video_id, hashlib.sha256(payload.encode("utf-8")).hexdigest())
        if created:
            try:
                self.enqueue(job.id)  # só quem criou enfileira: chamada repetida não duplica a execução
            except Exception as exc:  # executor encerrado etc.: sem isto o job ficaria QUEUED e bloquearia o vídeo
                try:
                    self.jobs.fail(job.id, "could not queue the render")
                except Exception:
                    pass
                raise ServiceUnavailable("render queue unavailable") from exc
        return job


class RunRender:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, jobs: RenderJobRepository,
                 files: RenderStorage, voice_for: Callable[[str], Voice], renderer_for: Callable[[str], Renderer], analyzer: QaAnalyzer,
                 steps=None):
        self.videos, self.scripts, self.assets, self.jobs, self.files = videos, scripts, assets, jobs, files
        self.voice_for, self.renderer_for, self.analyzer = voice_for, renderer_for, analyzer
        self.steps = steps

    def execute(self, job_id: str) -> None:
        """Roda um job. Nunca levanta (a exceção iria para um Future que ninguém lê): qualquer falha vira job FAILED
        com a causa e o vídeo continua no estado anterior. Se nem o banco responder, o reaper do `enqueue` encerra o job parado."""
        work = None
        try:
            job = self.jobs.get(job_id)
            if job is None or not self.jobs.start(job_id):
                return
            try:
                def render():
                    nonlocal work
                    video = _require_video(self.videos, job.video_id)
                    if video.status not in (VideoStatus.ASSETS_READY, VideoStatus.RENDERED):
                        raise RenderRefused(f"video state changed to {video.status.value}")
                    pairs = _scenes_with_assets(self.videos, self.scripts, self.assets, job.video_id)
                    work = self.files.work_dir(video.project_id, video.id, job_id)
                    self._render(job, video, pairs, work)
                if self.steps is None:
                    render()
                else:
                    run_step(self.steps, job.video_id, "render", job.input_hash, render, reusable=False)
            except RenderRefused as exc:
                self._fail(job_id, str(exc), work)
            except Exception as exc:  # voz, ffmpeg, disco, banco
                self._fail(job_id, f"{type(exc).__name__}: {str(exc)[:300]}", work)
        except Exception:
            pass
        finally:
            if work is not None:
                try:
                    self.files.cleanup(work)
                except Exception:
                    pass

    def _fail(self, job_id: str, error: str, work) -> None:
        if work is not None:
            error = error.replace(str(work), "<work>")  # não vaza o caminho do container pela API
        try:
            self.jobs.fail(job_id, error)
        except Exception:
            pass

    def _render(self, job: RenderJob, video, pairs, work) -> None:
        voice, renderer = self.voice_for(video.project_id), self.renderer_for(video.project_id)
        wavs, seconds = [], []
        for scene, _ in pairs:
            wav = work / f"speech_{scene.idx:03d}.wav"
            seconds.append(voice.speak(scene.narration, wav))
            wavs.append(wav)
        lengths = [scene_length(s) for s in seconds]
        total, limit = sum(lengths), MAX_SECONDS[video.format]
        if total > limit:
            raise RenderRefused(f"video would last {total:.0f}s, above the {limit}s limit for {video.format.value}")
        cues: list[Cue] = []
        offset = 0.0
        for (scene, _), speech, length in zip(pairs, seconds, lengths):
            cues += make_cues(scene.narration, offset, speech)
            offset += length
        stock = any(a.provider == "stock" for _, a in pairs)
        spec = RenderSpec(scenes=[s for s, _ in pairs], images=[self.files.image_path(a.path) for _, a in pairs], speech_wavs=wavs,
                          scene_seconds=lengths, cues=cues, format=video.format, music=True, work_dir=work,
                          disclosure="Imagens ilustrativas" if stock else "Ilustração gerada por IA")
        mp4 = renderer.render(spec, work / "final.mp4")
        metrics = self.analyzer.analyze(mp4, narration=work / NARRATION_FILE)
        qa = evaluate_qa({**metrics, "expected_s": round(total, 3)}, video.format)
        if not self.jobs.alive(job.id):  # perdeu a posse (encerrado por outro processo / vídeo mudou): não publica nada
            raise RenderRefused("render was cancelled or the video state changed")
        relative = self.files.publish(video.project_id, video.id, job.id, mp4, to_srt(cues))
        key = hashlib.sha256(f"video|{renderer.name}|{job.input_hash}|{job.id}".encode()).hexdigest()
        asset = self.assets.add(Asset(id=uuid.uuid4().hex, kind=AssetKind.video, cache_key=key, path=relative, provider=renderer.name,
                                      model="ffmpeg", license="gerado pelo estúdio a partir de assets licenciados"))
        if not self.jobs.complete(job.id, asset, qa):
            raise RenderRefused("video state changed during the render")
        self.files.prune(video.project_id, video.id, relative)  # só o arquivo do job vencedor sobrevive


class GetRenderFile:
    SERVABLE = (VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL, VideoStatus.APPROVED, VideoStatus.PUBLISHED)

    def __init__(self, videos: VideoRepository, jobs: RenderJobRepository, files: RenderStorage):
        self.videos, self.jobs, self.files = videos, jobs, files

    def execute(self, video_id: str, kind: str):
        """Serve o arquivo do asset do render bem-sucedido mais recente, nunca um nome fixo."""
        video = _require_video(self.videos, video_id)
        if video.status not in self.SERVABLE:
            return None
        asset = self.jobs.latest_output(video_id)
        return self.files.resolve(asset.path, kind) if asset else None


class GetRender:
    def __init__(self, videos: VideoRepository, jobs: RenderJobRepository):
        self.videos, self.jobs = videos, jobs

    def execute(self, video_id: str) -> tuple[RenderJob | None, QaReport | None]:
        video = _require_video(self.videos, video_id)
        return self.jobs.latest(video_id), video.qa_report


@dataclass(frozen=True)
class Rendering:
    start: StartRender
    get: GetRender
    file: GetRenderFile
