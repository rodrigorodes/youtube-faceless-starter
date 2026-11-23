import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import VideoStatus  # noqa: E402
from app.studio.domain.states import (  # noqa: E402
    VIDEO_TRANSITIONS, InvalidTransition, assert_transition, can_transition, to_mermaid,
)


def test_cannot_publish_without_approval():
    assert not can_transition(VideoStatus.RENDERED, VideoStatus.APPROVED)
    assert not can_transition(VideoStatus.AWAITING_APPROVAL, VideoStatus.PUBLISHED)
    assert not can_transition(VideoStatus.FAILED, VideoStatus.PUBLISHED)
    assert not can_transition(VideoStatus.FAILED, VideoStatus.APPROVED)


def test_only_awaiting_approval_can_be_approved_or_rejected():
    for s in VideoStatus:
        assert can_transition(s, VideoStatus.APPROVED) == (s == VideoStatus.AWAITING_APPROVAL)
        assert can_transition(s, VideoStatus.REJECTED) == (s == VideoStatus.AWAITING_APPROVAL)


def test_only_approved_can_be_published():
    for s in VideoStatus:
        assert can_transition(s, VideoStatus.PUBLISHED) == (s == VideoStatus.APPROVED)


def test_approved_can_reopen_for_editing_but_published_cannot():
    assert can_transition(VideoStatus.APPROVED, VideoStatus.SCRIPTED)
    assert can_transition(VideoStatus.APPROVED, VideoStatus.PUBLISHED)
    assert not can_transition(VideoStatus.PUBLISHED, VideoStatus.SCRIPTED)
    assert not can_transition(VideoStatus.PUBLISHED, VideoStatus.APPROVED)


def test_terminal_states_have_no_exit():
    assert VIDEO_TRANSITIONS[VideoStatus.PUBLISHED] == frozenset()
    assert VIDEO_TRANSITIONS[VideoStatus.REJECTED] == frozenset()


def test_every_status_has_an_entry_and_no_self_loop():
    assert set(VIDEO_TRANSITIONS) == set(VideoStatus)
    assert all(s not in nxt for s, nxt in VIDEO_TRANSITIONS.items())


def test_failed_can_resume_only_before_approval():
    resumable = VIDEO_TRANSITIONS[VideoStatus.FAILED]
    assert VideoStatus.RENDERED in resumable and VideoStatus.IDEA in resumable
    assert not resumable & {VideoStatus.APPROVED, VideoStatus.PUBLISHED, VideoStatus.REJECTED, VideoStatus.AWAITING_APPROVAL}


def test_assert_transition_raises():
    with pytest.raises(InvalidTransition):
        assert_transition(VideoStatus.IDEA, VideoStatus.PUBLISHED)
    assert_transition(VideoStatus.IDEA, VideoStatus.SCRIPTED)


def test_mermaid_mentions_every_status_and_is_deterministic():
    text = to_mermaid()
    assert all(s.value in text for s in VideoStatus) and text == to_mermaid()


def test_pedir_ajustes_reopens_a_rendered_or_awaiting_version_but_nothing_else():
    """"Pedir ajustes" (Qualidade): só versões renderizadas, em revisão ou aprovadas voltam à edição."""
    reopenable = {s for s in VideoStatus if can_transition(s, VideoStatus.SCRIPTED) and s not in
                  (VideoStatus.IDEA, VideoStatus.FAILED)}
    assert reopenable == {VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL, VideoStatus.APPROVED}
    assert not can_transition(VideoStatus.PUBLISHED, VideoStatus.SCRIPTED)
    assert not can_transition(VideoStatus.REJECTED, VideoStatus.SCRIPTED)
