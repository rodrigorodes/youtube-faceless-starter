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


@pytest.mark.parametrize("text,expected", [
    ("dois milhões de pessoas", {"2000000"}), ("quatro milhões", {"4000000"}), ("três bilhões", {"3000000000"}),
    ("um milhão", {"1000000"}), ("um bilhão", {"1000000000"}), ("meio milhão", {"500000"}),
    ("uma dúzia", {"12"}), ("meia dúzia", {"6"}), ("5k", {"5000"}), ("5 K ingressos", {"5000"}),
    ("2 milhões", {"2000000"}), ("1,5 milhão", {"1500000"}), ("2 bilhões", {"2000000000"}),
    ("milhões de pessoas", {"1000000"}), ("dois palcos", {"2"}), ("um concerto", set()),
    ("duzentos e cinquenta mil", {"250000"}),
])
def test_scale_words_are_numbers(text, expected):
    assert numbers_in(text) == expected


def test_invented_scale_is_flagged_even_if_the_small_number_exists():
    src = ["São 2 palcos e 4 dias, 5 mil, 3 artistas, 1 sala"]
    assert check_narration("Foram dois milhões de pessoas.", src) == [Unsupported("number", "2000000")]
    assert check_narration("Foram três bilhões de ouvintes.", src) == [Unsupported("number", "3000000000")]
    assert check_narration("Um milhão de fãs.", src) == [Unsupported("number", "1000000")]
    assert check_narration("Foram dois palcos e cinco mil pessoas.", src) == []


def test_huge_digit_strings_do_not_crash():
    assert numbers_in("9" * 5000) == {"9" * 5000}


def test_name_after_abbreviation_or_quote_is_checked():
    assert {"silva", "costa"} <= proper_nouns_in("O Dr. Silva abriu. Convidado: Prof. Costa.")
    assert "silva" in proper_nouns_in("\u201cSilva\u201d disse que sim")
    assert proper_nouns_in("Quem chegou? Jarre abriu.") == set()  # limite documentado: capitalizada sozinha no início


def test_letters_without_decomposition_match_the_source():
    assert check_narration("No palco, R\u00f8dh\u00e5d tocou", ["R\u00f8dh\u00e5d played the closing set"]) == []
    assert normalize("Stra\u00dfe \u0141\u00f3d\u017a \u00c6on") == "strasse lodz aeon"


# ---- supporting_claim_ids: a citação da cena acompanha o texto editado -----------------------------------------
from app.studio.domain.facts import supporting_claim_ids  # noqa: E402

CLAIMS = [
    ("c1", "Constantinopla caiu em 29 de maio de 1453 depois de um cerco de 53 dias."),
    ("c2", "O sultão Mehmed II comandava cerca de 80 mil soldados otomanos."),
    ("c3", "A cidade era defendida por aproximadamente 7 mil homens sob o imperador Constantino XI."),
]


def test_supporting_claims_follow_the_numbers_and_names_in_the_new_text():
    assert supporting_claim_ids("O sultão Mehmed II comandava cerca de 80 mil soldados.", CLAIMS) == ["c2"]
    assert supporting_claim_ids("Eram 80 mil atacantes contra 7 mil defensores.", CLAIMS) == ["c2", "c3"]


def test_supporting_claims_are_empty_when_the_text_has_nothing_checkable():
    assert supporting_claim_ids("A cidade era enorme e muito bonita.", CLAIMS) == []


def test_supporting_claims_are_none_when_a_token_is_not_in_any_claim():
    """Se algum número/nome não está em nenhum fato, não há citação completa: quem chama mantém a anterior."""
    assert supporting_claim_ids("O cerco durou 987654 dias.", CLAIMS) is None


def test_the_derived_claims_make_the_fact_check_pass():
    text = "O sultão Mehmed II comandava cerca de 80 mil soldados."
    ids = supporting_claim_ids(text, CLAIMS)
    cited = [t for cid, t in CLAIMS if cid in ids]
    assert check_narration(text, cited) == []
    assert check_narration(text, [CLAIMS[0][1]]) != []  # com a citação antiga (c1) o fact-check reprovaria


# ---- formatos numéricos de milhar/decimal (pt-BR com ponto, espaço e vírgula; en com vírgula e ponto) ----

@pytest.mark.parametrize("text", ["132.011,65", "132 011,65", "132\u00a0011,65", "132\u202f011,65", "132,011.65"])
def test_mixed_thousand_and_decimal_separators_are_one_number(text):
    assert numbers_in(text) == {"132011.65"}


@pytest.mark.parametrize("text", ["3 600", "3\u00a0600", "3.600", "3,600"])
def test_space_grouped_thousands_equal_other_notations(text):
    assert numbers_in(text) == {"3600"}


def test_space_grouping_does_not_merge_dates_years_or_loose_numbers():
    assert numbers_in("em 2023 tinha 153.391.145 habitantes") == {"2023", "153391145"}
    assert numbers_in("21 10 2026") == {"21", "10", "2026"}
    assert numbers_in("2026 100 pessoas") == {"2026", "100"}
    assert numbers_in("1 2 3") == {"1", "2", "3"}


def test_area_written_in_either_notation_is_supported_by_the_source():
    source = "Tem 132 011,65 km² de área e em 2023 tinha 153.391.145 habitantes"
    assert check_narration("Em 2023 tinha 132.011,65 km² e 153.391.145 habitantes.", [source]) == []
    other = check_narration("A ilha tem 132.011,66 km².", [source])  # valor diferente continua recusado
    assert [(i.kind, i.value) for i in other] == [("number", "132011.66")]


def test_numbers_in_and_check_narration_handle_word_zero():
    """Regressão P1-1: palavra 'zero' (_WORDS['zero'] == 0) não pode causar KeyError em _parse_run."""
    assert numbers_in("zero") == {"0"}
    assert numbers_in("sistema binário de zero e um") == {"0"}
    assert check_narration("O sistema binário de zero e um.", ["Base binária com 0 e 1."]) == []
    unsupported = check_narration("O sistema binário de zero e um.", ["Texto sem números."])
    assert [(i.kind, i.value) for i in unsupported] == [("number", "0")]

