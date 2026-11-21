"""F4-09: roteiro longo de ~480 s em 2–4 temas/estilos, determinístico e offline."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import CostGuard  # noqa: E402
from app.studio.application.longform import GenerateLongScript  # noqa: E402
from app.studio.application.ports import ScriptRecord, TextResult  # noqa: E402
from app.studio.domain.claims import extract_claims  # noqa: E402
from app.studio.domain.contracts import Scene, Script, SourceSnapshot, UsageEntry, Video, VideoFormat, VideoStatus  # noqa: E402

V, P = "v" * 32, "p" * 32
SOURCE = "O canal cresceu 42 por cento no ano passado e esse crescimento mudou o mercado inteiro."
CID = extract_claims("s" * 32, SOURCE)[0].id

# (tema, estilo, cenas, palavras/minuto)
CASES = [
    ("A economia das assinaturas", "documental", 12, 145.0),
    ("Cinco erros ao investir", "lista", 14, 160.0),
    ("A queda de Constantinopla", "narrativa", 16, 150.0),
]


class Videos:
    status = VideoStatus.IDEA

    def __init__(self, topic="tema longo"):
        self.topic = topic

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic=self.topic, format=VideoFormat.long, status=self.status)


class Snapshots:
    def list(self, video_id):
        return [SourceSnapshot(id="s" * 32, video_id=V, url="https://example.com", content_sha256="a" * 64, text=SOURCE)]


class Repo:
    def __init__(self):
        self.records, self._scenes = [], []

    def save_planned_version(self, video_id, text, drafts, claim_ids, plan, content_hash, expected, new):
        self._scenes = [Scene(id=f"{i:032x}", video_id=video_id, idx=i, narration=d.narration, caption=d.caption,
                              label=d.label, image_prompt=d.image_prompt, claim_ids=list(d.claim_ids))
                        for i, d in enumerate(drafts)]
        version = len(self.records) + 1
        self.records.append(ScriptRecord(script=Script(id=f"{version:032x}", video_id=video_id, version=version,
                                                       text=text, claim_ids=claim_ids),
                                         plan=plan, content_hash=content_hash, approval=None))
        return self.records[-1].script

    def list_script_records(self, video_id):
        return list(self.records)


class Usage:
    def record(self, video_id, entry):
        pass

    def spent_video(self, video_id):
        return 0.0

    def spent_month(self):
        return 0.0


class Text:
    name = "fake-480"

    def __init__(self, payloads):
        self.payloads, self.calls, self.prompts = list(payloads), 0, []

    def cost_estimate(self, prompt):
        return 0.0

    def complete(self, prompt, *, json_schema=None):
        self.calls += 1
        self.prompts.append(prompt)
        raw = self.payloads.pop(0)
        return TextResult(text=raw if isinstance(raw, str) else json.dumps(raw),
                          usage=UsageEntry(step="longform", provider="fake", model="m", cost_usd=0.0))


def outline(chapters):
    return json.dumps({"chapters": [
        {"title": f"Cap {i}", "block": block, "scene_count": count, "references": [CID]}
        for i, (block, count) in enumerate(chapters)
    ]})


def scenes_payload(n, words):
    body = " ".join(["ha"] * words)
    return json.dumps({"scenes": [
        {"narration": f"{body} cena {chr(ord('a') + i)}.", "caption": "Legenda", "label": "CEN",
         "image_prompt": "wide empty stage with colored lights", "claim_ids": [CID]}
        for i in range(n)
    ]})


def chapters_for(n):
    context = max(2, round(n * 0.25))
    development = n - 4 - context
    return [("hook", 2), ("context", context), ("development", development), ("cta", 2)]


@pytest.mark.parametrize("topic,style,scene_count,wpm", CASES)
def test_long_script_reaches_480_seconds_across_themes_and_styles(topic, style, scene_count, wpm):
    words = round(480 * wpm / (60 * scene_count))
    repo = Repo()
    text = Text([outline(chapters_for(scene_count)), scenes_payload(scene_count, words)])
    generator = GenerateLongScript(Videos(topic), Snapshots(), repo, text, CostGuard(Usage(), 1.0, 15.0), Usage(), repo)

    result = generator.execute(V, target_seconds=480, words_per_minute=wpm)

    assert text.calls == 2  # duas passagens (plano + cenas)
    assert result.scene_count == scene_count
    assert 400 <= result.estimated_duration_seconds <= 560, (topic, style, result.estimated_duration_seconds)
    assert [c.block.value for c in result.plan.chapters] == ["hook", "context", "development", "cta"]
    assert result.review.passed
    assert len(result.script.claim_ids) >= 1
    assert len(repo.records[0].content_hash) == 64
    # as duas passagens têm prompts distintos (curto x longo, plano x cenas)
    assert text.prompts[0] != text.prompts[1]
    assert "capítulos" in text.prompts[0] and "cenas" in text.prompts[1]
