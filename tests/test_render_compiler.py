"""RP-023 — compilador puro ``RenderPlan`` -> plano de execução FFmpeg (sem executar).

O compilador é determinístico e **não toca mídia**: recebe o plano e os assets já
resolvidos (RP-04) e devolve os comandos/graphs que o executor (RP-05) roda. Nada aqui
importa FFmpeg, ``subprocess``, PIL ou SDK de provedor — a guarda de arquitetura prova
por execução.

Paridade com o renderer legado (``adapters/render_ffmpeg.py``), que é a régua do §11:
Ken Burns (``zoompan``) por shot, selo/disclosure como overlay, legenda queimada por
trecho com ``enable``, fade in/out por segmento, concat sem reencode, mixagem com
ducking (``sidechaincompress``) e ``loudnorm`` -16.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.render_compiler import (  # noqa: E402
    CompileError,
    CompiledRender,
    compile_render_plan,
)
from app.studio.domain.asset_resolver import AssetDescriptor  # noqa: E402
from app.studio.domain.contracts import Asset, AssetKind, VideoFormat  # noqa: E402
from app.studio.domain.render import FADE_S, FPS  # noqa: E402
from app.studio.domain.render_plan import RenderPlan, StyleSnapshot  # noqa: E402
from app.studio.domain.render_plan_builder import (  # noqa: E402
    DEFAULT_TICKS_PER_SECOND,
    StoryboardScene,
    asset_reference_for,
    build_render_plan,
)
from app.studio.domain.ticks import ticks_to_seconds  # noqa: E402

SHA_A = "a" * 64
SHA_B = "b" * 64


def image_ref(asset_id="asset-01", uri=None, sha=SHA_A):
    return asset_reference_for(
        Asset(id=asset_id, kind=AssetKind.image, cache_key="c" * 64, path=uri or f"img/{asset_id}.png",
              provider="p", model="m", license="Imagem gerada por IA"),
        content_sha256=sha, media_type="image",
    )


def descriptor_for(asset_id="asset-01", uri=None, sha=SHA_A, media_type="image", **overrides):
    data = dict(
        asset_id=asset_id,
        asset_version=1,
        uri=uri or f"img/{asset_id}.png",
        content_sha256=sha,
        media_type=media_type,
        license="Imagem gerada por IA",
        location=f"/storage/{asset_id}.png",
        available=True,
        codec="png",
        width=1920,
        height=1080,
    )
    data.update(overrides)
    return AssetDescriptor(**data)


def plan_with(scenes, assets=None, **overrides):
    data = dict(
        plan_id="plan-001",
        revision=1,
        project_id="project-001",
        video_id="video-001",
        format=VideoFormat.short,
        scenes=scenes,
        assets=assets or [image_ref()],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=3),
        builder_version="render-plan-builder/1",
    )
    data.update(overrides)
    return build_render_plan(**data)


def simple_plan(**overrides):
    return plan_with([StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.", speech_seconds=2.0)], **overrides)


def compile_simple(plan=None, **overrides):
    plan = plan or simple_plan()
    assets = overrides.pop("assets", None)
    if assets is None:
        assets = {a.asset_id: descriptor_for(a.asset_id, a.uri, a.content_sha256) for a in plan.asset_manifest}
    data = dict(plan=plan, assets=assets, work_dir="/work/job-1")
    data.update(overrides)
    return compile_render_plan(**data)


def scene_filter(compiled, index=0):
    return compiled.shots[index].filter_complex


# ------------------------------------------------------------------ forma geral


def test_compiler_is_pure_and_deterministic():
    first, second = compile_simple(), compile_simple()
    assert first == second
    assert isinstance(first, CompiledRender)
    assert first.to_json() == second.to_json()
    assert first.digest() == second.digest()
    assert len(first.digest()) == 64
    # os caminhos são do plano de execução, não da mídia: o compilador não abriu nada
    assert not Path("/work/job-1").exists()


def test_compiled_plan_carries_the_output_timebase_and_duration():
    compiled = compile_simple()
    plan = simple_plan()
    assert compiled.plan_id == "plan-001" and compiled.revision == 1
    assert compiled.format == "short"
    assert (compiled.width, compiled.height) == (1080, 1920)
    assert compiled.ticks_per_second == DEFAULT_TICKS_PER_SECOND
    assert (compiled.fps_num, compiled.fps_den) == (FPS, 1)
    assert compiled.total_ticks == plan.timeline.duration_ticks
    assert compiled.to_dict()["total_ticks"] == plan.timeline.duration_ticks


def test_compiler_emits_one_segment_per_shot_in_timeline_order():
    plan = plan_with(
        [StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.", speech_seconds=2.0),
         StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration="Segunda cena do vídeo.", speech_seconds=3.0)],
        assets=[image_ref(), image_ref("asset-02", sha=SHA_B)],
    )
    compiled = compile_simple(plan, assets={
        "asset-01": descriptor_for("asset-01"),
        "asset-02": descriptor_for("asset-02", sha=SHA_B),
    })
    placements = [(s.scene_id, s.start_ticks, s.duration_ticks) for s in compiled.shots]
    scenes = sorted(plan.timeline.scenes, key=lambda s: s.start_tick)
    assert placements == [(s.scene_id, s.start_tick, s.duration_ticks) for s in scenes]
    # segmentos contíguos: concat não produz lacuna nem sobreposição
    for previous, current in zip(compiled.shots, compiled.shots[1:]):
        assert previous.start_ticks + previous.duration_ticks == current.start_ticks


def test_compiler_supports_a_multi_shot_scene_with_contiguous_shots():
    # R1/C4: o contrato hospeda multi-shot; o compilador já compila shots sequenciais de uma cena
    from app.studio.domain.render_plan import Shot

    base = simple_plan()
    scene = base.timeline.scenes[0]
    half = scene.duration_ticks // 2
    multi = scene.model_copy(update={"shots": [
        Shot(shot_id="shot-01", track_id="visual-main", start_tick=0, duration_ticks=half, asset_ref="asset-01"),
        Shot(shot_id="shot-02", track_id="visual-main", start_tick=half, duration_ticks=scene.duration_ticks - half, asset_ref="asset-01"),
    ]})
    plan = base.model_copy(update={"timeline": base.timeline.model_copy(update={"scenes": [multi], "narration": [], "subtitles": []})})
    compiled = compile_simple(plan)
    assert [(s.shot_id, s.start_ticks, s.duration_ticks) for s in compiled.shots] == [
        ("shot-01", 0, half), ("shot-02", half, scene.duration_ticks - half)
    ]
    assert sum(s.frames for s in compiled.shots) == round(scene.duration_ticks * FPS / DEFAULT_TICKS_PER_SECOND)


# ------------------------------------------------------------------ paridade visual


def test_still_image_compiles_to_ken_burns_with_legacy_geometry_and_encoding():
    compiled = compile_simple()
    shot = compiled.shots[0]
    graph = shot.filter_complex
    assert shot.frames == 70  # scene_length(2.0) = 2.8 s * 25 fps
    assert "scale=1620:2880:flags=lanczos" in graph
    assert "zoompan=z='1':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=70:s=1080x1920:fps=25" in graph
    assert "format=yuv420p" in graph
    assert f"fade=t=in:st=0:d={FADE_S}" in graph
    assert f"fade=t=out:st={2.8 - FADE_S:.3f}:d={FADE_S}" in graph
    assert shot.args[:5] == ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y")
    assert ("-frames:v", "70") == shot.args[shot.args.index("-frames:v"):shot.args.index("-frames:v") + 2]
    assert ("-r", "25") == shot.args[shot.args.index("-r"):shot.args.index("-r") + 2]
    for flag, value in (("-c:v", "libx264"), ("-preset", "veryfast"), ("-crf", "21"), ("-pix_fmt", "yuv420p")):
        assert flag in shot.args and shot.args[shot.args.index(flag) + 1] == value


@pytest.mark.parametrize(
    "motion,zoom,x",
    [
        ("zoom_in", "1+0.10*on/70", "iw/2-(iw/zoom/2)"),
        ("zoom_out", "1.10-0.10*on/70", "iw/2-(iw/zoom/2)"),
        ("pan_right", "1.12", "(iw-iw/zoom)*on/70"),
        ("pan_left", "1.12", "(iw-iw/zoom)*(1-on/70)"),
    ],
)
def test_explicit_motion_compiles_to_the_legacy_ken_burns_expressions(motion, zoom, x):
    plan = plan_with(
        [StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.", speech_seconds=2.0)],
        motions={"scene-01": motion},
    )
    graph = compile_simple(plan).shots[0].filter_complex
    assert f"zoompan=z='{zoom}':x='{x}':y='ih/2-(ih/zoom/2)':d=70" in graph


def test_static_overlay_carries_label_and_disclosure_for_the_executor_to_render():
    plan = plan_with([StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.", speech_seconds=2.0, label="DADOS")],
                     disclosure="Imagens ilustrativas")
    compiled = compile_simple(plan, labels={"scene-01": "DADOS"})
    static = compiled.shots[0].static_overlay
    assert static.kind == "static" and static.label == "DADOS" and static.disclosure == "Imagens ilustrativas"
    assert static.path == "/work/job-1/static_000.png"
    assert "-i" in compiled.shots[0].args and static.path in compiled.shots[0].args


def test_caption_overlays_are_burned_per_chunk_with_absolute_times_made_relative():
    plan = simple_plan()
    # a cena é a primeira; as legendas têm tempo relativo à cena já no plano
    compiled = compile_simple(plan)
    shot = compiled.shots[0]
    assert shot.captions
    assert [c.kind for c in shot.captions] == ["caption"] * len(shot.captions)
    assert shot.captions[0].path == "/work/job-1/cue_000_00.png"
    expected_enable = "gte(t,{:.3f})*lt(t,{:.3f})".format(
        ticks_to_seconds(shot.captions[0].start_ticks, DEFAULT_TICKS_PER_SECOND),
        ticks_to_seconds(shot.captions[0].end_ticks, DEFAULT_TICKS_PER_SECOND),
    )
    assert shot.captions[0].enable == expected_enable
    # inputs do ffmpeg: 0 = mídia, 1 = selo/disclosure, 2.. = legendas, na mesma ordem do graph
    assert shot.args.count("-i") == 2 + len(shot.captions)
    assert "[o1][2:v]overlay=0:0:format=auto:enable=" in shot.filter_complex
    for n, caption in enumerate(shot.captions, start=2):
        assert f"[{n}:v]" in shot.filter_complex
    for caption in shot.captions:
        assert caption.text
        assert 0 <= caption.start_ticks < caption.end_ticks <= shot.duration_ticks


def test_caption_graph_windows_match_the_contract_ticks():
    plan = simple_plan()
    compiled = compile_simple(plan)
    for caption, cue in zip(compiled.shots[0].captions, sorted(plan.timeline.subtitles, key=lambda c: c.start_tick)):
        assert caption.start_ticks == cue.start_tick - plan.timeline.scenes[0].start_tick
        assert caption.end_ticks == cue.start_tick + cue.duration_ticks - plan.timeline.scenes[0].start_tick


# ------------------------------------------------------------------ áudio


def test_narration_track_keeps_scene_order_and_pads_with_lead_and_tail():
    plan = plan_with(
        [StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.", speech_seconds=2.0),
         StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration="Segunda cena do vídeo.", speech_seconds=1.0)],
        assets=[image_ref(), image_ref("asset-02")],
    )
    compiled = compile_simple(plan, assets={"asset-01": descriptor_for("asset-01"), "asset-02": descriptor_for("asset-02")})
    narration = compiled.audio.narration
    assert [v.source_id for v in narration.voices] == ["voice:scene-01", "voice:scene-02"]
    assert [v.path for v in narration.voices] == ["/work/job-1/speech_000.wav", "/work/job-1/speech_001.wav"]
    assert narration.output == "/work/job-1/narration.wav"
    assert (narration.lead_seconds, narration.tail_seconds) == (0.30, 0.50)


def test_audio_mix_reproduces_ducking_and_loudnorm_from_the_legacy_renderer():
    compiled = compile_simple()
    mix = compiled.audio.filter_complex
    assert "sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350" in mix
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in mix
    assert "volume=0.40" in mix
    assert "amix=inputs=2:duration=longest:normalize=0" in mix
    args = compiled.audio.args
    assert ("-c:a", "aac") == args[args.index("-c:a"):args.index("-c:a") + 2]
    assert ("-b:a", "160k") == args[args.index("-b:a"):args.index("-b:a") + 2]
    assert "-shortest" in args and "-movflags" in args


def test_silent_music_still_compiles_the_mix_graph_with_a_silent_track():
    compiled = compile_simple(plan_with([StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.", speech_seconds=2.0)], music=False))
    assert compiled.audio.music.silent is True
    assert compiled.audio.music.params == {}
    # C2: `music=False` não remove a trilha — o grafo de mixagem é o mesmo
    assert "sidechaincompress" in compiled.audio.filter_complex
    assert "loudnorm=I=-16" in compiled.audio.filter_complex


def test_music_track_carries_the_deterministic_synthesis_params():
    compiled = compile_simple()
    music = compiled.audio.music
    assert music.source_id == "music" and music.silent is False
    assert music.params == {"bpm": 122, "seed": 7}
    assert music.duration_ticks == compiled.total_ticks + compiled.ticks_per_second


# ------------------------------------------------------------------ montagem


def test_concat_and_final_commands_use_the_same_flags_as_the_legacy_assembly():
    compiled = compile_simple()
    concat = compiled.concat
    assert concat.output == "/work/job-1/video_only.mp4"
    assert concat.manifest_path == "/work/job-1/concat.txt"
    assert concat.args[:6] == ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f")
    assert ("-c", "copy") == concat.args[concat.args.index("-c"):concat.args.index("-c") + 2]
    assert compiled.final_output == "/work/job-1/final.mp4"
    final = compiled.final_args
    assert ("-map", "0:v") == final[final.index("-map"):final.index("-map") + 2]
    assert ("-map", "[a]") == final[final.index("-map", final.index("-map") + 1):final.index("-map", final.index("-map") + 1) + 2]
    assert "+faststart" in final[final.index("-movflags") + 1]


def test_compiled_plan_serializes_to_stable_json():
    compiled = compile_simple()
    payload = json.loads(compiled.to_json())
    assert payload["shots"][0]["frames"] == 70
    assert payload["audio"]["music"]["params"] == {"bpm": 122, "seed": 7}
    assert payload["digest"] == compiled.digest()


def test_digest_changes_when_the_plan_changes():
    one = compile_simple()
    other = compile_simple(plan_with([StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Outra narração da cena.", speech_seconds=2.0)]))
    assert one.digest() != other.digest()


# ------------------------------------------------------------------ entradas de mídia


def test_video_asset_compiles_to_a_trimmed_segment_instead_of_ken_burns():
    plan = plan_with([StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.", speech_seconds=2.0)],
                     assets=[image_ref()])
    video = descriptor_for("asset-01", media_type="video", codec="h264", duration_ticks=plan.timeline.duration_ticks, uri="clip/1.mp4", location="/storage/1.mp4")
    # o manifesto precisa dizer vídeo para o plano referenciar um vídeo
    plan = plan_with(
        [StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.", speech_seconds=2.0)],
        assets=[image_ref().model_copy(update={"media_type": "video", "metadata": {"codec": "h264", "width": "1920", "height": "1080", "duration_ticks": str(plan.timeline.duration_ticks)}})],
    )
    compiled = compile_simple(plan, assets={"asset-01": video})
    graph = compiled.shots[0].filter_complex
    assert "trim=start=0" in graph and "zoompan" not in graph
    assert "fps=25" in graph


def test_text_asset_compiles_to_an_executor_rendered_card():
    plan = plan_with(
        [StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.", speech_seconds=2.0)],
        assets=[image_ref().model_copy(update={"media_type": "text", "metadata": {"text": "42%"}})],
    )
    text = descriptor_for("asset-01", media_type="text", codec=None, width=None, height=None, location="")
    compiled = compile_simple(plan, assets={"asset-01": text})
    shot = compiled.shots[0]
    assert shot.text_card is not None and shot.text_card.text == "42%"
    assert shot.text_card.path == "/work/job-1/text_000.png"
    assert shot.text_card.path in shot.args


# ------------------------------------------------------------------ recusas claras


def test_compiler_rejects_an_asset_that_was_not_resolved():
    with pytest.raises(CompileError, match="asset-01"):
        compile_simple(assets={})


def test_compiler_rejects_a_shot_whose_asset_is_unavailable():
    with pytest.raises(CompileError, match="asset-01"):
        compile_simple(assets={"asset-01": descriptor_for(available=False, license=None, codec=None, width=None, height=None)})


def test_compiler_refuses_layered_visual_tracks_instead_of_producing_a_wrong_video():
    # RP-023 é o esqueleto: composição de camadas sobrepostas é RP-024
    from app.studio.domain.render_plan import Composition, Effects, Scene, Shot, Timeline, Track, Transition
    from app.studio.domain.render_plan import Output, Provenance

    base = simple_plan()
    scene = base.timeline.scenes[0]
    layered = base.model_copy(update={
        "timeline": base.timeline.model_copy(update={
            "tracks": [Track(track_id="visual-main", kind="visual"), Track(track_id="visual-top", kind="visual")],
            "scenes": [scene.model_copy(update={"shots": [
                Shot(shot_id="shot-01", track_id="visual-main", start_tick=0, duration_ticks=scene.duration_ticks, asset_ref="asset-01"),
                Shot(shot_id="shot-02", track_id="visual-top", start_tick=0, duration_ticks=scene.duration_ticks, asset_ref="asset-01"),
            ]})],
        })
    })
    with pytest.raises(CompileError, match="layer|overlap|track"):
        compile_simple(layered)


def test_compiler_rejects_a_text_asset_without_text_metadata():
    plan = plan_with(
        [StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.", speech_seconds=2.0)],
        assets=[image_ref().model_copy(update={"media_type": "text"})],
    )
    text = descriptor_for("asset-01", media_type="text", codec=None, width=None, height=None, location="")
    with pytest.raises(CompileError, match="text"):
        compile_simple(plan, assets={"asset-01": text})