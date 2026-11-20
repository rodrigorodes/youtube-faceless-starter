import pytest
from pydantic import ValidationError

from app.studio.domain.content_brief import ContentBrief


def brief(**changes):
    values = {
        "topic": "A queda de Constantinopla",
        "audience": "Interessados em história",
        "objective": "Explicar as causas",
        "interest_hypothesis": "O evento mudou o comércio",
    }
    values.update(changes)
    return ContentBrief(**values)


def test_manual_brief_round_trips_with_optional_editorial_details():
    original = brief(
        references=["Livro indicado manualmente", "https://example.org/source"],
        target_duration_seconds=480,
        voice="Narrador",
        pace="moderado",
        structure="cronológica",
        language="português",
        constraints=["Sem especulação"],
    )
    restored = ContentBrief.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.schema_version == 1
    assert restored.trend_id is None
    assert restored.references == ("Livro indicado manualmente", "https://example.org/source")


def test_trend_is_optional_and_preserved_when_supplied():
    assert brief(trend_id="trend-123").trend_id == "trend-123"


@pytest.mark.parametrize("field", [
    "topic", "audience", "objective", "interest_hypothesis", "trend_id",
    "voice", "pace", "structure", "language",
])
def test_text_fields_reject_blank_values(field):
    with pytest.raises(ValidationError):
        brief(**{field: "  "})


@pytest.mark.parametrize("field", ["references", "constraints"])
def test_collection_entries_cannot_be_blank(field):
    with pytest.raises(ValidationError):
        brief(**{field: ["valid", "  "]})


@pytest.mark.parametrize("value", [0, -1, True, "480", 1.5])
def test_duration_must_be_a_positive_integer_when_present(value):
    with pytest.raises(ValidationError):
        brief(target_duration_seconds=value)


@pytest.mark.parametrize("value", [0, 2, True, "1"])
def test_unknown_or_non_integer_schema_version_is_rejected(value):
    with pytest.raises(ValidationError):
        brief(schema_version=value)


def test_contract_is_immutable_and_rejects_unknown_fields():
    result = brief(references=["manual"])
    with pytest.raises(ValidationError):
        result.topic = ""
    with pytest.raises(ValidationError):
        brief(unexpected=True)
    assert isinstance(result.references, tuple)
