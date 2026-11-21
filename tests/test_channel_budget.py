"""Budget por canal/produção (F10-05): limites hard e soft distintos.

Hard bloqueia; soft só sinaliza revisão humana. O guard da fatia A não é hard limit — aqui os
limites são definidos por canal e passados ao guard. Custo é honesto: Real/Estimado/Sem custo/
Desconhecido; ausência de uso nunca vira zero.
"""
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.channel_budget import (  # noqa: E402
    BudgetDecision,
    BudgetDecisionKind,
    BudgetLimitInvalid,
    BudgetLimits,
    CostSummary,
    evaluate_budget,
)
from app.studio.domain.provider import EconomicProfile  # noqa: E402

PID = "a" * 32


def limits(**kw):
    base = dict(project_id=PID, hard_monthly_usd=Decimal("10"), soft_monthly_usd=Decimal("5"),
                hard_video_usd=Decimal("2"), soft_video_usd=Decimal("1"))
    base.update(kw)
    return BudgetLimits(**base)


def test_limits_accept_soft_below_hard():
    lim = limits()
    assert lim.soft_monthly_usd == Decimal("5") and lim.hard_monthly_usd == Decimal("10")
    assert lim.economic_profile is EconomicProfile.BALANCED


def test_soft_above_hard_is_refused():
    with pytest.raises(BudgetLimitInvalid):
        limits(soft_monthly_usd=Decimal("11"))
    with pytest.raises(BudgetLimitInvalid):
        limits(soft_video_usd=Decimal("3"))


def test_negative_or_non_finite_amounts_are_refused():
    for bad in (Decimal("-1"), Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(BudgetLimitInvalid):
            limits(hard_monthly_usd=bad)


def test_zero_hard_blocks_any_paid_production():
    lim = limits(hard_monthly_usd=Decimal("0"), soft_monthly_usd=Decimal("0"))
    assert lim.is_blocked(estimate_usd=Decimal("0.01"))


def test_hard_limits_feed_the_paid_guard():
    assert limits().guard_limits() == (Decimal("10"), Decimal("2"))


def test_decision_within_soft_is_within():
    decision = evaluate_budget(spent_usd=Decimal("1"), estimate_usd=Decimal("1"),
                               soft_usd=Decimal("5"), hard_usd=Decimal("10"), scope="monthly")
    assert decision.kind is BudgetDecisionKind.WITHIN
    assert decision.projected_usd == Decimal("2")


def test_decision_above_soft_warns_without_blocking():
    decision = evaluate_budget(spent_usd=Decimal("4"), estimate_usd=Decimal("2"),
                               soft_usd=Decimal("5"), hard_usd=Decimal("10"), scope="monthly")
    assert decision.kind is BudgetDecisionKind.SOFT_LIMIT
    assert "humana" in decision.message.lower()


def test_decision_above_hard_blocks():
    decision = evaluate_budget(spent_usd=Decimal("9.5"), estimate_usd=Decimal("1"),
                               soft_usd=Decimal("5"), hard_usd=Decimal("10"), scope="video")
    assert decision.kind is BudgetDecisionKind.HARD_BLOCKED
    assert decision.scope == "video"


def test_hard_equal_to_soft_still_blocks_before_soft():
    decision = evaluate_budget(spent_usd=Decimal("9"), estimate_usd=Decimal("2"),
                               soft_usd=Decimal("10"), hard_usd=Decimal("10"), scope="monthly")
    assert decision.kind is BudgetDecisionKind.HARD_BLOCKED


# --------------------------------------------------------------- CostSummary


def test_cost_summary_never_merges_real_and_estimate():
    summary = CostSummary(real_usd=Decimal("1.50"), estimate_usd=Decimal("0.20"),
                          free_calls=2, unknown_calls=1, unattributed_calls=0)
    assert summary.spent_usd == Decimal("1.70")
    assert summary.has_usage is True
    assert summary.labels()["real"] == "Real US$ 1,50"
    assert summary.labels()["unknown"] == "Desconhecido em 1 chamada(s)"


def test_cost_summary_without_usage_is_explicit_and_not_zero():
    summary = CostSummary(real_usd=Decimal("0"), estimate_usd=Decimal("0"),
                          free_calls=0, unknown_calls=0, unattributed_calls=0)
    assert summary.has_usage is False
    labels = summary.labels()
    assert labels["real"] == "Sem registro de uso"
    assert "0,00" not in labels["real"]
    assert labels["estimate"] == "Sem registro de uso"
    assert labels["unknown"] == "Sem registro de uso"


def test_cost_summary_counts_unknown_calls_separately():
    summary = CostSummary(real_usd=Decimal("0"), estimate_usd=Decimal("0"),
                          free_calls=0, unknown_calls=3, unattributed_calls=1)
    assert summary.has_usage is True
    assert summary.labels()["unknown"] == "Desconhecido em 3 chamada(s)"


def test_cost_summary_rejects_negative_amounts():
    with pytest.raises(BudgetLimitInvalid):
        CostSummary(real_usd=Decimal("-1"), estimate_usd=Decimal("0"), free_calls=0,
                    unknown_calls=0, unattributed_calls=0)
