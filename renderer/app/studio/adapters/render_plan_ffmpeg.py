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
import shutil
import subprocess
import uuid
import wave
from collections.abc import Mapping
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ... import rich
from ..application.ports import RenderSpec
from ..application.render_compiler import CompiledRender, compile_render_plan
from ..domain.asset_resolver import IMAGE_CODECS, AssetDescriptor
from ..domain.contracts import VideoFormat
from ..domain.render import LEAD, SIZE, TAIL
from ..domain.render_plan import AssetReference, Motion, StyleSnapshot
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
                 motions: Mapping[str, Motion] | None = None, timeout_floor: int = 300, runner=None):
        self.model = model
        self.cycle = tuple(KEN_BURNS_CYCLE if cycle is None else cycle)
        self.motions = dict(motions or {})
        self.timeout_floor = timeout_floor
        self._run = runner or _run

    def render(self, spec: RenderSpec, out_path: Path) -> Path:
        return self.execute(self.compile_spec(spec), spec.speech_wavs, Path(out_path))

    def compile_spec(self, spec: RenderSpec) -> CompiledRender:
        """Reconstrói o plano do ``RenderSpec`` e o compila (puro) — sem tocar FFmpeg.

        Separado de ``execute`` para que o grafo/comando possa ser validado por unidade,
        sem renderizar nada (o compilador em si continua em ``application``).
        """
        work = Path(spec.work_dir or ".")
        plan = self._build_plan(spec)
        descriptors = self._descriptors(plan, spec)
        labels = {scene.id: scene.label for scene in spec.scenes}
        return compile_render_plan(plan=plan, assets=descriptors, work_dir=str(work), labels=labels)

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

    def execute(self, compiled: CompiledRender, speech_wavs, out_path: Path) -> Path:
        """Materializa overlays, monta áudio, roda FFmpeg e publica de forma atômica."""
        Path(compiled.final_output).parent.mkdir(parents=True, exist_ok=True)
        fmt = VideoFormat(compiled.format)
        self._materialize(compiled, fmt)
        narration_inputs = self._narration_inputs(compiled, speech_wavs)
        rich.build_narration_track(narration_inputs, Path(compiled.audio.narration.output))
        self._write_music(compiled)
        total_seconds = compiled.total_ticks / compiled.ticks_per_second
        timeout = int(self.timeout_floor + 3 * total_seconds)
        for shot in compiled.shots:
            self._run(list(shot.args), timeout)
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

    def _narration_inputs(self, compiled: CompiledRender, speech_wavs) -> list[Path]:
        voices = compiled.audio.narration.voices
        wavs = list(speech_wavs)
        if len(wavs) != len(voices):
            raise RuntimeError(f"narration has {len(voices)} scenes but {len(wavs)} speech files")
        lengths = self._scene_seconds(compiled)
        inputs: list[Path] = []
        for voice, speech in zip(voices, wavs):
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
