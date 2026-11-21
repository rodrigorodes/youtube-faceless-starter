"""Executor FFmpeg do Render Plan (RP-024..RP-026) — o único lugar com ``subprocess``.

Consome o ``CompiledRender`` do compilador puro (``application/render_compiler.py``,
RP-023): materializa os overlays (selo/disclosure/legendas com **Pillow**), sintetiza a
trilha de música, monta a faixa de narração, roda um ``ffmpeg`` por shot, concatena sem
reencode e mixa com *ducking* + ``loudnorm`` — o mesmo grafo que o renderer legado
produzia. O vídeo final é publicado de forma **atômica** (arquivo temporário +
``os.replace``), nunca deixando um ``.mp4`` parcial no destino.

Decisão §5.4 do design: o ``subprocess`` só mora aqui. O compilador continua **puro** —
nada de FFmpeg/PIL no ``domain``/``application`` (``tests/test_architecture.py``).

Rollout (§5.6/§11-R2, revisto): o **caminho baseado em plano é agora o único**. O
executor reconstrói o ``RenderPlan`` a partir do ``RenderSpec`` que o ``RunRender``
produz — é o único ponto onde o hash de conteúdo dos assets pode ser calculado (I/O de
leitura) sem contaminar o núcleo puro. O antigo renderer (``render_ffmpeg.py``, com
Ken Burns por ``index % 4``) foi removido depois de a paridade ser medida (§11-R6).

Paridade preservada: Ken Burns por modo **explícito** do plano (sem ``index % 4``),
selo (``label``), aviso de imagem sintética (``disclosure``), legenda queimada por trecho
com ``enable`` semiaberto, *ducking* da música sob a narração, ``loudnorm=I=-16``, fades
por segmento, 1080×1920 (short) e 1920×1080 (long) e timebase **25 fps**.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import uuid
import wave
from collections.abc import Mapping
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ... import rich
from ..application.ports import RenderQaInputs, RenderSpec
from ..application.render_cache import PlanRegeneration
from ..application.render_compiler import CompiledRender, compile_render_plan
from ..domain.asset_resolver import IMAGE_CODECS, AssetDescriptor
from ..domain.contracts import VideoFormat
from ..domain.render import LEAD, SIZE, TAIL
from ..domain.render_cache import CacheEntry, NodeId, PlanArtifact, plan_graph
from ..domain.render_plan import AssetReference, Motion, RenderPlan, StyleSnapshot
from ..domain.render_plan_builder import StoryboardScene, build_render_plan

FONT, FONT_BOLD = rich.FONT, rich.FONT_BOLD
# Identidade do canal por chave + versão (R4). O RenderSpec do RunRender não carrega o
# perfil do canal; o bundle neutro é declarado aqui até a fiação do StyleSnapshot (RP-016).
DEFAULT_STYLE_ID = "studio-default"
DEFAULT_STYLE_VERSION = 1
# Licença das imagens que o próprio estúdio gera a partir dos assets licenciados.
GENERATED_LICENSE = "gerado pelo estúdio a partir de assets licenciados"
# Movimento de Ken Burns **declarado** por shot (R3): a política preserva o efeito visual
# do renderer removido, mas entra no plano como ``Effects.motion`` explícito por cena — o
# compilador nunca decide movimento por ``index % 4``. Um produtor de beats/movimento
# (fatia posterior) substitui este default por um plano próprio.
KEN_BURNS_CYCLE: tuple[Motion, ...] = ("zoom_in", "zoom_out", "pan_right", "pan_left")

_LAYOUT = {  # margens que respeitam a interface dos Shorts (vertical) e a área segura do vídeo horizontal
    VideoFormat.short: {"caption_bottom": 1560, "caption_font": 58, "caption_side": 100, "box_side": 50, "line_h": 78},
    VideoFormat.long: {"caption_bottom": 960, "caption_font": 50, "caption_side": 300, "box_side": 250, "line_h": 68},
}


def _wrap(draw, text, font, max_width):
    return rich._wrap(draw, text, font, max_width)


def static_overlay(fmt: VideoFormat, label: str, disclosure: str, dst: Path) -> None:
    """PNG transparente com o aviso de imagem sintética e o selo do dia."""
    w, h = SIZE[fmt]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((60, 96), disclosure, font=ImageFont.truetype(FONT, 30), fill=(255, 255, 255, 190))
    if label:
        badge = ImageFont.truetype(FONT_BOLD, 46)
        box = draw.textbbox((0, 0), label, font=badge)
        bw, bh = box[2] - box[0], box[3] - box[1]
        draw.rounded_rectangle((60, 160, 60 + bw + 56, 160 + bh + 40), radius=26, fill=(255, 0, 140, 235))
        draw.text((60 + 28, 160 + 14), label, font=badge, fill="white")
    img.save(dst)


def caption_overlay(fmt: VideoFormat, text: str, dst: Path) -> None:
    """PNG transparente com um trecho de legenda queimada."""
    w, h = SIZE[fmt]
    lay = _LAYOUT[fmt]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_BOLD, lay["caption_font"])
    lines = _wrap(draw, text, font, w - 2 * lay["caption_side"])[:4]
    height = len(lines) * lay["line_h"] + 64
    bottom = lay["caption_bottom"]
    top = bottom - height
    draw.rounded_rectangle((lay["box_side"], top, w - lay["box_side"], bottom), radius=36, fill=(0, 0, 0, 165))
    y = top + 32
    for line in lines:
        draw.text((lay["caption_side"] + 2, y + 2), line, font=font, fill=(0, 0, 0, 200))
        draw.text((lay["caption_side"], y), line, font=font, fill="white")
        y += lay["line_h"]
    img.save(dst)


def text_card(fmt: VideoFormat, text: str, dst: Path) -> None:
    """Card local de um asset de texto (RP-021): fundo sólido + texto centralizado."""
    w, h = SIZE[fmt]
    img = Image.new("RGB", (w, h), (16, 18, 32))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_BOLD, 140 if fmt == VideoFormat.short else 120)
    lines = _wrap(draw, text, font, int(w * 0.8))[:6]
    line_h = font.size + 24
    y = h // 2 - len(lines) * line_h // 2
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        draw.text(((w - (box[2] - box[0])) // 2, y), line, font=font, fill="white")
        y += line_h
    img.save(dst)


def _sha256_file(path: Path) -> str:
    """sha256 do conteúdo físico do artefato: é a identidade que o índice de cache guarda."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    """Nome de arquivo seguro e estável para um id lógico (plan_id/node_key têm ``:``)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_")[:120] or "x"


