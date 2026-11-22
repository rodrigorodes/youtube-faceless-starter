"""Casos de uso de renderização: enfileirar (idempotente), executar (voz → vídeo → QA → publicar) e consultar."""
import hashlib
import json
import shutil
import uuid
import wave
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ..domain.contracts import Asset, AssetKind, RenderJob, UsageEntry, Video, VideoStatus
from ..domain.effective_config import ConfigSource, EffectiveConfig
from ..domain.qa_report import QaReport
from ..domain.render import MAX_SECONDS, NARRATION_FILE, Cue, make_cues, scene_length, split_chunks, to_srt
from ..domain.render_cache import NodeId, narration_fingerprint
from ..domain.render_plan import ConfigSnapshot, StyleSnapshot
from ..domain.run_config import RunConfigStatus
from ..domain.visual_style import ResolvedStyle
from .budget import PaidOperationGuard, paid_key, provider_settlement
from .editorial import StateConflict, _require_video
from .errors import ServiceUnavailable
from .observability import run_step
from .ports import (AssetRepository, ProductionRunConfigStore, QualityEvaluator, RenderJobRepository, RenderPlanRepository,
                    Renderer, RenderSpec, RenderStorage, SceneDurationStore, SceneNarrationStore, ScriptRepository,
                    VideoRepository, Voice)


class RenderRefused(ValueError):
    """O vídeo não pode ser renderizado (ex.: passaria do limite de duração do formato)."""


def _voice_identity(voice: Voice) -> str:
    """Identidade da voz que muda o áudio: nome + modelo (fingerprint da narração, RP-06c/VS-06).

    Como o ``Voice`` carrega o **modelo efetivo** (estilo > projeto > default, resolvido na
    composição), esta identidade é a mesma da voz que sintetiza: o cache e o ledger não registram
    uma voz diferente da que falou.
    """
    model = getattr(voice, "model", "") or ""
    return f"{voice.name}:{model}" if model else str(voice.name)


