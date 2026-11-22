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

    def begin(self, key, video_id, estimate_usd, monthly_limit_usd, video_limit_usd, **_scopes):
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


# --------------------------------------------------- F01.T03: escopo global x canal


class ScopedPaidRepo:
    """Registra os tetos por escopo recebidos do guard, sem banco."""

    def __init__(self):
        self.calls = []

    def begin(self, key, video_id, estimate_usd, monthly_limit_usd, video_limit_usd,
              *, global_monthly_limit_usd=None):
        self.calls.append({"key": key, "video_id": video_id, "estimate": estimate_usd,
                           "channel_monthly": monthly_limit_usd, "channel_video": video_limit_usd,
                           "global_monthly": global_monthly_limit_usd})
        return BeginResult.CREATED


def test_guard_sends_the_global_ceiling_and_the_channel_ceiling_separately():
    """O teto do canal não pode substituir o global: os dois escopos chegam ao repositório."""
    repo = ScopedPaidRepo()
    guard = PaidOperationGuard(repo, Decimal("10"), Decimal("2"),
                               limits_for=lambda video_id: (Decimal("1"), Decimal("0.5")))
    guard.reserve("k", "v", Decimal("0.4"))
    call = repo.calls[-1]
    assert call["global_monthly"] == Decimal("10")  # teto GLOBAL das settings
    assert (call["channel_monthly"], call["channel_video"]) == (Decimal("1"), Decimal("0.5"))


def test_guard_without_channel_budget_uses_the_settings_ceiling_for_both_scopes():
    repo = ScopedPaidRepo()
    guard = PaidOperationGuard(repo, Decimal("10"), Decimal("2"), limits_for=lambda video_id: None)
    guard.reserve("k", "v", Decimal("0.4"))
    call = repo.calls[-1]
    assert call["global_monthly"] == Decimal("10")
    assert (call["channel_monthly"], call["channel_video"]) == (Decimal("10"), Decimal("2"))


def test_operation_without_video_is_explicitly_the_global_scope():
    repo = ScopedPaidRepo()
    guard = PaidOperationGuard(repo, Decimal("10"), Decimal("2"))
    guard.reserve("k", None, Decimal("0.4"))
    call = repo.calls[-1]
    # sem vídeo não há canal: o guard não inventa atribuição, só o teto global se aplica
    assert call["video_id"] is None
    assert call["global_monthly"] == Decimal("10")


# ------------------------------------------- F01.T03: piso de gasto do coordenador


class _Video:
    def __init__(self, project_id):
        self.project_id = project_id


class _Videos:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_video(self, video_id):
        return self.mapping.get(video_id)


class _Budgets:
    def __init__(self, limits):
        self.limits = limits

    def get(self, project_id):
        return next((lim for lim in self.limits if lim.project_id == project_id), None)


class _ScopedUsage:
    """Uso medido por escopo: cada canal com o seu gasto e o global separado."""

    def __init__(self, by_project, global_summary=None):
        self.by_project = by_project
        self.global_summary = global_summary

    def month_summary(self, project_id):
        return self.by_project.get(project_id, _empty())

    def global_month_summary(self):
        return self.global_summary or _empty()


def _empty():
    return CostSummary(real_usd=Decimal("0"), estimate_usd=Decimal("0"),
                       free_calls=0, unknown_calls=0, unattributed_calls=0)


def _summary(amount):
    return CostSummary(real_usd=Decimal(amount), estimate_usd=Decimal("0"),
                       free_calls=0, unknown_calls=0, unattributed_calls=0)


OTHER = "b" * 32


def _floor(limits, by_project, global_summary=None, default="15"):
    from app.studio.application.channel_budget import ChannelBudgetFloor

    return ChannelBudgetFloor(_ScopedUsage(by_project, global_summary), _Videos({OTHER: _Video(PID)}),
                              _Budgets(limits), default_ceiling_usd=Decimal(default))


def _limits(**kw):
    from app.studio.domain.channel_budget import BudgetLimits

    base = dict(project_id=PID, hard_monthly_usd=Decimal("9"), soft_monthly_usd=Decimal("5"),
                hard_video_usd=Decimal("2"), soft_video_usd=Decimal("1"))
    base.update(kw)
    return BudgetLimits(**base)


def test_channel_floor_measures_the_channel_scope_not_the_global_spend():
    """Gasto de outro canal não consome o teto soft deste canal."""
    floor = _floor([_limits()], {PID: _summary("4")}, global_summary=_summary("44"))
    projection = floor.project(type("R", (), {"video_id": OTHER}), None)
    assert projection.projected_usd == Decimal("4")  # gasto do canal, não o global de 44
    assert projection.ceiling_usd == Decimal("5")  # soft do canal


def test_channel_floor_keeps_the_global_ceiling_as_an_upper_bound():
    floor = _floor([_limits(hard_monthly_usd=Decimal("40"), soft_monthly_usd=Decimal("30"))],
                   {PID: _summary("4")}, default="15")
    projection = floor.project(type("R", (), {"video_id": OTHER}), None)
    assert projection.ceiling_usd == Decimal("15")  # o soft do canal não pode afrouxar o teto global


def test_channel_floor_without_configuration_uses_the_settings_ceiling():
    floor = _floor([], {PID: _summary("4")}, default="15")
    projection = floor.project(type("R", (), {"video_id": OTHER}), None)
    assert projection.ceiling_usd == Decimal("15")
    assert projection.projected_usd == Decimal("4")


def test_channel_floor_without_video_measures_the_global_scope():
    floor = _floor([_limits()], {PID: _summary("4")}, global_summary=_summary("12"))
    projection = floor.project(type("R", (), {"video_id": None}), None)
    assert projection.projected_usd == Decimal("12")
    assert projection.ceiling_usd == Decimal("15")
