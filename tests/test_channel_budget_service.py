"""Budget por canal via aplicação (F10-05) e ligação do limite hard ao guard da fatia A.

O guard recebe limites por chamador; aqui o canal define os limites e o guard passa a consultá-los.
"""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.budget import BeginResult, BudgetDenied, PaidOperationGuard  # noqa: E402
from app.studio.application.channel_budget import (  # noqa: E402
    GetChannelBudget,
    SetChannelBudget,
)
from app.studio.application.errors import ProjectNotFound  # noqa: E402
from app.studio.domain.channel_budget import BudgetLimitInvalid, CostSummary  # noqa: E402
from app.studio.domain.provider import EconomicProfile  # noqa: E402

PID = "a" * 32


class FakeVideoRepo:
    def __init__(self, known=(PID,)):
        self.known = set(known)

    def get_project(self, project_id):
        return object() if project_id in self.known else None


class FakeBudgetRepo:
    def __init__(self):
        self.rows = {}

    def get(self, project_id):
        return self.rows.get(project_id)

    def upsert(self, limits):
        self.rows[limits.project_id] = limits
        return limits


class FakeUsage:
    def __init__(self, summary=None):
        self.summary = summary or CostSummary(real_usd=Decimal("0"), estimate_usd=Decimal("0"),
                                              free_calls=0, unknown_calls=0, unattributed_calls=0)

    def month_summary(self, project_id):
        return self.summary


def test_set_budget_persists_validated_limits():
    repo = FakeBudgetRepo()
    saved = SetChannelBudget(repo, FakeVideoRepo()).execute(
        PID, hard_monthly_usd=Decimal("20"), soft_monthly_usd=Decimal("10"),
        hard_video_usd=Decimal("4"), soft_video_usd=Decimal("2"),
        economic_profile=EconomicProfile.ECONOMY)
    assert saved.hard_monthly_usd == Decimal("20")
    assert saved.economic_profile is EconomicProfile.ECONOMY
    assert repo.get(PID) == saved


def test_set_budget_refuses_soft_above_hard():
    with pytest.raises(BudgetLimitInvalid):
        SetChannelBudget(FakeBudgetRepo(), FakeVideoRepo()).execute(
            PID, hard_monthly_usd=Decimal("5"), soft_monthly_usd=Decimal("9"),
            hard_video_usd=Decimal("1"), soft_video_usd=Decimal("0"))


def test_set_budget_refuses_missing_project():
    with pytest.raises(ProjectNotFound):
        SetChannelBudget(FakeBudgetRepo(), FakeVideoRepo(known=())).execute(
            PID, hard_monthly_usd=Decimal("5"), soft_monthly_usd=Decimal("5"),
            hard_video_usd=Decimal("1"), soft_video_usd=Decimal("1"))


def test_get_budget_returns_persisted_limits_with_summary_and_decisions():
    repo = FakeBudgetRepo()
    SetChannelBudget(repo, FakeVideoRepo()).execute(
        PID, hard_monthly_usd=Decimal("10"), soft_monthly_usd=Decimal("5"),
        hard_video_usd=Decimal("2"), soft_video_usd=Decimal("1"))
    usage = FakeUsage(CostSummary(real_usd=Decimal("4"), estimate_usd=Decimal("2"),
                                  free_calls=1, unknown_calls=0, unattributed_calls=0))
    view = GetChannelBudget(repo, FakeVideoRepo(), usage,
                            default_hard_monthly=Decimal("15"),
                            default_hard_video=Decimal("0")).execute(PID)
    assert view.configured is True
    assert view.summary.spent_usd == Decimal("6")
    assert view.monthly.kind.value == "SOFT_LIMIT"
    assert view.video.kind.value == "WITHIN"


def test_get_budget_without_row_uses_defaults_and_reports_not_configured():
    view = GetChannelBudget(FakeBudgetRepo(), FakeVideoRepo(), FakeUsage(),
                            default_hard_monthly=Decimal("15"),
                            default_hard_video=Decimal("0")).execute(PID)
    assert view.configured is False
    assert view.limits.hard_monthly_usd == Decimal("15")
    assert view.summary.has_usage is False


# ----------------------------------------------------------- guard hard limit


class EnforcingPaidRepo:
    """Reserva que recusa quando a estimativa passa dos limites recebidos (hard limit real)."""

    def __init__(self):
        self.calls = []

    def begin(self, key, video_id, estimate_usd, monthly_limit_usd, video_limit_usd):
        self.calls.append((key, video_id, estimate_usd, monthly_limit_usd, video_limit_usd))
        if estimate_usd > monthly_limit_usd or (video_id and estimate_usd > video_limit_usd):
            return BeginResult.DENIED
        return BeginResult.CREATED


def test_guard_uses_project_limits_from_resolver():
    repo = EnforcingPaidRepo()
    guard = PaidOperationGuard(repo, Decimal("100"), Decimal("100"),
                               limits_for=lambda video_id: (Decimal("0.10"), Decimal("0.05")))
    assert guard.reserve("k1", "v1", Decimal("0.04")) is BeginResult.CREATED
    with pytest.raises(BudgetDenied):
        guard.reserve("k2", "v1", Decimal("0.50"))
    assert repo.calls[-1][3] == Decimal("0.10")  # teto mensal por canal chegou ao repositório


def test_guard_without_resolver_keeps_caller_defaults():
    repo = EnforcingPaidRepo()
    guard = PaidOperationGuard(repo, Decimal("100"), Decimal("100"))
    assert guard.reserve("k", "v", Decimal("5")) is BeginResult.CREATED
    assert repo.calls[-1][3] == Decimal("100")


def test_resolver_returning_none_falls_back_to_defaults():
    repo = EnforcingPaidRepo()
    guard = PaidOperationGuard(repo, Decimal("50"), Decimal("50"), limits_for=lambda video_id: None)
    guard.reserve("k", "v", Decimal("5"))
    assert repo.calls[-1][3] == Decimal("50")
