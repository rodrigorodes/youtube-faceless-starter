"""Contrato editorial isolado; referências são entradas, não fontes verificadas."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ContentBrief(BaseModel):
    """Briefing manual ou ligado a tendência, sem pesquisa ou persistência."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Annotated[int, Field(strict=True)] = 1
    topic: NonBlank
    audience: NonBlank
    objective: NonBlank
    interest_hypothesis: NonBlank
    references: tuple[NonBlank, ...] = ()
    trend_id: NonBlank | None = None
    target_duration_seconds: Annotated[int, Field(strict=True, gt=0)] | None = None
    voice: NonBlank | None = None
    pace: NonBlank | None = None
    structure: NonBlank | None = None
    language: NonBlank | None = None
    constraints: tuple[NonBlank, ...] = ()

    @field_validator("schema_version")
    @classmethod
    def _known_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported schema_version")
        return value
