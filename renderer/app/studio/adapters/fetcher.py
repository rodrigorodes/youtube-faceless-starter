"""Busca de fontes por HTTP com defesa contra SSRF.

Cada salto (URL inicial e cada redirect) é revalidado: só http(s), host na allowlist, sem credenciais na URL e
todos os endereços resolvidos precisam ser públicos. Limite conhecido: o httpx resolve o nome de novo ao conectar
(janela de DNS rebinding); a allowlist restrita a domínios do próprio evento é a defesa principal.
"""
import codecs
import ipaddress
import socket
from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from ..application.editorial import SourceRefused, SourceUnavailable, host_allowed
from ..application.ports import FetchedPage

_TEXT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}
_CHARSETS = {"utf-8", "ascii", "iso8859-1", "iso8859-15", "cp1252", "utf-16", "utf-16-le", "utf-16-be"}
_REDIRECTS = {301, 302, 303, 307, 308}
_SKIP = {"script", "style", "noscript", "template"}
_BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header", "footer", "title",
          "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"}
USER_AGENT = "faceless-studio/0.3 (+source snapshot; personal use)"


class _HtmlText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _clean(text: str) -> str:
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    parser = _HtmlText()
    parser.feed(html)
    parser.close()
    return _clean("".join(parser.parts))


class HttpxFetcher:
    def __init__(self, allowlist: tuple[str, ...], max_bytes: int = 2_000_000,
                 resolver: Callable = socket.getaddrinfo, transport: httpx.BaseTransport | None = None,
                 timeout: float = 15.0, max_redirects: int = 3):
        self.allowlist, self.max_bytes, self.resolver = tuple(allowlist), max_bytes, resolver
        self.transport, self.timeout, self.max_redirects = transport, timeout, max_redirects

    def _check(self, url: str) -> None:
        if not host_allowed(url, self.allowlist):
            raise SourceRefused("url host is not in the allowlist")
        parts = urlsplit(url)
        try:
            answers = self.resolver(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
        except OSError as exc:
            raise SourceUnavailable("could not resolve the source host") from exc
        if not answers:
            raise SourceUnavailable("could not resolve the source host")
        for answer in answers:
            address = ipaddress.ip_address(str(answer[4][0]).split("%")[0])
            address = getattr(address, "ipv4_mapped", None) or address
            if not address.is_global:
                raise SourceRefused("source host resolves to a private address")

    def fetch(self, url: str) -> FetchedPage:
        current = url
        with httpx.Client(transport=self.transport, timeout=self.timeout, follow_redirects=False,
                          headers={"User-Agent": USER_AGENT}, trust_env=False) as client:  # proxy do ambiente anularia a checagem de IP
            for _ in range(self.max_redirects + 1):
                self._check(current)
                try:
                    with client.stream("GET", current) as response:
                        if response.status_code in _REDIRECTS:
                            location = response.headers.get("location")
                            if not location:
                                raise SourceUnavailable("redirect without location")
                            target = urljoin(current, location)
                            if urlsplit(current).scheme == "https" and urlsplit(target).scheme != "https":
                                raise SourceRefused("redirect would downgrade https to http")
                            current = target
                            continue
                        if response.status_code != 200:
                            raise SourceUnavailable(f"source returned HTTP {response.status_code}")
                        ctype = response.headers.get("content-type", "").split(";")[0].strip().lower()
                        if ctype not in _TEXT_TYPES:
                            raise SourceRefused(f"unsupported content type {ctype or 'missing'!r}")
                        buffer = bytearray()
                        for chunk in response.iter_bytes():
                            buffer += chunk
                            if len(buffer) >= self.max_bytes:
                                break  # corta por tamanho: página enorme não estoura memória
                        charset = response.charset_encoding or "utf-8"
                except httpx.HTTPError as exc:
                    raise SourceUnavailable(f"could not fetch the source ({type(exc).__name__})") from exc
                try:
                    if codecs.lookup(charset).name not in _CHARSETS:  # idna, punycode, rot13… não são páginas de texto
                        raise LookupError(charset)
                    raw = bytes(buffer[: self.max_bytes]).decode(charset, errors="replace")
                except (LookupError, UnicodeError):
                    raw = bytes(buffer[: self.max_bytes]).decode("utf-8", errors="replace")
                text = html_to_text(raw) if ctype != "text/plain" else _clean(raw)
                if not text:
                    raise SourceRefused("source page has no readable text (empty)")
                return FetchedPage(text=text, final_url=current)
        raise SourceRefused("too many redirects")
