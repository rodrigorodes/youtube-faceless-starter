import pytest
from pydantic import ValidationError

from app.studio.domain.contracts import VideoFormat
from app.studio.domain.render import scene_length
from app.studio.domain.render_plan import (
    AssetReference,
    RenderPlan,
    StyleSnapshot,
    Transition,
)
from app.studio.domain.render_plan_builder import (
    DEFAULT_TICKS_PER_SECOND,
    PlanBuildError,
    StoryboardOverlay,
    StoryboardScene,
    StoryboardShot,
    build_render_plan,
)
from app.studio.domain.ticks import seconds_to_ticks

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


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


def build(**overrides):
    data = dict(
        plan_id="plan-001",
        revision=1,
        project_id="project-001",
        video_id="video-001",
        format=VideoFormat.short,
        scenes=[
            StoryboardScene(
                scene_id="scene-01",
                asset_id="asset-01",
                narration="Cena única",
                speech_seconds=2.0,
            )
        ],
        assets=[asset_ref()],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=3),
        builder_version="render-plan-builder/1",
    )
    data.update(overrides)
    return build_render_plan(**data)


# --------------------------------------------------------------------------- tests


def test_multishot_scene_creates_contiguous_sequential_base_shots():
    # 0.3 lead + 6.8 speech + 0.5 tail = 7.6s (190000 ticks at 25000 tps)
    speech = 6.8
    assert scene_length(speech) == 7.6

    shots = [
        StoryboardShot(shot_id="shot-01-a", asset_id="asset-01", duration_s=2.0),
        StoryboardShot(shot_id="shot-01-b", asset_id="asset-02", duration_s=3.0),
        StoryboardShot(shot_id="shot-01-c", asset_id="asset-03", duration_s=2.6),
    ]

    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com múltiplos shots",
        speech_seconds=speech,
        shots=shots,
    )

    plan = build(
        scenes=[scene],
        assets=[
            asset_ref("asset-01", content_sha256=SHA_A),
            asset_ref("asset-02", content_sha256=SHA_B),
            asset_ref("asset-03", content_sha256=SHA_C),
        ],
    )

    assert isinstance(plan, RenderPlan)
    plan_scene = plan.timeline.scenes[0]
    base_shots = plan_scene.base_shots
    assert len(base_shots) == 3

    # Ausência de gaps na track visual-main e ticks corretos
    expected_durations = [
        seconds_to_ticks(2.0, DEFAULT_TICKS_PER_SECOND),  # 50000
        seconds_to_ticks(3.0, DEFAULT_TICKS_PER_SECOND),  # 75000
        seconds_to_ticks(2.6, DEFAULT_TICKS_PER_SECOND),  # 65000
    ]
    assert [s.duration_ticks for s in base_shots] == expected_durations
    assert sum(s.duration_ticks for s in base_shots) == plan_scene.duration_ticks

    # Contiguidade e offsets
    assert base_shots[0].start_tick == 0
    assert base_shots[0].shot_id == "shot-01-a"
    assert base_shots[0].asset_ref == "asset-01"
    assert base_shots[0].track_id == "visual-main"

    assert base_shots[1].start_tick == base_shots[0].start_tick + base_shots[0].duration_ticks
    assert base_shots[1].shot_id == "shot-01-b"
    assert base_shots[1].asset_ref == "asset-02"

    assert base_shots[2].start_tick == base_shots[1].start_tick + base_shots[1].duration_ticks
    assert base_shots[2].shot_id == "shot-01-c"
    assert base_shots[2].asset_ref == "asset-03"

    assert base_shots[2].start_tick + base_shots[2].duration_ticks == plan_scene.start_tick + plan_scene.duration_ticks


