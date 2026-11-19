"""Título, descrição e tags (domínio puro). A descrição sempre termina com o aviso de conteúdo sintético."""
import re
from dataclasses import dataclass

DISCLOSURE_TEXT = ("Imagens ilustrativas geradas por IA (não são fotos nem vídeos do evento). "
                   "Narração sintetizada por IA e trilha original gerada por software.")
MAX_TITLE, MAX_DESCRIPTION, MAX_TAGS = 100, 4900, 8


@dataclass(frozen=True)
class Metadata:
    title: str
    description: str
    tags: list[str]


def build_metadata(topic: str, narrations: list[str], source_urls: list[str], title_hint: str = "") -> Metadata:
    title = (title_hint or topic).strip()[:MAX_TITLE]
    tail = ("Fontes:\n" + "\n".join(source_urls) + "\n\n" if source_urls else "") + DISCLOSURE_TEXT
    room = max(0, MAX_DESCRIPTION - len(tail) - 2)
    summary = " ".join(narrations)[: min(600, room)].strip()
    description = f"{summary}\n\n{tail}" if summary else tail
    tags: list[str] = []
    for word in re.findall(r"[^\W\d_]{4,}", topic):
        if word.lower() not in (t.lower() for t in tags):
            tags.append(word[:30])
    return Metadata(title=title, description=description[:MAX_DESCRIPTION] if len(tail) <= MAX_DESCRIPTION else tail[-MAX_DESCRIPTION:], tags=tags[:MAX_TAGS])
