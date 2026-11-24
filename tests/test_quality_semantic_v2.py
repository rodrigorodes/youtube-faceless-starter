"""Testes do avaliador semântico aprimorado (Onda 5 / Task 4)."""
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.studio.adapters.quality_semantic import (
    NotVerifiedSemanticChecker,
    TextCoherenceSemanticChecker,
)
from app.studio.domain.contracts import VideoFormat
from app.studio.domain.quality import SemanticResult
from app.studio.domain.render_plan import AssetReference, StyleSnapshot
from app.studio.domain.render_plan_builder import StoryboardScene, build_render_plan

SHA = "d" * 64


def _plan(narration="Narração clara sobre inovação e ciência."):
    scenes = [
        StoryboardScene(
            scene_id="s1",
            asset_id="a1",
            narration=narration,
            speech_seconds=2.0,
            label="CIENCIA",
        )
    ]
    assets = [
        AssetReference(
            asset_id="a1",
            asset_version=1,
            uri="cache/a1.png",
            content_sha256=SHA,
            media_type="image",
            license="CC0",
        )
    ]
    return build_render_plan(
        plan_id="p:sem",
        revision=1,
        project_id="proj_1",
        video_id="vid_1",
        format=VideoFormat.short,
        scenes=scenes,
        assets=assets,
        style_snapshot=StyleSnapshot(style_id="s1", version=1),
        music=False,
    )


def test_not_verified_semantic_checker_returns_honest_gap():
    checker = NotVerifiedSemanticChecker()
    plan = _plan()
    res = checker.check(plan, media_path=Path("fake.mp4"))
    assert res.verdict == "not_verified"
    assert "no semantic/vision provider" in res.reason


def test_text_coherence_checker_without_model_gracefully_degrades():
    checker = TextCoherenceSemanticChecker(text_model=None)
    plan = _plan()
    res = checker.check(plan, media_path=Path("fake.mp4"))
    assert res.verdict == "not_verified"
    assert "no text model" in res.reason.lower() or "not configured" in res.reason.lower()


def test_text_coherence_checker_detects_incoherent_empty_narration():
    # Sem narração ou narração vazia
    checker = TextCoherenceSemanticChecker(text_model=MagicMock())
    plan = _plan(narration="")
    res = checker.check(plan, media_path=Path("fake.mp4"))
    assert res.verdict == "failed"
    assert "narração vazia" in res.reason.lower() or "incoerente" in res.reason.lower()


def test_text_coherence_checker_verifies_valid_narration():
    mock_model = MagicMock()
    mock_model.generate.return_value = MagicMock(text='{"coherent": true, "reason": "Roteiro coerente com o tema"}')
    checker = TextCoherenceSemanticChecker(text_model=mock_model)
    plan = _plan(narration="Narração completa e consistente.")
    res = checker.check(plan, media_path=Path("fake.mp4"))
    assert res.verdict == "verified"
