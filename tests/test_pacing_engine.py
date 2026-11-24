import pytest
from pydantic import ValidationError

from app.studio.domain.pacing import (
    Motion,
    PacingEngine,
    PacingPlan,
    PacingPreset,
    ShotTiming,
)


class TestPacingModels:
    def test_shot_timing_immutability_and_defaults(self):
        shot = ShotTiming(shot_index=0, start_tick=0, duration_ticks=75)
        assert shot.shot_index == 0
        assert shot.start_tick == 0
        assert shot.duration_ticks == 75
        assert shot.motion == "none"

        with pytest.raises(ValidationError):
            shot.duration_ticks = 100  # frozen

    def test_pacing_plan_properties(self):
        s0 = ShotTiming(shot_index=0, start_tick=0, duration_ticks=60, motion="zoom_in")
        s1 = ShotTiming(shot_index=1, start_tick=60, duration_ticks=60, motion="zoom_out")
        plan = PacingPlan(scene_id="scene_1", shots=(s0, s1), total_duration_ticks=120)

        assert plan.scene_id == "scene_1"
        assert len(plan.shots) == 2
        assert plan.target_shot_durations_ticks == (60, 60)
        assert plan.transition_points_ticks == (60,)
        assert plan.total_duration_ticks == 120

        with pytest.raises(ValidationError):
            plan.scene_id = "scene_2"  # frozen


class TestPacingEngineValidations:
    def test_invalid_duration_ticks(self):
        with pytest.raises(ValueError, match="total_duration_ticks"):
            PacingEngine.calculate(scene_id="s1", total_duration_ticks=0, ticks_per_second=30)
        with pytest.raises(ValueError, match="total_duration_ticks"):
            PacingEngine.calculate(scene_id="s1", total_duration_ticks=-10, ticks_per_second=30)

    def test_invalid_ticks_per_second(self):
        with pytest.raises(ValueError, match="ticks_per_second"):
            PacingEngine.calculate(scene_id="s1", total_duration_ticks=100, ticks_per_second=0)
        with pytest.raises(ValueError, match="ticks_per_second"):
            PacingEngine.calculate(scene_id="s1", total_duration_ticks=100, ticks_per_second=-30)

    def test_invalid_asset_count(self):
        with pytest.raises(ValueError, match="asset_count"):
            PacingEngine.calculate(scene_id="s1", total_duration_ticks=100, ticks_per_second=30, asset_count=0)

    def test_invalid_preset_string(self):
        with pytest.raises(ValueError):
            PacingEngine.calculate(
                scene_id="s1",
                total_duration_ticks=100,
                ticks_per_second=30,
                preset="ultra_fast",
            )


class TestPacingEngineExactDurations:
    @pytest.mark.parametrize("fps", [24, 25, 30, 60])
    @pytest.mark.parametrize("seconds", [1.0, 2.5, 3.5, 5.0, 7.3, 10.0])
    def test_exact_duration_preservation_across_framerates(self, fps: int, seconds: float):
        total_ticks = int(seconds * fps)
        if total_ticks <= 0:
            return
        plan = PacingEngine.calculate(
            scene_id="s_fps",
            total_duration_ticks=total_ticks,
            ticks_per_second=fps,
            preset=PacingPreset.dynamic,
        )
        assert sum(s.duration_ticks for s in plan.shots) == total_ticks
        assert plan.total_duration_ticks == total_ticks

        current = 0
        for s in plan.shots:
            assert s.start_tick == current
            current += s.duration_ticks
        assert current == total_ticks

    @pytest.mark.parametrize("prime_ticks", [31, 71, 101, 337, 1009, 30007])
    def test_exact_remainder_absorption_with_prime_ticks(self, prime_ticks: int):
        plan = PacingEngine.calculate(
            scene_id="s_prime",
            total_duration_ticks=prime_ticks,
            ticks_per_second=30,
            asset_count=3,
        )
        assert sum(s.duration_ticks for s in plan.shots) == prime_ticks
        assert plan.total_duration_ticks == prime_ticks
        assert plan.shots[0].start_tick == 0
        assert plan.shots[-1].start_tick + plan.shots[-1].duration_ticks == prime_ticks


