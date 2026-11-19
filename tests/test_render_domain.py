import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.render import (  # noqa: E402
    FPS, LEAD, MAX_SECONDS, TAIL, Cue, evaluate_qa, make_cues, scene_length, split_chunks, to_srt, to_srt_time,
)


def test_scene_length_is_whole_frames_and_covers_lead_speech_tail():
    for speech in (0.1, 1.0, 3.337, 12.9):
        length = scene_length(speech)
        assert length >= LEAD + speech + TAIL - 1e-9 and abs(length * FPS - round(length * FPS)) < 1e-9


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_blank_text_has_no_chunks(text):
    assert split_chunks(text) == []


def test_chunks_respect_max_chars_and_keep_every_word_in_order():
    text = "O Amsterdam Dance Event celebrou 30 anos e tomou conta da cidade com mais de 3.600 artistas, 1.300 eventos e 300 espaços. Foi enorme!"
    chunks = split_chunks(text, max_chars=42)
    assert all(0 < len(c) <= 42 for c in chunks) and len(chunks) >= 3
    assert " ".join(chunks).split() == text.split()


def test_chunks_prefer_sentence_and_clause_boundaries():
    chunks = split_chunks("Primeira frase curta. Segunda frase também curta, com vírgula e mais palavras aqui.", max_chars=45)
    assert chunks[0] == "Primeira frase curta." and chunks[1].startswith("Segunda")


def test_a_single_huge_word_is_still_cut_to_max_chars():
    assert all(len(c) <= 10 for c in split_chunks("x" * 35, max_chars=10)) and "".join(split_chunks("x" * 35, max_chars=10)) == "x" * 35


def test_cues_are_proportional_inside_the_speech_window_and_do_not_overlap():
    cues = make_cues("Uma frase curta. Outra frase bem mais comprida que a primeira, com muito mais texto.", start=10.0, speech_seconds=6.0, max_chars=40)
    assert cues[0].start == pytest.approx(10.0 + LEAD) and cues[-1].end == pytest.approx(10.0 + LEAD + 6.0)
    assert all(a.end <= b.start + 1e-9 for a, b in zip(cues, cues[1:])) and all(c.end > c.start for c in cues)
    lengths = [len(c.text) for c in cues]
    durations = [c.end - c.start for c in cues]
    ratio = [d / n for d, n in zip(durations, lengths)]
    assert max(ratio) - min(ratio) < 1e-6  # tempo proporcional ao número de caracteres


def test_srt_format_numbering_and_time():
    assert to_srt_time(3723.456) == "01:02:03,456" and to_srt_time(0) == "00:00:00,000" and to_srt_time(59.9996) == "00:01:00,000"
    srt = to_srt([Cue(0.3, 2.5, "Olá, mundo."), Cue(2.5, 4.0, "Segunda linha.")])
    assert srt == "1\n00:00:00,300 --> 00:00:02,500\nOlá, mundo.\n\n2\n00:00:02,500 --> 00:00:04,000\nSegunda linha.\n"
    assert to_srt([]) == ""


def test_limits_by_format():
    assert MAX_SECONDS[VideoFormat.short] == 175 and MAX_SECONDS[VideoFormat.long] > 175


GOOD = dict(duration_s=30.0, expected_s=30.0, width=1080, height=1920, has_audio=True, integrated_lufs=-16.0, silence_ratio=0.2, black_ratio=0.0)


def qa(fmt=VideoFormat.short, **kw):
    return evaluate_qa({**GOOD, **kw}, fmt)


def test_good_video_passes_and_keeps_metrics():
    r = qa()
    assert r.passed and r.failures == [] and r.metrics["integrated_lufs"] == -16.0


@pytest.mark.parametrize("kw,needle", [
    ({"has_audio": False, "integrated_lufs": None}, "audio"),
    ({"integrated_lufs": None}, "silent"),
    ({"integrated_lufs": -60.0}, "silent"),
    ({"silence_ratio": 0.9}, "silence"),
    ({"black_ratio": 0.5}, "black"),
    ({"duration_s": 200.0, "expected_s": 200.0}, "duration"),
    ({"duration_s": 1.0, "expected_s": 1.0}, "duration"),
    ({"duration_s": 33.0}, "expected"),
    ({"width": 1920, "height": 1080}, "resolution"),
    ({"integrated_lufs": -5.0}, "loud"),
])
def test_qa_failures(kw, needle):
    r = qa(**kw)
    assert not r.passed and any(needle in f for f in r.failures)


def test_long_format_uses_landscape_and_longer_limit():
    assert qa(VideoFormat.long, width=1920, height=1080, duration_s=600.0, expected_s=600.0).passed
    assert not qa(VideoFormat.long, width=1080, height=1920, duration_s=600.0, expected_s=600.0).passed
    assert not qa(VideoFormat.long, width=1920, height=1080, duration_s=MAX_SECONDS[VideoFormat.long] + 5, expected_s=MAX_SECONDS[VideoFormat.long] + 5).passed


def test_missing_metric_fails_closed():
    r = evaluate_qa({"duration_s": 30.0}, VideoFormat.short)
    assert not r.passed and r.failures