def _sha256_file(path: Path) -> str:
    """sha256 do conteúdo físico de um artefato — a identidade que o índice de cache guarda."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wav_seconds(path: Path) -> float:
    """Duração **real** de um WAV, medida do arquivo — nunca uma estimativa."""
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        frames = handle.getnframes()
    return frames / rate if rate else 0.0


def _voice_settlement(voice: Voice, text: str, seconds: float):
    """Encerra o custo da voz: FREE se comprovadamente zero, ACTUAL só com evidência de cobrança, senão ESTIMATE."""
    estimate = getattr(voice, "cost_estimate", None)
    amount = Decimal(str(estimate(text))) if callable(estimate) else Decimal("0")
    entry = UsageEntry(step="voice", provider=voice.name, model=getattr(voice, "model", "") or "local", cost_usd=float(amount))
    charge = getattr(voice, "charge_evidence", None)
    evidence = charge(text, seconds) if callable(charge) else None
    return provider_settlement(entry, settled_by=f"studio:voice:{voice.name}", charge=evidence)


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


def style_from_effective_config(config: EffectiveConfig) -> ResolvedStyle | None:
    """Projeta a configuração efetiva congelada no estilo que o renderer consome (F03.T03). Puro.

    O plano e a voz saem do **mesmo** ``EffectiveConfig`` lido no início da execução: não há
    segunda leitura de canal/estilo no meio do TTS. Só os valores **declarados** por uma camada
    criativa (vídeo/canal/estilo) entram no ``ResolvedStyle``; o que a proveniência marca como
    ``engine_default`` continua sendo decisão do motor (ciclo de Ken Burns, layout, bpm/seed
    default), exatamente como antes desta fiação. Sem estilo selecionado, devolve ``None`` — o
    bundle neutro do renderer.
    """
    if not isinstance(config, EffectiveConfig):
        raise TypeError("style_from_effective_config expects an EffectiveConfig")
    if config.style is None:
        return None
    provenance = config.provenance

    def declared(group: str) -> dict:
        values = getattr(config, group)
        return {str(key): value for key, value in values.items()
                if provenance.get(f"audiovisual.{group}.{key}") != ConfigSource.ENGINE_DEFAULT.value}

    motion = (tuple(config.motion)
              if provenance.get("audiovisual.motion") != ConfigSource.ENGINE_DEFAULT.value else ())
    return ResolvedStyle(
        snapshot=StyleSnapshot(style_id=config.style.id, version=config.style.version),
        motion=motion,
        music=declared("music"),
        transition=declared("transition"),
        caption=declared("caption"),
        palette=declared("palette"),
        voice=declared("voice"),
    )


def config_snapshot_for(config: EffectiveConfig) -> ConfigSnapshot:
    """Identidade da configuração efetiva que o plano grava (F03.T03). Puro.

    Só o que governa o render viaja no plano: ``style`` e ``audiovisual.*``. Editorial e
    política de provedor ficam de fora (não são consumo do renderer), e o documento completo
    continua sendo o snapshot do run (F03.T02).
    """
    if not isinstance(config, EffectiveConfig):
        raise TypeError("config_snapshot_for expects an EffectiveConfig")
    relevant = {key: source for key, source in config.provenance.items()
                if key == "style" or key.startswith("audiovisual.")}
    return ConfigSnapshot(content_hash=config.content_hash, schema_version=config.schema_version,
                          provenance=dict(sorted(relevant.items())))


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
                 files: RenderStorage, voice_for: Callable[[Video], Voice], renderer_for: Callable[[str], Renderer], quality: QualityEvaluator,
                 steps=None, paid: PaidOperationGuard | None = None, plans: RenderPlanRepository | None = None,
                 narration_reuse: bool = True, style_for: Callable[[Video], ResolvedStyle | None] | None = None,
                 effective_config_for: Callable[[Video], EffectiveConfig] | None = None,
                 config_store: ProductionRunConfigStore | None = None,
                 voice_for_config: Callable[[Video, EffectiveConfig], Voice] | None = None,
                 style_for_config: Callable[[EffectiveConfig], ResolvedStyle | None] | None = None,
                 scene_durations: "SceneDurationStore | None" = None,
                 scene_narration: "SceneNarrationStore | None" = None):
        self.videos, self.scripts, self.assets, self.jobs, self.files = videos, scripts, assets, jobs, files
        self.voice_for, self.renderer_for, self.quality = voice_for, renderer_for, quality
        # VS-06: a voz efetiva é resolvida por **vídeo** (o estilo do canal/override decide),
        # não pelo project_id: a mesma voz que sintetiza entra no cache/ledger. Injetada pela
        # composição (o core não conhece banco).
        self.steps, self.paid = steps, paid
        # RP-016/VS-05c: de quem é a identidade visual versionada do plano. Injetada pela composição
        # (o core não conhece banco): recebe o **vídeo** e resolve canal → override do vídeo. Sem
        # resolvedor, o plano não referencia estilo e o renderer usa o default — o comportamento de
        # antes desta fiação.
        self.style_for = style_for
        # RP-06c: o índice de cache do plano (fingerprint da entrada da narração) permite pular o
        # TTS de uma cena inalterada. Sem repositório (unidade), o comportamento é o de antes.
        self.plans = plans
        self.narration_reuse = narration_reuse
        # F03.T03: UMA configuração efetiva por execução, lida no início, governa voz e plano.
        # O run já existente entrega o snapshot congelado (`config_store`); o render avulso
        # (sem run) resolve uma vez com `effective_config_for`. Sem nenhum dos dois, o caminho
        # legado (`voice_for`/`style_for`) é preservado byte a byte.
        self.effective_config_for = effective_config_for
        self.config_store = config_store
        # Projeções do snapshot: a voz é construída pela composição (provider) e o estilo é puro
        # (`style_from_effective_config` como default). Ausentes = fallback legado.
        self.voice_for_config = voice_for_config
        self.style_for_config = style_for_config
        # W4.3: duração real por cena e cópia durável do WAV para pré-escuta. Opcionais: sem eles,
        # o render é exatamente o de antes.
        self.scene_durations = scene_durations
        self.scene_narration = scene_narration

    def execute(self, job_id: str, run_id: str | None = None) -> None:
        """Roda um job. Nunca levanta (a exceção iria para um Future que ninguém lê): qualquer falha vira job FAILED
        com a causa e o vídeo continua no estado anterior. Se nem o banco responder, o reaper do `enqueue` encerra o job parado.

        ``run_id`` é o run de produção dono do job (quando existe): o snapshot congelado da
        configuração efetiva é lido dele e nunca re-resolvido. Sem run, o render avulso resolve a
        configuração **uma vez** no início da execução.
        """
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
                    config = self._effective_config(video, run_id)
                    pairs = _scenes_with_assets(self.videos, self.scripts, self.assets, job.video_id)
                    work = self.files.work_dir(video.project_id, video.id, job_id)
                    self._render(job, video, pairs, work, config)
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

    def _effective_config(self, video: Video, run_id: str | None) -> EffectiveConfig | None:
        """Lê o snapshot do run (se houver) ou resolve uma vez; ``None`` = caminho legado.

        Run `resolved` devolve a configuração congelada sem recalcular nada (retry/replay leem o
        mesmo hash). Run `legacy` devolve ``None`` de propósito: nunca ganha snapshot depois do
        fato (F03.T02). Sem run/job, o render avulso resolve **neste instante** — a única leitura
        de canal/estilo da execução.
        """
        if run_id is not None and self.config_store is not None:
            stored = self.config_store.run_config(run_id)
            if stored is not None:
                return stored.config if stored.status is RunConfigStatus.RESOLVED else None
        if self.effective_config_for is None:
            return None
        config = self.effective_config_for(video)
        if not isinstance(config, EffectiveConfig):
            raise TypeError("effective_config_for must return an EffectiveConfig")
        if config.video_id != video.id:
            raise ValueError("the effective config belongs to another video")
        return config

    def _fail(self, job_id: str, error: str, work) -> None:
        if work is not None:
            error = error.replace(str(work), "<work>")  # não vaza o caminho do container pela API
        try:
            self.jobs.fail(job_id, error)
        except Exception:
            pass

    def _cached_narration(self, scene, voice_id: str, entries: dict) -> Path | None:
        """WAV de narração reusável: fingerprint da **entrada** igual e artefato físico íntegro.

        A entrada da cena (texto falado + identidade da voz) é comparada com o fingerprint do nó
        ``narration`` registrado pela revisão anterior — uma decisão tomada **antes** de sintetizar
        (RP-06c). Qualquer dúvida (sem registro, fingerprint diferente, arquivo ausente, hash
        divergente, erro de leitura) cai fora do reúso: sintetizar é sempre seguro.
        """
        if not entries:
            return None
        fingerprint = narration_fingerprint(
            " ".join(split_chunks(scene.narration)), f"voice:{scene.id}", {"voice": voice_id} if voice_id else None)
        entry = entries.get(NodeId("narration", scene.id))
        if entry is None or entry.fingerprint != fingerprint:
            return None
        path = Path(entry.artifact_uri)
        try:
            if not path.is_file() or _sha256_file(path) != entry.artifact_sha256:
                return None
        except OSError:
            return None
        return path

    def _voice(self, video, config: EffectiveConfig | None) -> Voice:
        """Voz da execução: do snapshot (projeção da composição) ou o resolvedor legado."""
        if config is not None and self.voice_for_config is not None:
            return self.voice_for_config(video, config)
        return self.voice_for(video)

    def _style(self, video, config: EffectiveConfig | None) -> ResolvedStyle | None:
        """Estilo da execução: do snapshot (uma projeção) ou o resolvedor legado."""
        if config is not None:
            if self.style_for_config is not None:
                return self.style_for_config(config)
            return style_from_effective_config(config)
        return self.style_for(video) if self.style_for is not None else None

    def _render(self, job: RenderJob, video, pairs, work, config: EffectiveConfig | None = None) -> None:
        # F03.T03: voz e estilo saem da MESMA configuração, projetada no início — nenhuma leitura
        # de canal/estilo acontece depois deste ponto (o TTS pode demorar; o snapshot não muda).
        voice, renderer, style = self._voice(video, config), self.renderer_for(video.project_id), self._style(video, config)
        voice_id = _voice_identity(voice)
        # Uma consulta ao índice por render (não uma por cena): o reúso da narração inteira.
        entries = self.plans.entries(f"plan:{video.id}") if (self.plans is not None and self.narration_reuse) else {}
        wavs, seconds = [], []
        for scene, _ in pairs:
            wav = work / f"speech_{scene.idx:03d}.wav"
            cached = self._cached_narration(scene, voice_id, entries)
            if cached is not None:
                # Narração em cache (texto/voz inalterados) e WAV íntegro: reusa e **pula o TTS**.
                # A duração é **medida do próprio WAV reusado** — nunca estimada.
                shutil.copyfile(cached, wav)
                wavs.append(wav)
                seconds.append(_wav_seconds(wav))
                continue
            if self.paid is None:
                seconds.append(voice.speak(scene.narration, wav))
            else:
                # chave por conteúdo (texto + voz + modelo), não por job: retentativa da mesma narração não cobra de novo
                key = paid_key("voice", video.id, scene.idx, voice.name, getattr(voice, "model", ""), scene.narration)
                estimate = getattr(voice, "cost_estimate", None)
                amount = Decimal(str(estimate(scene.narration))) if callable(estimate) else Decimal("0")
                seconds.append(self.paid.run(
                    key, video.id, amount,
                    call=lambda s=scene, w=wav: voice.speak(s.narration, w),
                    settle=lambda secs, t=scene.narration: _voice_settlement(voice, t, secs),
                    allow_free_replay=True))
            wavs.append(wav)
        lengths = [scene_length(s) for s in seconds]
        total, limit = sum(lengths), MAX_SECONDS[video.format]
        if total > limit:
            raise RenderRefused(f"video would last {total:.0f}s, above the {limit}s limit for {video.format.value}")
        # W4.3: a duração medida vira dado da cena e o WAV fica disponível para pré-escuta.
        if self.scene_durations is not None:
            self.scene_durations.save_durations(video.id, {scene.id: float(sec) for (scene, _), sec in zip(pairs, seconds)})
        if self.scene_narration is not None:
            for (scene, _), wav in zip(pairs, wavs):
                try:
                    shutil.copyfile(wav, self.scene_narration.narration_path(video.project_id, video.id, scene.id))
                except OSError:
                    pass
        cues: list[Cue] = []
        offset = 0.0
        for (scene, _), speech, length in zip(pairs, seconds, lengths):
            cues += make_cues(scene.narration, offset, speech)
            offset += length
        stock = any(a.provider == "stock" for _, a in pairs)
        spec = RenderSpec(scenes=[s for s, _ in pairs], images=[self.files.image_path(a.path) for _, a in pairs], speech_wavs=wavs,
                          scene_seconds=lengths, cues=cues, format=video.format, music=True, work_dir=work,
                          disclosure="Imagens ilustrativas" if stock else "Ilustração gerada por IA", voice_id=voice_id,
                          style=style,
                          config_snapshot=(config_snapshot_for(config) if config is not None else None))
        mp4 = renderer.render(spec, work / "final.mp4")
        # A identidade do render nasce antes do QA: é o mesmo checksum que a publicação reutiliza
        # (o asset de saída), então o relatório já sai vinculado à versão que será aprovada.
        key = hashlib.sha256(f"video|{renderer.name}|{job.input_hash}|{job.id}".encode()).hexdigest()
        qa_inputs = renderer.qa_inputs(spec)
        qa = self.quality.evaluate(qa_inputs.plan, media_path=mp4, narration_path=work / NARRATION_FILE,
                                   descriptors=qa_inputs.descriptors, render_id=job.id, checksum=key)
        if not self.jobs.alive(job.id):  # perdeu a posse (encerrado por outro processo / vídeo mudou): não publica nada
            raise RenderRefused("render was cancelled or the video state changed")
        relative = self.files.publish(video.project_id, video.id, job.id, mp4, to_srt(cues))
        asset = self.assets.add(Asset(id=uuid.uuid4().hex, kind=AssetKind.video, cache_key=key, path=relative, provider=renderer.name,
                                      model=renderer.name, license="gerado pelo estúdio a partir de assets licenciados"))
        if not self.jobs.complete(job.id, asset, qa):
            raise RenderRefused("video state changed during the render")
        self.files.prune(video.project_id, video.id, relative)  # só o arquivo do job vencedor sobrevive


class GetRenderFile:
    SERVABLE = (VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL, VideoStatus.APPROVED, VideoStatus.PUBLISHED)

    def __init__(self, videos: VideoRepository, jobs: RenderJobRepository, files: RenderStorage):
        self.videos, self.jobs, self.files = videos, jobs, files

    def execute(self, video_id: str, kind: str, output_asset_id: str | None = None):
        """Serve o arquivo do asset do render bem-sucedido mais recente, nunca um nome fixo."""
        video = _require_video(self.videos, video_id)
        if video.status not in self.SERVABLE:
            return None
        if video.status in (VideoStatus.APPROVED, VideoStatus.PUBLISHED):
            asset = self.jobs.approved_output(video_id)
            if output_asset_id and (not asset or asset.id != output_asset_id):
                return None
        else:
            asset = self.jobs.output(video_id, output_asset_id) if output_asset_id else self.jobs.latest_output(video_id)
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