def test_multishot_supports_asset_offset_motion_and_transition():
    speech = 6.7  # 7.5s = 187500 ticks
    shots = [
        StoryboardShot(
            shot_id="shot-01",
            asset_id="asset-01",
            duration_s=4.0,
            asset_offset_s=1.5,
            motion="zoom_in",
            transition=Transition(kind="cut"),
        ),
        StoryboardShot(
            shot_id="shot-02",
            asset_id="asset-02",
            duration_s=3.5,
            asset_offset_s=0.0,
            motion="pan_left",
        ),
    ]

    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com atributos avançados de shot",
        speech_seconds=speech,
        shots=shots,
    )

    plan = build(
        scenes=[scene],
        assets=[
            asset_ref("asset-01", content_sha256=SHA_A),
            asset_ref("asset-02", content_sha256=SHA_B),
        ],
    )

    s1, s2 = plan.timeline.scenes[0].base_shots
    assert s1.asset_offset_ticks == seconds_to_ticks(1.5, DEFAULT_TICKS_PER_SECOND)
    assert s1.effects.motion == "zoom_in"
    assert s1.transition == Transition(kind="cut")

    assert s2.asset_offset_ticks == 0
    assert s2.effects.motion == "pan_left"
    assert s2.transition is None


def test_multishot_adjusts_one_tick_rounding_residue_on_final_shot():
    # 0.3 + 1.2 + 0.5 = 2.0s scene_length (50000 ticks)
    speech = 1.2
    assert scene_length(speech) == 2.0

    # 3 shots: 0.6666s + 0.6666s + 0.6668s = 2.0s
    # In ticks: 0.6666 * 25000 = 16665; 16665 + 16665 + 16670 = 50000 ticks.
    # Now suppose shots: 0.6667s, 0.6667s, 0.6666s = 2.0s
    # 0.6667 * 25000 = 16667.5 -> round to even: 16668
    # 16668 + 16668 + 16665 = 50001 (1 tick residue over 50000!)
    shots = [
        StoryboardShot(shot_id="s1", asset_id="asset-01", duration_s=0.6667),
        StoryboardShot(shot_id="s2", asset_id="asset-01", duration_s=0.6667),
        StoryboardShot(shot_id="s3", asset_id="asset-01", duration_s=0.6666),
    ]

    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com arredondamento fracionário",
        speech_seconds=speech,
        shots=shots,
    )

    plan = build(scenes=[scene], assets=[asset_ref("asset-01")])
    base_shots = plan.timeline.scenes[0].base_shots

    # Verifica que a soma dos ticks bate exatamente com a cena e que a validação passou sem erro
    assert sum(s.duration_ticks for s in base_shots) == plan.timeline.scenes[0].duration_ticks
    assert base_shots[0].duration_ticks == 16667
    assert base_shots[1].duration_ticks == 16667
    assert base_shots[2].duration_ticks == 16666  # adjusted 1 tick to fit 50000 exactly


def test_parity_preserved_when_shots_is_none_or_empty():
    speech = 2.0
    # shots=None
    scene_none = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Sem shots explícitos",
        speech_seconds=speech,
        shots=None,
    )
    plan_none = build(scenes=[scene_none], assets=[asset_ref("asset-01")])
    shots_none = plan_none.timeline.scenes[0].base_shots
    assert len(shots_none) == 1
    assert shots_none[0].shot_id == "shot:scene-01"
    assert shots_none[0].duration_ticks == plan_none.timeline.scenes[0].duration_ticks

    # shots=[]
    scene_empty = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Shots lista vazia",
        speech_seconds=speech,
        shots=[],
    )
    plan_empty = build(scenes=[scene_empty], assets=[asset_ref("asset-01")])
    shots_empty = plan_empty.timeline.scenes[0].base_shots
    assert len(shots_empty) == 1
    assert shots_empty[0].shot_id == "shot:scene-01"
    assert shots_empty[0].duration_ticks == plan_empty.timeline.scenes[0].duration_ticks