def _artifact_kind(node: NodeId) -> tuple[str | None, str]:
    """(media_type, codec) do artefato físico de um nó, para o registro de ``plan_artifacts``.

    ``media_type`` segue a whitelist do schema (image/video/graphic/text): áudio não é um
    tipo aceito, então narração/trilha ficam sem media_type e só carregam o codec.
    """
    if node.kind in ("narration", "music"):
        return None, "pcm_s16le"
    return "video", "h264"


def _run(cmd: list[str], timeout: int = 600) -> None:
    try:
        subprocess.run(cmd, check=True, timeout=timeout, capture_output=True)
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or b"").decode("utf-8", "replace").strip()[-300:]
        raise RuntimeError(f"ffmpeg failed: {tail}") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg timed out") from None


def _write_silence(path: Path, seconds: float, rate: int = rich.MUSIC_SR) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(b"\x00\x00" * max(0, int(seconds * rate)))


def _probe_image(path: Path, asset_id: str) -> tuple[str, int, int]:
    try:
        with Image.open(path) as img:
            codec = (img.format or "").lower()
            width, height = img.size
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise RuntimeError(f"image asset {asset_id!r} is not a readable image") from None
    if codec not in IMAGE_CODECS:
        raise RuntimeError(f"unsupported image codec {codec!r} for asset {asset_id!r}")
    if width < 1 or height < 1:
        raise RuntimeError(f"image asset {asset_id!r} has an empty resolution")
    return codec, width, height


