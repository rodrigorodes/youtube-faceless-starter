"""Executor FFmpeg do Render Plan (RP-024..RP-026) — o único lugar com ``subprocess``.

Consome o ``CompiledRender`` do compilador FFmpeg (``adapters/render_plan_compiler.py``,
RP-023): materializa os overlays (selo/disclosure/legendas com **Pillow**), sintetiza a
trilha de música, monta a faixa de narração, roda um ``ffmpeg`` por shot, concatena sem
reencode e mixa com *ducking* + ``loudnorm`` — o mesmo grafo que o renderer legado
produzia. O vídeo final é publicado de forma **atômica** (arquivo temporário +
``os.replace``), nunca deixando um ``.mp4`` parcial no destino.

Decisão §5.4 do design: o ``subprocess`` só mora aqui. A validação/estrutura neutra do
plano fica no ``application`` e a sintaxe FFmpeg no compilador do ``adapters`` — nada de
FFmpeg/PIL no ``domain``/``application`` (``tests/test_architecture.py``).

Rollout (§5.6/§11-R2, revisto): o **caminho baseado em plano é agora o único**. O
executor reconstrói o ``RenderPlan`` a partir do ``RenderSpec`` que o ``RunRender``
produz — é o único ponto onde o hash de conteúdo dos assets pode ser calculado (I/O de
leitura) sem contaminar o núcleo puro. O antigo renderer (``render_ffmpeg.py``, com
Ken Burns por ``index % 4``) foi removido depois de a paridade ser medida (§11-R6).

Paridade preservada: Ken Burns por modo **explícito** do plano (sem ``index % 4``),
selo (``label``), aviso de imagem sintética (``disclosure``), legenda queimada por trecho
com ``enable`` semiaberto, *ducking* da música sob a narração, ``loudnorm=I=-16``, fades
por segmento, 1080×1920 (short) e 1920×1080 (long) e timebase **25 fps**.

VE-02: o overlay de imagem é composto **dentro** do segmento base pelo compilador puro
(entrada extra + ``overlay`` com ``enable`` na janela relativa ao shot); o executor só
roda o comando — áudio, montagem e duração do vídeo não mudam.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
import wave
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from PIL import Image, ImageDraw, ImageFont

from ... import rich
from ..application.ports import RenderQaInputs, RenderSpec
from ..application.render_cache import PlanRegeneration
from ..domain.asset_resolver import IMAGE_CODECS, VIDEO_CODECS, AssetDescriptor
from ..domain.audio_catalog import AudioCatalog
from ..domain.audio_multitrack import MultitrackAudioPlan
from ..domain.contracts import VideoFormat
from ..domain.pacing import PacingPreset
from ..domain.render import LEAD, SIZE, TAIL
from ..domain.render_cache import CacheEntry, NodeId, PlanArtifact, plan_graph
from ..domain.render_engine import RenderProgress, RenderProgressStage, evaluate_preflight
from ..domain.render_plan import AssetReference, Motion, RenderPlan, StyleSnapshot
from ..domain.render_plan_builder import DEFAULT_MUSIC_PARAMS, StoryboardOverlay, StoryboardScene, build_render_plan
from ..domain.visual_style import ResolvedStyle
from .render_plan_compiler import CompiledRender, compile_multitrack_audio_args, compile_render_plan


class RenderCancelledError(RuntimeError):
    """Lançada quando o cancelamento cooperativo interrompe a execução entre segmentos."""


def _brief_render_hints(
    creative_brief: Mapping[str, object] | object | None,
) -> tuple[PacingPreset | None, tuple[Motion, ...] | None, dict[str, str | int | float | bool]]:
    """Traduz o CreativeBrief persistido em dicas determinísticas de plano (pacing/motion/music).

    Não altera a identidade congelada (`EffectiveConfig` / `config_snapshot`).
    """
    if creative_brief is None:
        return None, None, {}
    if isinstance(creative_brief, Mapping):
        raw_pacing = str(creative_brief.get("pacing") or "").strip().lower()
        raw_visual = str(creative_brief.get("visual_direction") or "").strip().lower()
        raw_tone = str(creative_brief.get("tone") or "").strip()
    else:
        raw_pacing = str(getattr(creative_brief, "pacing", "") or "").strip().lower()
        raw_visual = str(getattr(creative_brief, "visual_direction", "") or "").strip().lower()
        raw_tone = str(getattr(creative_brief, "tone", "") or "").strip()

    pacing_preset: PacingPreset | None = None
    motion_cycle: tuple[Motion, ...] | None = None
    music_hints: dict[str, str | int | float | bool] = {}

    if any(k in raw_pacing for k in ("dynamic", "fast", "dinâm", "dinam", "rápid", "rapid")):
        pacing_preset = PacingPreset.dynamic
        motion_cycle = ("zoom_in", "pan_right", "zoom_out", "pan_left")
        music_hints["bpm"] = 132
        music_hints["creative_brief_pacing"] = "dynamic"
    elif any(k in raw_pacing for k in ("cinematic", "slow", "cinemat", "lent", "calm")):
        pacing_preset = PacingPreset.cinematic
        motion_cycle = ("zoom_in", "zoom_out")
        music_hints["bpm"] = 106
        music_hints["creative_brief_pacing"] = "cinematic"
    elif any(k in raw_pacing for k in ("balanced", "moderate", "moderad", "equilibr")):
        pacing_preset = PacingPreset.balanced
        motion_cycle = ("zoom_in", "pan_right", "zoom_out")
        music_hints["bpm"] = 120
        music_hints["creative_brief_pacing"] = "balanced"

    if any(k in raw_visual for k in ("estátic", "estatic", "static", "sem movimento")):
        motion_cycle = ("none",)

    if raw_tone:
        music_hints["creative_brief_tone"] = raw_tone[:64]

    return pacing_preset, motion_cycle, music_hints

FONT, FONT_BOLD = rich.FONT, rich.FONT_BOLD
# Bundle neutro usado **apenas quando o vídeo não tem canal/estilo a referenciar** (RP-016):
# com um estilo resolvido a montante, o ``RenderSpec`` o carrega e ele é usado. Sem canal,
# ``studio-default@1`` é honesto — não há identidade real a apontar.
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

# Cores atuais do overlay (o default histórico). O estilo sobrepõe só estas três chaves; a
# sombra do texto e o disclosure continuam fixos — não há knob de estilo para eles (VS-04).
_DEFAULT_COLORS = {"caption_text": (255, 255, 255, 255), "caption_box": (0, 0, 0, 165), "accent": (255, 0, 140, 235)}
_HEX_COLOR = re.compile(r"^#([0-9A-Fa-f]{6})([0-9A-Fa-f]{2})?$")


def _rgba(color: str) -> tuple[int, int, int, int]:
    """``#RRGGBB``/``#RRGGBBAA`` → RGBA; sem alfa, 255 (opaco). Puro (sem Pillow)."""
    match = _HEX_COLOR.match(color)
    if match is None:  # o domínio já valida a forma; aqui é defesa em profundidade
        raise ValueError(f"invalid hex color: {color!r}")
    body, alpha = match.group(1), match.group(2)
    return tuple(int(body[i:i + 2], 16) for i in (0, 2, 4)) + (int(alpha, 16) if alpha else 255,)


