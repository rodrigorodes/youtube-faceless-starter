"""Rollout do caminho de plano (RP-032) — kill-switch/availability, sem dispatch dual.

O legado foi removido (emenda §14 do design): a flag **não** troca para um renderer
antigo — ele não existe. Desligada, o render é recusado de forma explícita, e a volta é o
redeploy da imagem anterior. Este teste fixa isso: a flag é disponibilidade do caminho
novo, não um caminho de rollback em runtime.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.quality_ffmpeg import FfmpegQualityEvaluator  # noqa: E402
from app.studio.adapters.render_disabled import DisabledRenderer, RenderPlanDisabled  # noqa: E402
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer  # noqa: E402
from app.studio.application.config import build  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402


def test_the_flag_defaults_to_enabled_and_the_plan_renderer_is_registered():
    studio = Studio(Settings())
    assert isinstance(studio.quality_evaluator, FfmpegQualityEvaluator)
    assert isinstance(build("renderer", "ffmpeg:rich"), PlanFfmpegRenderer)


def test_disabling_the_flag_refuses_the_render_instead_of_falling_back():
    Studio(Settings(render_plan_enabled=False))
    renderer = build("renderer", "ffmpeg:rich")
    assert isinstance(renderer, DisabledRenderer)
    assert renderer.name == "ffmpeg"  # a identidade do asset de vídeo não muda
    with pytest.raises(RenderPlanDisabled, match="redeploy"):
        renderer.render(spec=None, out_path=Path("out.mp4"))


def test_the_env_flag_parses_on_and_off_with_enabled_as_default():
    assert Settings.from_env({}).render_plan_enabled is True
    assert Settings.from_env({"STUDIO_RENDER_PLAN_ENABLED": "1"}).render_plan_enabled is True
    assert Settings.from_env({"STUDIO_RENDER_PLAN_ENABLED": "0"}).render_plan_enabled is False
    assert Settings.from_env({"STUDIO_RENDER_PLAN_ENABLED": "false"}).render_plan_enabled is False
