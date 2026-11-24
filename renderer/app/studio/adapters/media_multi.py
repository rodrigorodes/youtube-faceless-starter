"""Agregador multi-provedor de busca de mídia (adapter da porta ``MediaSearch``).

Permite consultar simultaneamente múltiplos provedores de mídia stock (ex: Pexels, Pixabay),
isolando falhas individuais de forma resiliente e agregando candidatos.
"""
from collections.abc import Sequence

from ..application.ports import ImageResult, MediaCandidate, MediaFetcher, MediaSearch, ModelUnavailable


class MultiProviderMediaSearch:
    """Implementação da porta ``MediaSearch`` que agrega múltiplos provedores."""

    name = "multi"

    def __init__(self, providers: Sequence[MediaSearch] | None = None) -> None:
        self.providers = list(providers) if providers is not None else []

    def search(
        self,
        query: str,
        *,
        media_type: str = "image",
        orientation: str = "landscape",
        per_page: int = 10,
    ) -> list[MediaCandidate]:
        text = (query or "").strip()
        if not text:
            return []

        aggregated: list[MediaCandidate] = []
        for provider in self.providers:
            try:
                found = provider.search(
                    text,
                    media_type=media_type,
                    orientation=orientation,
                    per_page=per_page,
                )
                if found:
                    aggregated.extend(found)
            except Exception:
                # Falha em um provedor não derruba a busca; prossegue com os demais
                continue

        return aggregated


class MultiProviderMediaFetcher:
    """Implementação da porta ``MediaFetcher`` que despacha para o fetcher correto.

    Inspeciona a URL, source_url e licença do candidato para encaminhar o download
    ao fetcher de domínio correspondente (ex: Pexels, Pixabay).
    """

    name = "multi"

    def __init__(self, fetchers: Sequence[MediaFetcher] | None = None) -> None:
        self.fetchers = list(fetchers) if fetchers is not None else []
        self._by_name = {f.name: f for f in self.fetchers}

    def fetch(self, candidate: MediaCandidate) -> ImageResult:
        url = (candidate.url or "").lower()
        source_url = (candidate.source_url or "").lower()
        license_text = (candidate.license or "").lower()

        target: MediaFetcher | None = None
        if "pixabay.com" in url or "pixabay.com" in source_url or "pixabay" in license_text:
            target = self._by_name.get("pixabay")
        elif "pexels.com" in url or "pexels.com" in source_url or "pexels" in license_text:
            target = self._by_name.get("pexels")

        if target is not None:
            return target.fetch(candidate)

        for fetcher in self.fetchers:
            try:
                return fetcher.fetch(candidate)
            except ModelUnavailable:
                continue

        raise ModelUnavailable("no suitable media fetcher found for candidate")
