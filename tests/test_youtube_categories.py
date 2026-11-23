import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.youtube_categories import youtube_category_for  # noqa: E402


@pytest.mark.parametrize("texts,expected", [
    (("Games", "GTA 6, lançamento"), "20"),
    (("Festivais & Lineups", "ADE 2026"), "10"),
    (("Música Eletrônica",), "10"),
    (("Cachorro", "Canil", "kennel"), "15"),
    (("Cane Corso",), None),  # sem palavra-chave conhecida: sem Em Alta, em vez de Em Alta fora do nicho
    (("História",), "27"),
    (("Corte de carne",), "26"),
    (("Inteligência artificial",), "28"),
    (("",), None),
    ((), None),
])
def test_category_is_derived_from_pillar_and_niche_words(texts, expected):
    assert youtube_category_for(*texts) == expected


def test_accents_and_case_do_not_matter():
    assert youtube_category_for("MÚSICA") == youtube_category_for("musica") == "10"


def test_words_must_match_whole_tokens():
    assert youtube_category_for("popular") is None  # "pop" não casa dentro de "popular"
