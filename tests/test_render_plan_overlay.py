"""VE-02 — compositor FFmpeg do overlay de imagem (grafo puro + render real).

Prova, sem e com FFmpeg:

- (a) plano **sem** overlay continua idêntico ao de antes (grafo e ``args`` exatos);
- (b) o overlay entra como entrada extra e só é composto na janela
  ``[start, start+duration)`` relativa ao segmento base;
- (c) áudio e duração não mudam (o overlay é só visual);
- (d) o plano compilado é determinístico (mesmo digest, ordem embutida);
- (e) plano inválido falha antes de qualquer chamada ao FFmpeg.

Os testes de render real rodam só no container (``scripts/test-container.sh``); sem
``ffmpeg``/``ffprobe`` são pulados. Nada aqui toca a suíte completa nem o host.
"""
import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.render_plan_compiler import compile_render_plan  # noqa: E402
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer  # noqa: E402
from app.studio.application.ports import OverlayLayer, RenderSpec  # noqa: E402
from app.studio.application.render_compiler import CompileError  # noqa: E402
from app.studio.domain.asset_resolver import AssetDescriptor  # noqa: E402
from app.studio.domain.contracts import Asset, AssetKind, Scene, VideoFormat  # noqa: E402
from app.studio.domain.render import SIZE, make_cues, scene_length  # noqa: E402
from app.studio.domain.render_plan import Composition, Shot, StyleSnapshot, Track  # noqa: E402
from app.studio.domain.render_plan_builder import (  # noqa: E402
    PlanBuildError,
    StoryboardOverlay,
    StoryboardScene,
    asset_reference_for,
    build_render_plan,
)

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
SHA_A = "a" * 64
SHA_B = "b" * 64
SCENE_ID = "scene-01"


# ------------------------------------------------------------------ helpers de plano


def image_ref(asset_id: str = "asset-01", *, sha: str = SHA_A):
    return asset_reference_for(
        Asset(id=asset_id, kind=AssetKind.image, cache_key="c" * 64, path=f"img/{asset_id}.png",
              provider="p", model="m", license="Imagem gerada por IA"),
        content_sha256=sha, media_type="image",
    )


def descriptor_for(asset_id: str = "asset-01", *, sha: str = SHA_A, **overrides):
    data = dict(
        asset_id=asset_id, asset_version=1, uri=f"img/{asset_id}.png",
        content_sha256=sha, media_type="image", license="Imagem gerada por IA",
        location=f"/storage/{asset_id}.png", available=True, codec="png",
        width=1080, height=1920,
    )
    data.update(overrides)
    return AssetDescriptor(**data)


def silent_scene(scene_id: str):
    return StoryboardScene(scene_id=scene_id, asset_id="asset-01", narration="Cena sem fala.", speech_seconds=0.0)


def plan_with_overlay(*, overlays=None, speech_seconds: float = 2.0, scenes=None):
    return build_render_plan(
        plan_id="plan-overlay", revision=1, project_id="p", video_id="v", format=VideoFormat.short,
        scenes=scenes or [StoryboardScene(scene_id=SCENE_ID, asset_id="asset-01",
                                          narration="Primeira cena do vídeo.", speech_seconds=speech_seconds)],
        assets=[image_ref("asset-01"), image_ref("asset-overlay", sha=SHA_B)],
        style_snapshot=StyleSnapshot(style_id="s", version=1),
        overlays=overlays if overlays is not None else [
            StoryboardOverlay(scene_id=SCENE_ID, asset_id="asset-overlay", start_s=0.1, duration_s=0.2)
        ],
    )


def compile_plan(plan):
    assets = {a.asset_id: descriptor_for(a.asset_id, sha=a.content_sha256) for a in plan.asset_manifest}
    return compile_render_plan(plan=plan, assets=assets, work_dir="/work/job-1")


# ------------------------------------------------------------- (a) paridade sem overlay


def test_plan_without_overlay_keeps_the_exact_legacy_segment_command():
    """I13: sem camadas o grafo e os ``args`` são exatamente os de antes."""
    plan = plan_with_overlay(overlays=[], scenes=[
        silent_scene("scene-01"), silent_scene("scene-02"), silent_scene("scene-03")])
    shot = compile_plan(plan).shots[0]
    assert shot.overlays == ()
    assert "-loop" not in shot.args
    assert "force_original_aspect_ratio" not in shot.filter_complex
    assert shot.args.count("-i") == 2  # mídia + selo/disclosure; nenhuma entrada de overlay
    expected_graph = (
        "[0:v]scale=1620:2880:flags=lanczos,"
        "zoompan=z='1':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=20:s=1080x1920:fps=25,"
        "format=yuv420p[b0];[b0][1:v]overlay=0:0:format=auto[o1];"
        "[o1]fade=t=in:st=0:d=0.25,fade=t=out:st=0.550:d=0.25[v]"
    )
    assert shot.filter_complex == expected_graph
    assert list(shot.args) == [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", "/storage/asset-01.png", "-i", "/work/job-1/static_000.png",
        "-filter_complex", expected_graph,
        "-map", "[v]", "-frames:v", "20", "-r", "25",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "/work/job-1/scene_000.mp4",
    ]


