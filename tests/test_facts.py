import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.facts import Unsupported, check_narration, normalize, numbers_in, proper_nouns_in  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("vinte e um de outubro", {"21"}),
    ("trinta anos", {"30"}),
    ("três mil e seiscentos artistas", {"3600"}),
    ("mais de mil e trezentos eventos", {"1300"}),
    ("mais de trezentos locais", {"300"}),
    ("cinquenta anos de Oxygène", {"50"}),
    ("oito horas seguidas", {"8"}),
    ("cento e vinte", {"120"}),
    ("dois dias", {"2"}),
    ("um concerto e uma sessão", set()),  # "um/uma" sozinhos são artigos
    ("30 YEARS ADE", {"30"}),
    ("Paul Kalkbrenner", set()),
])
def test_digits_and_words_equal(text, expected):
    assert numbers_in(text) == expected


@pytest.mark.parametrize("text", ["3.600", "3,600", "3600", "3.600+", "três mil e seiscentos"])
def test_thousand_separators_pt_and_en(text):
    assert numbers_in(text) == {"3600"}


def test_decimal_and_mil():
    assert numbers_in("1,5 mil") == {"1500"}
    assert numbers_in("2,5") == {"2.5"}
    assert numbers_in("3 mil pessoas") == {"3000"}
    assert numbers_in("1.300+ events") == {"1300"}


def test_date_21_10_and_times():
    assert numbers_in("21/10") == {"21", "10"}
    assert numbers_in("21 ––– 25/10") == {"21", "25", "10"}
    assert numbers_in("17:30 – 22:30") == {"17", "30", "22"}
    assert numbers_in("21.10.2026") == {"21", "10", "2026"}
    assert numbers_in("8h set") == {"8"}


def test_accents_folded():
    assert normalize("Oxygène  Amsterdã ") == "oxygene amsterda"


def test_sentence_start_capital_ignored():
    assert proper_nouns_in("Na quarta, Jarre abriu. Quarta-feira chegou.") == {"jarre"}


def test_hyphenated_name_split_and_multiword_start():
    assert proper_nouns_in("Na abertura, Jean-Michel Jarre tocou") == {"jean", "michel", "jarre"}
    assert proper_nouns_in("Paul Kalkbrenner tocou") == {"paul", "kalkbrenner"}


def test_documented_limit_single_initial_word_is_not_checked():
    assert proper_nouns_in("Madonna tocou") == set()  # limite conhecido (docstring de facts.py)
    assert proper_nouns_in("Hoje Jarre tocou") == {"hoje", "jarre"}  # início + capitalizada: os dois são checados


def test_number_supported_by_source():
    src = ["The program has 3,600 artists, 1,300+ events and 300+ venues from 21 to 25 October."]
    assert check_narration("Eram mais de três mil e seiscentos artistas e mais de mil e trezentos eventos.", src) == []
    assert check_narration("A programação foi de vinte e um a vinte e cinco de outubro.", src) == []


def test_invented_number_is_flagged():
    src = ["The program has 3,600 artists."]
    assert check_narration("Eram quatro mil artistas.", src) == [Unsupported("number", "4000")]


def test_proper_noun_not_in_source_is_flagged():
    src = ["Jean-Michel Jarre opened the festival at AFAS Live."]
    assert check_narration("Na abertura, Jean-Michel Jarre tocou no AFAS Live.", src) == []
    assert check_narration("Na abertura, Madonna tocou no AFAS Live.", src) == [Unsupported("name", "madonna")]


def test_allow_names_for_exonyms():
    src = ["Amsterdam Dance Event"]
    assert check_narration("O festival, em Amsterdã, começou.", src) == [Unsupported("name", "amsterda")]
    assert check_narration("O festival, em Amsterdã, começou.", src, allow_names=frozenset({"amsterda"})) == []


def test_empty_sources_flag_everything_checkable():
    assert check_narration("Eram trinta artistas.", []) == [Unsupported("number", "30")]
    assert check_narration("Sem fatos aqui.", []) == []
