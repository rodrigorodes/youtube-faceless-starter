"""O modelo copia ids de fato (hash hex de 10 chars) com erros de transcrição; o parser os resolve
quando a correção é inequívoca e continua recusando ids realmente inventados."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import ScriptRejected, parse_drafts  # noqa: E402

VALID = {"3ad7edf068", "afb959c2c5", "1ce16e4a96", "9483fb8664"}


def scenes(*claim_lists):
    return json.dumps({"scenes": [
        {"narration": f"Narração da cena {i}.", "caption": "c", "label": "l",
         "image_prompt": "uma ilha tropical com vulcões", "claim_ids": ids}
        for i, ids in enumerate(claim_lists)]})


def parse(*claim_lists):
    return parse_drafts(scenes(*claim_lists), VALID)


def pad(*first):
    return [*first] + [["afb959c2c5"]] * (4 - len(first))  # MIN_SCENES com cenas válidas


def test_transposed_characters_resolve_to_the_only_close_valid_id():
    drafts = parse(*pad(["afb959c2c5"], ["afb959c2c5"], ["afb959c2c5"], ["3ad7fed068"]))  # real: edf -> fed
    assert drafts[3].claim_ids == ["3ad7edf068"]


@pytest.mark.parametrize("written", ["[3ad7edf068]", " 3AD7EDF068 ", "3ad7edf06", "3ad7edf0688", "3ad7edf069"])
def test_formatting_and_single_edit_slips_resolve(written):
    assert parse(*pad(["afb959c2c5"], ["afb959c2c5"], ["afb959c2c5"], [written]))[3].claim_ids == ["3ad7edf068"]


def test_resolved_ids_are_deduplicated():
    drafts = parse(*pad(["afb959c2c5"], ["afb959c2c5"], ["afb959c2c5"], ["3ad7edf068", "3ad7fed068"]))
    assert drafts[3].claim_ids == ["3ad7edf068"]


@pytest.mark.parametrize("invented", ["deadbeef00", "3ad7aaaaaa", "xxxxxxxxxx", "3ad7"])
def test_invented_ids_are_still_rejected(invented):
    with pytest.raises(ScriptRejected, match="unknown claim ids"):
        parse(*pad(["afb959c2c5"], ["afb959c2c5"], ["afb959c2c5"], [invented]))


def test_ambiguous_near_miss_is_rejected():
    valid = {"aaaaaaaaaa", "aaaaaaaaab"}  # 'aaaaaaaaac' está a 1 edição dos dois
    raw = scenes(*[["aaaaaaaaac"]] * 4)
    with pytest.raises(ScriptRejected, match="unknown claim ids"):
        parse_drafts(raw, valid)
