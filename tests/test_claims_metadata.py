import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.claims import extract_claims  # noqa: E402
from app.studio.domain.contracts import FactCheckReport, Scene, SceneFactCheck, SourceSnapshot, UnsupportedItem  # noqa: E402
from app.studio.domain.metadata import DISCLOSURE_TEXT, build_metadata  # noqa: E402

TEXT = """ADE 2026
Amsterdam Dance Event celebrates 30 years with more than 3,600 artists, 1,300 events and 300 venues across the city.
short line.
Jean-Michel Jarre opens the festival with a concert at AFAS Live on 21 October to mark 50 years of Oxygène.
this sentence is long enough but has no digits or capitalised names at all in it so it is dropped.
"""


def test_claims_deterministic_and_filtered():
    a = extract_claims("s" * 32, TEXT)
    assert a == extract_claims("s" * 32, TEXT)
    texts = [c.text for c in a]
    assert any("3,600 artists" in t for t in texts) and any("Jarre" in t for t in texts)
    assert not any("short line" in t or "no digits" in t for t in texts)
    assert len({c.id for c in a}) == len(a) and all(len(c.id) == 10 for c in a)


def test_claims_limit_and_dedupe():
    text = "\n".join([f"Event number {i} happens in Amsterdam during the festival week with 100 guests." for i in range(60)] * 2)
    assert len(extract_claims("s" * 32, text, limit=10)) == 10
    assert len(extract_claims("s" * 32, text, limit=100)) == 60


def test_metadata_has_disclosure_and_sources():
    m = build_metadata("ADE 2026: destaques", ["Primeira cena.", "Segunda cena."], ["https://amsterdam-dance-event.nl/x"])
    assert DISCLOSURE_TEXT in m.description and "https://amsterdam-dance-event.nl/x" in m.description
    assert m.description.endswith(DISCLOSURE_TEXT) and len(m.tags) <= 8 and all(len(t) <= 30 for t in m.tags)


def test_title_trimmed_to_100_and_description_bounded():
    m = build_metadata("t" * 300, ["palavra " * 2000], ["https://a.example/" + "x" * 50] * 5, title_hint="h" * 300)
    assert len(m.title) == 100 and len(m.description) <= 4900 and DISCLOSURE_TEXT in m.description


def test_fact_check_report_override_needs_reason():
    ok = FactCheckReport(passed=True, overridden=True, override_reason="verificado manualmente", scenes=[])
    assert ok.passed
    for reason in (None, "", "   "):
        with pytest.raises(ValidationError):
            FactCheckReport(passed=True, overridden=True, override_reason=reason, scenes=[])


def test_new_contracts_roundtrip():
    s = SourceSnapshot(id="a" * 32, video_id="b" * 32, url="https://x.example", content_sha256="c" * 64, text="t")
    r = FactCheckReport(passed=False, scenes=[SceneFactCheck(idx=0, unsupported=[UnsupportedItem(kind="number", value="4000")])])
    assert s.text == "t" and r.scenes[0].unsupported[0].value == "4000"
    assert Scene(id="a" * 32, video_id="b" * 32, idx=0, narration="Uma fala válida", image_prompt="uma cena genérica longa").claim_ids == []