def test_multishot_with_overlays():
    speech = 6.7  # 7.5s = 187500 ticks
    shots = [
        StoryboardShot(shot_id="shot-01-a", asset_id="asset-01", duration_s=4.0),
        StoryboardShot(shot_id="shot-01-b", asset_id="asset-02", duration_s=3.5),
    ]
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com multi-shot e overlay",
        speech_seconds=speech,
        shots=shots,
    )
    overlay = StoryboardOverlay(
        scene_id="scene-01",
        asset_id="asset-overlay",
        start_s=1.0,
        duration_s=2.0,
        z_index=1,
    )

    plan = build(
        scenes=[scene],
        assets=[
            asset_ref("asset-01"),
            asset_ref("asset-02", content_sha256=SHA_B),
            asset_ref("asset-overlay", content_sha256=SHA_C),
        ],
        overlays=[overlay],
    )

    plan_scene = plan.timeline.scenes[0]
    assert len(plan_scene.base_shots) == 2
    assert len(plan_scene.overlay_shots) == 1
    ov_shot = plan_scene.overlay_shots[0]
    assert ov_shot.asset_ref == "asset-overlay"
    assert ov_shot.role == "overlay"
    assert ov_shot.track_id == "visual-overlay"


def test_multishot_rejects_missing_asset_in_manifest():
    speech = 6.7
    shots = [
        StoryboardShot(shot_id="shot-01-a", asset_id="asset-01", duration_s=4.0),
        StoryboardShot(shot_id="shot-01-b", asset_id="asset-missing", duration_s=3.5),
    ]
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com asset faltante",
        speech_seconds=speech,
        shots=shots,
    )

    with pytest.raises(PlanBuildError, match="references asset 'asset-missing' that is not in the manifest"):
        build(scenes=[scene], assets=[asset_ref("asset-01")])


def test_storyboard_shot_validates_fields():
    with pytest.raises(ValidationError):
        # shot_id cannot be blank
        StoryboardShot(shot_id="", asset_id="asset-01", duration_s=2.0)

    with pytest.raises(ValidationError):
        # asset_id cannot be blank
        StoryboardShot(shot_id="shot-01", asset_id="", duration_s=2.0)

    with pytest.raises(ValidationError):
        # duration_s must be > 0
        StoryboardShot(shot_id="shot-01", asset_id="asset-01", duration_s=0.0)

    with pytest.raises(ValidationError):
        # duration_s cannot be negative
        StoryboardShot(shot_id="shot-01", asset_id="asset-01", duration_s=-1.0)

    with pytest.raises(ValidationError):
        # asset_offset_s cannot be negative
        StoryboardShot(shot_id="shot-01", asset_id="asset-01", duration_s=2.0, asset_offset_s=-0.5)


def test_multishot_with_negative_1_tick_rounding_residue():
    # 0.3 + 1.2 + 0.5 = 2.0s = 50000 ticks
    speech = 1.2
    assert scene_length(speech) == 2.0

    # 0.6666s -> 16665, 0.6669s -> 16673, 0.6665s -> 16663. Sum = 50001 (diff = -1)
    shots = [
        StoryboardShot(shot_id="s1", asset_id="asset-01", duration_s=0.6666),
        StoryboardShot(shot_id="s2", asset_id="asset-01", duration_s=0.6669),
        StoryboardShot(shot_id="s3", asset_id="asset-01", duration_s=0.6665),
    ]
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com residuo negativo de 1 tick",
        speech_seconds=speech,
        shots=shots,
    )
    plan = build(scenes=[scene], assets=[asset_ref("asset-01")])
    base_shots = plan.timeline.scenes[0].base_shots
    assert sum(s.duration_ticks for s in base_shots) == plan.timeline.scenes[0].duration_ticks
    assert base_shots[0].duration_ticks == 16665
    assert base_shots[1].duration_ticks == 16673
    assert base_shots[2].duration_ticks == 16662  # adjusted -1 tick to fit 50000 exactly


def test_multishot_across_multiple_scenes():
    # scene 1: speech=1.2 (2.0s = 50000 ticks), 2 shots (1.0s, 1.0s)
    scene1 = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena 1 com 2 shots",
        speech_seconds=1.2,
        shots=[
            StoryboardShot(shot_id="shot-01-a", asset_id="asset-01", duration_s=1.0),
            StoryboardShot(shot_id="shot-01-b", asset_id="asset-02", duration_s=1.0),
        ],
    )
    # scene 2: speech=2.0 (2.8s = 70000 ticks), 1 legacy shot (shots=None)
    scene2 = StoryboardScene(
        scene_id="scene-02",
        asset_id="asset-03",
        narration="Cena 2 legado",
        speech_seconds=2.0,
        shots=None,
    )

    plan = build(
        scenes=[scene1, scene2],
        assets=[
            asset_ref("asset-01"),
            asset_ref("asset-02", content_sha256=SHA_B),
            asset_ref("asset-03", content_sha256=SHA_C),
        ],
    )

    sc1, sc2 = plan.timeline.scenes
    assert len(sc1.base_shots) == 2
    assert len(sc2.base_shots) == 1
    assert sc1.start_tick == 0
    assert sc1.duration_ticks == 50000
    assert sc2.start_tick == 50000
    assert sc2.duration_ticks == 70000
    assert plan.timeline.duration_ticks == 120000


