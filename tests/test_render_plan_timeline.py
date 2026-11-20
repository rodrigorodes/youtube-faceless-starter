"""RP-010..RP-014 — timebase racional, tracks, intervalos, narração/legenda e alinhamento.

Contrato puro (`app.studio.domain.render_plan`): sem I/O. Cobre a fatia 3 da
fundação Render Plan (design §5.1/§7.2/§9 e writing-block RP-02):

- RP-010: `Timebase` racional (`fps_num`/`fps_den`) + `ticks_per_second` explícito;
  toda fronteira de quadro é um tick inteiro, ou a timebase é rejeitada.
- RP-011: cenas, shots e **tracks**; shot referencia um track visual declarado.
- RP-012: sobreposição, contiguidade e lacunas **por track** e por cena.
- RP-013: narração e legendas associadas à timeline (cues com intervalo e faixa).
- RP-014: duração pelo formato de saída, zero lacuna não intencional e
  sincronização dentro da tolerância por tipo de mídia.
"""
import pytest
from pydantic import ValidationError

from app.studio.domain.contracts import VideoFormat
from app.studio.domain.render_plan import (
    AssetReference,
    GeneratedAudioSource,
    NarrationCue,
    Output,
    Provenance,
    RenderPlan,
    Scene,
    Shot,
    StyleSnapshot,
    SubtitleCue,
    Timebase,
    Timeline,
    Track,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


# --------------------------------------------------------------------------- #
# Construtores
# --------------------------------------------------------------------------- #

def asset(asset_id="asset-image-01", sha=SHA_A, **overrides):
    data = dict(asset_id=asset_id, asset_version=1,
                uri=f"storage/{asset_id}.png", content_sha256=sha, media_type="image")
    data.update(overrides)
    return AssetReference(**data)


def voice(source_id="voice-01", duration_ticks=250):
    return GeneratedAudioSource(source_id=source_id, kind="voice", duration_ticks=duration_ticks)


def shot(shot_id="shot-01", track_id="visual-main", start_tick=0, duration_ticks=250,
         asset_ref="asset-image-01", **overrides):
    data = dict(shot_id=shot_id, track_id=track_id, start_tick=start_tick,
                duration_ticks=duration_ticks, asset_ref=asset_ref)
    data.update(overrides)
    return Shot(**data)


def scene(scene_id="scene-01", start_tick=0, duration_ticks=250, shots=None, **overrides):
    data = dict(scene_id=scene_id, start_tick=start_tick, duration_ticks=duration_ticks,
                shots=shots if shots is not None else [shot()])
    data.update(overrides)
    return Scene(**data)


def timebase(ticks_per_second=25, fps_num=25, fps_den=1):
    return Timebase(ticks_per_second=ticks_per_second, fps_num=fps_num, fps_den=fps_den)


def timeline(scenes=None, tracks=None, narration=None, subtitles=None, **overrides):
    data = dict(
        timebase=timebase(),
        tracks=tracks if tracks is not None else [Track(track_id="visual-main", kind="visual")],
        scenes=scenes if scenes is not None else [scene()],
        narration=narration if narration is not None else [],
        subtitles=subtitles if subtitles is not None else [],
    )
    data.update(overrides)
    return Timeline(**data)


def plan(timeline_obj=None, **overrides):
    data = dict(
        plan_id="plan-01", revision=1, project_id="project-01", video_id="video-01",
        output=Output(format=VideoFormat.short, width=1080, height=1920),
        timeline=timeline_obj if timeline_obj is not None else timeline(),
        asset_manifest=[asset()],
        generated_audio=[voice()],
        style_snapshot=StyleSnapshot(style_id="channel-01", version=3),
        provenance=Provenance(builder_version="1.0.0"),
    )
    data.update(overrides)
    return RenderPlan(**data)


# --------------------------------------------------------------------------- #
# RP-010 — timebase racional e ticks inteiros
# --------------------------------------------------------------------------- #

def test_timebase_defaults_to_25_fps_and_exposes_ticks_per_frame():
    t = Timebase(ticks_per_second=25)
    assert (t.fps_num, t.fps_den) == (25, 1)
    assert t.fps == 25.0
    assert t.ticks_per_frame == 1


def test_timebase_represents_rational_frame_rates_exactly():
    t = Timebase(ticks_per_second=30000, fps_num=30000, fps_den=1001)
    assert t.ticks_per_frame == 1001              # 1 quadro = 30000*1001/30000 ticks
    assert Timebase(ticks_per_second=1000, fps_num=25).ticks_per_frame == 40


@pytest.mark.parametrize(
    "tps,num,den",
    [
        (25, 30, 1),        # 30 fps não cabe em 25 ticks/s
        (25, 30000, 1001),  # nem 29.97 em 25 ticks/s
        (24, 25, 1),
    ],
)
def test_timebase_rejects_frame_rate_not_representable_in_ticks(tps, num, den):
    with pytest.raises(ValidationError, match="tick|frame"):
        Timebase(ticks_per_second=tps, fps_num=num, fps_den=den)


def test_timebase_accepts_frame_rate_dividing_ticks_per_second():
    assert Timebase(ticks_per_second=30, fps_num=30).ticks_per_frame == 1
    assert Timebase(ticks_per_second=24000, fps_num=24).ticks_per_frame == 1000


def test_ticks_per_second_is_explicit_and_strictly_integer():
    with pytest.raises(ValidationError):
        Timebase(ticks_per_second=25.0)
    with pytest.raises(ValidationError):
        Timebase(ticks_per_second=True)
    with pytest.raises(ValidationError):
        Timebase()  # sem ticks_per_second explícito


def test_output_no_longer_carries_a_redundant_integer_fps():
    assert "fps" not in Output(format=VideoFormat.short, width=1080, height=1920).model_dump()


# --------------------------------------------------------------------------- #
# RP-011 — cenas, shots e tracks
# --------------------------------------------------------------------------- #

def test_multi_shot_scene_on_a_declared_track_is_valid():
    p = plan(timeline_obj=timeline(scenes=[scene(shots=[
        shot(shot_id="shot-01", start_tick=0, duration_ticks=100),
        shot(shot_id="shot-02", start_tick=100, duration_ticks=150),
    ])]))
    assert p.timeline.duration_ticks == 250


def test_shot_referencing_undeclared_track_is_rejected():
    with pytest.raises(ValidationError, match="track"):
        timeline(scenes=[scene(shots=[shot(track_id="ghost")])])


def test_shot_may_not_live_on_a_non_visual_track():
    tracks = [Track(track_id="visual-main", kind="visual"), Track(track_id="voice", kind="narration")]
    with pytest.raises(ValidationError, match="visual"):
        timeline(tracks=tracks, scenes=[scene(shots=[shot(track_id="voice")])])


def test_duplicate_track_ids_are_rejected():
    with pytest.raises(ValidationError, match="track"):
        timeline(tracks=[Track(track_id="visual-main", kind="visual"),
                         Track(track_id="visual-main", kind="visual")])


def test_at_least_one_track_is_required():
    with pytest.raises(ValidationError):
        Timeline(timebase=timebase(), tracks=[], scenes=[scene()])


# --------------------------------------------------------------------------- #
# RP-012 — sobreposição, contiguidade e lacunas
# --------------------------------------------------------------------------- #

def test_overlapping_shots_on_the_same_track_are_rejected():
    with pytest.raises(ValidationError, match="overlap"):
        timeline(scenes=[scene(shots=[
            shot(shot_id="shot-01", start_tick=0, duration_ticks=150),
            shot(shot_id="shot-02", start_tick=100, duration_ticks=150),
        ])])


def test_gap_on_a_visual_track_is_rejected():
    with pytest.raises(ValidationError, match="gap|cover"):
        timeline(scenes=[scene(shots=[
            shot(shot_id="shot-01", start_tick=0, duration_ticks=100),
            shot(shot_id="shot-02", start_tick=150, duration_ticks=100),
        ])])


def test_layered_tracks_may_overlap_when_the_scene_is_fully_covered():
    tracks = [Track(track_id="bg", kind="visual"), Track(track_id="overlay", kind="visual")]
    p = plan(
        asset_manifest=[asset("asset-bg", SHA_A), asset("asset-overlay", SHA_B)],
        timeline_obj=timeline(tracks=tracks, scenes=[scene(shots=[
            shot(shot_id="shot-bg", track_id="bg", start_tick=0, duration_ticks=250, asset_ref="asset-bg"),
            shot(shot_id="shot-ov", track_id="overlay", start_tick=100, duration_ticks=50, asset_ref="asset-overlay"),
        ])]),
    )
    assert p.timeline.duration_ticks == 250


def test_cross_track_overlap_still_must_be_covered_end_to_end():
    tracks = [Track(track_id="bg", kind="visual"), Track(track_id="overlay", kind="visual")]
    with pytest.raises(ValidationError, match="gap|cover"):
        plan(
            asset_manifest=[asset("asset-bg", SHA_A), asset("asset-overlay", SHA_B)],
            timeline_obj=timeline(tracks=tracks, scenes=[scene(shots=[
                shot(shot_id="shot-bg", track_id="bg", start_tick=0, duration_ticks=100, asset_ref="asset-bg"),
                shot(shot_id="shot-ov", track_id="overlay", start_tick=200, duration_ticks=50, asset_ref="asset-overlay"),
            ])]),
        )


def test_scenes_must_tile_the_timeline_without_gaps():
    with pytest.raises(ValidationError, match="gap|overlap|start|end"):
        timeline(scenes=[
            scene(scene_id="scene-01", start_tick=0, duration_ticks=100),
            scene(scene_id="scene-02", start_tick=150, duration_ticks=100),
        ])


def test_scenes_must_tile_the_timeline_without_overlap():
    with pytest.raises(ValidationError, match="gap|overlap|start|end"):
        timeline(scenes=[
            scene(scene_id="scene-01", start_tick=0, duration_ticks=150),
            scene(scene_id="scene-02", start_tick=100, duration_ticks=150),
        ])


def test_timeline_must_start_at_tick_zero():
    with pytest.raises(ValidationError, match="start|zero|0"):
        timeline(scenes=[scene(start_tick=10)])


def test_contiguous_scenes_are_valid():
    p = plan(timeline_obj=timeline(scenes=[
        scene(scene_id="scene-01", start_tick=0, duration_ticks=100,
              shots=[shot(shot_id="s1", start_tick=0, duration_ticks=100)]),
        scene(scene_id="scene-02", start_tick=100, duration_ticks=150,
              shots=[shot(shot_id="s2", start_tick=100, duration_ticks=150)]),
    ]))
    assert p.timeline.duration_ticks == 250


# --------------------------------------------------------------------------- #
# RP-013 — narração e legendas na timeline
# --------------------------------------------------------------------------- #

def _tracks():
    return [
        Track(track_id="visual-main", kind="visual"),
        Track(track_id="voice", kind="narration"),
        Track(track_id="subs", kind="subtitle"),
    ]


def test_narration_and_subtitles_are_timed_on_the_timeline():
    p = plan(timeline_obj=timeline(
        tracks=_tracks(),
        narration=[NarrationCue(scene_id="scene-01", track_id="voice", source_ref="voice-01",
                                start_tick=0, duration_ticks=250)],
        subtitles=[SubtitleCue(scene_id="scene-01", track_id="subs", text="Olá",
                               start_tick=10, duration_ticks=100)],
    ))
    assert p.timeline.narration[0].source_ref == "voice-01"
    assert p.timeline.subtitles[0].text == "Olá"


def test_narration_cue_must_live_on_a_narration_track():
    with pytest.raises(ValidationError, match="track|narration"):
        timeline(tracks=_tracks(),
                 narration=[NarrationCue(scene_id="scene-01", track_id="visual-main",
                                         source_ref="voice-01", start_tick=0, duration_ticks=250)])


def test_subtitle_cue_must_live_on_a_subtitle_track():
    with pytest.raises(ValidationError, match="track|subtitle"):
        timeline(tracks=_tracks(),
                 subtitles=[SubtitleCue(scene_id="scene-01", track_id="voice", text="x",
                                        start_tick=0, duration_ticks=10)])


def test_cue_referencing_unknown_scene_is_rejected():
    with pytest.raises(ValidationError, match="scene"):
        timeline(tracks=_tracks(),
                 narration=[NarrationCue(scene_id="ghost", track_id="voice", source_ref="voice-01",
                                         start_tick=0, duration_ticks=250)])


def test_narration_source_ref_must_resolve():
    with pytest.raises(ValidationError, match="unknown|media|resolve"):
        plan(timeline_obj=timeline(tracks=_tracks(),
             narration=[NarrationCue(scene_id="scene-01", track_id="voice", source_ref="ghost-voice",
                                     start_tick=0, duration_ticks=250)]))


def test_cues_on_the_same_track_must_not_overlap():
    with pytest.raises(ValidationError, match="overlap"):
        timeline(tracks=_tracks(),
                 narration=[
                     NarrationCue(scene_id="scene-01", track_id="voice", source_ref="voice-01",
                                  start_tick=0, duration_ticks=150),
                     NarrationCue(scene_id="scene-01", track_id="voice", source_ref="voice-01",
                                  start_tick=100, duration_ticks=150),
                 ])


# --------------------------------------------------------------------------- #
# RP-014 — duração, lacunas e alinhamento
# --------------------------------------------------------------------------- #

def test_duration_must_respect_the_output_format_limit():
    big = scene(duration_ticks=25 * 200, shots=[shot(duration_ticks=25 * 200)])
    with pytest.raises(ValidationError, match="limit|above"):
        plan(output=Output(format=VideoFormat.short, width=1080, height=1920),
             timeline_obj=timeline(scenes=[big]))
    long_plan = plan(output=Output(format=VideoFormat.long, width=1920, height=1080),
                     timeline_obj=timeline(scenes=[big]))
    assert long_plan.timeline.duration_ticks == 25 * 200


def test_duration_must_respect_the_minimum():
    short = scene(duration_ticks=25, shots=[shot(duration_ticks=25)])
    with pytest.raises(ValidationError, match="below|minimum|min"):
        plan(timeline_obj=timeline(scenes=[short], narration=[], subtitles=[]))


def test_narration_may_exceed_the_scene_within_one_frame():
    p = plan(timeline_obj=timeline(
        tracks=_tracks(),
        narration=[NarrationCue(scene_id="scene-01", track_id="voice", source_ref="voice-01",
                                start_tick=0, duration_ticks=251)],   # 1 tick além da cena
    ))
    assert p.timeline.duration_ticks == 250


def test_narration_beyond_one_frame_is_rejected():
    with pytest.raises(ValidationError, match="scene|sync|align"):
        plan(timeline_obj=timeline(
            tracks=_tracks(),
            narration=[NarrationCue(scene_id="scene-01", track_id="voice", source_ref="voice-01",
                                    start_tick=0, duration_ticks=260)],
        ))


def test_subtitle_must_stay_inside_its_scene_within_tolerance():
    # tps=25, tolerância de legenda = 0.5 s (12 ticks); a cena termina em 250.
    with pytest.raises(ValidationError, match="scene|align|sync"):
        plan(timeline_obj=timeline(
            tracks=_tracks(),
            narration=[],
            subtitles=[SubtitleCue(scene_id="scene-01", track_id="subs", text="x",
                                   start_tick=300, duration_ticks=10)],
        ))


def test_subtitles_must_follow_the_narration_within_tolerance():
    with pytest.raises(ValidationError, match="sync|narration|align"):
        plan(timeline_obj=timeline(
            tracks=_tracks(),
            narration=[NarrationCue(scene_id="scene-01", track_id="voice", source_ref="voice-01",
                                    start_tick=100, duration_ticks=100)],   # narração 100..200
            subtitles=[SubtitleCue(scene_id="scene-01", track_id="subs", text="x",
                                   start_tick=0, duration_ticks=50)],       # 0..50, fora da narração
        ))


def test_subtitles_within_narration_tolerance_are_accepted():
    p = plan(timeline_obj=timeline(
        tracks=_tracks(),
        narration=[NarrationCue(scene_id="scene-01", track_id="voice", source_ref="voice-01",
                                start_tick=100, duration_ticks=100)],
        subtitles=[SubtitleCue(scene_id="scene-01", track_id="subs", text="x",
                               start_tick=90, duration_ticks=110)],         # 90..200, folga de 10 <= 12.5
    ))
    assert p.timeline.subtitles[0].duration_ticks == 110


# --------------------------------------------------------------------------- #
# Round-trip com a timeline estendida
# --------------------------------------------------------------------------- #

def test_extended_plan_round_trips_through_json_without_loss():
    original = plan(timeline_obj=timeline(
        tracks=_tracks(),
        narration=[NarrationCue(scene_id="scene-01", track_id="voice", source_ref="voice-01",
                                start_tick=0, duration_ticks=250)],
        subtitles=[SubtitleCue(scene_id="scene-01", track_id="subs", text="Olá mundo",
                               start_tick=10, duration_ticks=100)],
    ))
    dumped = original.model_dump_json()
    again = RenderPlan.model_validate_json(dumped)
    assert again == original
    assert again.model_dump_json() == dumped
