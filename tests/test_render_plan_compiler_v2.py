"""Testes focados do compilador FFmpeg v2 (Onda 1 - Fundação).

Cobre:
- Transição 'cut' produz corte seco (sem filtro fade) no filter_complex.
- Transição 'none' em schema_version >= 2 produz corte seco (sem filtro fade).
- Preservação do fade legado em schema_version == 1.
- Transição 'fade' aplica fade out configurado.
- Shot de vídeo com asset_offset_ticks compila trim com offset em segundos.
- AudioMix declarativo compila MIX_FILTER com ganho, ducking e loudnorm customizados.
- _descriptors no executor identifica arquivos de vídeo (.mp4, .mov, .webm, .mkv) como media_type='video'.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.render_plan_compiler import (
    _fade_filter,
    compile_render_plan,
)
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.application.render_compiler import CompileError
from app.studio.application.ports import RenderSpec
from app.studio.domain.asset_resolver import AssetDescriptor
from app.studio.domain.contracts import Asset, AssetKind, VideoFormat
from app.studio.domain.render import FADE_S
from app.studio.domain.render_plan import (
    AssetReference,
    AudioMix,
    RenderPlan,
    Shot,
    StyleSnapshot,
    Transition,
)
from app.studio.domain.render_plan_builder import (
    DEFAULT_TICKS_PER_SECOND,
    StoryboardScene,
    StoryboardShot,
    asset_reference_for,
    build_render_plan,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def image_ref(asset_id="asset-01", uri=None, sha=SHA_A):
    return asset_reference_for(
        Asset(
            id=asset_id,
            kind=AssetKind.image,
            cache_key="c" * 64,
            path=uri or f"img/{asset_id}.png",
            provider="p",
            model="m",
            license="Imagem gerada por IA",
        ),
        content_sha256=sha,
        media_type="image",
    )


def video_ref(asset_id="asset-video-01", uri=None, sha=SHA_B, duration_ticks=100000):
    return asset_reference_for(
        Asset(
            id=asset_id,
            kind=AssetKind.video,
            cache_key="v" * 64,
            path=uri or f"video/{asset_id}.mp4",
            provider="p",
            model="m",
            license="Vídeo gerado por IA",
        ),
        content_sha256=sha,
        media_type="video",
        metadata={"codec": "h264", "width": "1080", "height": "1920", "duration_ticks": str(duration_ticks)},
    )


def descriptor_for(asset_id="asset-01", uri=None, sha=SHA_A, media_type="image", **overrides):
    data = dict(
        asset_id=asset_id,
        asset_version=1,
        uri=uri or f"img/{asset_id}.png",
        content_sha256=sha,
        media_type=media_type,
        license="Imagem gerada por IA",
        location=f"/storage/{asset_id}.{'mp4' if media_type == 'video' else 'png'}",
        available=True,
        codec="h264" if media_type == "video" else "png",
        width=1080,
        height=1920,
    )
    if media_type == "video":
        data["duration_ticks"] = overrides.pop("duration_ticks", 100000)
    data.update(overrides)
    return AssetDescriptor(**data)


def plan_v2_with(scenes, assets=None, audio_mix=None, schema_version=2, **overrides):
    data = dict(
        plan_id="plan-v2-001",
        revision=1,
        project_id="project-001",
        video_id="video-001",
        format=VideoFormat.short,
        scenes=scenes,
        assets=assets or [image_ref()],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=3),
        builder_version="render-plan-builder/2",
    )
    data.update(overrides)
    plan = build_render_plan(**data)
    updates = {}
    if audio_mix is not None:
        updates["audio_mix"] = audio_mix
    if schema_version != plan.schema_version:
        updates["schema_version"] = schema_version
    if updates:
        plan = plan.model_copy(update=updates)
    return plan


def test_fade_filter_cut_returns_empty():
    assert _fade_filter(Transition(kind="cut"), 2.0, DEFAULT_TICKS_PER_SECOND, "shot-1") == ""


def test_fade_filter_none_in_v2_returns_empty():
    assert _fade_filter(Transition(kind="none"), 2.0, DEFAULT_TICKS_PER_SECOND, "shot-1", schema_version=2) == ""
    assert _fade_filter(None, 2.0, DEFAULT_TICKS_PER_SECOND, "shot-1", schema_version=2) == ""


def test_fade_filter_none_in_v1_preserves_legacy_fade():
    expected = f"fade=t=in:st=0:d={FADE_S},fade=t=out:st={2.0 - FADE_S:.3f}:d={FADE_S}"
    assert _fade_filter(Transition(kind="none"), 2.0, DEFAULT_TICKS_PER_SECOND, "shot-1", schema_version=1) == expected
    assert _fade_filter(None, 2.0, DEFAULT_TICKS_PER_SECOND, "shot-1", schema_version=1) == expected


def test_fade_filter_fade_applies_configured_fade_out():
    fade_trans = Transition(kind="fade", duration_ticks=2500)  # 0.1s em 25000 tps
    res = _fade_filter(fade_trans, 2.0, DEFAULT_TICKS_PER_SECOND, "shot-1")
    assert f"fade=t=in:st=0:d={FADE_S}" in res
    assert "fade=t=out:st=1.900:d=0.100" in res


def test_fade_filter_crossfade_raises_compile_error():
    trans = Transition(kind="crossfade", duration_ticks=2500)
    with pytest.raises(CompileError, match="transition kind 'crossfade' is not yet supported in the single-shot compiler"):
        _fade_filter(trans, 2.0, DEFAULT_TICKS_PER_SECOND, "shot-1")


def test_cut_transition_in_compiled_plan_produces_clean_cut_without_fade():
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com corte seco.",
        speech_seconds=2.0,
        shots=[StoryboardShot(shot_id="shot-01", asset_id="asset-01", duration_s=2.8, transition=Transition(kind="cut"))],
    )
    plan = plan_v2_with([scene], assets=[image_ref("asset-01")])
    assets = {"asset-01": descriptor_for("asset-01")}
    compiled = compile_render_plan(plan=plan, assets=assets, work_dir="/work/job-1")
    graph = compiled.shots[0].filter_complex
    assert "fade=" not in graph
    assert "format=yuv420p[v]" in graph


def test_none_transition_in_v2_plan_produces_no_fade():
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena sem transição em v2.",
        speech_seconds=2.0,
    )
    plan = plan_v2_with([scene], assets=[image_ref("asset-01")], schema_version=2)
    assets = {"asset-01": descriptor_for("asset-01")}
    compiled = compile_render_plan(plan=plan, assets=assets, work_dir="/work/job-1")
    graph = compiled.shots[0].filter_complex
    assert "fade=" not in graph
    assert "format=yuv420p[v]" in graph


def test_schema_version_1_preserves_legacy_fade_filter():
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena legado v1.",
        speech_seconds=2.0,
    )
    plan = plan_v2_with([scene], assets=[image_ref("asset-01")], schema_version=1)
    assets = {"asset-01": descriptor_for("asset-01")}
    compiled = compile_render_plan(plan=plan, assets=assets, work_dir="/work/job-1")
    graph = compiled.shots[0].filter_complex
    assert f"fade=t=in:st=0:d={FADE_S}" in graph
    assert f"fade=t=out:st={2.8 - FADE_S:.3f}:d={FADE_S}" in graph


def test_video_shot_with_offset_compiles_trim_filter():
    # 25000 ticks offset = 1.0s, duração = 2.8s
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-video-01",
        narration="Cena com vídeo e offset.",
        speech_seconds=2.0,
        shots=[StoryboardShot(shot_id="shot-01", asset_id="asset-video-01", duration_s=2.8, asset_offset_s=1.0)],
    )
    vref = video_ref("asset-video-01")
    plan = plan_v2_with([scene], assets=[vref])
    assets = {"asset-video-01": descriptor_for("asset-video-01", sha=SHA_B, media_type="video")}
    compiled = compile_render_plan(plan=plan, assets=assets, work_dir="/work/job-1")
    graph = compiled.shots[0].filter_complex
    assert "trim=start=1.000000:duration=2.800000" in graph
    assert "setpts=PTS-STARTPTS" in graph


def test_audio_mix_compilation_with_custom_parameters():
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com mixagem customizada.",
        speech_seconds=2.0,
    )
    custom_mix = AudioMix(
        music_gain=0.15,
        ducking_threshold=0.05,
        ducking_ratio=5.0,
        loudnorm_i=-14.0,
        loudnorm_tp=-2.0,
        loudnorm_lra=9.0,
    )
    plan = plan_v2_with([scene], assets=[image_ref("asset-01")], audio_mix=custom_mix)
    assets = {"asset-01": descriptor_for("asset-01")}
    compiled = compile_render_plan(plan=plan, assets=assets, work_dir="/work/job-1")
    audio = compiled.audio
    assert "volume=0.15" in audio.filter_complex
    assert "threshold=0.05" in audio.filter_complex
    assert "ratio=5" in audio.filter_complex
    assert "loudnorm=I=-14:TP=-2:LRA=9" in audio.filter_complex
    assert audio.filter_complex in audio.args


def test_descriptors_identifies_video_media_type_from_suffix_or_metadata(tmp_path):
    renderer = PlanFfmpegRenderer()

    # Prepara arquivos falsos
    img_path = tmp_path / "asset-image.png"
    from PIL import Image
    with Image.new("RGB", (1080, 1920), color="blue") as im:
        im.save(img_path)

    vid_path = tmp_path / "asset-clip.mp4"
    vid_path.write_bytes(b"dummy video content")

    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-clip",
        narration="Cena com vídeo.",
        speech_seconds=2.0,
    )
    vref = AssetReference(
        asset_id="asset-clip",
        asset_version=1,
        uri="asset-clip.mp4",
        content_sha256=hashlib.sha256(vid_path.read_bytes()).hexdigest(),
        media_type="video",
        license="CC0",
        metadata={"codec": "h264", "width": "1080", "height": "1920", "duration_ticks": "50000"},
    )
    iref = AssetReference(
        asset_id="asset-image",
        asset_version=1,
        uri="asset-image.png",
        content_sha256=hashlib.sha256(img_path.read_bytes()).hexdigest(),
        media_type="image",
        license="CC0",
    )
    plan = plan_v2_with([scene], assets=[vref, iref])

    class FakeSceneRow:
        def __init__(self, asset_id):
            self.asset_id = asset_id
            self.idx = 0
            self.id = "s-1"
            self.video_id = "v-1"
            self.narration = "n"
            self.label = ""

    spec = RenderSpec(
        scenes=[FakeSceneRow("asset-clip"), FakeSceneRow("asset-image")],
        images=[vid_path, img_path],
        speech_wavs=[],
        scene_seconds=[2.8, 2.8],
        cues=[],
        format=VideoFormat.short,
    )

    descriptors = renderer._descriptors(plan, spec)
    assert descriptors["asset-clip"].media_type == "video"
    assert descriptors["asset-image"].media_type == "image"
