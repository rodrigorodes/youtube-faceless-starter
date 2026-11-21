"""Budget por canal (F10-05): leitura com painel honesto e escrita dos limites.

Os limites hard vão para o guard de operação paga (`guard_limits`); o soft é o gatilho de revisão
humana. Sem linha persistida, valem os tetos padrão das configurações e o painel diz que não há
configuração de canal.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..domain.channel_budget import (
    BudgetDecision,
    BudgetLimits,
    CostSummary,
    evaluate_budget,
)
from ..domain.ids import check_id
from ..domain.provider import EconomicProfile
from .errors import ProjectNotFound
from .ports import ChannelBudgetRepository, ChannelUsageRepository, VideoRepository


@dataclass(frozen=True)
class ChannelBudgetView:
    limits: BudgetLimits
    configured: bool
    summary: CostSummary
    monthly: BudgetDecision
    video: BudgetDecision


class GetChannelBudget:
    def __init__(self, budgets: ChannelBudgetRepository, videos: VideoRepository,
                 usage: ChannelUsageRepository, *, default_hard_monthly: Decimal,
                 default_hard_video: Decimal):
        self.budgets = budgets
        self.videos = videos
        self.usage = usage
        self.default_hard_monthly = Decimal(str(default_hard_monthly))
        self.default_hard_video = Decimal(str(default_hard_video))

    def execute(self, project_id: str) -> ChannelBudgetView:
        p_id = check_id(project_id)
        if self.videos.get_project(p_id) is None:
            raise ProjectNotFound(p_id)
        persisted = self.budgets.get(p_id)
        configured = persisted is not None
        limits = persisted or BudgetLimits(
            project_id=p_id,
            hard_monthly_usd=self.default_hard_monthly,
            soft_monthly_usd=self.default_hard_monthly,
            hard_video_usd=self.default_hard_video,
            soft_video_usd=self.default_hard_video,
        )
        summary = self.usage.month_summary(p_id)
        monthly = evaluate_budget(summary.spent_usd, Decimal("0"), limits.soft_monthly_usd,
                                  limits.hard_monthly_usd, scope="monthly")
        video = evaluate_budget(Decimal("0"), Decimal("0"), limits.soft_video_usd,
                                limits.hard_video_usd, scope="video")
        return ChannelBudgetView(limits, configured, summary, monthly, video)


class SetChannelBudget:
    def __init__(self, budgets: ChannelBudgetRepository, videos: VideoRepository):
        self.budgets = budgets
        self.videos = videos

    def execute(self, project_id: str, *, hard_monthly_usd: object, soft_monthly_usd: object,
                hard_video_usd: object, soft_video_usd: object,
                economic_profile: EconomicProfile = EconomicProfile.BALANCED) -> BudgetLimits:
        p_id = check_id(project_id)
        if self.videos.get_project(p_id) is None:
            raise ProjectNotFound(p_id)
        limits = BudgetLimits(p_id, hard_monthly_usd, soft_monthly_usd, hard_video_usd,
                              soft_video_usd, economic_profile)
        return self.budgets.upsert(limits)