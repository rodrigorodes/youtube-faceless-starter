"""Validated daily, non-monetary YouTube metrics (tokens remain in n8n)."""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from ..domain.ids import check_id
from pydantic import field_validator


class DailyMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    video_id: str
    date: date
    views: int | None = Field(default=None, ge=0)
    estimated_minutes_watched: float | None = Field(default=None, ge=0)
    average_view_duration_s: float | None = Field(default=None, ge=0)
    average_view_percentage: float | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    subscribers_gained: int | None = Field(default=None, ge=0)

    @field_validator("video_id")
    @classmethod
    def validate_video_id(cls, value):
        return check_id(value)


class Analytics:
    def __init__(self, repository):
        self.repository = repository

    def upsert(self, metric: DailyMetric):
        self.repository.upsert(metric)

    def weekly(self, start: date, end: date):
        return self.repository.weekly(start, end)
