"""Checagem factual determinística (domínio puro).

Regra: todo número e nome próprio da narração precisa aparecer nas fontes. Formatos equivalentes casam
(`3.600`, `3,600`, `três mil e seiscentos`). Limite conhecido: a primeira palavra de uma frase, sozinha, não
é tratada como nome próprio (não há léxico para distinguir de palavra comum); se vier seguida de outra
palavra capitalizada, os dois tokens são checados.
"""
import re
import unicodedata
from dataclasses import dataclass
from collections.abc import Sequence
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
_BIG = {"milhao": 10**6, "milhoes": 10**6, "bilhao": 10**9, "bilhoes": 10**9}
_MULT = {"mil": 1000, "k": 1000, **_BIG}  # após dígitos ("5k", "2 milhões")
_HALF_ONE = {"um": Decimal(1), "uma": Decimal(1), "meio": Decimal("0.5"), "meia": Decimal("0.5")}
_DOZEN = {"duzia", "duzias"}
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[a-z]+")
_THOUSANDS = re.compile(r"\d{1,3}(?:[.,]\d{3})+")
_DECIMAL = re.compile(r"\d+[.,]\d+")
_PT_THOUSANDS_DECIMAL = re.compile(r"\d{1,3}(?:\.\d{3})+,\d+")  # 132.011,65
_EN_THOUSANDS_DECIMAL = re.compile(r"\d{1,3}(?:,\d{3})+\.\d+")  # 132,011.65
# Milhar por espaço ("132 011,65", "3 600"; já normalizado: NBSP/NNBSP viram espaço): só grupos de
# exatamente 3 dígitos, fora de outro número — "2026 100" e "21 10 2026" continuam separados.
_SPACE_THOUSANDS = re.compile(r"(?<![\d.,])\d{1,3}(?: \d{3})+(?!\d)")


_FOLD = str.maketrans({"ø": "o", "đ": "d", "ð": "d", "ł": "l", "ß": "ss", "æ": "ae", "œ": "oe", "þ": "th"})


def normalize(text: str) -> str:
    folded = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(folded.lower().translate(_FOLD).split())


def _fmt(value: Decimal) -> str:
    text = format(value, "f")  # exato (sem normalize/arredondamento do contexto) e sem int(): número gigante não estoura
    return text.rstrip("0").rstrip(".") if "." in text else text


def _digit_values(token: str) -> list[Decimal]:
    if token.isdigit():
        return [Decimal(token)]
    if _THOUSANDS.fullmatch(token):
        return [Decimal(token.replace(".", "").replace(",", ""))]
    if _PT_THOUSANDS_DECIMAL.fullmatch(token):
        return [Decimal(token.replace(".", "").replace(",", "."))]
    if _EN_THOUSANDS_DECIMAL.fullmatch(token):
        return [Decimal(token.replace(",", ""))]
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
    tokens = _TOKEN.findall(_SPACE_THOUSANDS.sub(lambda m: m.group(0).replace(" ", ""), normalize(text)))
    found: set[str] = set()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if token[0].isdigit():
            values = _digit_values(token)
            if len(values) == 1 and nxt in _MULT:
                values = [values[0] * _MULT[nxt]]
                i += 1
            found.update(_fmt(v) for v in values)
            i += 1
        elif token in _HALF_ONE and nxt in _BIG:  # "um milhão", "meio milhão"
            found.add(_fmt(_HALF_ONE[token] * _BIG[nxt]))
            i += 2
        elif token in ("um", "uma", "meia") and nxt in _DOZEN:  # "uma dúzia", "meia dúzia"
            found.add(_fmt(_HALF_ONE[token] * 12))
            i += 2
        elif token in _WORDS or token == "mil":  # "um/uma" sozinhos não iniciam número
            value, i = _parse_run(tokens, i)
            scale = _BIG.get(tokens[i], 1) if i < len(tokens) else 1
            if scale > 1:
                i += 1
            found.add(_fmt(Decimal(value) * scale))
        elif token in _BIG:  # escala sem número: "milhões de pessoas"
            found.add(str(_BIG[token]))
            i += 1
        else:
            i += 1
    return found


