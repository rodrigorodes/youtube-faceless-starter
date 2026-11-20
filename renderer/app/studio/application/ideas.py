"""Pontuação de ideias de vídeo pela rubrica (o modelo dá as notas; a ordem e os pesos são do domínio)."""
import json
from collections.abc import Callable
from dataclasses import dataclass

from ..domain.rubric import IdeaScores, score
from .editorial import CostGuard
from .ports import TextModel, UsageRepository

MAX_TOPICS, MAX_TOPIC_CHARS = 20, 150


class IdeaInputRefused(ValueError):
    pass


class IdeasRejected(ValueError):
    pass


@dataclass(frozen=True)
class RankedIdea:
    topic: str
    score: float
    scores: IdeaScores


@dataclass(frozen=True)
class AnalyticsIdea:
    idea: RankedIdea
    note: str
    evidence: list[dict]


def _prompt(topics: list[str]) -> str:
    listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
    return ("Avalie cada ideia de vídeo curto abaixo de 1 a 5 em: relevance (interesse do público), verifiability "
            "(existe fonte oficial que sustente os fatos), visual (dá para ilustrar sem fotos reais) e freshness (atualidade).\n"
            f"IDEIAS:\n{listing}\n\nResponda apenas com JSON: {{\"ideas\": [{{\"topic\": <texto exato da ideia>, "
            "\"relevance\": n, \"verifiability\": n, \"visual\": n, \"freshness\": n}]}")


def _parse(raw: str, topics: list[str]) -> dict[str, IdeaScores]:
    try:
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])["ideas"]
        if not isinstance(data, list):
            raise TypeError
        parsed: dict[str, IdeaScores] = {}
        for entry in data:
            topic = entry["topic"].strip()
            if topic not in topics or topic in parsed:
                raise ValueError(f"unexpected or duplicate topic {topic!r}")
            parsed[topic] = IdeaScores(**{k: v for k, v in entry.items() if k != "topic"})
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:  # ValidationError é ValueError
        raise IdeasRejected(f"model output is not a valid rubric ({type(exc).__name__})") from None
    if set(parsed) != set(topics):
        raise IdeasRejected("model output does not cover every topic")
    return parsed


class ScoreIdeas:
    def __init__(self, text_model: TextModel | None, guard: CostGuard, usage: UsageRepository,
                 model_for: Callable[[str | None], TextModel] | None = None):
        self.text_model, self.guard, self.usage, self.model_for = text_model, guard, usage, model_for

    def execute(self, topics: list[str], project_id: str | None = None) -> list[RankedIdea]:
        if not isinstance(topics, list) or not 1 <= len(topics) <= MAX_TOPICS or not all(isinstance(t, str) for t in topics):
            raise IdeaInputRefused(f"send 1-{MAX_TOPICS} topics")
        topics = [t.strip() for t in topics]
        if any(not t or len(t) > MAX_TOPIC_CHARS for t in topics) or len(set(topics)) != len(topics):
            raise IdeaInputRefused(f"topics must be unique, non-empty and up to {MAX_TOPIC_CHARS} characters")
        prompt = _prompt(topics)
        model = self.model_for(project_id) if self.model_for else self.text_model
        self.guard.check(None, model.cost_estimate(prompt))
        result = model.complete(prompt)
        self.usage.record(None, result.usage)
        parsed = _parse(result.text, topics)
        ranked = [RankedIdea(t, score(parsed[t]), parsed[t]) for t in topics]
        return sorted(ranked, key=lambda r: -r.score)  # sorted é estável: empate mantém a ordem enviada

    def execute_analytics(self, rows: list[dict], video_id: str, project_id: str) -> list[AnalyticsIdea]:
        row = next((r for r in rows if r["video_id"] == video_id), None)
        if not row or not row["views_complete"] or row["sample_small"] or not row["suggestion"]:
            return []
        suggestion = row["suggestion"]
        ranked = self.execute([suggestion["topic"]], project_id)
        return [AnalyticsIdea(ranked[0], suggestion["note"], suggestion["evidence"])]
