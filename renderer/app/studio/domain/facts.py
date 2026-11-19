"""Checagem factual determinística (domínio puro).

Regra: todo número e nome próprio da narração precisa aparecer nas fontes. Formatos equivalentes casam
(`3.600`, `3,600`, `três mil e seiscentos`). Limite conhecido: a primeira palavra de uma frase, sozinha, não
é tratada como nome próprio (não há léxico para distinguir de palavra comum); se vier seguida de outra
palavra capitalizada, os dois tokens são checados.
"""
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

_WORDS = {
    "zero": 0, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9,
    "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14, "quinze": 15, "dezesseis": 16,
    "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50,
    "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90, "cem": 100, "cento": 100, "duzentos": 200,
    "trezentos": 300, "quatrocentos": 400, "quinhentos": 500, "seiscentos": 600, "setecentos": 700,
    "oitocentos": 800, "novecentos": 900,
}
_ARTICLE_UNITS = {"um": 1, "uma": 1}  # só contam dentro de um número composto ("vinte e um")
_MULT = {"mil": 1000, "milhao": 1_000_000, "milhoes": 1_000_000}
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[a-z]+")
_THOUSANDS = re.compile(r"\d{1,3}(?:[.,]\d{3})+")
_DECIMAL = re.compile(r"\d+[.,]\d+")


def normalize(text: str) -> str:
    folded = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(folded.lower().split())


def _fmt(value: Decimal) -> str:
    return str(int(value)) if value == value.to_integral_value() else format(value.normalize(), "f")


def _digit_values(token: str) -> list[Decimal]:
    if token.isdigit():
        return [Decimal(token)]
    if _THOUSANDS.fullmatch(token):
        return [Decimal(token.replace(".", "").replace(",", ""))]
    if _DECIMAL.fullmatch(token):
        return [Decimal(token.replace(",", "."))]
    return [Decimal(part) for part in re.split(r"[.,]", token)]  # datas como 21.10.2026


def _fits(prev: str, word: str, current: int, mil_used: bool) -> bool:
    if word == "mil":
        return not mil_used and 0 < current < 1000
    value = _WORDS.get(word) or _ARTICLE_UNITS.get(word, 0)
    if prev == "mil":
        return 1 <= value <= 999
    prev_value = _WORDS.get(prev) or _ARTICLE_UNITS.get(prev, 0)
    if 20 <= prev_value <= 90 and prev_value % 10 == 0:
        return 1 <= value <= 9
    if prev_value >= 100 and prev_value % 100 == 0:
        return 0 < value < 100
    return False


def _parse_run(tokens: list[str], start: int) -> tuple[int, int]:
    total = current = 0
    mil_used, prev, j = False, None, start
    while j < len(tokens):
        word = tokens[j]
        if word == "e":  # "e" só continua o número se a próxima palavra encaixa
            nxt = tokens[j + 1] if j + 1 < len(tokens) else ""
            if prev and (nxt in _WORDS or nxt in _ARTICLE_UNITS or nxt == "mil") and _fits(prev, nxt, current, mil_used):
                j += 1
                continue
            break
        if word not in _WORDS and word not in _ARTICLE_UNITS and word != "mil":
            break
        if prev is not None and not _fits(prev, word, current, mil_used):
            break
        if word == "mil":
            total += (current or 1) * 1000
            current, mil_used = 0, True
        else:
            current += _WORDS.get(word) or _ARTICLE_UNITS[word]
        prev, j = word, j + 1
    return total + current, j


def numbers_in(text: str) -> set[str]:
    tokens = _TOKEN.findall(normalize(text))
    found: set[str] = set()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token[0].isdigit():
            values = _digit_values(token)
            if len(values) == 1 and i + 1 < len(tokens) and tokens[i + 1] in _MULT:
                values = [values[0] * _MULT[tokens[i + 1]]]
                i += 1
            found.update(_fmt(v) for v in values)
            i += 1
        elif token in _WORDS or token == "mil":  # "um/uma" sozinhos não iniciam número
            value, i = _parse_run(tokens, i)
            found.add(str(value))
        else:
            i += 1
    return found


_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[^\W\d_]+")


def proper_nouns_in(text: str) -> set[str]:
    names: set[str] = set()
    for sentence in _SENTENCE.split(text):
        words = _WORD.findall(sentence.replace("-", " "))
        for index, word in enumerate(words):
            if len(word) < 3 or not word[0].isupper():
                continue
            starts_name = index == 0 and len(words) > 1 and words[1][0].isupper()
            if index > 0 or starts_name:
                names.add(normalize(word))
    return names


@dataclass(frozen=True)
class Unsupported:
    kind: str  # "number" | "name"
    value: str


def check_narration(narration: str, source_texts: list[str], allow_names: frozenset[str] = frozenset()) -> list[Unsupported]:
    source_numbers: set[str] = set()
    source_words: set[str] = set()
    for source in source_texts:
        source_numbers |= numbers_in(source)
        source_words |= set(re.findall(r"[a-z]+", normalize(source)))
    allowed = {normalize(name) for name in allow_names}
    issues = [Unsupported("number", n) for n in sorted(numbers_in(narration) - source_numbers, key=lambda x: (len(x), x))]
    issues += [Unsupported("name", n) for n in sorted(proper_nouns_in(narration)) if n not in source_words and n not in allowed]
    return issues
