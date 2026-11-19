import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import (  # noqa: E402
    Asset, AssetKind, Project, UsageEntry, Video, VideoFormat, VideoStatus, load_versioned,
)


def test_video_defaults_are_private_and_new():
    v = Video(id="a" * 32, project_id="b" * 32, topic="ADE 2026", format=VideoFormat.short)
    assert v.privacy == "private" and v.status == VideoStatus.IDEA and v.schema_version == 1


def test_asset_requires_license():
    with pytest.raises(ValidationError):
        Asset(id="a" * 32, kind=AssetKind.image, cache_key="c" * 64, path="x", provider="p", model="m", license="", cost_usd=0)


def test_usage_rejects_negative_and_nan_cost():
    for bad in (-0.01, float("nan")):
        with pytest.raises(ValidationError):
            UsageEntry(step="script", provider="p", model="m", cost_usd=bad)


def test_usage_keeps_cache_tokens_separate_and_nullable():
    u = UsageEntry(step="script", provider="p", model="m", input_tokens=10, output_tokens=5, cost_usd=0)
    assert u.cache_read_tokens is None and u.cache_write_tokens is None


def test_load_versioned_rejects_unknown_version():
    with pytest.raises(ValueError, match="schema_version"):
        load_versioned(Project, {"schema_version": 2, "id": "a" * 32, "name": "x"})


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Project(id="a" * 32, name="x", surprise=1)


def test_project_config_defaults_empty():
    assert Project(id="a" * 32, name="x").config == {}
