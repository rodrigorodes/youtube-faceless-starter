import json
from decimal import Decimal
import pytest
from pydantic import ValidationError

from app.studio.application.budget import paid_key
from app.studio.application.creative_director import CreateCreativeBrief
from app.studio.application.editorial import (
    EditorialContext,
    build_prompt,
    parse_drafts,
    parse_scene_drafts,
)
from app.studio.application.ports import SceneDraft, TextResult
from app.studio.domain.claims import Claim
from app.studio.domain.contracts import UsageEntry
from app.studio.domain.creative_director import CreativeBrief


def sample_brief_json(**overrides):
    base = {
        "schema_version": 1,
        "topic": "History of the Printing Press",
        "narrative_goal": "Engage viewers with the transformative power of the press",
        "hook": "Did you know one invention changed human thought forever?",
        "content_structure": [
            "Hook & Origin",
            "Gutenberg's Revolution",
            "Impact on Society",
        ],
        "tone": "Educational and energetic",
        "pacing": "Fast-paced with deliberate pauses",
        "visual_direction": "Engraving style illustrations with dynamic zooms",
        "recommended_media_types": ["image", "video"],
        "caption_strategy": "Bold keyword highlight on bottom third",
        "audio_guidance": "Epic classical music building to a climax",
        "max_budget_usd": None,
        "quality_criteria": ["High contrast", "No modern artifacts"],
    }
    base.update(overrides)
    return json.dumps(base)


class FakeTextModel:
    name = "fake-text-model"
    model = "gpt-4o"

    def __init__(self, response_text: str, cost: float = 0.01):
        self.response_text = response_text
        self.cost = cost
        self.prompts: list[str] = []
        self.schemas: list[dict | None] = []

    def cost_estimate(self, prompt: str) -> float:
        return self.cost

    def complete(self, prompt: str, *, json_schema: dict | None = None) -> TextResult:
        self.prompts.append(prompt)
        self.schemas.append(json_schema)
        return TextResult(
            text=self.response_text,
            usage=UsageEntry(
                step="creative_direction",
                provider="openai",
                model=self.model,
                cost_usd=self.cost,
                input_tokens=100,
                output_tokens=50,
            ),
        )


class FakePaidGuard:
    def __init__(self):
        self.calls: list[dict] = []

    def run(self, key, video_id, estimate_usd, call, settle, validate=None):
        self.calls.append({
            "key": key,
            "video_id": video_id,
            "estimate_usd": estimate_usd,
        })
        res = call()
        if validate is not None:
            return validate(res)
        return res


# ---------------------------------------------------------------------------
# CreateCreativeBrief tests
# ---------------------------------------------------------------------------


def test_create_creative_brief_executes_without_guard():
    raw_json = sample_brief_json()
    model = FakeTextModel(raw_json, cost=0.02)
    use_case = CreateCreativeBrief(model)

    channel_ctx = {"name": "Tech History", "tone": "dynamic", "audience": "curious minds"}
    brief = use_case.execute("History of the Printing Press", channel_ctx)

    assert isinstance(brief, CreativeBrief)
    assert brief.topic == "History of the Printing Press"
    assert brief.hook == "Did you know one invention changed human thought forever?"
    assert brief.pacing == "Fast-paced with deliberate pauses"
    assert brief.visual_direction == "Engraving style illustrations with dynamic zooms"
    assert len(model.prompts) == 1
    assert "History of the Printing Press" in model.prompts[0]
    assert "Tech History" in model.prompts[0]
    assert model.schemas[0] is not None


def test_create_creative_brief_handles_markdown_code_fences():
    raw_json = f"```json\n{sample_brief_json()}\n```"
    model = FakeTextModel(raw_json)
    use_case = CreateCreativeBrief(model)

    brief = use_case.execute("History of the Printing Press", {"tone": "epic"})
    assert isinstance(brief, CreativeBrief)
    assert brief.topic == "History of the Printing Press"


