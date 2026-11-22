"""Domínio long-form (F4-02..F4-08): estrutura por blocos, revisão determinística,
hash de conteúdo, aprovação por versão e propagação de invalidação. Sem I/O, sem provedor."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import Scene  # noqa: E402
from app.studio.domain.longform import (  # noqa: E402
    Block,
    Chapter,
    DownstreamOutput,
    ScriptApproval,
    ScriptPlan,
    approval_is_current,
    chapter_for_position,
    invalidated_outputs,
    plan_content_hash,
    review_script,
    validate_structure,
    with_chapter_scene_delta,
)
from app.studio.domain.narration_duration import estimate_text_durations  # noqa: E402

VIDEO = "a" * 32


def chapter(title, block, scenes, seconds, references=()):
    return Chapter(title=title, block=block, scene_count=scenes, target_seconds=seconds, references=tuple(references))


def plan(*chapters, wpm=150.0, target=480.0):
    return ScriptPlan(words_per_minute=wpm, target_seconds=target, chapters=tuple(chapters))


def scene(idx, narration, claim_ids=("c1",)):
    return Scene(id=f"{idx:032x}", video_id=VIDEO, idx=idx, narration=narration,
                 image_prompt="wide empty stage with colored lights", claim_ids=list(claim_ids))


GOOD_PLAN = plan(
    chapter("Abertura", Block.HOOK, 2, 60, ["c1"]),
    chapter("Contexto", Block.CONTEXT, 3, 120, ["c1"]),
    chapter("Desenvolvimento", Block.DEVELOPMENT, 5, 200, ["c1"]),
    chapter("Payoff e convite", Block.CTA, 2, 100, ["c1"]),
)


# --- estrutura por blocos (F4-02) ---------------------------------------------


def test_plan_requires_hook_and_closing_block_in_order():
    validate_structure(GOOD_PLAN)
    missing_hook = plan(chapter("Contexto", Block.CONTEXT, 1, 60),
                        chapter("Payoff", Block.PAYOFF, 1, 60))
    with pytest.raises(ValueError):
        validate_structure(missing_hook)
    missing_close = plan(chapter("Abertura", Block.HOOK, 1, 60),
                         chapter("Desenvolvimento", Block.DEVELOPMENT, 1, 60))
    with pytest.raises(ValueError):
        validate_structure(missing_close)


def test_plan_rejects_scene_count_outside_the_long_form_range():
    too_short = plan(chapter("Abertura", Block.HOOK, 1, 30), chapter("Payoff", Block.CTA, 1, 30))
    with pytest.raises(ValueError):
        validate_structure(too_short)
    assert GOOD_PLAN.scene_count == 12


def test_plan_rejects_non_finite_or_non_positive_pacing():
    with pytest.raises(ValueError):
        plan(chapter("Abertura", Block.HOOK, 8, 60), chapter("Payoff", Block.CTA, 4, 60), wpm=0.0)
    with pytest.raises(ValueError):
        plan(chapter("Abertura", Block.HOOK, 8, 60), chapter("Payoff", Block.CTA, 4, 60), wpm=float("nan"))


# --- duração configurável reutilizando a contagem existente (F4-03) -----------


def test_estimate_text_durations_reuses_word_counting():
    estimate = estimate_text_durations(["um dois tres quatro", "cinco seis"], 60.0)
    assert estimate.scene_seconds == (4.0, 2.0) and estimate.total_seconds == 6.0
    with pytest.raises(ValueError):
        estimate_text_durations(["um"], 0.0)


# --- revisão determinística (F4-05) -------------------------------------------


def test_review_accepts_a_coherent_script():
    sources = ["Fatos: " + " ".join(str(i) for i in range(12)) + " unidades."]
    body = " ".join(["ha"] * 100)
    scenes = [scene(i, f"{body} cena {i}.") for i in range(12)]
    review = review_script(GOOD_PLAN, scenes, sources=sources,
                           known_claim_ids={"c1"}, tolerance=0.30)
    assert review.passed
    assert review.estimated_seconds >= 400
    assert review.continuity_ok and review.structure_ok
    assert review.redundant_scene_idxs == ()
    assert review.unsupported == ()


def test_review_flags_redundant_scenes_and_citation_gaps():
    scenes = [scene(i, "Narracao repetida igual.") for i in range(12)]
    scenes[0] = scene(0, "Narracao repetida igual.", claim_ids=())
    review = review_script(GOOD_PLAN, scenes, sources=[], known_claim_ids={"c1"}, tolerance=0.90)
    assert not review.passed
    assert review.redundant_scene_idxs  # cenas iguais detectadas
    assert 0 in review.uncited_scene_idxs


def test_review_flags_invented_numbers_and_unknown_claims():
    scenes = [scene(i, "A empresa gastou 9999 unidades em 2026.") for i in range(12)]
    for i, item in enumerate(scenes):
        scenes[i] = scene(i, item.narration, claim_ids=("ghost",))
    review = review_script(GOOD_PLAN, scenes, sources=["A empresa existe."],
                           known_claim_ids={"c1"}, tolerance=0.99)
    assert not review.passed
    assert review.unknown_claim_ids == ("ghost",)
    assert any(item.kind == "number" and item.value == "9999" for item in review.unsupported)


def test_review_flags_duration_out_of_tolerance_and_broken_continuity():
    short_plan = plan(chapter("Abertura", Block.HOOK, 8, 60), chapter("Payoff", Block.CTA, 4, 60))
    scenes = [scene(i, "curto") for i in range(5)]  # 5 != 12
    review = review_script(short_plan, scenes, sources=[], known_claim_ids={"c1"}, tolerance=0.05)
    assert not review.continuity_ok and not review.duration_ok and not review.passed


# --- hash e aprovação por versão (F4-06) --------------------------------------


def test_plan_content_hash_is_stable_and_changes_with_content():
    scenes = [scene(i, f"Texto {i}") for i in range(3)]
    a = plan_content_hash(GOOD_PLAN, scenes)
    assert len(a) == 64 and a == plan_content_hash(GOOD_PLAN, list(scenes))
    changed = list(scenes)
    changed[2] = scene(2, "Texto diferente")
    assert plan_content_hash(GOOD_PLAN, changed) != a


def test_approval_is_bound_to_version_and_hash():
    approval = ScriptApproval(video_id=VIDEO, script_version=2, content_hash="f" * 64,
                              decision="approved", approved_by="operador",
                              approved_at=datetime.now(timezone.utc))
    assert approval_is_current(approval, version=2, content_hash="f" * 64)
    assert not approval_is_current(approval, version=2, content_hash="e" * 64)
    assert not approval_is_current(approval, version=3, content_hash="f" * 64)


def test_rejected_approval_requires_a_reason():
    with pytest.raises(ValueError):
        ScriptApproval(video_id=VIDEO, script_version=1, content_hash="f" * 64,
                       decision="rejected", approved_by="operador")


# --- propagação de invalidação (F4-08) ----------------------------------------


def test_editing_the_script_invalidates_only_downstream_outputs():
    invalidated = invalidated_outputs(DownstreamOutput.SCRIPT)
    assert invalidated == frozenset({
        DownstreamOutput.FACT_CHECK, DownstreamOutput.STORYBOARD, DownstreamOutput.ASSETS,
        DownstreamOutput.RENDER, DownstreamOutput.QA, DownstreamOutput.APPROVAL,
        DownstreamOutput.PUBLISHING,
    })
    assert DownstreamOutput.SCRIPT not in invalidated
    assert DownstreamOutput.SOURCES not in invalidated


def test_regenerating_assets_invalidates_only_the_render_chain():
    invalidated = invalidated_outputs(DownstreamOutput.ASSETS)
    assert invalidated == frozenset({DownstreamOutput.RENDER, DownstreamOutput.QA,
                                     DownstreamOutput.APPROVAL, DownstreamOutput.PUBLISHING})
    assert DownstreamOutput.FACT_CHECK not in invalidated
    assert DownstreamOutput.STORYBOARD not in invalidated


def test_editing_the_scene_text_leaves_the_storyboard_valid():
    # Reescrita só do texto não muda o prompt visual: o storyboard não depende dela.
    assert invalidated_outputs(DownstreamOutput.SCENE_TEXT) == frozenset({
        DownstreamOutput.FACT_CHECK, DownstreamOutput.RENDER, DownstreamOutput.QA,
        DownstreamOutput.APPROVAL, DownstreamOutput.PUBLISHING,
    })


# --- edição por cena: posição e ajuste do plano (W4.1) ------------------------


def test_chapter_for_position_maps_scene_and_append_positions():
    assert chapter_for_position(GOOD_PLAN, 0) == 0
    assert chapter_for_position(GOOD_PLAN, 1) == 0
    assert chapter_for_position(GOOD_PLAN, 2) == 1
    assert chapter_for_position(GOOD_PLAN, 4) == 1
    assert chapter_for_position(GOOD_PLAN, 5) == 2
    assert chapter_for_position(GOOD_PLAN, 11) == 3
    assert chapter_for_position(GOOD_PLAN, 12) == 3  # inserir no fim fica no último capítulo
    with pytest.raises(ValueError):
        chapter_for_position(GOOD_PLAN, -1)


def test_with_chapter_scene_delta_keeps_total_and_redistributes_targets():
    added = with_chapter_scene_delta(GOOD_PLAN, 1, 1)
    assert added.scene_count == 13
    assert added.chapters[1].scene_count == 4
    assert added.target_seconds == GOOD_PLAN.target_seconds
    assert sum(c.target_seconds for c in added.chapters) == pytest.approx(GOOD_PLAN.target_seconds)

    removed = with_chapter_scene_delta(GOOD_PLAN, 2, -1)
    assert removed.scene_count == 11
    assert removed.chapters[2].scene_count == 4
    assert sum(c.target_seconds for c in removed.chapters) == pytest.approx(GOOD_PLAN.target_seconds)

    with pytest.raises(ValueError):
        with_chapter_scene_delta(GOOD_PLAN, 3, -2)
    with pytest.raises(ValueError):
        with_chapter_scene_delta(GOOD_PLAN, 99, 1)

    single = plan(chapter("Abertura", Block.HOOK, 1, 60), chapter("Contexto", Block.CONTEXT, 1, 120),
                  chapter("Desenvolvimento", Block.DEVELOPMENT, 1, 200), chapter("Fecho", Block.CTA, 1, 100))
    with pytest.raises(ValueError):
        with_chapter_scene_delta(single, 0, -1)
