"""Budget por canal (F10-05): leitura com painel honesto e escrita dos limites.

Os limites hard vão para o guard de operação paga (`guard_limits`); o soft é o gatilho de revisão
humana. Sem linha persistida, valem os tetos padrão das configurações e o painel diz que não há
configuração de canal.

F01.T03: cada escopo é medido no **próprio** escopo. O teto global (settings) é independente do teto
do canal; o resumo do painel e o piso do coordenador usam a mesma atribuição do ledger, nunca o gasto
global para decidir sobre um canal.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol

from ..domain.channel_budget import (
    BudgetDecision,
    BudgetLimits,
    CostSummary,
    evaluate_budget,
)
from ..domain.ids import InvalidId, check_id
from ..domain.provider import EconomicProfile, RankingOrder, policy_for
from .errors import ProjectNotFound
from .ports import ChannelBudgetRepository, ChannelUsageRepository, VideoRepository
from .production import BudgetProjection


class ScopedUsageRepository(Protocol):
    """Leitura de gasto por escopo: o mesmo que o teto desconta (canal e global)."""

    def month_summary(self, project_id: str) -> CostSummary: ...

    def global_month_summary(self) -> CostSummary: ...


@dataclass(frozen=True)
class ChannelBudgetFloor:
    """Piso medido do gasto mensal para o modo guardado do coordenador (F01.T03).

    O hard bloqueia no guard; aqui o soft decide a pausa humana. O gasto medido é o **do canal do
    vídeo** (não o global, que faria o gasto de A pausar B). O teto efetivo é o menor entre o soft do
    canal e o teto das settings: nenhum canal pode afrouxar o limite global. Sem configuração de canal,
    vale o teto das settings. Operação sem vídeo é escopo global explícito e mede o gasto global.
    """

    usage: ScopedUsageRepository
    videos: VideoRepository
    budgets: ChannelBudgetRepository
    default_ceiling_usd: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "default_ceiling_usd",
                           _ceiling(self.default_ceiling_usd, "default ceiling"))

    def project(self, run, next_stage) -> BudgetProjection:
        video = self._video(run)
        if video is None:
            return BudgetProjection(projected_usd=self.usage.global_month_summary().spent_usd,
                                    ceiling_usd=self.default_ceiling_usd)
        summary = self.usage.month_summary(video.project_id)
        limits = self.budgets.get(video.project_id)
        ceiling = self.default_ceiling_usd
        if limits is not None:
            ceiling = min(_ceiling(limits.soft_monthly_usd, "soft monthly ceiling"), ceiling)
        return BudgetProjection(projected_usd=summary.spent_usd, ceiling_usd=ceiling)

    def _video(self, run):
        video_id = getattr(run, "video_id", None)
        if not video_id:
            return None
        try:
            return self.videos.get_video(video_id)
        except InvalidId:
            return None  # id estranho não decide orçamento: cai no escopo global (tolerância do guard)


def _ceiling(value: object, label: str) -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a monetary value") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} must be a finite non-negative Decimal")
    return amount


@dataclass(frozen=True)
class ChannelBudgetView:
    limits: BudgetLimits
    configured: bool
    summary: CostSummary
    monthly: BudgetDecision
    video: BudgetDecision

    @property
    def limits_source(self) -> str:
        """Origem dos limites **vigentes**: `canal` quando persistidos, `servidor` no padrão."""
        return "canal" if self.configured else "servidor"


# F06.T03: os perfis não são texto de marketing — cada opção descreve a política que o roteador
# realmente aplica (piso de qualidade, ranking e tolerância a custo desconhecido).
_PROFILE_LABELS = {
    EconomicProfile.ECONOMY: "Economia",
    EconomicProfile.BALANCED: "Equilibrado",
    EconomicProfile.PREMIUM: "Premium",
}


def _profile_description(profile: EconomicProfile) -> str:
    policy = policy_for(profile)
    if policy.ranking is RankingOrder.COST_FIRST:
        return (f"Menor custo conhecido primeiro; piso de qualidade {policy.min_quality}. "
                "Custo desconhecido fica fora: sem preço não há como garantir economia.")
    if policy.ranking is RankingOrder.QUALITY_FIRST:
        return (f"Qualidade primeiro; piso {policy.min_quality}. Custo desconhecido só é aceito "
                "em operação sem teto — com teto ele fica fora.")
    return (f"Melhor qualidade até {policy.balanced_cost_factor:g}× a opção paga mais barata; "
            f"piso {policy.min_quality}. Custo desconhecido fica fora.")


@dataclass(frozen=True)
class EconomicProfileOption:
    """Opção de perfil econômico para a tela: o dado vem da política, não do mockup."""

    profile: EconomicProfile
    label: str
    description: str
    active: bool
    min_quality: int
    ranking: RankingOrder


def economic_profile_options(current: EconomicProfile | str) -> tuple[EconomicProfileOption, ...]:
    """Os três perfis reais, com a política vigente e qual está ativo no canal."""
    if not isinstance(current, EconomicProfile):
        current = EconomicProfile(current)
    return tuple(
        EconomicProfileOption(
            profile=profile,
            label=_PROFILE_LABELS[profile],
            description=_profile_description(profile),
            active=profile is current,
            min_quality=policy_for(profile).min_quality,
            ranking=policy_for(profile).ranking,
        )
        for profile in EconomicProfile
    )


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