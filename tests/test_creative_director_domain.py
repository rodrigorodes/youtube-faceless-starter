import pytest
from pydantic import ValidationError

from app.studio.domain.creative_director import CreativeBrief, MediaType


def sample_brief_data(**overrides):
    base = {
        "topic": "History of the Printing Press",
        "narrative_goal": "Engage viewers with the transformative power of the press",
        "hook": "Did you know one invention changed human thought forever?",
        "content_structure": ("Hook & Origin", "Gutenberg's Revolution", "Impact on Society"),
        "tone": "Educational and energetic",
        "pacing": "Fast-paced with deliberate pauses",
        "visual_direction": "Engraving style illustrations with dynamic zooms",
        "caption_strategy": "Bold keyword highlight on bottom third",
        "audio_guidance": "Epic classical music building to a climax",
    }
    base.update(overrides)
    return base


def test_creative_brief_valid_defaults():
    data = sample_brief_data()
    brief = CreativeBrief(**data)

    assert brief.schema_version == 1
    assert brief.topic == "History of the Printing Press"
    assert brief.narrative_goal == "Engage viewers with the transformative power of the press"
    assert brief.hook == "Did you know one invention changed human thought forever?"
    assert brief.content_structure == ("Hook & Origin", "Gutenberg's Revolution", "Impact on Society")
    assert brief.tone == "Educational and energetic"
    assert brief.pacing == "Fast-paced with deliberate pauses"
    assert brief.visual_direction == "Engraving style illustrations with dynamic zooms"
    assert brief.recommended_media_types == ("image", "video")
    assert brief.caption_strategy == "Bold keyword highlight on bottom third"
    assert brief.audio_guidance == "Epic classical music building to a climax"
    assert brief.max_budget_usd is None
    assert brief.quality_criteria == ()


def test_creative_brief_custom_optional_fields():
    data = sample_brief_data(
        recommended_media_types=("image", "graphic", "text"),
        max_budget_usd=15.50,
        quality_criteria=("Clear pronunciation", "High contrast visuals"),
    )
    brief = CreativeBrief(**data)

    assert brief.recommended_media_types == ("image", "graphic", "text")
    assert brief.max_budget_usd == 15.50
    assert brief.quality_criteria == ("Clear pronunciation", "High contrast visuals")


def test_creative_brief_zero_budget_allowed():
    brief = CreativeBrief(**sample_brief_data(max_budget_usd=0.0))
    assert brief.max_budget_usd == 0.0


def test_creative_brief_negative_budget_rejected():
    with pytest.raises(ValidationError):
        CreativeBrief(**sample_brief_data(max_budget_usd=-0.01))


def test_creative_brief_schema_version_validation():
    with pytest.raises(ValidationError):
        CreativeBrief(**sample_brief_data(schema_version=2))


@pytest.mark.parametrize(
    "field",
    [
        "topic",
        "narrative_goal",
        "hook",
        "tone",
        "pacing",
        "visual_direction",
        "caption_strategy",
        "audio_guidance",
    ],
)
@pytest.mark.parametrize("bad_value", ["", "   ", "\t\n"])
def test_creative_brief_non_blank_string_fields(field, bad_value):
    with pytest.raises(ValidationError):
        CreativeBrief(**sample_brief_data(**{field: bad_value}))


def test_creative_brief_content_structure_min_two_sections():
    # Empty tuple
    with pytest.raises(ValidationError):
        CreativeBrief(**sample_brief_data(content_structure=()))

    # Only 1 section
    with pytest.raises(ValidationError):
        CreativeBrief(**sample_brief_data(content_structure=("Only One",)))

    # Blank item in sections
    with pytest.raises(ValidationError):
        CreativeBrief(**sample_brief_data(content_structure=("Section 1", "  ")))

    # 2 sections is valid
    brief = CreativeBrief(**sample_brief_data(content_structure=("Intro", "Outro")))
    assert brief.content_structure == ("Intro", "Outro")


def test_creative_brief_recommended_media_types_validation():
    # Valid kinds
    brief = CreativeBrief(**sample_brief_data(recommended_media_types=("video", "text")))
    assert brief.recommended_media_types == ("video", "text")

    # Invalid media type
    with pytest.raises(ValidationError):
        CreativeBrief(**sample_brief_data(recommended_media_types=("audio",)))


def test_creative_brief_quality_criteria_non_blank():
    with pytest.raises(ValidationError):
        CreativeBrief(**sample_brief_data(quality_criteria=("Valid", "   ")))


def test_creative_brief_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        CreativeBrief(**sample_brief_data(extra_custom_field="not allowed"))


def test_creative_brief_frozen():
    brief = CreativeBrief(**sample_brief_data())
    with pytest.raises(ValidationError):
        brief.topic = "New Topic"


def test_creative_brief_serialization_roundtrip():
    data = sample_brief_data(
        recommended_media_types=("image", "video", "graphic"),
        max_budget_usd=20.0,
        quality_criteria=("Criterion 1", "Criterion 2"),
    )
    brief = CreativeBrief(**data)
    dumped = brief.model_dump()
    reloaded = CreativeBrief.model_validate(dumped)
    assert brief == reloaded
