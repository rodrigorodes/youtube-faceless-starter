import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import CostGuard  # noqa: E402
from app.studio.application.ideas import IdeaInputRefused, IdeasRejected, ScoreIdeas  # noqa: E402
from app.studio.application.ports import TextResult  # noqa: E402
from app.studio.domain.contracts import UsageEntry  # noqa: E402
from app.studio.domain.policy import CostRefused  # noqa: E402
from app.studio.domain.rubric import IdeaScores, score  # noqa: E402


def test_weights_sum_to_a_five_point_scale():
    assert score(IdeaScores(relevance=5, verifiability=5, visual=5, freshness=5)) == pytest.approx(5.0)
    assert score(IdeaScores(relevance=1, verifiability=1, visual=1, freshness=1)) == pytest.approx(1.0)
    assert score(IdeaScores(relevance=5, verifiability=1, visual=1, freshness=1)) == pytest.approx(0.3 * 5 + 0.35 + 0.2 + 0.15)


@pytest.mark.parametrize("bad", [0, 6, -1, float("nan"), float("inf"), True, "4", None])
def test_scores_outside_the_scale_are_refused(bad):
    with pytest.raises(ValueError):
        IdeaScores(relevance=bad, verifiability=3, visual=3, freshness=3)


def test_unknown_field_is_refused():
    with pytest.raises(ValidationError):
        IdeaScores(relevance=3, verifiability=3, visual=3, freshness=3, extra=1)


class Usage:
    def __init__(self):
        self.entries = []

    def record(self, video_id, entry):
        self.entries.append((video_id, entry))

    def spent_video(self, video_id):
        return 0.0

    def spent_month(self):
        return 0.0


class Text:
    name = "fake"

    def __init__(self, payload, cost=0.0):
        self.payload, self.cost, self.calls, self.prompts = payload, cost, 0, []

    def cost_estimate(self, prompt):
        return self.cost

    def complete(self, prompt, *, json_schema=None):
        self.calls += 1
        self.prompts.append(prompt)
        raw = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return TextResult(raw, UsageEntry(step="ideas", provider="fake", model="m", cost_usd=0))


def item(topic, r, v, vis, f):
    return {"topic": topic, "relevance": r, "verifiability": v, "visual": vis, "freshness": f}


def make(payload, cost=0.0, cap_video=0.0):
    usage, text = Usage(), Text(payload, cost)
    return ScoreIdeas(None, CostGuard(usage, cap_video, 15.0), usage, model_for=lambda project_id: text), text, usage


def test_ranking_is_sorted_by_score_and_stable_on_ties():
    payload = {"ideas": [item("B", 3, 3, 3, 3), item("A", 5, 5, 5, 5), item("C", 3, 3, 3, 3)]}
    ranked = make(payload)[0].execute(["B", "A", "C"])
    assert [r.topic for r in ranked] == ["A", "B", "C"] and ranked[0].score == pytest.approx(5.0)


def test_usage_recorded_without_video_and_prompt_fits_limit():
    use, text, usage = make({"ideas": [item("T", 3, 3, 3, 3)]})
    use.execute(["T"])
    assert len(usage.entries) == 1 and usage.entries[0][0] is None
    long_topics = [f"{i:03d}" + "x" * 147 for i in range(20)]
    use2, text2, _ = make({"ideas": [item(t, 3, 3, 3, 3) for t in long_topics]})
    assert len(use2.execute(long_topics)) == 20
    assert len(text2.prompts[0]) <= 3900  # cabe no limite do bridge sem corte


@pytest.mark.parametrize("topics", [[], [""], ["   "], ["ok"] * 21, ["x" * 151], "texto", ["ok", 3]])
def test_input_validation(topics):
    use, text, _ = make({"ideas": []})
    with pytest.raises(IdeaInputRefused):
        use.execute(topics)
    assert text.calls == 0


@pytest.mark.parametrize("payload", [
    "não é json", {"nada": 1}, {"ideas": []}, {"ideas": [item("A", 9, 3, 3, 3)]}, {"ideas": [item("Outro", 3, 3, 3, 3)]},
    {"ideas": [item("A", 3, 3, 3, 3), item("A", 3, 3, 3, 3)]}, {"ideas": [{"topic": "A", "relevance": 3}]}, {"ideas": ["A"]},
])
def test_bad_model_output_is_rejected_and_nothing_partial(payload):
    use, text, usage = make(payload)
    with pytest.raises(IdeasRejected):
        use.execute(["A"])
    assert len(usage.entries) == 1  # a chamada aconteceu e foi contabilizada