def test_create_creative_brief_with_budget_cap():
    raw_json = sample_brief_json(max_budget_usd=10.0)
    model = FakeTextModel(raw_json)
    use_case = CreateCreativeBrief(model)

    brief = use_case.execute("History of the Printing Press", {}, budget_cap=10.0)
    assert brief.max_budget_usd == 10.0
    assert "10.0" in model.prompts[0] or "10" in model.prompts[0]


def test_create_creative_brief_sets_budget_cap_if_model_returns_none():
    raw_json = sample_brief_json(max_budget_usd=None)
    model = FakeTextModel(raw_json)
    use_case = CreateCreativeBrief(model)

    brief = use_case.execute("History of the Printing Press", {}, budget_cap=25.0)
    assert brief.max_budget_usd == 25.0


def test_create_creative_brief_with_guard_uses_paid_key():
    raw_json = sample_brief_json()
    model = FakeTextModel(raw_json, cost=0.03)
    guard = FakePaidGuard()
    use_case = CreateCreativeBrief(model, guard=guard)

    channel_ctx = {"video_id": "v-1234", "name": "Curious Minds"}
    brief = use_case.execute("History of the Printing Press", channel_ctx)

    assert isinstance(brief, CreativeBrief)
    assert len(guard.calls) == 1
    call_info = guard.calls[0]
    assert call_info["video_id"] == "v-1234"
    assert call_info["estimate_usd"] == Decimal("0.03")

    prompt = model.prompts[0]
    expected_key = paid_key("creative_direction", "v-1234", getattr(model, "model", ""), model.name, prompt)
    assert call_info["key"] == expected_key


def test_create_creative_brief_rejects_blank_topic():
    model = FakeTextModel(sample_brief_json())
    use_case = CreateCreativeBrief(model)

    with pytest.raises(ValueError, match="topic"):
        use_case.execute("   ", {})


def test_create_creative_brief_rejects_non_dict_channel_context():
    model = FakeTextModel(sample_brief_json())
    use_case = CreateCreativeBrief(model)

    with pytest.raises(ValueError, match="channel_context"):
        use_case.execute("Valid Topic", "not-a-dict")  # type: ignore


def test_create_creative_brief_rejects_negative_budget_cap():
    model = FakeTextModel(sample_brief_json())
    use_case = CreateCreativeBrief(model)

    with pytest.raises(ValueError, match="budget_cap"):
        use_case.execute("Valid Topic", {}, budget_cap=-5.0)


# ---------------------------------------------------------------------------
# SceneDraft ports tests
# ---------------------------------------------------------------------------


def test_scene_draft_backward_compatible_defaults():
    draft = SceneDraft(
        narration="Narração de teste",
        caption="Legenda curta",
        label="Cena 1",
        image_prompt="Prompt de imagem detalhado",
        claim_ids=["c1"],
    )
    assert draft.visual_intent == ""
    assert draft.recommended_asset_kind == "image"
    assert draft.search_queries == []


def test_scene_draft_with_enriched_fields():
    draft = SceneDraft(
        narration="Narração de teste",
        caption="Legenda curta",
        label="Cena 1",
        image_prompt="Prompt de imagem detalhado",
        claim_ids=["c1"],
        visual_intent="Close cinematográfico na prensa móvel",
        recommended_asset_kind="video",
        search_queries=["gutenberg press", "movable type"],
    )
    assert draft.visual_intent == "Close cinematográfico na prensa móvel"
    assert draft.recommended_asset_kind == "video"
    assert draft.search_queries == ["gutenberg press", "movable type"]


# ---------------------------------------------------------------------------
# Editorial build_prompt & parse tests
# ---------------------------------------------------------------------------