# ---------------------------------------------------- (b) overlay só na janela (grafo)


def test_overlay_becomes_an_extra_input_and_is_enabled_only_in_its_window():
    shot = compile_plan(plan_with_overlay()).shots[0]
    assert len(shot.overlays) == 1
    layer = shot.overlays[0]
    assert (layer.start_ticks, layer.duration_ticks) == (2500, 5000)  # 0.1 s .. 0.3 s a 25k ticks/s
    assert layer.fit == "contain"

    assert shot.args.count("-i") == 3 + len(shot.captions)  # mídia + selo + legendas + uma camada
    assert shot.args[shot.args.index("-loop") + 1] == "1"
    assert "/storage/asset-overlay.png" in shot.args
    assert "[3:v]scale=" in shot.filter_complex  # a camada é a 4ª entrada (após as legendas)
    assert "force_original_aspect_ratio=decrease" in shot.filter_complex
    assert "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black@0" in shot.filter_complex
    assert "overlay=0:0:format=auto:enable='gte(t,0.100)*lt(t,0.300)'" in shot.filter_complex

    # empilhamento declarado: base -> overlay -> selo/disclosure -> legendas -> fade
    graph = shot.filter_complex
    assert graph.index("force_original_aspect_ratio") < graph.index("[1:v]")
    assert graph.index("[1:v]") < graph.index("fade=t=in")
    assert graph.rstrip().endswith("[v]")


def test_overlay_cover_fills_the_frame_and_crops_instead_of_padding():
    plan = plan_with_overlay(overlays=[StoryboardOverlay(
        scene_id=SCENE_ID, asset_id="asset-overlay", start_s=0.0, duration_s=0.2, fit="cover")])
    graph = compile_plan(plan).shots[0].filter_complex
    assert "force_original_aspect_ratio=increase" in graph
    assert "crop=1080:1920" in graph
    assert "pad=" not in graph
    assert "enable='gte(t,0.000)*lt(t,0.200)'" in graph


# --------------------------------------------------------- (c) áudio/duração preservados


def test_overlay_does_not_change_the_segment_frame_count_or_the_concat_manifest():
    with_overlay = compile_plan(plan_with_overlay())
    without_overlay = compile_plan(plan_with_overlay(overlays=[]))
    assert with_overlay.shots[0].frames == without_overlay.shots[0].frames
    assert with_overlay.shots[0].duration_ticks == without_overlay.shots[0].duration_ticks
    # o overlay não vira segmento: a montagem só conhece o segmento base
    assert [s["shot_id"] for s in with_overlay.to_dict()["shots"]] == ["shot:scene-01"]
    assert with_overlay.concat.output == without_overlay.concat.output
    # a mixagem de áudio é a mesma (o overlay é só visual)
    assert with_overlay.audio.filter_complex == without_overlay.audio.filter_complex
    assert with_overlay.audio.args == without_overlay.audio.args


# ------------------------------------------------------------------ (d) determinismo


def test_overlay_compilation_is_deterministic_and_ignores_shot_order():
    plan = plan_with_overlay()
    first, second = compile_plan(plan), compile_plan(plan)
    assert first.digest() == second.digest()
    assert first.shots[0].filter_complex == second.shots[0].filter_complex
    assert first.shots[0].args == second.shots[0].args
    scene = plan.timeline.scenes[0]
    shuffled = plan.model_copy(update={"timeline": plan.timeline.model_copy(update={
        "scenes": [scene.model_copy(update={"shots": list(reversed(scene.shots))})]})})
    assert compile_plan(shuffled).digest() == first.digest()


# --------------------------------------------------------------- (e) plano inválido


def test_overlay_outside_its_scene_is_refused_by_the_builder():
    with pytest.raises(PlanBuildError, match="outside"):
        plan_with_overlay(overlays=[StoryboardOverlay(
            scene_id=SCENE_ID, asset_id="asset-overlay", start_s=0.5, duration_s=5.0)])


