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


def test_caption_font_and_style_kind_validation():
    patch = normalize_style_patch({"caption": {"font_family": "inter", "style_kind": "simples"}})
    assert patch["caption"]["font_family"] == "inter"
    assert patch["caption"]["style_kind"] == "simple"

    patch_caixa = normalize_style_patch({"caption": {"style_kind": "caixa"}})
    assert patch_caixa["caption"]["style_kind"] == "box"

    patch_destaque = normalize_style_patch({"caption": {"style_kind": "destaque"}})
    assert patch_destaque["caption"]["style_kind"] == "word_highlight"

    for fam in ("dejavu", "roboto", "georgia", "inter"):
        p = normalize_style_patch({"caption": {"font_family": fam}})
        assert p["caption"]["font_family"] == fam

    for sk in ("box", "simple", "word_highlight"):
        p = normalize_style_patch({"caption": {"style_kind": sk}})
        assert p["caption"]["style_kind"] == sk

    with pytest.raises(StylePatchInvalid):
        normalize_style_patch({"caption": {"font_family": "comic-sans"}})

    with pytest.raises(StylePatchInvalid):
        normalize_style_patch({"caption": {"font_family": 123}})

    with pytest.raises(StylePatchInvalid):
        normalize_style_patch({"caption": {"style_kind": "neon"}})

    with pytest.raises(StylePatchInvalid):
        normalize_style_patch({"caption": {"style_kind": 123}})


def test_clean_params_caption_font_and_style_kind():
    params = clean_params({"caption": {"font_family": "roboto", "style_kind": "caixa"}})
    assert params["caption"] == {"font_family": "roboto", "style_kind": "box"}

    params_dest = clean_params({"caption": {"style_kind": "destaque"}})
    assert params_dest["caption"] == {"style_kind": "word_highlight"}

    params_simp = clean_params({"caption": {"style_kind": "simples"}})
    assert params_simp["caption"] == {"style_kind": "simple"}

    with pytest.raises(VisualStyleParamsInvalid):
        clean_params({"caption": {"font_family": "helvetica"}})

    with pytest.raises(VisualStyleParamsInvalid):
        clean_params({"caption": {"style_kind": "glow"}})

    with pytest.raises(VisualStyleParamsInvalid):
        clean_params({"caption": {"font_family": 999}})

    with pytest.raises(VisualStyleParamsInvalid):
        clean_params({"caption": {"style_kind": 999}})


def test_caption_layout_passes_font_family_and_style_kind():
    style = ResolvedStyle(
        id="s1",
        name="Styled",
        version=1,
        caption={"font_family": "georgia", "style_kind": "simple"},
    )
    lay = caption_layout(VideoFormat.short, style)
    assert lay.get("font_family") == "georgia"
    assert lay.get("style_kind") == "simple"


def test_caption_overlay_simple_skips_box(tmp_path):
    from PIL import Image
    from app.studio.adapters.render_plan_ffmpeg import caption_overlay

    dst_box = tmp_path / "caption_box.png"
    dst_simple = tmp_path / "caption_simple.png"

    style_box = ResolvedStyle(id="s_box", name="Box", version=1, caption={"style_kind": "box"})
    style_simple = ResolvedStyle(id="s_sim", name="Simple", version=1, caption={"style_kind": "simple"})

    text = "Legenda teste simples"
    caption_overlay(VideoFormat.short, text, dst_box, style_box)
    caption_overlay(VideoFormat.short, text, dst_simple, style_simple)

    assert dst_box.exists()
    assert dst_simple.exists()

    img_box = Image.open(dst_box)
    img_simple = Image.open(dst_simple)

    # In box mode, pixel at (75, 1500) has background box color (alpha > 0)
    assert img_box.getpixel((75, 1500))[3] > 0

    # In simple mode, pixel at (75, 1500) has no background box (alpha == 0, transparent)
    assert img_simple.getpixel((75, 1500)) == (0, 0, 0, 0)


def test_resolve_caption_font_returns_font_and_falls_back():
    from unittest.mock import MagicMock, patch
    from PIL import ImageFont
    from app.studio.adapters.render_plan_ffmpeg import FONT_BOLD, resolve_caption_font

    font = resolve_caption_font("dejavu", 40)
    assert font is not None
    assert isinstance(font, (ImageFont.FreeTypeFont, ImageFont.ImageFont))

    font_none = resolve_caption_font(None, 40)
    assert font_none is not None

    font_unknown = resolve_caption_font("unknown_font_family", 40)
    assert font_unknown is not None

    with patch("PIL.ImageFont.truetype") as mock_truetype:
        fake_font = MagicMock()
        mock_truetype.return_value = fake_font
        result = resolve_caption_font("roboto", 48)
        assert result == fake_font
        assert mock_truetype.called

