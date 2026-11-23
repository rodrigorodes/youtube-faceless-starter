import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

import pytest

from app.studio.adapters.render_plan_ffmpeg import _LAYOUT, caption_layout
from app.studio.domain.contracts import VideoFormat
from app.studio.domain.visual_style import (
    ResolvedStyle,
    StylePatchInvalid,
    VisualStyleParamsInvalid,
    clean_params,
    normalize_style_patch,
)


def test_caption_position_validation_and_normalization():
    patch = normalize_style_patch({"caption": {"position": "topo"}})
    assert patch["caption"]["position"] == "top"

    patch_meio = normalize_style_patch({"caption": {"position": "meio"}})
    assert patch_meio["caption"]["position"] == "middle"

    patch_base = normalize_style_patch({"caption": {"position": "base"}})
    assert patch_base["caption"]["position"] == "bottom"

    patch_top = normalize_style_patch({"caption": {"position": "top"}})
    assert patch_top["caption"]["position"] == "top"

    with pytest.raises(Exception):
        normalize_style_patch({"caption": {"position": "diagonal"}})

    with pytest.raises(Exception):
        normalize_style_patch({"caption": {"position": 123}})


def test_clean_params_caption_position():
    params = clean_params({"caption": {"position": "meio", "bottom": 1300}})
    assert params["caption"] == {"position": "middle", "bottom": 1300}

    with pytest.raises(VisualStyleParamsInvalid):
        clean_params({"caption": {"position": "invalido"}})

    with pytest.raises(VisualStyleParamsInvalid):
        clean_params({"caption": {}})


def test_caption_layout_calculates_top_and_middle():
    style_top = ResolvedStyle(id="s1", name="Top", version=1, caption={"position": "top"})
    style_mid = ResolvedStyle(id="s2", name="Mid", version=1, caption={"position": "middle"})
    style_bot = ResolvedStyle(id="s3", name="Bot", version=1, caption={"position": "bottom"})

    lay_top = caption_layout(VideoFormat.short, style_top)
    lay_mid = caption_layout(VideoFormat.short, style_mid)
    lay_bot = caption_layout(VideoFormat.short, style_bot)

    assert lay_top["caption_bottom"] < lay_mid["caption_bottom"] < lay_bot["caption_bottom"]
    assert lay_bot["caption_bottom"] == 1560
    assert lay_top["caption_bottom"] == 480
    assert lay_mid["caption_bottom"] == (1920 // 2) + 120

    # Long format
    lay_top_long = caption_layout(VideoFormat.long, style_top)
    lay_mid_long = caption_layout(VideoFormat.long, style_mid)
    lay_bot_long = caption_layout(VideoFormat.long, style_bot)

    assert lay_top_long["caption_bottom"] < lay_mid_long["caption_bottom"] < lay_bot_long["caption_bottom"]
    assert lay_bot_long["caption_bottom"] == 960
    assert lay_top_long["caption_bottom"] == 300
    assert lay_mid_long["caption_bottom"] == (1080 // 2) + 80


def test_caption_layout_explicit_bottom_overrides_position():
    style_override = ResolvedStyle(
        id="s4",
        name="Override",
        version=1,
        caption={"position": "top", "bottom": 1200},
    )
    lay = caption_layout(VideoFormat.short, style_override)
    assert lay["caption_bottom"] == 1200


def test_caption_layout_defaults_without_position():
    lay = caption_layout(VideoFormat.short, None)
    assert lay["caption_bottom"] == _LAYOUT[VideoFormat.short]["caption_bottom"]

    lay_style_empty = caption_layout(VideoFormat.short, ResolvedStyle())
    assert lay_style_empty["caption_bottom"] == _LAYOUT[VideoFormat.short]["caption_bottom"]
