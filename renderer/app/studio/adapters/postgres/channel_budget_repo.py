"""Repositórios Postgres de budget por canal (F10-05). Transacional, sem autocommit."""
from __future__ import annotations

from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from ...application.errors import ProjectNotFound
from ...domain.channel_budget import BudgetLimitInvalid, BudgetLimits, CostSummary
from ...domain.ids import check_id
from ...domain.provider import EconomicProfile
from .editorial_repo import _Base
from .repo import _translated

_COLS = ("project_id, hard_monthly_usd, soft_monthly_usd, hard_video_usd, soft_video_usd, "
         "economic_profile, updated_at")


def _limits(row: dict) -> BudgetLimits:
    return BudgetLimits(
        project_id=row["project_id"],
        hard_monthly_usd=row["hard_monthly_usd"],
        soft_monthly_usd=row["soft_monthly_usd"],
        hard_video_usd=row["hard_video_usd"],
        soft_video_usd=row["soft_video_usd"],
        economic_profile=EconomicProfile(row["economic_profile"]),
        updated_at=row["updated_at"],
    )


class PostgresChannelBudgetRepository(_Base):
    def get(self, project_id: str) -> BudgetLimits | None:
        p_id = check_id(project_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLS} FROM studio.channel_budgets WHERE project_id = %s", (p_id,))
            row = cur.fetchone()
            return _limits(row) if row else None

    def upsert(self, limits: BudgetLimits) -> BudgetLimits:
        if not isinstance(limits, BudgetLimits):
            raise BudgetLimitInvalid("limits must be a BudgetLimits")
        try:
            with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""INSERT INTO studio.channel_budgets (
                        project_id, hard_monthly_usd, soft_monthly_usd, hard_video_usd, soft_video_usd,
                        economic_profile
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (project_id) DO UPDATE SET
                        hard_monthly_usd = EXCLUDED.hard_monthly_usd,
                        soft_monthly_usd = EXCLUDED.soft_monthly_usd,
                        hard_video_usd = EXCLUDED.hard_video_usd,
                        soft_video_usd = EXCLUDED.soft_video_usd,
                        economic_profile = EXCLUDED.economic_profile,
                        updated_at = now()
                    RETURNING {_COLS}""",
                    (limits.project_id, limits.hard_monthly_usd, limits.soft_monthly_usd,
                     limits.hard_video_usd, limits.soft_video_usd, limits.economic_profile.value),
                )
                return _limits(cur.fetchone())
        except psycopg.errors.ForeignKeyViolation as exc:
            raise ProjectNotFound(limits.project_id) from exc
        except psycopg.errors.CheckViolation as exc:
            raise BudgetLimitInvalid("database rejected the budget limits") from exc


class PostgresChannelUsageRepository(_Base):
    def month_summary(self, project_id: str) -> CostSummary:
        p_id = check_id(project_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN ul.cost_confirmation_kind = 'ACTUAL'
                                      THEN ul.cost_usd ELSE 0 END), 0) AS real_usd,
                    COALESCE(SUM(CASE WHEN ul.cost_confirmation_kind = 'ESTIMATE'
                                      THEN ul.cost_usd ELSE 0 END), 0) AS estimate_usd,
                    COUNT(*) FILTER (WHERE ul.cost_confirmation_kind = 'FREE') AS free_calls,
                    COUNT(*) FILTER (WHERE ul.cost_confirmation_kind IS NULL) AS unknown_calls,
                    (SELECT COUNT(*) FROM studio.usage_ledger
                      WHERE video_id IS NULL AND created_at >= date_trunc('month', now())) AS unattributed_calls
                FROM studio.usage_ledger ul
                JOIN studio.videos v ON v.id = ul.video_id
                WHERE v.project_id = %s AND ul.created_at >= date_trunc('month', now())
                """,
                (p_id,),
            )
            row = cur.fetchone()
        return CostSummary(
            real_usd=Decimal(row["real_usd"]),
            estimate_usd=Decimal(row["estimate_usd"]),
            free_calls=int(row["free_calls"]),
            unknown_calls=int(row["unknown_calls"]),
            unattributed_calls=int(row["unattributed_calls"]),
        )