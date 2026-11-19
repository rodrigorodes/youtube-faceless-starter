import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.storage import cache_path, video_dir  # noqa: E402
from app.studio.domain.ids import InvalidId, asset_cache_key, check_id  # noqa: E402

BAD = ["", "../x", "A" * 32, "a" * 33, "a" * 31 + "/", "a" * 32 + "\n", None, 123]


@pytest.mark.parametrize("bad", BAD)
def test_check_id_rejects_bad_values(bad):
    with pytest.raises(InvalidId):
        check_id(bad)


@pytest.mark.parametrize("bad", BAD)
def test_video_dir_rejects_bad_ids(tmp_path, bad):
    with pytest.raises(InvalidId):
        video_dir(tmp_path, bad, "b" * 32)
    with pytest.raises(InvalidId):
        video_dir(tmp_path, "a" * 32, bad)


def test_video_dir_layout_and_stays_inside_root(tmp_path):
    d = video_dir(tmp_path, "a" * 32, "b" * 32)
    assert d == tmp_path / "projects" / ("a" * 32) / "videos" / ("b" * 32)
    assert tmp_path in d.parents


def test_cache_key_is_stable_and_sensitive():
    base = ("image", "openrouter", "m:free", "palco", {"aspect": "9:16"})
    a = asset_cache_key(*base)
    assert a == asset_cache_key(*base) and len(a) == 64
    assert a != asset_cache_key("image", "openrouter", "m:free", "palco ", {"aspect": "9:16"})
    assert a != asset_cache_key("image", "openrouter", "m:free", "palco", {"aspect": "16:9"})
    assert a == asset_cache_key("image", "openrouter", "m:free", "palco", dict(reversed(list({"aspect": "9:16"}.items()))))


def test_cache_path_layout_and_rejects_bad_key(tmp_path):
    key = asset_cache_key("image", "p", "m", "x", {})
    assert cache_path(tmp_path, key) == tmp_path / "cache" / key[:2] / key
    with pytest.raises(InvalidId):
        cache_path(tmp_path, "../../etc/passwd")
