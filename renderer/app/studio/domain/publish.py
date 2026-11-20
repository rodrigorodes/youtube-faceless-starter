"""Regras puras de publicação: metadados do YouTube, agendamento, descrição com créditos, validação de IDs e da URI de upload."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

TITLE_MAX, DESC_MAX, DESC_REVIEW_MAX = 100, 5000, 4000  # o revisor escreve até 4000; créditos e fontes ocupam o resto
TAG_MAX, TAGS_COUNT = 30, 15
MIN_LEAD, MAX_LEAD = timedelta(minutes=15), timedelta(days=365)
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_UPLOAD_ID = re.compile(r"[A-Za-z0-9_-]{1,512}")
UPLOAD_HOST, UPLOAD_PATH = "www.googleapis.com", "/upload/youtube/v3/videos"


class InvalidPublishData(ValueError):
    pass


def default_title(topic: str) -> str:
    title = " ".join(topic.split())
    return title if len(title) <= TITLE_MAX else title[:TITLE_MAX - 1].rstrip() + "…"


def _no_angle(text: str, what: str) -> None:
    if "<" in text or ">" in text:
        raise InvalidPublishData(f"{what} must not contain < or > (YouTube refuses them)")


def validate_metadata(title: str, description: str, tags: list[str]) -> tuple[str, str, list[str]]:
    title, description = title.strip(), description.strip()
    if not title:
        raise InvalidPublishData("title must not be blank")
    if len(title) > TITLE_MAX:
        raise InvalidPublishData(f"title is longer than {TITLE_MAX} characters")
    if len(description) > DESC_REVIEW_MAX:
        raise InvalidPublishData(f"description is longer than {DESC_REVIEW_MAX} characters")
    _no_angle(title, "title")
    _no_angle(description, "description")
    clean: list[str] = []
    for tag in (t.strip() for t in tags):
        if not tag or tag.lower() in (c.lower() for c in clean):
            continue
        if len(tag) > TAG_MAX or "," in tag:
            raise InvalidPublishData(f"tag {tag[:20]!r} is longer than {TAG_MAX} characters or contains a comma")
        _no_angle(tag, "tag")
        clean.append(tag)
    if len(clean) > TAGS_COUNT:
        raise InvalidPublishData(f"more than {TAGS_COUNT} tags")
    return title, description, clean


def default_description(text: str, limit: int = 600) -> str:
    """Descrição inicial sugerida: o texto do roteiro (já checado), cortado em fronteira de palavra."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def validate_publish_at(when: datetime | None, now: datetime) -> datetime | None:
    """Agendamento: com fuso, entre 15 min e 1 ano à frente; normalizado para UTC."""
    if when is None:
        return None
    if when.tzinfo is None:
        raise InvalidPublishData("publish_at needs a time zone (e.g. 2026-12-01T18:00:00-03:00)")
    when = when.astimezone(timezone.utc)
    if not now + MIN_LEAD <= when <= now + MAX_LEAD:
        raise InvalidPublishData("publish_at must be between 15 minutes and 1 year from now")
    return when


def build_description(base: str, credits: list[str], sources: list[str], synthetic: bool) -> str:
    """Descrição final: texto do revisor + aviso de IA + créditos + fontes. Se passar do limite, corta o texto-base."""
    parts: list[str] = []
    if synthetic:
        parts.append("Imagens e ilustrações geradas com inteligência artificial; narração sintética.")
    unique_credits = list(dict.fromkeys(c.strip() for c in credits if c.strip()))
    if unique_credits:
        parts.append("Créditos das imagens:\n" + "\n".join(unique_credits))
    unique_sources = list(dict.fromkeys(s.strip() for s in sources if s.strip()))
    if unique_sources:
        parts.append("Fontes:\n" + "\n".join(unique_sources))
    tail = "\n\n".join(parts)
    base = base.strip()
    room = DESC_MAX - len(tail) - (2 if tail else 0)
    if len(base) > room:
        base = base[:max(0, room - 1)].rstrip() + "…" if room > 1 else ""
    text = "\n\n".join(p for p in (base, tail) if p)
    return text.replace("<", "").replace(">", "")[:DESC_MAX]


def srt_to_vtt(srt: str) -> str:
    """WebVTT para a tag <track> da página de prévia."""
    cues = []
    for block in srt.strip().split("\n\n") if srt.strip() else []:
        lines = block.split("\n")
        if len(lines) >= 3 and "-->" in lines[1]:
            cues.append(lines[1].replace(",", ".") + "\n" + "\n".join(lines[2:]) + "\n")
    return "\n".join(["WEBVTT\n", *cues]) if cues else "WEBVTT\n"


def valid_youtube_id(value) -> bool:
    return isinstance(value, str) and _YOUTUBE_ID.fullmatch(value) is not None


def valid_upload_uri(uri) -> bool:
    """O n8n envia o token OAuth a esta URL: só aceita a sessão resumable de vídeo do próprio YouTube."""
    if not isinstance(uri, str) or not uri or len(uri) > 2000 or uri != uri.strip() or any(c in uri for c in " \t\r\n\\"):
        return False
    try:
        parts = urlsplit(uri)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.hostname != UPLOAD_HOST or port is not None or parts.username or parts.password or parts.path != UPLOAD_PATH:
        return False
    ids = parse_qs(parts.query).get("upload_id", [])
    return len(ids) == 1 and _UPLOAD_ID.fullmatch(ids[0]) is not None


def youtube_insert_body(title: str, description: str, tags: list[str], publish_at: datetime | None) -> dict:
    """Corpo do `videos.insert`. Sempre `private` (com `publishAt` o YouTube publica sozinho); declara conteúdo sintético e não-infantil."""
    snippet = {"title": title, "description": description, "categoryId": "24", "defaultLanguage": "pt-BR", "defaultAudioLanguage": "pt-BR"}
    if tags:
        snippet["tags"] = tags
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if publish_at is not None:
        status["publishAt"] = publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {"snippet": snippet, "status": status}
