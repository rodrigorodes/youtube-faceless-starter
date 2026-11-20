"""Regras de domínio e validação estrita de tendências (sem I/O)."""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field


class TrendRefused(ValueError):
    pass


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    url: str = Field(pattern=r"^https?://")
    channel: str = Field(default="", max_length=100)
    views: int | None = Field(default=None, ge=0)
    published_at: datetime | None = None


class TrendItem(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    topic: str = Field(min_length=3, max_length=300)
    source_name: str = Field(min_length=1, max_length=80)
    source_url: str = Field(pattern=r"^https://")
    observed_at: datetime
    window_start: datetime
    window_end: datetime
    metric_name: str | None = Field(default=None, max_length=50)
    metric_value: float | None = Field(default=None, ge=0)
    evidence: list[Evidence] = Field(default_factory=list, max_length=5)


def validate_trends(items: list[TrendItem], allowed_hosts: tuple[str, ...], clock: Callable[[], datetime] | None = None) -> None:
    if not items or not (1 <= len(items) <= 50):
        raise TrendRefused("batch must contain between 1 and 50 items")

    now = clock() if clock else datetime.now(timezone.utc)
    allowed = {h.strip().lower() for h in allowed_hosts if h.strip()}

    for item in items:
        host = urlsplit(item.source_url).hostname or ""
        if host.lower() not in allowed:
            raise TrendRefused(f"source host not allowed: {host!r}")

        if item.observed_at.tzinfo is None:
            raise TrendRefused("observed_at timezone required")
        if item.observed_at > now + timedelta(seconds=300):
            raise TrendRefused("observed_at cannot be in the future")

        if item.window_start.tzinfo is None or item.window_end.tzinfo is None:
            raise TrendRefused("window timezone required")
        if item.window_end < item.window_start:
            raise TrendRefused("window_end must be greater than or equal to window_start")
        if (item.window_end - item.window_start).days > 31:
            raise TrendRefused("window interval must be at most 31 days")
