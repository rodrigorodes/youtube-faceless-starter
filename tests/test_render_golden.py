"""Golden de render (VE-00): determinismo na mesma versão + paridade audiovisual sem overlays.

Roda só no container do renderer (``scripts/test-container.sh``): sem ffmpeg o teste é pulado.
O envelope esperado fica em ``tests/golden/render_baseline.json``; os critérios estão em
``tests/golden_render.py``. Não compara digest nem hash de MP4 entre versões do código (D4).
"""
import json
import shutil
from pathlib import Path

import pytest

import golden_render as g

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe not installed"
)
BASELINE = json.loads((Path(__file__).parent / "golden" / "render_baseline.json").read_text(encoding="utf-8"))


def test_baseline_declares_every_case_and_only_those():
    assert set(BASELINE["cases"]) == set(g.CASES)


@needs_ffmpeg
@pytest.mark.parametrize("name", sorted(g.CASES))
def test_same_version_same_case_is_deterministic(name):
    first, second = g.render_case(name), g.render_case(name)
    assert first["digest"] == second["digest"], "o plano de execução compilado mudou entre duas execuções"
    assert first["media"] == second["media"], "a assinatura ffprobe/QA mudou entre duas execuções"


@needs_ffmpeg
@pytest.mark.parametrize("name", sorted(g.CASES))
def test_render_without_overlays_keeps_audiovisual_parity(name):
    actual = g.render_case(name)["media"]
    assert g.compare(BASELINE["cases"][name], actual) == []


def test_compare_flags_each_kind_of_regression():
    base = dict(BASELINE["cases"]["short_1scene_music"])
    assert g.compare(base, dict(base)) == []
    assert g.compare(base, {**base, "frames": base["frames"] + 1})
    assert g.compare(base, {**base, "has_audio": False})
    assert g.compare(base, {**base, "duration_s": base["duration_s"] + 1})
    assert g.compare(base, {**base, "integrated_lufs": base["integrated_lufs"] - 5})
    assert g.compare(base, {**base, "integrated_lufs": None})
    assert g.compare(base, {**base, "black_ratio": 0.5})
    assert g.compare(base, {**base, "width": base["width"] - 2})