class PlanFfmpegRenderer:
    """Implementação de ``Renderer`` que executa **exclusivamente** o Render Plan.

    ``render(spec, out_path)`` reconstrói o plano a partir do ``RenderSpec`` do
    ``RunRender`` (a mesma entrada do renderer antigo), resolve os descriptors de mídia,
    compila o plano (puro) e executa o plano de execução. O movimento de Ken Burns entra
    no plano **explícito por cena** (``cycle`` por posição + ``motions`` por ``scene_id``);
    o ``index % 4`` do renderer removido nunca é reintroduzido no compilador.
    """

    name = "ffmpeg"

    def __init__(self, model: str = "rich", *, cycle: tuple[Motion, ...] | None = None,
                 motions: Mapping[str, Motion] | None = None, timeout_floor: int = 300, runner=None,
                 plans=None, cache_root: Path | None = None):
        self.model = model
        self.cycle = tuple(KEN_BURNS_CYCLE if cycle is None else cycle)
        self.motions = dict(motions or {})
        self.timeout_floor = timeout_floor
        self._run = runner or _run
        # RP-06b: com um repositório a instância reusa artefatos (segmentos/wavs/montagem) por
        # fingerprint de conteúdo. Sem repositório (unidade/kill-switch) o comportamento é o de
        # antes: renderiza tudo, sem tocar banco nem cache.
        self.plans = plans
        self.cache_root = Path(cache_root) if cache_root is not None else None
        self._regeneration = PlanRegeneration(plans) if plans is not None else None

    def render(self, spec: RenderSpec, out_path: Path) -> Path:
        """Rota de produção: decide o reúso, executa só o que falta e registra os artefatos.

        Cada render é uma **revisão** nova do plano lógico (``revision + 1``): é isso que dá ao
        ``PlanRegeneration`` a revisão anterior para comparar por fingerprint. Sem repositório,
        a revisão é sempre 1 e nada é persistido (caminho de unidade).
        """
        plan = self._plan_for_render(spec)
        compiled, labels = self._compile(plan, spec)
        reuse = self._reuse_hits(plan, labels)
        out = self.execute(compiled, spec.speech_wavs, Path(out_path), reuse=reuse)
        self._record(plan, compiled, labels, reuse)
        return out

    def qa_inputs(self, spec: RenderSpec) -> RenderQaInputs:
        """Plano lógico + descriptors resolvidos — a entrada do QA versionado (F6).

        Reconstrói o plano do ``RenderSpec`` (a mesma entrada do ``render``) e resolve os
        descriptors dos assets: é o único ponto com I/O de leitura de mídia, então é daqui
        que o QA persistido tira o plano e a resolução dos assets, mantendo o núcleo puro.
        """
        plan = self._build_plan(spec)
        return RenderQaInputs(plan=plan, descriptors=tuple(self._descriptors(plan, spec).values()))

    def compile_spec(self, spec: RenderSpec) -> CompiledRender:
        """Reconstrói o plano do ``RenderSpec`` e o compila (puro) — sem tocar FFmpeg.

        Separado de ``execute`` para que o grafo/comando possa ser validado por unidade,
        sem renderizar nada (o compilador em si continua em ``application``).
        """
        return self._compile(self._build_plan(spec), spec)[0]

    def _compile(self, plan: RenderPlan, spec: RenderSpec) -> tuple[CompiledRender, dict[str, str]]:
        work = Path(spec.work_dir or ".")
        descriptors = self._descriptors(plan, spec)
        labels = {scene.id: scene.label for scene in spec.scenes}
        compiled = compile_render_plan(plan=plan, assets=descriptors, work_dir=str(work), labels=labels)
        return compiled, labels

    # ------------------------------------------------------------------ reúso (RP-06b)

    def _plan_for_render(self, spec: RenderSpec) -> RenderPlan:
        plan = self._build_plan(spec)
        if self.plans is None:
            return plan
        previous = self.plans.latest_plan(plan.plan_id)
        if previous is None:
            return plan
        # Nova revisão por render: a comparação por fingerprint é entre esta e a anterior.
        return plan.model_copy(update={"revision": previous.revision + 1})

    def _reuse_hits(self, plan: RenderPlan, labels: Mapping[str, str]) -> dict[NodeId, Path]:
        """Nós reusáveis cujo artefato físico **existe e confere** com o hash registrado.

        O ``PlanRegeneration`` aplica a propagação de dependência (mudar uma cena invalida
        ``concat``/``final``); aqui só se confirma a evidência física. Qualquer dúvida (arquivo
        ausente, hash divergente, erro de leitura) cai fora do reúso: re-renderizar é seguro.
        """
        if self._regeneration is None:
            return {}
        recorded = self.plans.entries(plan.plan_id)
        decision = self._regeneration.decide(plan, labels=labels)
        hits: dict[NodeId, Path] = {}
        for node in decision.cache_hits:
            entry = recorded.get(node)
            if entry is None:
                continue
            path = Path(entry.artifact_uri)
            try:
                if not path.is_file() or _sha256_file(path) != entry.artifact_sha256:
                    continue
            except OSError:
                continue
            hits[node] = path
        return hits

    def _record(self, plan: RenderPlan, compiled: CompiledRender, labels: Mapping[str, str],
                reuse: Mapping[NodeId, Path]) -> None:
        """Persiste a revisão e registra cada artefato produzido/reusado — o cache do próximo ciclo.

        Registra a identidade **física** real (``content_sha256`` do arquivo, codec, localização)
        em ``plan_artifacts`` e a ligação **lógica** (fingerprint do nó → artefato) em
        ``render_cache_entries``. Um nó sem artefato físico não é registrado: nada de cache
        otimista.
        """
        if self.plans is None or self.cache_root is None:
            return
        graph = plan_graph(plan, labels=labels)
        entries: list[CacheEntry] = []
        artifacts: list[PlanArtifact] = []
        for item in graph.nodes:
            location = reuse.get(item.node)
            if location is None:
                produced = self._produced(item.node, compiled)
                if produced is None or not Path(produced).is_file():
                    continue
                location = self._store(plan.plan_id, item.node, item.fingerprint, Path(produced))
            try:
                digest = _sha256_file(location)
            except OSError:
                continue
            media_type, codec = _artifact_kind(item.node)
            entries.append(CacheEntry(plan_id=plan.plan_id, node=item.node, fingerprint=item.fingerprint,
                                      artifact_sha256=digest, artifact_uri=str(location), revision=plan.revision))
            artifacts.append(PlanArtifact(content_sha256=digest, location=str(location), codec=codec,
                                          media_type=media_type, byte_size=location.stat().st_size))
        self.plans.save_plan(plan)
        self.plans.record_entries(entries)
        self.plans.record_artifacts(artifacts)

    def _store(self, plan_id: str, node: NodeId, fingerprint: str, source: Path) -> Path:
        """Copia o artefato produzido para o cache persistente (fora do `work/` descartável)."""
        suffix = ".wav" if node.kind in ("narration", "music") else ".mp4"
        dest = self.cache_root / _slug(plan_id) / node.kind / f"{_slug(node.key)}-{fingerprint[:16]}{suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, tmp)
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        return dest

    @staticmethod
    def _produced(node: NodeId, compiled: CompiledRender) -> Path | None:
        if node.kind == "visual":
            return next((Path(s.output) for s in compiled.shots if s.shot_id == node.key), None)
        if node.kind == "narration":
            return next((Path(v.path) for v in compiled.audio.narration.voices if v.scene_id == node.key), None)
        if node.kind == "music":
            return Path(compiled.audio.music_path) if compiled.audio.music.source_id == node.key else None
        if node.kind == "concat":
            return Path(compiled.concat.output)
        if node.kind == "final":
            return Path(compiled.final_output)
        return None

    # ------------------------------------------------------------------ construção

    def _build_plan(self, spec: RenderSpec):
        if not spec.scenes:
            raise RuntimeError("render spec has no scenes")
        rows = list(spec.scenes)
        images = list(spec.images)
        lengths = list(spec.scene_seconds)
        if not (len(rows) == len(images) == len(lengths)):
            raise RuntimeError("render spec lists (scenes/images/scene_seconds) have different lengths")
        video_id = rows[0].video_id
        asset_paths: dict[str, Path] = {}
        manifest_by_id: dict[str, AssetReference] = {}
        scenes: list[StoryboardScene] = []
        for row, image, length in zip(rows, images, lengths):
            if not row.asset_id:
                raise RuntimeError(f"scene {row.idx} has no linked asset to build the render plan")
            path = Path(image)
            known = asset_paths.get(row.asset_id)
            if known is not None and known != path:
                raise RuntimeError(f"asset {row.asset_id!r} is linked to two different files")
            asset_paths[row.asset_id] = path
            if row.asset_id not in manifest_by_id:  # o mesmo asset pode servir mais de uma cena
                manifest_by_id[row.asset_id] = AssetReference(
                    asset_id=row.asset_id,
                    asset_version=1,
                    uri=path.as_posix(),
                    content_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    media_type="image",
                    license=GENERATED_LICENSE,
                )
            scenes.append(StoryboardScene(
                scene_id=row.id,
                asset_id=row.asset_id,
                narration=row.narration,
                speech_seconds=max(0.0, float(length) - LEAD - TAIL),
                label=row.label,
                voice_id=spec.voice_id,
            ))
        manifest = list(manifest_by_id.values())
        return build_render_plan(
            plan_id=f"plan:{video_id}",
            revision=1,
            project_id=video_id,
            video_id=video_id,
            format=spec.format,
            scenes=scenes,
            assets=manifest,
            style_snapshot=StyleSnapshot(style_id=DEFAULT_STYLE_ID, version=DEFAULT_STYLE_VERSION),
            disclosure=spec.disclosure,
            music=spec.music,
            motions=self._motions([row.id for row in rows]),
        )

    def _motions(self, scene_ids: list[str]) -> dict[str, Motion]:
        """Movimento declarado por cena: o ciclo por posição, sobreposto por ``motions``."""
        known = set(scene_ids)
        chosen: dict[str, Motion] = {}
        for index, scene_id in enumerate(scene_ids):
            chosen[scene_id] = self.cycle[index % len(self.cycle)] if self.cycle else "none"
        chosen.update({scene_id: motion for scene_id, motion in self.motions.items() if scene_id in known})
        return chosen

    def _descriptors(self, plan, spec: RenderSpec) -> dict[str, AssetDescriptor]:
        by_asset: dict[str, Path] = {}
        for row, image in zip(spec.scenes, spec.images):
            by_asset.setdefault(row.asset_id, Path(image))  # mesmo asset serve várias cenas
        descriptors: dict[str, AssetDescriptor] = {}
        for reference in plan.asset_manifest:
            path = by_asset[reference.asset_id]
            codec, width, height = _probe_image(path, reference.asset_id)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            descriptors[reference.asset_id] = AssetDescriptor(
                asset_id=reference.asset_id,
                asset_version=reference.asset_version,
                uri=reference.uri,
                content_sha256=digest,
                media_type="image",
                license=reference.license,
                location=path.as_posix(),
                available=True,
                codec=codec,
                width=width,
                height=height,
                byte_size=path.stat().st_size,
            )
        return descriptors

    # ------------------------------------------------------------------ execução

    def execute(self, compiled: CompiledRender, speech_wavs, out_path: Path, *,
                reuse: Mapping[NodeId, Path] | None = None) -> Path:
        """Materializa overlays, monta áudio, roda FFmpeg e publica de forma atômica.

        ``reuse`` mapeia nó lógico → artefato físico já existente (RP-06b). Um shot/narração/
        montagem em ``reuse`` **não** roda FFmpeg: o artefato é copiado para o caminho que o
        plano espera. ``concat``/``final`` continuam sendo recomputados quando qualquer cena
        mudou (a dependência os invalida); só quando **nada** mudou o MP4 final vem do cache.
        """
        reuse = reuse or {}
        final_node = NodeId("final", "video")
        if final_node in reuse:  # nada mudou: o MP4 final já existe como artefato físico
            return self._publish(Path(reuse[final_node]), Path(out_path))
        Path(compiled.final_output).parent.mkdir(parents=True, exist_ok=True)
        fmt = VideoFormat(compiled.format)
        self._materialize(compiled, fmt)
        narration_inputs = self._narration_inputs(compiled, speech_wavs, reuse)
        rich.build_narration_track(narration_inputs, Path(compiled.audio.narration.output))
        music_node = NodeId("music", compiled.audio.music.source_id)
        if music_node in reuse:  # trilha inalterada: o WAV vem do cache
            shutil.copyfile(reuse[music_node], Path(compiled.audio.music_path))
        else:
            self._write_music(compiled)
        total_seconds = compiled.total_ticks / compiled.ticks_per_second
        timeout = int(self.timeout_floor + 3 * total_seconds)
        for shot in compiled.shots:
            cached = reuse.get(NodeId("visual", shot.shot_id))
            if cached is not None:  # cena não impactada: segmento de vídeo vem do cache
                Path(shot.output).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(cached, shot.output)
            else:
                self._run(list(shot.args), timeout)
        if NodeId("concat", "video") in reuse:
            shutil.copyfile(reuse[NodeId("concat", "video")], compiled.concat.output)
        else:
            Path(compiled.concat.manifest_path).write_text(
                "".join(f"file '{Path(shot.output).as_posix()}'\n" for shot in compiled.shots), encoding="utf-8")
            self._run(list(compiled.concat.args), timeout)
        self._run(list(compiled.audio.args), timeout)
        return self._publish(Path(compiled.final_output), Path(out_path))

    def _materialize(self, compiled: CompiledRender, fmt: VideoFormat) -> None:
        for shot in compiled.shots:
            static_overlay(fmt, shot.static_overlay.label, shot.static_overlay.disclosure, Path(shot.static_overlay.path))
            for caption in shot.captions:
                caption_overlay(fmt, caption.text, Path(caption.path))
            if shot.text_card is not None:
                text_card(fmt, shot.text_card.text, Path(shot.text_card.path))

    def _narration_inputs(self, compiled: CompiledRender, speech_wavs,
                          reuse: Mapping[NodeId, Path] | None = None) -> list[Path]:
        reuse = reuse or {}
        voices = compiled.audio.narration.voices
        wavs = list(speech_wavs)
        if len(wavs) != len(voices):
            raise RuntimeError(f"narration has {len(voices)} scenes but {len(wavs)} speech files")
        lengths = self._scene_seconds(compiled)
        inputs: list[Path] = []
        for voice, speech in zip(voices, wavs):
            cached = reuse.get(NodeId("narration", voice.scene_id))
            if cached is not None:  # narração não impactada: o WAV vem do cache
                inputs.append(cached)
                continue
            dst = Path(voice.path)
            if voice.source_id is None:  # cena silenciosa: silêncio do mesmo comprimento (C2)
                _write_silence(dst, max(0.0, lengths.get(voice.scene_id, 0.0) - LEAD - TAIL))
            elif Path(speech).resolve() != dst.resolve():  # a fala já pode estar no caminho que o plano espera
                shutil.copyfile(Path(speech), dst)
            inputs.append(dst)
        return inputs

    @staticmethod
    def _scene_seconds(compiled: CompiledRender) -> dict[str, float]:
        tps = compiled.ticks_per_second
        lengths: dict[str, float] = {}
        for shot in compiled.shots:
            lengths[shot.scene_id] = lengths.get(shot.scene_id, 0.0) + shot.duration_ticks / tps
        return lengths

    def _write_music(self, compiled: CompiledRender) -> None:
        music = compiled.audio.music
        seconds = music.duration_ticks / compiled.ticks_per_second
        path = Path(compiled.audio.music_path)
        if music.silent:  # `music=False` mantém o grafo de mixagem com a trilha muda (C2)
            _write_silence(path, seconds)
        else:
            rich.synth_music(seconds, path, bpm=int(music.params.get("bpm", 122)))

    @staticmethod
    def _publish(source: Path, out_path: Path) -> Path:
        """Move o artefato final de forma atômica: nunca deixa um `.mp4` parcial visível."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_name(f"{out_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, tmp)
            os.replace(tmp, out_path)
        finally:
            tmp.unlink(missing_ok=True)
        return out_path