def test_build_prompt_without_brief_is_unchanged():
    claims = [Claim(id="c1", snapshot_id="s" * 32, text="Gutenberg inventou a prensa móvel.")]
    prompt = build_prompt("Prensa Móvel", claims, 2)
    assert "DIRETRIZES DO DIRETOR CRIATIVO" not in prompt
    assert "visual_intent" not in prompt
    assert "search_queries" not in prompt


def test_build_prompt_with_brief_injects_guidelines_and_schema():
    claims = [Claim(id="c1", snapshot_id="s" * 32, text="Gutenberg inventou a prensa móvel.")]
    brief = CreativeBrief.model_validate_json(sample_brief_json())

    prompt = build_prompt("Prensa Móvel", claims, 2, brief=brief)
    assert "DIRETRIZES DO DIRETOR CRIATIVO" in prompt
    assert brief.hook in prompt
    assert brief.pacing in prompt
    assert brief.visual_direction in prompt
    assert "visual_intent" in prompt
    assert "recommended_asset_kind" in prompt
    assert "search_queries" in prompt


def test_parse_scene_drafts_extracts_enriched_fields():
    raw = json.dumps({
        "scenes": [
            {
                "narration": "Gutenberg transformou o mundo com a prensa moderna.",
                "caption": "A Revolução da Imprensa",
                "label": "Introdução",
                "image_prompt": "Oficina do século XV com prensa de madeira e tipos móveis",
                "claim_ids": ["c1"],
                "visual_intent": "Plano médio da oficina com luz suave entrando pela janela",
                "recommended_asset_kind": "video",
                "search_queries": ["printing press 15th century", "gutenberg workshop"],
            },
            {
                "narration": "Livros se tornaram acessíveis para toda a sociedade.",
                "caption": "Acesso ao Conhecimento",
                "label": "Desenvolvimento",
                "image_prompt": "Pilha de livros impressos e pessoas lendo em praça pública",
                "claim_ids": ["c1"],
            },
        ]
    })

    drafts = parse_scene_drafts(raw, {"c1"}, min_scenes=2, max_scenes=4)
    assert len(drafts) == 2

    assert drafts[0].visual_intent == "Plano médio da oficina com luz suave entrando pela janela"
    assert drafts[0].recommended_asset_kind == "video"
    assert drafts[0].search_queries == ["printing press 15th century", "gutenberg workshop"]

    # Scene 2 does not have enriched fields; should fallback to defaults
    assert drafts[1].visual_intent == ""
    assert drafts[1].recommended_asset_kind == "image"
    assert drafts[1].search_queries == []


def test_create_creative_brief_rejects_invalid_json():
    model = FakeTextModel("Not a valid json response at all")
    use_case = CreateCreativeBrief(model)

    with pytest.raises(ValueError, match="not valid JSON"):
        use_case.execute("Valid Topic", {})


def test_create_creative_brief_rejects_invalid_schema():
    # content_structure with only 1 section violates minimum of 2
    bad_json = sample_brief_json(content_structure=["Single section"])
    model = FakeTextModel(bad_json)
    use_case = CreateCreativeBrief(model)

    with pytest.raises(ValidationError):
        use_case.execute("Valid Topic", {})