def test_missing_topic_in_output_is_rejected():
    use, *_ = make({"ideas": [item("A", 3, 3, 3, 3)]})
    with pytest.raises(IdeasRejected):
        use.execute(["A", "B"])


def test_cost_guard_blocks_before_calling_the_model():
    use, text, usage = make({"ideas": [item("A", 3, 3, 3, 3)]}, cost=0.5)
    with pytest.raises(CostRefused):
        use.execute(["A"])
    assert text.calls == 0 and usage.entries == []


def test_fenced_json_is_accepted():
    use, *_ = make("```json\n" + json.dumps({"ideas": [item("A", 4, 4, 4, 4)]}) + "\n```")
    assert use.execute(["A"])[0].topic == "A"


def test_deeply_nested_model_output_is_rejected_not_a_crash():
    use, *_ = make("{" + '{"a":' * 100000 + "1" + "}" * 100000)
    with pytest.raises(IdeasRejected):
        use.execute(["A"])


def test_analytics_suggestion_is_scored_with_provenance_and_project_provider():
    from datetime import date

    use, text, usage = make({"ideas": [item("Tema", 4, 4, 4, 4)]})
    selected = []
    use.model_for = lambda project: selected.append(project) or text
    day = date(2026, 11, 10)
    rows = [{"video_id": "a" * 32, "views_complete": True, "sample_small": False,
             "suggestion": {"topic": "Tema", "note": "Explorar", "evidence": [{"video_id": "a" * 32, "date": day}]}}]
    result = use.execute_analytics(rows, "a" * 32, "b" * 32)
    assert result[0].idea.topic == "Tema"
    assert result[0].evidence == [{"video_id": "a" * 32, "date": day}]
    assert result[0].note == "Explorar"
    assert selected == ["b" * 32] and len(usage.entries) == 1


@pytest.mark.parametrize("row", [
    None,
    {"views_complete": False, "sample_small": False, "suggestion": None},
    {"views_complete": True, "sample_small": True, "suggestion": None},
])
def test_analytics_without_eligible_suggestion_never_calls_model(row):
    use, text, usage = make({"ideas": []})
    rows = [] if row is None else [{"video_id": "a" * 32, **row}]
    assert use.execute_analytics(rows, "a" * 32, "b" * 32) == []
    assert text.calls == 0 and usage.entries == []


def test_analytics_editorial_endpoint_requires_auth_and_uses_video_project():
    from datetime import date
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.studio.api.routes import make_router

    video_id, project_id = "a" * 32, "b" * 32
    day = date(2026, 11, 10)
    row = {"video_id": video_id, "views_complete": True, "sample_small": False,
           "suggestion": {"topic": "Tema", "note": "Explorar", "evidence": [{"video_id": video_id, "date": day}]}}
    use, text, _ = make({"ideas": [item("Tema", 4, 4, 4, 4)]})
    projects = []
    use.model_for = lambda project: projects.append(project) or text
    uc = SimpleNamespace(editorial=SimpleNamespace(score_ideas=use),
                         get_video=SimpleNamespace(execute=lambda vid: SimpleNamespace(project_id=project_id) if vid == video_id else None),
                         analytics=SimpleNamespace(weekly=lambda start, end: [row]))
    app = FastAPI()
    app.include_router(make_router(lambda: uc, lambda: True))
    client = TestClient(app)
    body = {"video_id": video_id, "start": str(day), "end": str(day)}
    assert client.post("/studio/ideas/from-analytics", json=body).status_code == 401
    response = client.post("/studio/ideas/from-analytics", json=body, headers={"Authorization": "Bearer test-worker-token"})
    assert response.status_code == 200
    result = response.json()["ranked"]
    assert result[0]["topic"] == "Tema" and result[0]["evidence"] == [{"video_id": video_id, "date": str(day)}]
    assert projects == [project_id]
    assert client.post("/studio/ideas/from-analytics", json={**body, "start": "2026-11-01"}, headers={"Authorization": "Bearer test-worker-token"}).status_code == 422
    assert text.calls == 1


def test_analytics_scoring_respects_cost_cap():
    use, text, usage = make({"ideas": [item("Tema", 4, 4, 4, 4)]}, cost=0.5)
    rows = [{"video_id": "a" * 32, "views_complete": True, "sample_small": False,
             "suggestion": {"topic": "Tema", "note": "Explorar", "evidence": []}}]
    with pytest.raises(CostRefused):
        use.execute_analytics(rows, "a" * 32, "b" * 32)
    assert text.calls == 0 and usage.entries == []
