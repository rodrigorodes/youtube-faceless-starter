import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.render_plan_compiler import compile_render_plan  # noqa: E402
from app.studio.domain.asset_resolver import AssetDescriptor  # noqa: E402
from app.studio.domain.contracts import Asset, AssetKind, VideoFormat  # noqa: E402
from app.studio.domain.render_plan import (  # noqa: E402
    AssetReference,
    StyleSnapshot,
    Transition,
)
from app.studio.domain.render_plan_builder import (  # noqa: E402
    StoryboardScene,
    asset_reference_for,
    build_render_plan,
)
from app.studio.domain.visual_style import (  # noqa: E402
    APPLIED_GROUPS,
    LOADED_ONLY_GROUPS,
    ResolvedStyle,
    VisualStyle,
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


def build_plan_with_scenes(scenes, assets=None, **overrides):
    data = dict(
        plan_id="plan-transition-001",
        revision=1,
        project_id="project-001",
        video_id="video-001",
        format=VideoFormat.short,
        scenes=scenes,
        assets=assets or [image_ref()],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=1),
        builder_version="render-plan-builder/1",
    )
    data.update(overrides)
    return build_render_plan(**data)


def test_transition_is_promoted_to_applied_groups():
    assert "transition" in APPLIED_GROUPS
    assert "transition" not in LOADED_ONLY_GROUPS


def test_build_render_plan_with_style_fade_applies_transition_to_base_shots_except_last():
    scenes = [
        StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena.", speech_seconds=2.0),
        StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration="Segunda cena.", speech_seconds=2.0),
        StoryboardScene(scene_id="scene-03", asset_id="asset-03", narration="Terceira cena final.", speech_seconds=2.0),
    ]
    assets = [
        image_ref("asset-01"),
        image_ref("asset-02", sha=SHA_B),
        image_ref("asset-03", sha=SHA_A),
    ]
    style = ResolvedStyle(
        snapshot=StyleSnapshot(style_id="test-style", version=1),
        transition={"kind": "fade", "duration_ticks": 2500},
    )

    plan = build_plan_with_scenes(scenes, assets=assets, style=style)

    # Shots base de cenas com próximo vizinho devem ter a transição
    shot_0 = plan.timeline.scenes[0].shots[0]
    shot_1 = plan.timeline.scenes[1].shots[0]
    shot_2 = plan.timeline.scenes[2].shots[0]

    assert shot_0.transition == Transition(kind="fade", duration_ticks=2500)
    assert shot_1.transition == Transition(kind="fade", duration_ticks=2500)
    # Último shot não transiciona para o vazio: transition deve ser None
    assert shot_2.transition is None


def test_build_render_plan_with_none_or_missing_transition_preserves_legacy_none():
    scenes = [
        StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena.", speech_seconds=2.0),
        StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration="Segunda cena.", speech_seconds=2.0),
    ]
    assets = [image_ref("asset-01"), image_ref("asset-02", sha=SHA_B)]

    # 1. style com transition 'none'
    style_none = ResolvedStyle(
        snapshot=StyleSnapshot(style_id="style-none", version=1),
        transition={"kind": "none", "duration_ticks": 0},
    )
    plan_none = build_plan_with_scenes(scenes, assets=assets, style=style_none)
    for scene in plan_none.timeline.scenes:
        for shot in scene.shots:
            assert shot.transition is None

    # 2. style sem transition declarada
    style_empty = ResolvedStyle(
        snapshot=StyleSnapshot(style_id="style-empty", version=1),
        transition={},
    )
    plan_empty = build_plan_with_scenes(scenes, assets=assets, style=style_empty)
    for scene in plan_empty.timeline.scenes:
        for shot in scene.shots:
            assert shot.transition is None

    # 3. sem style (style=None)
    plan_nostyle = build_plan_with_scenes(scenes, assets=assets, style=None)
    for scene in plan_nostyle.timeline.scenes:
        for shot in scene.shots:
            assert shot.transition is None


def test_build_render_plan_skips_transition_if_fade_duration_exceeds_shot_duration():
    # speech_seconds = 0.1 -> scene_length(0.1) é cerca de 0.9s = 22500 ticks
    # Se configurarmos fade duration para 30000 ticks (> 22500), deve pular defensivamente
    scenes = [
        StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Cena curta.", speech_seconds=0.1),
        StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration="Cena seguinte.", speech_seconds=2.0),
    ]
    assets = [image_ref("asset-01"), image_ref("asset-02", sha=SHA_B)]
    style = ResolvedStyle(
        snapshot=StyleSnapshot(style_id="style-long-fade", version=1),
        transition={"kind": "fade", "duration_ticks": 30000},
    )

    plan = build_plan_with_scenes(scenes, assets=assets, style=style)
    # O shot da cena 1 é menor que 30000 ticks, portanto transition deve ser None para evitar quebra no render
    assert plan.timeline.scenes[0].shots[0].transition is None
    assert plan.timeline.scenes[1].shots[0].transition is None


def test_compile_render_plan_outputs_deterministic_ffmpeg_fade_filter_for_configured_duration():
    scenes = [
        StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena.", speech_seconds=2.0),
        StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration="Segunda cena.", speech_seconds=2.0),
    ]
    assets = [image_ref("asset-01"), image_ref("asset-02", sha=SHA_B)]
    descriptors = {
        "asset-01": descriptor_for("asset-01"),
        "asset-02": descriptor_for("asset-02", sha=SHA_B),
    }

    # 2500 ticks em 25000 tps = 0.1s
    style = ResolvedStyle(
        snapshot=StyleSnapshot(style_id="style-compile", version=1),
        transition={"kind": "fade", "duration_ticks": 2500},
    )
    plan = build_plan_with_scenes(scenes, assets=assets, style=style)

    compiled = compile_render_plan(plan=plan, assets=descriptors, work_dir="/tmp/work-transition")

    # Primeiro shot deve conter o fade out com d=0.100 (2500 ticks) e st=2.700 (2.8s - 0.1s)
    filter_shot_0 = compiled.shots[0].filter_complex
    assert "fade=t=in:st=0:d=0.25" in filter_shot_0
    assert "fade=t=out:st=2.700:d=0.100" in filter_shot_0

    # Segundo shot (último) tem transition=None; no schema v2 isso é corte seco (sem fade).
    filter_shot_1 = compiled.shots[1].filter_complex
    assert "fade=t=in" not in filter_shot_1
    assert "fade=t=out" not in filter_shot_1
    assert filter_shot_1.endswith("format=yuv420p[v]")


def test_build_render_plan_accepts_transition_kwarg_or_visual_style_object():
    scenes = [
        StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena.", speech_seconds=2.0),
        StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration="Segunda cena.", speech_seconds=2.0),
    ]
    assets = [image_ref("asset-01"), image_ref("asset-02", sha=SHA_B)]

    # Via kwarg transition diretamente
    plan_kwarg = build_plan_with_scenes(
        scenes,
        assets=assets,
        transition={"kind": "fade", "duration_ticks": 1250},
    )
    assert plan_kwarg.timeline.scenes[0].shots[0].transition == Transition(kind="fade", duration_ticks=1250)

    # Via VisualStyle de domínio com params
    visual_style = VisualStyle(
        id="a" * 32,
        name="Estilo Fade",
        params={"transition": {"kind": "fade", "duration_ticks": 5000}},
    )
    plan_vs = build_plan_with_scenes(scenes, assets=assets, style=visual_style)
    assert plan_vs.timeline.scenes[0].shots[0].transition == Transition(kind="fade", duration_ticks=5000)
