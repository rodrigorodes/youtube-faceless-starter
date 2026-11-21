import math
import unicodedata

import pytest

from app.studio.domain.contracts import Scene
from app.studio.domain.narration_duration import (
    MEASURED_PAUSE_SECONDS,
    MEASURED_SPEECH_WORDS_PER_MINUTE,
    MEASURED_UTTERANCE_OVERHEAD_SECONDS,
    estimate_narration_durations,
    estimate_voice_durations,
)


def scene(idx, narration, duration_s=None):
    return Scene(
        id=f"scene-{idx}", video_id="video", idx=idx, narration=narration,
        image_prompt="imagem de exemplo", duration_s=duration_s,
    )


def test_estimates_each_scene_and_total_without_modifying_scenes():
    scenes = [scene(0, "Olá, mundo! Tudo bem?", 99), scene(1, "Uma história de ação.")]

    result = estimate_narration_durations(scenes, words_per_minute=120)

    assert result.scene_seconds == pytest.approx((2.0, 2.0))
    assert result.total_seconds == pytest.approx(4.0)
    assert scenes[0].duration_s == 99
    assert scenes[1].duration_s is None


def test_unicode_hyphens_apostrophes_numbers_and_punctuation():
    scenes = [scene(0, "Ação: guarda-chuva, d'água e 2026...")]

    result = estimate_narration_durations(scenes, words_per_minute=60)

    assert result.scene_seconds == pytest.approx((5.0,))


def test_canonically_equivalent_portuguese_text_has_same_duration():
    composed = "ação coração pão"
    decomposed = unicodedata.normalize("NFD", composed)
    result = estimate_narration_durations(
        [scene(0, composed), scene(1, decomposed)], words_per_minute=60,
    )

    assert result.scene_seconds == pytest.approx((3.0, 3.0))
    assert result.total_seconds == pytest.approx(6.0)


def test_total_sums_different_scene_durations():
    result = estimate_narration_durations(
        [scene(0, "Uma palavra"), scene(1, "Uma cena com quatro")], 60,
    )

    assert result.scene_seconds == pytest.approx((2.0, 4.0))
    assert result.total_seconds == pytest.approx(6.0)


def test_empty_scenes_and_punctuation_only_are_zero():
    assert estimate_narration_durations([], 100).total_seconds == 0
    assert estimate_narration_durations([scene(0, " ... ! ")], 100).scene_seconds == (0,)


def test_configurable_fractional_rate():
    result = estimate_narration_durations([scene(0, "Um dois três")], 72.5)

    assert result.total_seconds == pytest.approx(180 / 72.5)


@pytest.mark.parametrize("rate", [0, -1, math.inf, -math.inf, math.nan, True, "120", None])
def test_invalid_rate_is_rejected_even_without_scenes(rate):
    with pytest.raises(ValueError):
        estimate_narration_durations([], rate)


def test_unrepresentable_duration_is_rejected():
    with pytest.raises(ValueError):
        estimate_narration_durations([scene(0, "cinco")], 5e-324)


def test_overflow_in_total_is_rejected_when_each_scene_is_finite():
    scenes = [scene(0, "cinco"), scene(1, "cinco"), scene(2, "cinco"), scene(3, "cinco")]
    assert math.isfinite(estimate_narration_durations(scenes[:1], 1e-306).total_seconds)

    with pytest.raises(ValueError):
        estimate_narration_durations(scenes, 1e-306)


# --- modelo medido do Piper (F4-03, calibração real) --------------------------

def test_voice_model_adds_measured_overhead_rate_and_pauses():
    result = estimate_voice_durations(["um dois três quatro cinco, seis"])

    expected = (
        MEASURED_UTTERANCE_OVERHEAD_SECONDS
        + 6 * 60 / MEASURED_SPEECH_WORDS_PER_MINUTE
        + MEASURED_PAUSE_SECONDS
    )
    assert result.scene_seconds == pytest.approx((expected,))
    assert result.total_seconds == pytest.approx(expected)


def test_voice_model_pays_overhead_per_synthesis_and_counts_punctuation_runs_once():
    result = estimate_voice_durations(["Um, dois! Três...", "Quatro?"])

    first = (
        MEASURED_UTTERANCE_OVERHEAD_SECONDS
        + 3 * 60 / MEASURED_SPEECH_WORDS_PER_MINUTE
        + 3 * MEASURED_PAUSE_SECONDS  # vírgula, exclamação, reticências
    )
    second = MEASURED_UTTERANCE_OVERHEAD_SECONDS + 60 / MEASURED_SPEECH_WORDS_PER_MINUTE + MEASURED_PAUSE_SECONDS
    assert result.scene_seconds == pytest.approx((first, second))
    assert result.total_seconds == pytest.approx(first + second)


def test_voice_model_of_silence_is_the_synthesis_overhead_only():
    assert estimate_voice_durations([]).total_seconds == 0
    assert estimate_voice_durations([" ... ! "]).total_seconds == pytest.approx(MEASURED_UTTERANCE_OVERHEAD_SECONDS)
