import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import ProductionMode, Video, VideoFormat
from app.studio.domain.channel import (
    CREATABLE_FIELDS,
    UPDATABLE_FIELDS,
    ChannelFieldInvalid,
    ChannelProfile,
    validate_production_mode,
    validate_video_format,
)


def test_production_mode_enum_values():
    assert ProductionMode.piloto.value == "piloto"
    assert ProductionMode.diretor.value == "diretor"


def test_channel_profile_defaults_and_validation():
    profile = ChannelProfile(
        id="a" * 32,
        project_id="b" * 32,
        name="Canal Teste",
    )
    assert profile.default_mode is ProductionMode.piloto
    assert profile.default_format is VideoFormat.short

    # Customizado com enum
    custom = ChannelProfile(
        id="a" * 32,
        project_id="b" * 32,
        name="Canal Teste",
        default_mode=ProductionMode.diretor,
        default_format=VideoFormat.long,
    )
    assert custom.default_mode is ProductionMode.diretor
    assert custom.default_format is VideoFormat.long

    # Customizado com string (normalização)
    custom_str = ChannelProfile(
        id="a" * 32,
        project_id="b" * 32,
        name="Canal Teste",
        default_mode="diretor",
        default_format="long",
    )
    assert custom_str.default_mode is ProductionMode.diretor
    assert custom_str.default_format is VideoFormat.long

    # default_mode inválido
    with pytest.raises(ChannelFieldInvalid):
        ChannelProfile(
            id="a" * 32,
            project_id="b" * 32,
            name="Canal Teste",
            default_mode="invalido",
        )

    # default_format inválido
    with pytest.raises(ChannelFieldInvalid):
        ChannelProfile(
            id="a" * 32,
            project_id="b" * 32,
            name="Canal Teste",
            default_format="invalido",
        )

    # Tipos não suportados
    with pytest.raises(ChannelFieldInvalid):
        ChannelProfile(
            id="a" * 32,
            project_id="b" * 32,
            name="Canal Teste",
            default_mode=123,
        )

    with pytest.raises(ChannelFieldInvalid):
        ChannelProfile(
            id="a" * 32,
            project_id="b" * 32,
            name="Canal Teste",
            default_format=None,
        )


def test_validate_helpers():
    assert validate_production_mode(ProductionMode.piloto) is ProductionMode.piloto
    assert validate_production_mode("diretor") is ProductionMode.diretor
    with pytest.raises(ChannelFieldInvalid):
        validate_production_mode("invalido")
    with pytest.raises(ChannelFieldInvalid):
        validate_production_mode(None)

    assert validate_video_format(VideoFormat.short) is VideoFormat.short
    assert validate_video_format("long") is VideoFormat.long
    with pytest.raises(ChannelFieldInvalid):
        validate_video_format("invalido")
    with pytest.raises(ChannelFieldInvalid):
        validate_video_format(None)


def test_creatable_and_updatable_fields_include_preferences():
    assert "default_mode" in CREATABLE_FIELDS
    assert "default_format" in CREATABLE_FIELDS
    assert "default_mode" in UPDATABLE_FIELDS
    assert "default_format" in UPDATABLE_FIELDS


def test_video_production_mode_default_and_custom():
    video = Video(
        id="v" * 32,
        project_id="p" * 32,
        topic="Um tema qualquer",
        format=VideoFormat.short,
    )
    assert video.production_mode is ProductionMode.piloto

    video_diretor = Video(
        id="v" * 32,
        project_id="p" * 32,
        topic="Um tema qualquer",
        format=VideoFormat.short,
        production_mode=ProductionMode.diretor,
    )
    assert video_diretor.production_mode is ProductionMode.diretor

    video_str = Video(
        id="v" * 32,
        project_id="p" * 32,
        topic="Um tema qualquer",
        format=VideoFormat.short,
        production_mode="diretor",
    )
    assert video_str.production_mode is ProductionMode.diretor
