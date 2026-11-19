"""Extração determinística de claims (frases verificáveis) de um snapshot de fonte."""
import hashlib
import re

from .contracts import Claim
from .facts import numbers_in, proper_nouns_in

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_MIN, _MAX = 40, 400


def extract_claims(snapshot_id: str, text: str, limit: int = 40) -> list[Claim]:
    claims: list[Claim] = []
    seen: set[str] = set()
    for raw in _SENTENCE.split(text):
        sentence = " ".join(raw.split())
        if not _MIN <= len(sentence) <= _MAX or not (any(c.isdigit() for c in sentence) or proper_nouns_in(sentence)):
            continue
        claim_id = hashlib.sha1(sentence.encode("utf-8")).hexdigest()[:10]
        if claim_id in seen:
            continue
        seen.add(claim_id)
        claims.append(Claim(id=claim_id, snapshot_id=snapshot_id, text=sentence))
        if len(claims) >= limit:
            break
    return claims