def test_generate_script_with_creative_brief():
    from app.studio.application.editorial import CostGuard, GenerateScript
    from app.studio.domain.contracts import Script, Video, VideoFormat, VideoStatus

    vid = "b" * 32
    video_obj = Video(id=vid, project_id="a" * 32, topic="ADE 2026", format=VideoFormat.short, status=VideoStatus.IDEA)

    class StubVideos:
        def __init__(self):
            self.status = VideoStatus.IDEA
        def get_video(self, _id):
            return Video(id=vid, project_id="a" * 32, topic="ADE 2026", format=VideoFormat.short, status=self.status)

    SOURCE_TEXT = (
        "Amsterdam Dance Event celebrates 30 years with more than 3,600 artists, 1,300 events and 300 venues across the city.\n"
        "Jean-Michel Jarre opens the festival with a concert at AFAS Live on 21 October to mark 50 years of Oxygène.\n"
    )

    class StubSnaps:
        def list(self, _id):
            return [
                type("Snap", (), {
                    "id": "s" * 32,
                    "url": "https://example.com",
                    "text": SOURCE_TEXT,
                })()
            ]

    class StubScripts:
        def __init__(self, videos):
            self.videos = videos
            self.drafts = []
        def save_and_advance(self, video_id, text, drafts, claim_ids, expected, new):
            self.videos.status = new
            self.drafts = drafts
            return Script(id="sc" * 16, video_id=video_id, version=1, text=text, claim_ids=claim_ids)

    class StubUsage:
        def record(self, video_id, entry): pass
        def spent_video(self, video_id): return 0.0
        def spent_month(self): return 0.0

    claims_ids = ["c1"]
    fake_llm_scenes = json.dumps({
        "scenes": [
            {
                "narration": "Amsterdam Dance Event celebrates 30 years.",
                "caption": "ADE 30 Anos",
                "label": "INTRO",
                "image_prompt": "Grand festival stage with laser lights",
                "claim_ids": claims_ids,
                "visual_intent": "Plano geral do palco com iluminação épica",
                "recommended_asset_kind": "video",
                "search_queries": ["ade festival", "electronic music stage"],
            },
            {
                "narration": "Jean-Michel Jarre opens festival.",
                "caption": "Abertura Épica",
                "label": "SHOW",
                "image_prompt": "Electronic music pioneer performing with synthesizers",
                "claim_ids": claims_ids,
                "visual_intent": "Close dinâmico nos sintetizadores",
                "recommended_asset_kind": "video",
                "search_queries": ["synthesizer live performance"],
            },
        ]
    })

    model = FakeTextModel(fake_llm_scenes)
    videos = StubVideos()
    snaps = StubSnaps()
    scripts = StubScripts(videos)
    usage = StubUsage()
    guard = CostGuard(usage, 5.0, 15.0)

    # We need real claims to be extracted by _claims
    # Let's see: _claims(snaps.list(video_id)) uses extract_claims
    from app.studio.domain.claims import extract_claims
    extracted = extract_claims("s" * 32, snaps.list(vid)[0].text)
    c_ids = [c.id for c in extracted]

    # Re-craft fake_llm_scenes with real claim IDs
    fake_llm_scenes = json.dumps({
        "scenes": [
            {
                "narration": "Amsterdam Dance Event celebrates 30 years.",
                "caption": "ADE 30 Anos",
                "label": "INTRO",
                "image_prompt": "Grand festival stage with laser lights",
                "claim_ids": [c_ids[0]],
                "visual_intent": "Plano geral do palco com iluminação épica",
                "recommended_asset_kind": "video",
                "search_queries": ["ade festival", "electronic music stage"],
            },
            {
                "narration": "Jean-Michel Jarre opens festival.",
                "caption": "Abertura Épica",
                "label": "SHOW",
                "image_prompt": "Electronic music pioneer performing with synthesizers",
                "claim_ids": [c_ids[1]],
                "visual_intent": "Close dinâmico nos sintetizadores",
                "recommended_asset_kind": "video",
                "search_queries": ["synthesizer live performance"],
            },
        ]
    })
    model = FakeTextModel(fake_llm_scenes)

    gen = GenerateScript(videos, snaps, scripts, model, guard, usage)
    brief = CreativeBrief.model_validate_json(sample_brief_json())

    script = gen.execute(vid, 2, brief=brief)
    assert script is not None
    assert "DIRETRIZES DO DIRETOR CRIATIVO" in model.prompts[0]
    assert brief.hook in model.prompts[0]
    assert len(scripts.drafts) == 2
    assert scripts.drafts[0].visual_intent == "Plano geral do palco com iluminação épica"
    assert scripts.drafts[0].recommended_asset_kind == "video"
    assert scripts.drafts[0].search_queries == ["ade festival", "electronic music stage"]