_SENTENCE = re.compile(r"(\n+|(?<=[.!?])\s+)")
_WORD = re.compile(r"[^\W\d_]+")
_ABBREVIATIONS = {"dr", "dra", "prof", "profa", "sr", "sra", "srta", "st", "mr", "mrs", "ms", "dj", "vs", "av", "eng", "ex"}


def _ends_with_abbreviation(sentence: str) -> bool:
    words = sentence.split()
    return bool(words) and words[-1].endswith(".") and words[-1][:-1].lower() in _ABBREVIATIONS


def _sentences(text: str) -> list[str]:
    """Quebra em frases sem separar "Dr. Silva": abreviatura seguida de ponto não encerra a frase."""
    parts = _SENTENCE.split(text)  # [trecho, separador, trecho, ...]
    sentences: list[str] = []
    for k in range(0, len(parts), 2):
        separator = parts[k - 1] if k else ""
        if sentences and "\n" not in separator and _ends_with_abbreviation(sentences[-1]):
            sentences[-1] += " " + parts[k]
        else:
            sentences.append(parts[k])
    return sentences


def proper_nouns_in(text: str) -> set[str]:
    names: set[str] = set()
    for sentence in _sentences(text):
        stripped = sentence.lstrip()
        opens_with_letter = bool(stripped) and stripped[0].isalpha()  # aspas/travessão: a 1ª palavra não é "início de frase"
        words = _WORD.findall(sentence.replace("-", " "))
        for index, word in enumerate(words):
            if len(word) < 3 or not word[0].isupper():
                continue
            starts_name = index == 0 and len(words) > 1 and words[1][0].isupper()
            if index > 0 or starts_name or not opens_with_letter:
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


def check_names(text: str, source_texts: list[str], allow_names: frozenset[str] = frozenset()) -> list[Unsupported]:
    """Só nomes próprios (ex.: image_prompt, onde números como "9:16" não são fatos)."""
    source_words: set[str] = set()
    for source in source_texts:
        source_words |= set(re.findall(r"[a-z]+", normalize(source)))
    allowed = {normalize(name) for name in allow_names}
    return [Unsupported("name", n) for n in sorted(proper_nouns_in(text)) if n not in source_words and n not in allowed]


def supporting_claim_ids(narration: str, claims: Sequence[tuple[str, str]],
                         allow_names: frozenset[str] = frozenset()) -> list[str] | None:
    """Fatos (id, texto) que juntos sustentam os números e nomes da narração, na ordem de `claims`.

    O fact-check confere cada cena só contra os fatos que ela cita; ao editar o texto, a citação precisa
    acompanhá-lo, ou a cena é reprovada por "fato" que existe nas fontes. Cobertura gulosa: a cada passo, o
    fato que cobre mais números/nomes ainda descobertos. `[]` se o texto não tem nada checável (a cena segue
    conferida contra todas as fontes); `None` se algum número ou nome não está em nenhum fato — quem chama
    mantém a citação anterior em vez de inventar uma.
    """
    allowed = {normalize(name) for name in allow_names}
    need_numbers = set(numbers_in(narration))
    need_names = {n for n in proper_nouns_in(narration) if n not in allowed}
    if not need_numbers and not need_names:
        return []
    indexed = [(cid, numbers_in(text), set(re.findall(r"[a-z]+", normalize(text)))) for cid, text in claims]
    chosen: set[str] = set()
    while need_numbers or need_names:
        gain, pick = 0, None
        for cid, numbers, words in indexed:
            if cid in chosen:
                continue
            covered = len(need_numbers & numbers) + len(need_names & words)
            if covered > gain:
                gain, pick = covered, (cid, numbers, words)
        if pick is None:
            return None
        chosen.add(pick[0])
        need_numbers -= pick[1]
        need_names -= pick[2]
    return [cid for cid, _, _ in indexed if cid in chosen]
