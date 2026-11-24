import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.render_plan_compiler import compile_render_plan  # noqa: E402
from app.studio.domain.asset_resolver import AssetDescriptor  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.pacing import PacingPreset  # noqa: E402
from app.studio.domain.render_plan import (  # noqa: E402
    AssetReference,
    AudioMix,
    RenderPlan,
    StyleSnapshot,
)
from app.studio.domain.render_plan_builder import (  # noqa: E402
    DEFAULT_TICKS_PER_SECOND,
    StoryboardScene,
    build_render_plan,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def asset_ref(asset_id="asset-01", **overrides):
    data = dict(
        asset_id=asset_id,
        asset_version=1,
        uri=f"storage/img/{asset_id}.png",
        content_sha256=SHA_A,
        media_type="image",
        license="Imagem gerada por IA",
    )
    data.update(overrides)
    return AssetReference(**data)


def descriptor(asset_id="asset-01", sha=SHA_A, **overrides):
    data = dict(
        asset_id=asset_id,
        asset_version=1,
        uri=f"storage/img/{asset_id}.png",
        content_sha256=sha,
        media_type="image",
        location=f"/storage/{asset_id}.png",
        available=True,
        codec="png",
        width=1080,
        height=1920,
        license="Imagem gerada por IA",
    )
    data.update(overrides)
    return AssetDescriptor(**data)


def story(scene_id="scene-01", asset_id="asset-01", speech=2.0, narration="Primeira cena do vídeo.", **overrides):
    data = dict(scene_id=scene_id, asset_id=asset_id, narration=narration, speech_seconds=speech)
    data.update(overrides)
    return StoryboardScene(**data)


def test_build_render_plan_with_pacing_splits_long_scene_with_alternating_motion():
    # 3.2s speech -> scene length = 4.0s (LEAD 0.3 + 3.2 + TAIL 0.5)
    # in dynamic (max 3.5s, target 2.5s) -> ceil(4.0/2.5) = 2 shots
    scene = story(scene_id="scene-01", speech=3.2)
    plan = build_render_plan(
        plan_id="plan-pacing-1",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
        pacing_preset="dynamic",
    )

    plan_scene = plan.timeline.scenes[0]
    assert len(plan_scene.shots) == 2
    assert plan_scene.shots[0].shot_id == "scene-01-shot-0"
    assert plan_scene.shots[1].shot_id == "scene-01-shot-1"
    assert plan_scene.shots[0].effects.motion == "zoom_in"
    assert plan_scene.shots[1].effects.motion == "zoom_out"
    assert plan_scene.shots[0].transition is not None
    assert plan_scene.shots[0].transition.kind == "cut"
    assert plan_scene.shots[0].role == "base"
    assert plan_scene.shots[1].role == "base"
    assert sum(s.duration_ticks for s in plan_scene.shots) == plan_scene.duration_ticks


def test_build_render_plan_with_pacing_preset_dynamic_splits_6s_scene():
    # 5.2s speech -> scene length = 6.0s (LEAD 0.3 + 5.2 + TAIL 0.5)
    # in dynamic -> 6.0s > 3.5s -> ceil(6.0/2.5) = 3 shots
    scene = story(scene_id="scene-01", speech=5.2)
    plan = build_render_plan(
        plan_id="plan-pacing-6s",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
        pacing_preset=PacingPreset.dynamic,
    )

    plan_scene = plan.timeline.scenes[0]
    assert len(plan_scene.shots) == 3
    assert [s.effects.motion for s in plan_scene.shots] == ["zoom_in", "zoom_out", "pan_left"]
    assert plan_scene.shots[0].transition.kind == "cut"
    assert plan_scene.shots[1].transition.kind == "cut"
    assert sum(s.duration_ticks for s in plan_scene.shots) == plan_scene.duration_ticks


def test_build_render_plan_with_pacing_preset_balanced_splits_6s_scene_into_2_shots():
    # 5.2s speech -> scene length = 6.0s (LEAD 0.3 + 5.2 + TAIL 0.5)
    # in balanced (max 5.0s, target 3.5s) -> 6.0s > 5.0s -> ceil(6.0/3.5) = 2 shots
    scene = story(scene_id="scene-01", speech=5.2)
    plan = build_render_plan(
        plan_id="plan-pacing-balanced-6s",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
        pacing_preset="balanced",
    )

    plan_scene = plan.timeline.scenes[0]
    assert len(plan_scene.shots) == 2
    assert [s.effects.motion for s in plan_scene.shots] == ["zoom_in", "zoom_out"]
    assert plan_scene.shots[0].transition.kind == "cut"
    assert sum(s.duration_ticks for s in plan_scene.shots) == plan_scene.duration_ticks


def test_build_render_plan_with_pacing_from_style():
    class FakeStyle:
        pacing = "dynamic"

    scene = story(scene_id="scene-01", speech=3.2)
    plan = build_render_plan(
        plan_id="plan-style-pacing",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
        style=FakeStyle(),
    )
    assert len(plan.timeline.scenes[0].shots) == 2


def test_build_render_plan_with_pacing_from_style_params_mapping():
    style = {"pacing": "balanced", "audio_mix": AudioMix(music_gain=0.15)}
    scene = story(scene_id="scene-01", speech=5.2)
    plan = build_render_plan(
        plan_id="plan-mapping-style",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
        style=style,
    )
    assert len(plan.timeline.scenes[0].shots) == 2
    assert plan.audio_mix.music_gain == 0.15


def test_build_render_plan_short_scene_keeps_single_shot_with_pacing():
    # 1.5s speech -> scene length = 2.32s (<= max 3.5s in dynamic) -> 1 shot
    scene = story(scene_id="scene-short", speech=1.5)
    plan = build_render_plan(
        plan_id="plan-short",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
        pacing_preset="dynamic",
    )
    plan_scene = plan.timeline.scenes[0]
    assert len(plan_scene.shots) == 1
    assert plan_scene.shots[0].effects.motion == "zoom_in"


def test_build_render_plan_video_asset_keeps_single_shot_in_moderate_duration():
    video_ref = AssetReference(
        asset_id="video-01",
        asset_version=1,
        uri="storage/video/clip-01.mp4",
        content_sha256=SHA_B,
        media_type="video",
        license="Video CC0",
    )
    # 4.0s scene -> in dynamic, static image would split, but video (<= 2 * max_s = 7.0s) stays 1 shot
    scene = story(scene_id="scene-video", asset_id="video-01", speech=3.2)
    plan = build_render_plan(
        plan_id="plan-video",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[video_ref],
        pacing_preset="dynamic",
    )
    plan_scene = plan.timeline.scenes[0]
    assert len(plan_scene.shots) == 1
    assert plan_scene.shots[0].effects.motion == "none"


def test_compile_render_plan_mix_filter_reflects_audio_mix(tmp_path):
    custom_mix = AudioMix(
        music_gain=0.22,
        ducking_threshold=0.04,
        ducking_ratio=8.0,
        loudnorm_i=-18.0,
        loudnorm_tp=-2.0,
        loudnorm_lra=9.0,
    )
    scene = story(scene_id="scene-01", speech=2.0)
    plan = build_render_plan(
        plan_id="plan-audio-check",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
        audio_mix=custom_mix,
    )
    work_dir = str(tmp_path / "job-audio")
    (tmp_path / "job-audio").mkdir(parents=True, exist_ok=True)
    compiled = compile_render_plan(
        plan=plan,
        assets={"asset-01": descriptor("asset-01")},
        work_dir=work_dir,
    )
    assert "volume=0.22" in compiled.audio.filter_complex
    assert "threshold=0.04:ratio=8" in compiled.audio.filter_complex
    assert "loudnorm=I=-18:TP=-2:LRA=9" in compiled.audio.filter_complex


def test_build_render_plan_preserves_custom_audio_mix():
    custom_mix = AudioMix(
        music_gain=0.25,
        ducking_threshold=0.03,
        ducking_ratio=15.0,
        afade_in_s=0.5,
        afade_out_s=0.75,
        loudnorm_i=-14.0,
        loudnorm_tp=-1.0,
        loudnorm_lra=10.0,
    )
    plan = build_render_plan(
        plan_id="plan-custom-audio",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[story()],
        assets=[asset_ref()],
        audio_mix=custom_mix,
    )
    assert plan.audio_mix == custom_mix
    assert plan.audio_mix.music_gain == 0.25
    assert plan.audio_mix.ducking_ratio == 15.0
    # round-trip check
    dumped = plan.model_dump_json()
    loaded = RenderPlan.model_validate_json(dumped)
    assert loaded.audio_mix == custom_mix


def test_compile_render_plan_populates_subtitles_ass(tmp_path):
    scene = story(scene_id="scene-01", speech=3.0, narration="Legendas sincronizadas no compilador v2.")
    plan = build_render_plan(
        plan_id="plan-subs-1",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
    )
    assert len(plan.timeline.subtitles) > 0

    work_dir = str(tmp_path / "job-subs")
    (tmp_path / "job-subs").mkdir(parents=True, exist_ok=True)

    compiled = compile_render_plan(
        plan=plan,
        assets={"asset-01": descriptor("asset-01")},
        work_dir=work_dir,
    )

    assert compiled.subtitles_ass_content is not None
    assert "[Script Info]" in compiled.subtitles_ass_content
    assert "[V4+ Styles]" in compiled.subtitles_ass_content
    assert "[Events]" in compiled.subtitles_ass_content
    assert "Dialogue:" in compiled.subtitles_ass_content
    assert "Legendas" in compiled.subtitles_ass_content

    assert compiled.subtitles_ass_path == f"{work_dir}/subtitles.ass"
    ass_file = Path(compiled.subtitles_ass_path)
    assert ass_file.exists()
    assert ass_file.read_text(encoding="utf-8") == compiled.subtitles_ass_content


def test_compile_render_plan_without_subtitles(tmp_path):
    # narration="" produces no subtitles, speech=2.0 satisfies min plan duration (2.0s)
    scene = story(scene_id="scene-silent", speech=2.0, narration="")
    plan = build_render_plan(
        plan_id="plan-silent",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
    )
    assert len(plan.timeline.subtitles) == 0

    work_dir = str(tmp_path / "job-silent")
    (tmp_path / "job-silent").mkdir(parents=True, exist_ok=True)

    compiled = compile_render_plan(
        plan=plan,
        assets={"asset-01": descriptor("asset-01")},
        work_dir=work_dir,
    )

    assert compiled.subtitles_ass_content is None
    assert compiled.subtitles_ass_path is None


def test_pacing_dynamic_with_narration_and_compile_render_plan_v2(tmp_path):
    # Cena com ~6s de fala e pacing_preset="dynamic" (divide a cena em múltiplos shots)
    scene = story(
        scene_id="scene-long-pacing",
        speech=6.0,
        narration="Esta é uma cena longa com seis segundos de fala narrada para testar a integração entre pacing e legendas.",
    )
    plan = build_render_plan(
        plan_id="plan-pacing-dynamic-narrated",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
        pacing_preset="dynamic",
    )

    # Verifica que o pacing dividiu a cena em múltiplos shots
    assert len(plan.timeline.scenes[0].shots) >= 3
    # Verifica que há legendas geradas na timeline
    assert len(plan.timeline.subtitles) > 0

    work_dir = str(tmp_path / "job-pacing-dynamic")
    (tmp_path / "job-pacing-dynamic").mkdir(parents=True, exist_ok=True)

    compiled = compile_render_plan(
        plan=plan,
        assets={"asset-01": descriptor("asset-01")},
        work_dir=work_dir,
    )

    # Confirma que compilou com sucesso sem colisão de legendas per-shot
    assert len(compiled.shots) == len(plan.timeline.scenes[0].shots)
    for shot in compiled.shots:
        assert len(shot.captions) == 0

    # Confirma que as legendas ASS foram geradas no nível global
    assert compiled.subtitles_ass_path is not None
    assert Path(compiled.subtitles_ass_path).exists()
    assert compiled.subtitles_ass_content is not None
    assert "Dialogue:" in compiled.subtitles_ass_content
    assert "pacing" in compiled.subtitles_ass_content
    assert "legendas" in compiled.subtitles_ass_content

