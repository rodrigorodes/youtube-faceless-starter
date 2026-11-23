"""Pesquisa de referência na Wikipédia (MediaWiki Action API), sem chave e sem raspagem de HTML.

O host é montado a partir de um código de idioma validado (`<lang>.wikipedia.org`, só https, sem redirect),
então não há URL controlada pelo usuário e o risco de SSRF não existe. O texto devolvido é o texto simples do
artigo (CC BY-SA): a URL do artigo é a proveniência registrada em "Fontes". A relevância não é garantida
(a busca é aproximada; `is_relevant` descarta o artigo que não cita o tema) — o humano revisa o roteiro na aprovação, e o fact-check exige que cada cena
cite afirmações do texto lido.
"""
import re
import time
import unicodedata
from collections.abc import Callable
from urllib.parse import quote

import httpx

from ..application.editorial import SourceUnavailable
from ..application.ports import ResearchDocument

USER_AGENT = "faceless-studio/0.3 (+research; personal use)"
FALLBACK_LANGUAGE = "en"
MIN_WORDS = 200          # descarta esboços e páginas de desambiguação
MAX_CHARS = 12_000       # o suficiente para dezenas de afirmações; o resto do artigo não ajuda um Short
_LANG = re.compile(r"^[a-z]{2,3}$")
_TAIL = re.compile(r"^\s*(See also|References|External links|Further reading|Notes|Ver também|Referências|"
                   r"Ligações externas|Notas|Bibliografia|Véase también|Referencias|Enlaces externos)\s*$",
                   re.IGNORECASE | re.MULTILINE)
_DISTINCTIVE = re.compile(r"\b(?:[A-Z]{2,}[A-Za-z0-9]*|[A-Za-z]*\d[A-Za-z0-9]*)\b")
_PUNCT = re.compile(r"[^\w\s'-]", re.UNICODE)


_STOPWORDS = frozenset({"and", "the", "for", "with", "how", "why", "what", "que", "para", "com", "uma", "dos", "das",
                        "como", "por", "sobre", "the", "you", "your", "from", "this", "that", "vs"})


def _fold(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c))


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"\w+", _fold(value)))


def is_relevant(topic: str, title: str, text: str) -> bool:
    """A busca da Wikipédia é aproximada (um erro de digitação devolve outro assunto): só vale o artigo cujo título
    cita uma palavra do tema, ou cujo texto cita uma sigla/número do tema (ex.: "GTA 6" → "Grand Theft Auto VI")."""
    significant = {t for t in _tokens(topic) if len(t) >= 3 and t not in _STOPWORDS}
    if significant & _tokens(title):
        return True
    distinctive = {_fold(t) for t in _DISTINCTIVE.findall(topic)}
    return bool(distinctive & _tokens(text))


def wiki_language(language: str | None) -> str:
    code = (language or "").split("-")[0].split("_")[0].strip().lower()
    return code if _LANG.fullmatch(code) else FALLBACK_LANGUAGE


def search_queries(topic: str) -> list[str]:
    """Consultas por ordem de precisão: siglas/números do tema (ex.: "GTA 6"), depois o tema limpo."""
    topic = " ".join(topic.split())
    queries: list[str] = []
    distinctive = _DISTINCTIVE.findall(topic)
    if distinctive:
        queries.append(" ".join(dict.fromkeys(distinctive)))
    cleaned = " ".join(_PUNCT.sub(" ", topic).split())[:120]
    if cleaned and cleaned not in queries:
        queries.append(cleaned)
    return queries


def article_text(extract: str) -> str:
    cut = _TAIL.search(extract)
    return (extract[:cut.start()] if cut else extract).strip()[:MAX_CHARS]


class WikipediaResearch:
    name = "wikipedia"

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 10.0, hits: int = 3,
                 sleep: Callable[[float], None] = time.sleep):
        self.transport, self.timeout, self.hits, self.sleep = transport, timeout, hits, sleep

    def _get(self, client: httpx.Client, lang: str, params: dict) -> dict:
        """Uma nova tentativa só para falha transitória (rede, 429, 5xx); 4xx definitivo não é repetido."""
        reason = "unknown"
        for attempt in range(2):
            if attempt:
                self.sleep(1.0)
            try:
                response = client.get(f"https://{lang}.wikipedia.org/w/api.php",
                                      params={"action": "query", "format": "json", "formatversion": "2", **params})
            except httpx.HTTPError as exc:
                reason = type(exc).__name__
                continue
            if response.status_code == 429 or response.status_code >= 500:
                reason = f"HTTP {response.status_code}"
                continue
            if response.status_code >= 400:
                raise SourceUnavailable(f"research source (wikipedia) refused the request (HTTP {response.status_code})")
            try:
                return response.json()
            except ValueError as exc:
                raise SourceUnavailable("research source (wikipedia) returned an unreadable response") from exc
        raise SourceUnavailable(f"research source (wikipedia) is unavailable right now ({reason})")

    def _titles(self, client: httpx.Client, lang: str, topic: str) -> list[str]:
        for query in search_queries(topic):
            data = self._get(client, lang, {"list": "search", "srsearch": query, "srnamespace": "0",
                                            "srlimit": str(self.hits)})
            hits = [h for h in (data.get("query", {}).get("search") or []) if h.get("wordcount", 0) >= MIN_WORDS]
            if hits:
                return [h["title"] for h in hits]
        return []

    def _document(self, client: httpx.Client, lang: str, title: str) -> ResearchDocument | None:
        data = self._get(client, lang, {"prop": "extracts", "explaintext": "1", "exsectionformat": "plain",
                                        "redirects": "1", "titles": title})
        pages = data.get("query", {}).get("pages") or []
        if not pages or pages[0].get("missing") or not pages[0].get("extract"):
            return None
        page = pages[0]
        url = f"https://{lang}.wikipedia.org/wiki/{quote(page['title'].replace(' ', '_'), safe='')}"
        return ResearchDocument(url=url, title=page["title"], text=article_text(page["extract"]))

    def search(self, topic: str, language: str) -> list[ResearchDocument]:
        lang = wiki_language(language)
        languages = [lang] if lang == FALLBACK_LANGUAGE else [lang, FALLBACK_LANGUAGE]
        with httpx.Client(transport=self.transport, timeout=self.timeout, follow_redirects=False,
                          headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as client:
            for code in languages:
                docs = [d for t in self._titles(client, code, topic)
                        if (d := self._document(client, code, t)) and is_relevant(topic, d.title, d.text)]
                if docs:
                    return docs
        return []
