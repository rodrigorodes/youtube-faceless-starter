"""Rubrica de ideias (domínio puro): quatro notas de 1 a 5 e pesos fixos."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Grade = Annotated[float, Field(ge=1, le=5, allow_inf_nan=False, strict=True)]
WEIGHTS = {"relevance": 0.30, "verifiability": 0.35, "visual": 0.20, "freshness": 0.15}


class IdeaScores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relevance: Grade      # interesse do público do canal
    verifiability: Grade  # há fonte oficial que sustente os fatos
    visual: Grade         # dá para ilustrar sem fotos reais
    freshness: Grade      # atualidade


def score(scores: IdeaScores) -> float:
    return sum(getattr(scores, name) * weight for name, weight in WEIGHTS.items())