_FONT_FAMILY_PATHS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "dejavu": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans",
    ),
    "roboto": (
        "/usr/share/fonts/truetype/roboto/unhinted/Roboto-Bold.ttf",
        "/usr/share/fonts/truetype/roboto/Roboto-Bold.ttf",
        "/usr/share/fonts/truetype/roboto/Roboto-Medium.ttf",
        "/Library/Fonts/Roboto-Bold.ttf",
        "Roboto-Bold.ttf",
        "Roboto-Bold",
        "Roboto",
    ),
    "georgia": (
        "/usr/share/fonts/truetype/msttcorefonts/georgiab.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Georgia_Bold.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "Georgia Bold",
        "Georgia",
    ),
    "inter": (
        "/usr/share/fonts/truetype/inter/Inter-Bold.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
        "/Library/Fonts/Inter-Bold.ttf",
        "Inter-Bold.ttf",
        "Inter-Bold",
        "Inter",
    ),
})


def _font_safe(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except (OSError, Exception):
        return ImageFont.load_default(size=size)


def resolve_caption_font(family: str | None, size: int) -> ImageFont.FreeTypeFont:
    """Carrega a fonte tipográfica da legenda com fallback gracioso para FONT_BOLD."""
    if family:
        candidates = _FONT_FAMILY_PATHS.get(str(family).strip().lower(), ())
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size)
            except (OSError, Exception):
                continue
    return _font_safe(FONT_BOLD, size)


