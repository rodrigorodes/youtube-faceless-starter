import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import JobStatus, PublicationStatus, VideoStatus
from app.studio.domain.panel import CostSummary, Stage, classify, cost_text, is_known_cost, topic_key


def test_topic_key_normalizes_whitespace_case_and_outer_punctuation():
    assert topic_key("  ADE   Lineup! ") == topic_key("ade lineup")
    assert topic_key("Ação e Reação") == topic_key("AÇÃO E REAÇÃO")
    assert topic_key(" ADE... ") == topic_key("ade")
    assert topic_key("tema um") != topic_key("tema dois")


@pytest.mark.parametrize(
    "status,job,step_running,pub,expected",
    [
        (VideoStatus.REJECTED, None, False, None, Stage.REJECTED),
        (VideoStatus.PUBLISHED, None, False, PublicationStatus.UPLOADED, Stage.COMPLETED),
        (VideoStatus.APPROVED, None, False, PublicationStatus.FAILED, Stage.FAILED),
        (VideoStatus.FAILED, None, False, None, Stage.FAILED),
        (VideoStatus.SCRIPTED, JobStatus.RUNNING, False, None, Stage.IN_PRODUCTION),
        (VideoStatus.SCRIPTED, JobStatus.QUEUED, False, None, Stage.IN_PRODUCTION),
        (VideoStatus.SCRIPTED, None, True, None, Stage.IN_PRODUCTION),
        (VideoStatus.APPROVED, None, False, PublicationStatus.UPLOADING, Stage.IN_PRODUCTION),
        (VideoStatus.ASSETS_READY, JobStatus.FAILED, False, None, Stage.FAILED),
        (VideoStatus.RENDERED, None, False, None, Stage.AWAITING_APPROVAL),
        (VideoStatus.AWAITING_APPROVAL, None, False, None, Stage.AWAITING_APPROVAL),
        (VideoStatus.APPROVED, None, False, None, Stage.APPROVED),
        (VideoStatus.APPROVED, None, False, PublicationStatus.PENDING, Stage.APPROVED),
        (VideoStatus.IDEA, None, False, None, Stage.PENDING),
        (VideoStatus.ASSETS_READY, None, False, None, Stage.PENDING),
    ],
)
def test_classify_maps_video_and_background_states_to_operator_stage(status, job, step_running, pub, expected):
    assert classify(status, job=job, step_running=step_running, publication=pub) == expected


def test_is_known_cost_rules():
    assert is_known_cost("opencode", "google/gemini:free", 0.0) is True
    assert is_known_cost("placeholder", "placeholder", 0.0) is True
    assert is_known_cost("demo", "demo", 0.0) is True
    assert is_known_cost("piper", "piper", 0.0) is True
    assert is_known_cost("stock", "stock", 0.0) is True
    assert is_known_cost("opencode", "openai/gpt-4o-mini", 0.0) is False
    assert is_known_cost("opencode", "openai/gpt-4o-mini", 0.02) is True


def test_cost_text_formats_honestly():
    assert cost_text(CostSummary(0.0, 0, 0)) == "sem registro de uso"
    assert cost_text(CostSummary(0.0, 2, 0)) == "US$ 0,00 (gratuito)"
    assert cost_text(CostSummary(0.12, 3, 0)) == "US$ 0,12"
    assert cost_text(CostSummary(0.0, 2, 1)) == "US$ 0,00 + 1 chamada sem custo informado"
    assert cost_text(CostSummary(0.5, 4, 2)) == "US$ 0,50 + 2 chamadas sem custo informado"