def test_multishot_inter_scene_transition_fallback():
    # Quando transition global é passada (ex: fade de 5000 ticks),
    # o último shot da cena 1 deve recebê-la se não tiver transição própria.
    scene1 = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena 1",
        speech_seconds=1.2,
        shots=[
            StoryboardShot(shot_id="s1", asset_id="asset-01", duration_s=1.0),
            StoryboardShot(shot_id="s2", asset_id="asset-01", duration_s=1.0),
        ],
    )
    scene2 = StoryboardScene(
        scene_id="scene-02",
        asset_id="asset-02",
        narration="Cena 2",
        speech_seconds=1.2,
        shots=[
            StoryboardShot(shot_id="s3", asset_id="asset-02", duration_s=2.0),
        ],
    )

    global_trans = Transition(kind="fade", duration_ticks=5000)
    plan = build(
        scenes=[scene1, scene2],
        assets=[asset_ref("asset-01"), asset_ref("asset-02", content_sha256=SHA_B)],
        transition=global_trans,
    )

    s1, s2 = plan.timeline.scenes[0].base_shots
    assert s1.transition is None
    assert s2.transition == global_trans

    # Última cena não recebe transição para frente
    s3 = plan.timeline.scenes[1].base_shots[0]
    assert s3.transition is None


def test_multishot_rejects_sub_tick_duration():
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com shot sub-tick",
        speech_seconds=1.2,
        shots=[
            StoryboardShot(shot_id="s1", asset_id="asset-01", duration_s=0.000001),
        ],
    )
    with pytest.raises(PlanBuildError, match="is below one tick"):
        build(scenes=[scene], assets=[asset_ref("asset-01")])


def test_multishot_rejects_non_storyboard_shot():
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com item inválido",
        speech_seconds=1.2,
        shots=[{"not": "a shot"}],  # type: ignore[list-item]
    )
    with pytest.raises(PlanBuildError, match="is not a StoryboardShot"):
        build(scenes=[scene], assets=[asset_ref("asset-01")])


def test_multishot_rejects_shots_duration_sum_diverging_above_tolerance():
    # speech=1.2 -> cena = 2.0s (50000 ticks). Shots somam 1.0s. Residuo = +1.000s (> 0.2s max allowed)
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com shots muito mais curtos que a cena",
        speech_seconds=1.2,
        shots=[
            StoryboardShot(shot_id="s1", asset_id="asset-01", duration_s=1.0),
        ],
    )
    with pytest.raises(
        PlanBuildError,
        match=r"shots duration sum diverges from scene duration by 1\.000s; ensure shots sum matches scene duration",
    ):
        build(scenes=[scene], assets=[asset_ref("asset-01")])


def test_multishot_rejects_shots_duration_sum_diverging_below_tolerance():
    # speech=1.2 -> cena = 2.0s (50000 ticks). Shots somam 3.0s. Residuo = -1.000s (|residuo| > 0.2s max allowed)
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com shots muito mais longos que a cena",
        speech_seconds=1.2,
        shots=[
            StoryboardShot(shot_id="s1", asset_id="asset-01", duration_s=1.5),
            StoryboardShot(shot_id="s2", asset_id="asset-01", duration_s=1.5),
        ],
    )
    with pytest.raises(
        PlanBuildError,
        match=r"shots duration sum diverges from scene duration by -1\.000s; ensure shots sum matches scene duration",
    ):
        build(scenes=[scene], assets=[asset_ref("asset-01")])