def caption_layout(fmt: VideoFormat, style: ResolvedStyle | None = None) -> dict:
    """Geometria da legenda: o ``_LAYOUT`` atual como **default**, sobreposto pelo estilo.

    ``caption.position`` posiciona a legenda verticalmente (top, middle, bottom).
    ``caption.bottom`` sobrepõe o cálculo com um pixel exato.
    ``caption.font_size`` sobrepõe ``caption_font``. Sem estilo (ou sem ``caption``),
    devolve o layout de sempre — a paridade byte-a-byte do overlay depende disto. Puro: só
    aritmética de dicionário, testável sem FFmpeg/Pillow.
    """
    layout = dict(_LAYOUT[fmt])
    caption = style.caption if style is not None else {}
    if "position" in caption:
        pos = str(caption["position"]).strip().lower()
        w, h = SIZE[fmt]
        if pos in ("top", "topo"):
            layout["caption_bottom"] = 480 if fmt == VideoFormat.short else 300
            layout["position"] = "top"
        elif pos in ("middle", "meio"):
            layout["caption_bottom"] = (h // 2) + 120 if fmt == VideoFormat.short else (h // 2) + 80
            layout["position"] = "middle"
        else:
            layout["caption_bottom"] = _LAYOUT[fmt]["caption_bottom"]
            layout["position"] = "bottom"
    if "bottom" in caption:
        layout["caption_bottom"] = caption["bottom"]
    if "font_size" in caption:
        layout["caption_font"] = caption["font_size"]
    if "font_family" in caption:
        layout["font_family"] = caption["font_family"]
    if "style_kind" in caption:
        layout["style_kind"] = caption["style_kind"]
    return layout


def overlay_colors(style: ResolvedStyle | None = None) -> dict:
    """Cores do overlay: as atuais como **default**, sobrepostas pela ``palette`` do estilo.

    ``caption_text``/``caption_box``/``accent`` viram RGBA (ver ``_rgba``). Sem estilo (ou sem
    ``palette``), devolve as cores de sempre. Puro: sem Pillow, testável por unidade.
    """
    colors = dict(_DEFAULT_COLORS)
    palette = style.palette if style is not None else {}
    for key in colors:
        if key in palette:
            colors[key] = _rgba(palette[key])
    return colors


def _wrap(draw, text, font, max_width):
    return rich._wrap(draw, text, font, max_width)


def static_overlay(fmt: VideoFormat, label: str, disclosure: str, dst: Path,
                   style: ResolvedStyle | None = None) -> None:
    """PNG transparente com o aviso de imagem sintética e o selo do dia."""
    w, h = SIZE[fmt]
    colors = overlay_colors(style)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((60, 96), disclosure, font=_font_safe(FONT, 30), fill=(255, 255, 255, 190))
    if label:
        badge = _font_safe(FONT_BOLD, 46)
        box = draw.textbbox((0, 0), label, font=badge)
        bw, bh = box[2] - box[0], box[3] - box[1]
        draw.rounded_rectangle((60, 160, 60 + bw + 56, 160 + bh + 40), radius=26, fill=colors["accent"])
        draw.text((60 + 28, 160 + 14), label, font=badge, fill="white")
    img.save(dst)


def caption_overlay(fmt: VideoFormat, text: str, dst: Path, style: ResolvedStyle | None = None) -> None:
    """PNG transparente com um trecho de legenda queimada (geometria/cores do estilo)."""
    w, h = SIZE[fmt]
    lay = caption_layout(fmt, style)
    colors = overlay_colors(style)
    style_kind = lay.get("style_kind", "box")
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = resolve_caption_font(lay.get("font_family"), lay["caption_font"])
    lines = _wrap(draw, text, font, w - 2 * lay["caption_side"])[:4]
    height = len(lines) * lay["line_h"] + 64
    bottom = lay["caption_bottom"]
    top = bottom - height
    y = top + 32
    if style_kind == "box":
        draw.rounded_rectangle((lay["box_side"], top, w - lay["box_side"], bottom), radius=36, fill=colors["caption_box"])
        for line in lines:
            draw.text((lay["caption_side"] + 2, y + 2), line, font=font, fill=(0, 0, 0, 200))
            draw.text((lay["caption_side"], y), line, font=font, fill=colors["caption_text"])
            y += lay["line_h"]
    else:
        for line in lines:
            for dx, dy in ((-2, -2), (-2, 2), (2, -2), (2, 2), (0, 2), (0, -2), (2, 0), (-2, 0), (2, 2)):
                draw.text((lay["caption_side"] + dx, y + dy), line, font=font, fill=(0, 0, 0, 220))
            draw.text((lay["caption_side"], y), line, font=font, fill=colors["caption_text"])
            y += lay["line_h"]
    img.save(dst)


def text_card(fmt: VideoFormat, text: str, dst: Path) -> None:
    """Card local de um asset de texto (RP-021): fundo sólido + texto centralizado."""
    w, h = SIZE[fmt]
    img = Image.new("RGB", (w, h), (16, 18, 32))
    draw = ImageDraw.Draw(img)
    font = _font_safe(FONT_BOLD, 140 if fmt == VideoFormat.short else 120)
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


def _probe_video(path: Path, reference: AssetReference, tps: int = 25000) -> tuple[str, int, int, int]:
    meta = reference.metadata or {}
    codec = meta.get("codec")
    width = meta.get("width")
    height = meta.get("height")
    duration_ticks = meta.get("duration_ticks")

    if codec and width and height and duration_ticks:
        try:
            return str(codec).strip().lower(), int(width), int(height), int(duration_ticks)
        except (ValueError, TypeError):
            pass

    if shutil.which("ffprobe") and path.is_file() and path.stat().st_size > 0:
        try:
            res = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=codec_name,width,height:format=duration",
                    "-of", "json", str(path),
                ],
                capture_output=True, text=True, check=True, timeout=10
            )
            data = json.loads(res.stdout)
            streams = data.get("streams", [])
            stream = streams[0] if streams else {}
            c = (stream.get("codec_name") or codec or "h264").lower()
            if c == "avc1":
                c = "h264"
            w = int(stream.get("width") or width or 1080)
            h = int(stream.get("height") or height or 1920)
            dur_s = float(data.get("format", {}).get("duration") or stream.get("duration") or 1.0)
            d_ticks = int(duration_ticks) if duration_ticks else max(1, round(dur_s * tps))
            return c, w, h, d_ticks
        except Exception:
            pass

    c = str(codec or "h264").strip().lower()
    w = int(width or 1080)
    h = int(height or 1920)
    d_ticks = int(duration_ticks or tps)
    return c, w, h, d_ticks


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
        """Rota de produção: preflight, decide o reúso, executa só o que falta e registra os artefatos.

        Cada render é uma **revisão** nova do plano lógico (``revision + 1``): é isso que dá ao
        ``PlanRegeneration`` a revisão anterior para comparar por fingerprint. Sem repositório,
        a revisão é sempre 1 e nada é persistido (caminho de unidade).
        """
        plan = self._plan_for_render(spec)
        compiled, labels = self._compile(plan, spec)
        self._preflight(plan, spec, Path(out_path))
        reuse = self._reuse_hits(plan, labels)
        out = self.execute(
            compiled,
            spec.speech_wavs,
            Path(out_path),
            reuse=reuse,
            style=spec.style,
            multitrack=spec.multitrack,
            audio_catalog=spec.audio_catalog,
            cancel_check=spec.cancel_check,
            on_progress=spec.on_progress,
        )
        self._record(plan, compiled, labels, reuse, skip_final=spec.multitrack is not None)
        return out

    def _preflight(self, plan: RenderPlan, spec: RenderSpec, out_path: Path) -> None:
        """Preflight real de assets + espaço em disco antes de acionar FFmpeg (REC-03.03b)."""
        if spec.on_progress is not None:
            spec.on_progress(RenderProgress(
                stage=RenderProgressStage.PREFLIGHT,
                completed_segments=0,
                total_segments=len(plan.timeline.scenes),
                percent=0.0,
                message="validating render plan and disk space",
            ))
        available_ids = [
            ref.asset_id for ref in plan.asset_manifest
            if ref.uri and Path(ref.uri).is_file()
        ]
        probe_dir = Path(spec.work_dir) if spec.work_dir is not None else out_path.parent
        probe_dir.mkdir(parents=True, exist_ok=True)
        disk_free_mb = shutil.disk_usage(probe_dir).free / (1024 * 1024)
        report = evaluate_preflight(
            plan,
            available_asset_keys=available_ids,
            disk_free_mb=disk_free_mb,
            required_free_mb=20.0,
        )
        if not report.is_valid:
            raise RuntimeError("render preflight failed: " + "; ".join(report.errors))

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
        sem renderizar nada (o compilador FFmpeg mora no ``adapters`` e é puro).
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
                reuse: Mapping[NodeId, Path], *, skip_final: bool = False) -> None:
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
            if skip_final and item.node == NodeId("final", "video"):
                continue
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
                row_media_type = "video" if path.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv") else "image"
                manifest_by_id[row.asset_id] = AssetReference(
                    asset_id=row.asset_id,
                    asset_version=1,
                    uri=path.as_posix(),
                    content_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    media_type=row_media_type,
                    license=GENERATED_LICENSE,
                )
            base_assets = [sa for sa in (getattr(row, "assets", None) or ()) if sa.role == "base"]
            scenes.append(StoryboardScene(
                scene_id=row.id,
                asset_id=row.asset_id,
                narration=row.narration,
                speech_seconds=max(0.0, float(length) - LEAD - TAIL),
                label=row.label,
                voice_id=spec.voice_id,
                asset_trim_start_s=float(base_assets[0].start_s) if base_assets else None,
                asset_trim_end_s=float(base_assets[0].end_s) if base_assets else None,
            ))
        manifest = list(manifest_by_id.values())
        # VE-01: camadas de imagem por cena. A licença é obrigatória (I16) e o asset entra no
        # manifesto com hash do arquivo e ``media_type="image"``; o builder valida a janela.
        overlays: list[StoryboardOverlay] = []
        for layer in spec.layers:
            if not str(layer.license).strip():
                raise RuntimeError(f"overlay layer {layer.asset_id!r} has no license")
            layer_path = Path(layer.image)
            if layer.asset_id not in manifest_by_id:
                layer_media_type = "video" if layer_path.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv") else "image"
                manifest_by_id[layer.asset_id] = AssetReference(
                    asset_id=layer.asset_id,
                    asset_version=1,
                    uri=layer_path.as_posix(),
                    content_sha256=hashlib.sha256(layer_path.read_bytes()).hexdigest(),
                    media_type=layer_media_type,
                    license=layer.license,
                )
            asset_paths.setdefault(layer.asset_id, layer_path)
            overlays.append(StoryboardOverlay(
                scene_id=layer.scene_id,
                asset_id=layer.asset_id,
                start_s=layer.start_s,
                duration_s=layer.duration_s,
                z_index=layer.z_index,
                fit=layer.fit,
                opacity=layer.opacity,
                scale=layer.scale,
                position_x=layer.position_x,
                position_y=layer.position_y,
            ))
        manifest = list(manifest_by_id.values())
        # VS-03 + REC-03.03a: estilo explícito vence; quando não declarado no estilo, o CreativeBrief
        # orienta pacing, ciclo de movimento e parâmetros musicais preservando config_snapshot congelado.
        brief_pacing, brief_motion, brief_music = _brief_render_hints(spec.creative_brief)
        if spec.style is not None and spec.style.motion:
            cycle = spec.style.motion
        elif brief_motion is not None:
            cycle = brief_motion
        else:
            cycle = self.cycle
        music_params: dict | None = None
        if spec.style is not None and spec.style.music:
            music_params = dict(spec.style.music)
            if brief_music:
                for k, v in brief_music.items():
                    music_params.setdefault(k, v)
        elif brief_music:
            music_params = {**DEFAULT_MUSIC_PARAMS, **brief_music}
        return build_render_plan(
            plan_id=f"plan:{video_id}",
            revision=1,
            project_id=video_id,
            video_id=video_id,
            format=spec.format,
            scenes=scenes,
            assets=manifest,
            style_snapshot=(spec.style.snapshot if spec.style is not None else None)
            or StyleSnapshot(style_id=DEFAULT_STYLE_ID, version=DEFAULT_STYLE_VERSION),
            disclosure=spec.disclosure,
            music=spec.music,
            motions=self._motions([row.id for row in rows], cycle),
            music_params=music_params,
            config_snapshot=spec.config_snapshot,
            overlays=overlays,
            pacing_preset=brief_pacing,
        )

    def _motions(self, scene_ids: list[str], cycle: tuple[Motion, ...] | None = None) -> dict[str, Motion]:
        """Movimento declarado por cena: o ciclo por posição, sobreposto por ``motions``.

        ``cycle`` é o ciclo efetivo (o do estilo, quando ele declara motion); ``None`` mantém
        o ciclo da instância (``self.cycle``). O ``motions`` por ``scene_id`` continua vencendo.
        """
        chosen_cycle = self.cycle if cycle is None else cycle
        known = set(scene_ids)
        chosen: dict[str, Motion] = {}
        for index, scene_id in enumerate(scene_ids):
            chosen[scene_id] = chosen_cycle[index % len(chosen_cycle)] if chosen_cycle else "none"
        chosen.update({scene_id: motion for scene_id, motion in self.motions.items() if scene_id in known})
        return chosen

    def _descriptors(self, plan, spec: RenderSpec) -> dict[str, AssetDescriptor]:
        by_asset: dict[str, Path] = {}
        for row, image in zip(spec.scenes, spec.images):
            by_asset.setdefault(row.asset_id, Path(image))  # mesmo asset serve várias cenas
        for layer in spec.layers:  # VE-01: o asset do overlay também precisa de descriptor
            by_asset.setdefault(layer.asset_id, Path(layer.image))
        descriptors: dict[str, AssetDescriptor] = {}
        tps = plan.timeline.ticks_per_second if hasattr(plan, "timeline") else 25000
        for reference in plan.asset_manifest:
            path = by_asset[reference.asset_id]
            is_video = (
                path.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")
                or reference.media_type == "video"
                or (reference.metadata and reference.metadata.get("media_type") == "video")
            )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if is_video:
                codec, width, height, duration_ticks = _probe_video(path, reference, tps)
                descriptors[reference.asset_id] = AssetDescriptor(
                    asset_id=reference.asset_id,
                    asset_version=reference.asset_version,
                    uri=reference.uri,
                    content_sha256=digest,
                    media_type="video",
                    license=reference.license,
                    location=path.as_posix(),
                    available=True,
                    codec=codec,
                    width=width,
                    height=height,
                    duration_ticks=duration_ticks,
                    byte_size=path.stat().st_size,
                )
            else:
                codec, width, height = _probe_image(path, reference.asset_id)
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
                reuse: Mapping[NodeId, Path] | None = None,
                style: ResolvedStyle | None = None,
                multitrack: MultitrackAudioPlan | None = None,
                audio_catalog: AudioCatalog | None = None,
                cancel_check=None,
                on_progress=None) -> Path:
        """Materializa overlays, monta áudio, roda FFmpeg e publica de forma atômica.

        ``reuse`` mapeia nó lógico → artefato físico já existente (RP-06b). Um shot/narração/
        montagem em ``reuse`` **não** roda FFmpeg: o artefato é copiado para o caminho que o
        plano espera. ``concat``/``final`` continuam sendo recomputados quando qualquer cena
        mudou (a dependência os invalida); só quando **nada** mudou o MP4 final vem do cache.

        ``style`` (VS-04) entra só na materialização dos overlays: legenda (geometria) e selo
        (cor). ``None`` = sem estilo resolvido ⇒ layout/cores default de sempre.
        """
        def _emit(stage: RenderProgressStage, done: int, total: int, pct: float, msg: str) -> None:
            if on_progress is not None:
                on_progress(RenderProgress(
                    stage=stage, completed_segments=done, total_segments=total,
                    percent=round(pct, 1), message=msg,
                ))

        def _check_cancel(done: int, total: int) -> None:
            if cancel_check is not None and cancel_check():
                _emit(RenderProgressStage.CANCELLED, done, total, (done / max(1, total)) * 100.0,
                      "render cancelled cooperatively")
                raise RenderCancelledError("render was cancelled cooperatively between segments")

        # VE-02: as camadas de imagem já vêm no ``filter_complex``/``args`` de cada segmento
        # base (compilador puro); o executor só roda o comando. Áudio, concat e duração do
        # vídeo não mudam — o overlay é só visual.
        reuse = reuse or {}
        total_shots = len(compiled.shots)
        _check_cancel(0, total_shots)
        final_node = NodeId("final", "video")
        if final_node in reuse and multitrack is None:  # nada mudou: o MP4 final já existe como artefato físico
            published = self._publish(Path(reuse[final_node]), Path(out_path))
            _emit(RenderProgressStage.COMPLETED, total_shots, total_shots, 100.0, "reused final artifact from cache")
            return published
        mt_args: tuple[str, ...] | None = None
        if multitrack is not None:
            video_codec_args: tuple[str, ...] = ("-c:v", "copy")
            if compiled.subtitles_ass_path:
                escaped_sub_path = (
                    compiled.subtitles_ass_path.replace("\\", "\\\\")
                    .replace("'", "'\\''")
                    .replace(":", "\\:")
                )
                video_codec_args = (
                    "-vf", f"subtitles='{escaped_sub_path}'",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                )
            mt_args = compile_multitrack_audio_args(
                multitrack=multitrack,
                audio_catalog=audio_catalog or AudioCatalog(),
                video_input=compiled.concat.output,
                narration_input=compiled.audio.narration.output,
                output_path=compiled.final_output,
                video_codec_args=video_codec_args,
            )
        Path(compiled.final_output).parent.mkdir(parents=True, exist_ok=True)
        if compiled.subtitles_ass_content and compiled.subtitles_ass_path:
            sub_path = Path(compiled.subtitles_ass_path)
            sub_path.parent.mkdir(parents=True, exist_ok=True)
            sub_path.write_text(compiled.subtitles_ass_content, encoding="utf-8")
        fmt = VideoFormat(compiled.format)
        self._materialize(compiled, fmt, style)
        narration_inputs = self._narration_inputs(compiled, speech_wavs, reuse)
        rich.build_narration_track(narration_inputs, Path(compiled.audio.narration.output))
        if mt_args is None:
            music_node = NodeId("music", compiled.audio.music.source_id)
            if music_node in reuse:  # trilha inalterada: o WAV vem do cache
                shutil.copyfile(reuse[music_node], Path(compiled.audio.music_path))
            else:
                self._write_music(compiled)
        total_seconds = compiled.total_ticks / compiled.ticks_per_second
        timeout = int(self.timeout_floor + 3 * total_seconds)
        for idx, shot in enumerate(compiled.shots):
            _check_cancel(idx, total_shots)
            cached = reuse.get(NodeId("visual", shot.shot_id))
            if cached is not None:  # cena não impactada: segmento de vídeo vem do cache
                Path(shot.output).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(cached, shot.output)
                msg = f"reused cached shot {shot.shot_id}"
            else:
                self._run(list(shot.args), timeout)
                msg = f"rendered shot {shot.shot_id}"
            done = idx + 1
            _emit(RenderProgressStage.RENDERING_SEGMENTS, done, total_shots,
                  (done / max(1, total_shots)) * 75.0, msg)
        _check_cancel(total_shots, total_shots)
        _emit(RenderProgressStage.CONCATENATING, total_shots, total_shots, 80.0, "concatenating segments")
        if NodeId("concat", "video") in reuse:
            shutil.copyfile(reuse[NodeId("concat", "video")], compiled.concat.output)
        else:
            Path(compiled.concat.manifest_path).write_text(
                "".join(f"file '{Path(shot.output).as_posix()}'\n" for shot in compiled.shots), encoding="utf-8")
            self._run(list(compiled.concat.args), timeout)
        _check_cancel(total_shots, total_shots)
        _emit(RenderProgressStage.MIXING_AUDIO, total_shots, total_shots, 90.0, "mixing final audio")
        self._run(list(mt_args if mt_args is not None else compiled.audio.args), timeout)
        published = self._publish(Path(compiled.final_output), Path(out_path))
        _emit(RenderProgressStage.COMPLETED, total_shots, total_shots, 100.0, "render complete")
        return published

    def _materialize(self, compiled: CompiledRender, fmt: VideoFormat,
                     style: ResolvedStyle | None = None) -> None:
        for shot in compiled.shots:
            static_overlay(fmt, shot.static_overlay.label, shot.static_overlay.disclosure,
                           Path(shot.static_overlay.path), style)
            for caption in shot.captions:
                caption_overlay(fmt, caption.text, Path(caption.path), style)
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
        path.parent.mkdir(parents=True, exist_ok=True)
        if music.silent:  # `music=False` mantém o grafo de mixagem com a trilha muda (C2)
            _write_silence(path, seconds)
        else:
            music_file = music.params.get("music_file")
            if music_file and Path(music_file).is_file():
                self._run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-stream_loop", "-1", "-i", str(music_file),
                    "-t", f"{seconds:.3f}", "-ar", "44100", "-ac", "2", str(path),
                ])
            else:
                # bpm/seed vêm do plano (canônico em DEFAULT_MUSIC_PARAMS); o fallback é o mesmo objeto
                params = music.params
                rich.synth_music(seconds, path,
                                 bpm=int(params.get("bpm", DEFAULT_MUSIC_PARAMS["bpm"])),
                                 seed=int(params.get("seed", DEFAULT_MUSIC_PARAMS["seed"])))

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