def test_overlay_crossing_a_base_boundary_is_refused_before_ffmpeg():
    base = plan_with_overlay(overlays=[])
    scene = base.timeline.scenes[0]
    total = scene.duration_ticks
    half = total // 2
    shots = [
        Shot(shot_id="base:0", track_id="visual-main", start_tick=0, duration_ticks=half,
             asset_ref="asset-01", role="base", z_index=0),
        Shot(shot_id="base:1", track_id="visual-main", start_tick=half, duration_ticks=total - half,
             asset_ref="asset-01", role="base", z_index=0),
        Shot(shot_id="overlay:0", track_id="visual-overlay", start_tick=half // 2, duration_ticks=half,
             asset_ref="asset-overlay", role="overlay", z_index=1, composition=Composition(fit="contain")),
    ]
    tracks = [Track(track_id="visual-main", kind="visual"), Track(track_id="visual-overlay", kind="visual")]
    timeline = base.timeline.model_copy(update={"tracks": tracks, "scenes": [scene.model_copy(update={"shots": shots})]})
    crossing = base.model_copy(update={"timeline": timeline})
    with pytest.raises(CompileError, match="boundary|host|base segment"):
        compile_plan(crossing)


# ------------------------------------------------- (b/c) render real no container


def tone_wav(path: Path, seconds: float = 1.0, amplitude: float = 0.4, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(32767 * amplitude * math.sin(2 * math.pi * 220 * i / rate))) for i in range(n)))


def _frame(video: Path, t: float) -> Image.Image:
    frame = video.with_name(f"frame_{t:.2f}.png")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-ss", f"{t}", "-frames:v", "1", str(frame)],
        check=True,
    )
    with Image.open(frame) as img:
        return img.convert("RGB").copy()


def _center_rgb(video: Path, t: float) -> tuple[int, int, int]:
    img = _frame(video, t)
    return img.getpixel((img.width // 2, img.height // 2))


def _format_duration(video: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(video)], text=True)
    return float(out.strip())


def _has_audio_stream(video: Path) -> bool:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(video)], text=True)
    return out.strip() == "audio"


def _render_layer(tmp_path, *, base: Path, overlay: Path, fit: str):
    fmt = VideoFormat.short
    speech = tmp_path / "s.wav"
    tone_wav(speech, seconds=1.2)
    length = scene_length(1.2)
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    scene = Scene(id=SCENE_ID, video_id="v" * 32, idx=0, narration="Narração curta.",
                  image_prompt="prompt de imagem válido", claim_ids=["c"], asset_id="asset-base")
    spec = RenderSpec(
        scenes=[scene], images=[base], speech_wavs=[speech], scene_seconds=[length],
        cues=make_cues(scene.narration, 0.0, 1.2), format=fmt, music=False, work_dir=work,
        layers=(OverlayLayer(scene_id=SCENE_ID, asset_id="asset-overlay", image=overlay,
                             license="CC0", start_s=0.2, duration_s=0.4, fit=fit),),
    )
    return PlanFfmpegRenderer().render(spec, tmp_path / "final.mp4"), length


@needs_ffmpeg
def test_real_render_draws_the_overlay_only_inside_its_window_and_keeps_audio_and_duration(tmp_path):
    base = tmp_path / "base.png"
    Image.new("RGB", SIZE[VideoFormat.short], (10, 10, 10)).save(base)
    overlay = tmp_path / "overlay.png"
    Image.new("RGB", SIZE[VideoFormat.short], (220, 30, 30)).save(overlay)
    out, length = _render_layer(tmp_path, base=base, overlay=overlay, fit="cover")

    # janela [0.2, 0.6): fora dela o quadro segue escuro; dentro, o overlay é vermelho
    assert _center_rgb(out, 0.05)[0] < 60
    assert _center_rgb(out, 0.40)[0] > 150
    assert _center_rgb(out, 0.80)[0] < 60

    assert abs(_format_duration(out) - length) <= 1.0  # duração do vídeo preservada
    assert _has_audio_stream(out)                      # a mixagem de áudio continua lá


@needs_ffmpeg
def test_real_render_contain_letterboxes_with_transparent_padding(tmp_path):
    base = tmp_path / "base.png"
    Image.new("RGB", SIZE[VideoFormat.short], (0, 200, 0)).save(base)  # base verde
    overlay = tmp_path / "overlay.png"
    Image.new("RGB", (540, 540), (220, 30, 30)).save(overlay)          # quadrado vermelho
    out, _ = _render_layer(tmp_path, base=base, overlay=overlay, fit="contain")

    assert _center_rgb(out, 0.40)[0] > 150            # centro: overlay vermelho
    top = _frame(out, 0.40).getpixel((540, 240))      # acima do quadrado: padding
    assert top[1] > 120 and top[0] < 80               # a base verde aparece (padding transparente)
