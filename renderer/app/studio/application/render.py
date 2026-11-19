"""Casos de uso de renderização: enfileirar (idempotente), executar (voz → vídeo → QA → publicar) e consultar."""
import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from ..domain.contracts import Asset, AssetKind, QaReport, RenderJob, VideoStatus
from ..domain.render import MAX_SECONDS, Cue, evaluate_qa, make_cues, scene_length, to_srt
from .editorial import StateConflict, _require_video
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
            self.enqueue(job.id)  # só quem criou enfileira: chamada repetida não duplica a execução
        return job


class RunRender:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, jobs: RenderJobRepository,
                 files: RenderStorage, voice_for: Callable[[str], Voice], renderer_for: Callable[[str], Renderer], analyzer: QaAnalyzer):
        self.videos, self.scripts, self.assets, self.jobs, self.files = videos, scripts, assets, jobs, files
        self.voice_for, self.renderer_for, self.analyzer = voice_for, renderer_for, analyzer

    def execute(self, job_id: str) -> None:
        """Roda um job. Nunca levanta: qualquer falha vira job FAILED com a causa (o vídeo continua no estado anterior)."""
        job = self.jobs.get(job_id)
        if job is None or not self.jobs.start(job_id):
            return
        work = None
        try:
            video = _require_video(self.videos, job.video_id)
            if video.status not in (VideoStatus.ASSETS_READY, VideoStatus.RENDERED):
                raise RenderRefused(f"video state changed to {video.status.value}")
            pairs = _scenes_with_assets(self.videos, self.scripts, self.assets, job.video_id)
            work = self.files.work_dir(video.project_id, video.id, job_id)
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
            metrics = self.analyzer.analyze(mp4)
            qa = evaluate_qa({**metrics, "expected_s": round(total, 3)}, video.format)
            relative = self.files.publish(video.project_id, video.id, mp4, to_srt(cues))
            key = hashlib.sha256(f"video|{renderer.name}|{job.input_hash}".encode()).hexdigest()
            asset = self.assets.add(Asset(id=uuid.uuid4().hex, kind=AssetKind.video, cache_key=key, path=relative, provider=renderer.name,
                                          model="ffmpeg", license="gerado pelo estúdio a partir de assets licenciados"))
            if not self.jobs.complete(job_id, asset, qa):
                raise RenderRefused("video state changed during the render")
        except RenderRefused as exc:
            self.jobs.fail(job_id, str(exc))
        except Exception as exc:  # voz, ffmpeg, disco, banco: o job registra a causa e a API responde por consulta
            self.jobs.fail(job_id, f"{type(exc).__name__}: {str(exc)[:300]}")
        finally:
            if work is not None:
                self.files.cleanup(work)


class GetRenderFile:
    SERVABLE = (VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL, VideoStatus.APPROVED, VideoStatus.PUBLISHED)

    def __init__(self, videos: VideoRepository, files: RenderStorage):
        self.videos, self.files = videos, files

    def execute(self, video_id: str, kind: str):
        video = _require_video(self.videos, video_id)
        return self.files.final_path(video.project_id, video.id, kind) if video.status in self.SERVABLE else None


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