class TestPacingEngineSingleAssetSplit:
    def test_short_single_image_keeps_single_shot(self):
        # 3.0s at 30 fps = 90 ticks (<= 3.5s) -> 1 shot
        plan = PacingEngine.calculate(
            scene_id="s_short",
            total_duration_ticks=90,
            ticks_per_second=30,
            asset_count=1,
            is_video_asset=False,
            preset=PacingPreset.dynamic,
        )
        assert len(plan.shots) == 1
        assert plan.shots[0].motion == "zoom_in"
        assert plan.shots[0].duration_ticks == 90
        assert plan.shots[0].start_tick == 0

    def test_long_single_image_splits_with_alternating_motion(self):
        # 6.0s at 30 fps = 180 ticks (> 3.5s) in dynamic (target 2.5s) -> ceil(6.0/2.5) = 3 shots
        plan = PacingEngine.calculate(
            scene_id="s_long",
            total_duration_ticks=180,
            ticks_per_second=30,
            asset_count=1,
            is_video_asset=False,
            preset=PacingPreset.dynamic,
        )
        assert len(plan.shots) == 3
        expected_motions = ["zoom_in", "zoom_out", "pan_left"]
        assert [s.motion for s in plan.shots] == expected_motions
        assert sum(s.duration_ticks for s in plan.shots) == 180

    def test_four_shots_single_image_cycles_through_all_motions(self):
        # 10.0s at 30 fps = 300 ticks in dynamic -> ceil(10.0/2.5) = 4 shots
        plan = PacingEngine.calculate(
            scene_id="s_four",
            total_duration_ticks=300,
            ticks_per_second=30,
            asset_count=1,
            is_video_asset=False,
            preset=PacingPreset.dynamic,
        )
        assert len(plan.shots) == 4
        expected_motions = ["zoom_in", "zoom_out", "pan_left", "pan_right"]
        assert [s.motion for s in plan.shots] == expected_motions


class TestPacingEngineVideoAsset:
    def test_single_video_asset_preserves_single_shot_without_motion(self):
        # 5.0s single video asset -> kept as 1 shot with motion="none"
        plan = PacingEngine.calculate(
            scene_id="s_video",
            total_duration_ticks=150,
            ticks_per_second=30,
            asset_count=1,
            is_video_asset=True,
            preset=PacingPreset.dynamic,
        )
        assert len(plan.shots) == 1
        assert plan.shots[0].motion == "none"
        assert plan.shots[0].duration_ticks == 150

    def test_multi_video_assets_distribute_with_no_motion(self):
        # 6.0s with 3 video assets -> 3 shots, all motion="none"
        plan = PacingEngine.calculate(
            scene_id="s_multi_video",
            total_duration_ticks=180,
            ticks_per_second=30,
            asset_count=3,
            is_video_asset=True,
            preset=PacingPreset.dynamic,
        )
        assert len(plan.shots) == 3
        for shot in plan.shots:
            assert shot.motion == "none"
        assert sum(s.duration_ticks for s in plan.shots) == 180


class TestPacingEngineMultiAssetDistribution:
    def test_multi_assets_evenly_distributed(self):
        # 7.5s with 3 assets at 30 fps = 225 ticks -> 3 shots of 75 ticks
        plan = PacingEngine.calculate(
            scene_id="s_multi",
            total_duration_ticks=225,
            ticks_per_second=30,
            asset_count=3,
            preset=PacingPreset.dynamic,
        )
        assert len(plan.shots) == 3
        assert [s.duration_ticks for s in plan.shots] == [75, 75, 75]
        assert [s.motion for s in plan.shots] == ["zoom_in", "zoom_out", "pan_left"]

    def test_excess_assets_capped_by_minimum_duration(self):
        # 3.0s with 5 assets in dynamic (min 1.5s): max_shots = 3.0 // 1.5 = 2 shots
        plan = PacingEngine.calculate(
            scene_id="s_capped",
            total_duration_ticks=90,
            ticks_per_second=30,
            asset_count=5,
            preset=PacingPreset.dynamic,
        )
        assert len(plan.shots) == 2
        assert sum(s.duration_ticks for s in plan.shots) == 90
        for s in plan.shots:
            assert s.duration_ticks >= int(1.5 * 30)


class TestPacingEnginePresets:
    def test_preset_differentiation_on_six_second_scene(self):
        # 6.0s at 30 fps = 180 ticks
        # Dynamic (target 2.5s, max 3.5s) -> 3 shots
        dyn = PacingEngine.calculate("s_dyn", 180, 30, asset_count=1, preset=PacingPreset.dynamic)
        # Balanced (target 3.5s, max 5.0s) -> 2 shots
        bal = PacingEngine.calculate("s_bal", 180, 30, asset_count=1, preset=PacingPreset.balanced)
        # Cinematic (target 5.0s, max 8.0s) -> 1 shot
        cin = PacingEngine.calculate("s_cin", 180, 30, asset_count=1, preset=PacingPreset.cinematic)

        assert len(dyn.shots) == 3
        assert len(bal.shots) == 2
        assert len(cin.shots) == 1

    def test_preset_as_string(self):
        plan_str = PacingEngine.calculate("s_str", 150, 30, preset="dynamic")
        plan_enum = PacingEngine.calculate("s_enum", 150, 30, preset=PacingPreset.dynamic)
        assert len(plan_str.shots) == len(plan_enum.shots)
