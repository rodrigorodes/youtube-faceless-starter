from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.captions_ass import AssSubtitleRenderer
from app.studio.domain.captions import CaptionLine, WordTiming
from app.studio.domain.contracts import VideoFormat


def test_word_timing_valid():
    wt = WordTiming(word="inteligência", start_ms=100, duration_ms=450)
    assert wt.word == "inteligência"
    assert wt.start_ms == 100
    assert wt.duration_ms == 450


def test_word_timing_validation():
    with pytest.raises(ValidationError):
        WordTiming(word="", start_ms=0, duration_ms=100)

    with pytest.raises(ValidationError):
        WordTiming(word="   ", start_ms=0, duration_ms=100)

    with pytest.raises(ValidationError):
        WordTiming(word="teste", start_ms=-1, duration_ms=100)

    with pytest.raises(ValidationError):
        WordTiming(word="teste", start_ms=0, duration_ms=-10)


def test_word_timing_frozen():
    wt = WordTiming(word="teste", start_ms=0, duration_ms=100)
    with pytest.raises(ValidationError):
        wt.word = "outro"  # type: ignore


def test_caption_line_valid():
    line = CaptionLine(start_ms=0, end_ms=1500, text="Olá mundo")
    assert line.start_ms == 0
    assert line.end_ms == 1500
    assert line.text == "Olá mundo"
    assert line.words == ()


def test_caption_line_with_words():
    w1 = WordTiming(word="Olá", start_ms=0, duration_ms=500)
    w2 = WordTiming(word="mundo", start_ms=500, duration_ms=1000)
    line = CaptionLine(start_ms=0, end_ms=1500, text="Olá mundo", words=[w1, w2])
    assert isinstance(line.words, tuple)
    assert len(line.words) == 2
    assert line.words[0].word == "Olá"
    assert line.words[1].word == "mundo"


def test_caption_line_validation():
    with pytest.raises(ValidationError):
        CaptionLine(start_ms=1000, end_ms=500, text="Invalido")

    with pytest.raises(ValidationError):
        CaptionLine(start_ms=-50, end_ms=500, text="Invalido")

    with pytest.raises(ValidationError):
        CaptionLine(start_ms=0, end_ms=-10, text="Invalido")


def test_caption_line_frozen():
    line = CaptionLine(start_ms=0, end_ms=1000, text="Texto")
    with pytest.raises(ValidationError):
        line.text = "Novo texto"  # type: ignore


def test_ms_to_ass_time():
    assert AssSubtitleRenderer.ms_to_ass_time(0) == "0:00:00.00"
    assert AssSubtitleRenderer.ms_to_ass_time(50) == "0:00:00.05"
    assert AssSubtitleRenderer.ms_to_ass_time(1000) == "0:00:01.00"
    assert AssSubtitleRenderer.ms_to_ass_time(1250) == "0:00:01.25"
    assert AssSubtitleRenderer.ms_to_ass_time(61500) == "0:01:01.50"
    assert AssSubtitleRenderer.ms_to_ass_time(3600000) == "1:00:00.00"
    assert AssSubtitleRenderer.ms_to_ass_time(3661250) == "1:01:01.25"
    assert AssSubtitleRenderer.ms_to_ass_time(-100) == "0:00:00.00"


def test_render_header_short_9_16():
    for fmt in ("short", "9:16", VideoFormat.short):
        ass = AssSubtitleRenderer.render(lines=[], format=fmt)
        assert "[Script Info]" in ass
        assert "PlayResX: 1080" in ass
        assert "PlayResY: 1920" in ass
        assert "[V4+ Styles]" in ass
        assert "&H00FFFFFF" in ass  # PrimaryColour (white)
        assert "&H0000FFFF" in ass  # SecondaryColour (yellow)
        assert "&H00000000" in ass  # OutlineColour (black)
        # Style line format: Fontsize=64, Bold=1, Outline=4, Alignment=2, MarginV=280
        assert ",64,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,4,0,2,10,10,280,1" in ass
        assert "[Events]" in ass
        assert "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text" in ass


def test_render_header_long_16_9():
    for fmt in ("long", "16:9", VideoFormat.long):
        ass = AssSubtitleRenderer.render(lines=[], format=fmt)
        assert "[Script Info]" in ass
        assert "PlayResX: 1920" in ass
        assert "PlayResY: 1080" in ass
        # Style line format: Fontsize=48, Bold=1, Outline=4, Alignment=2, MarginV=60
        assert ",48,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,4,0,2,10,10,60,1" in ass


def test_render_empty_lines():
    ass = AssSubtitleRenderer.render(lines=[], format="short")
    assert "Dialogue:" not in ass
    assert ass.endswith("\n")


def test_render_highlight_karaoke_tags():
    w1 = WordTiming(word="O", start_ms=0, duration_ms=200)
    w2 = WordTiming(word="futuro", start_ms=200, duration_ms=500)
    w3 = WordTiming(word="chegou", start_ms=700, duration_ms=400)
    line = CaptionLine(
        start_ms=0,
        end_ms=1100,
        text="O futuro chegou",
        words=(w1, w2, w3),
    )

    ass = AssSubtitleRenderer.render(lines=[line], format="short", style_kind="highlight")
    assert "Dialogue: 0,0:00:00.00,0:00:01.10,Default,,0,0,0,,{\\k20}O {\\k50}futuro {\\k40}chegou" in ass


def test_render_duration_rounding_and_minimum():
    # duration 4ms -> round(0.4) = 0 -> max(1, 0) = 1 cs
    # duration 15ms -> round(1.5) = 2 cs
    w1 = WordTiming(word="um", start_ms=0, duration_ms=4)
    w2 = WordTiming(word="dois", start_ms=10, duration_ms=15)
    line = CaptionLine(start_ms=0, end_ms=50, text="um dois", words=(w1, w2))

    ass = AssSubtitleRenderer.render(lines=[line], format="short", style_kind="highlight")
    assert "{\\k1}um " in ass
    assert "{\\k2}dois" in ass


def test_render_plain_style_and_no_words():
    # If style_kind != "highlight", plain line.text is used
    w1 = WordTiming(word="Olá", start_ms=0, duration_ms=500)
    line_with_words = CaptionLine(start_ms=0, end_ms=500, text="Olá mundo", words=(w1,))
    ass_plain = AssSubtitleRenderer.render(lines=[line_with_words], format="short", style_kind="plain")
    assert "Dialogue: 0,0:00:00.00,0:00:00.50,Default,,0,0,0,,Olá mundo" in ass_plain
    assert "\\k" not in ass_plain

    # If line.words is empty, plain line.text is used even with style_kind="highlight"
    line_no_words = CaptionLine(start_ms=500, end_ms=1000, text="Texto simples", words=())
    ass_no_words = AssSubtitleRenderer.render(lines=[line_no_words], format="short", style_kind="highlight")
    assert "Dialogue: 0,0:00:00.50,0:00:01.00,Default,,0,0,0,,Texto simples" in ass_no_words
    assert "\\k" not in ass_no_words


def test_render_multiple_lines():
    line1 = CaptionLine(start_ms=0, end_ms=1000, text="Linha um")
    line2 = CaptionLine(start_ms=1000, end_ms=2500, text="Linha dois")
    ass = AssSubtitleRenderer.render(lines=[line1, line2], format="16:9")

    events = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(events) == 2
    assert "0:00:00.00,0:00:01.00,Default,,0,0,0,,Linha um" in events[0]
    assert "0:00:01.00,0:00:02.50,Default,,0,0,0,,Linha dois" in events[1]
