"""Agregador multi-provedor de busca de mídia (adapter da porta ``MediaSearch``).

Permite consultar simultaneamente múltiplos provedores de mídia stock (ex: Pexels, Pixabay),
isolando falhas individuais de forma resiliente e agregando candidatos.
"""
from collections.abc import Sequence

from ..application.ports import MediaCandidate, MediaSearch


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
