"""Busca de mídia no Pexels (adapter da porta ``MediaSearch``).

Único lugar que conhece o fornecedor: traduz a resposta do Pexels para ``MediaCandidate``.
Licença e proveniência são obrigatórias; foto sem página de origem ou URL confiável é
recusada, nunca "completada" com licença inventada. O núcleo não importa este módulo.

A API de fotos do Pexels **não** devolve um campo de licença por foto: a licença é a do
provedor (``Pexels License``), documentada nos termos. O adapter usa essa licença conhecida e
recusa tudo quando ela não é informada — não fabrica licença para um provedor desconhecido.
"""
from decimal import Decimal

import httpx

from ..application.config import ProviderNotFound
from ..application.ports import ImageResult, MediaCandidate, ModelUnavailable
from ..domain.contracts import UsageEntry
from .image_stock import MAX_BYTES, SEARCH_URL, trusted_image_url

MAX_QUERY = 100
ORIENTATIONS = frozenset({"landscape", "portrait", "square"})
# Licença documentada do provedor; sobrescrevível para outro provedor que a exponha.
LICENSE = "Pexels License"


def _candidate_from_photo(photo: object, orientation: str, license_text: str) -> MediaCandidate | None:
    """Converte uma foto do Pexels em candidato; ``None`` sem licença/proveniência."""
    if not isinstance(photo, dict):
        return None
    license_text = (license_text or "").strip()
    if not license_text:
        return None
    source_url = str(photo.get("url") or "").strip()
    if not source_url.startswith("https://"):
        return None
    src = photo.get("src")
    if not isinstance(src, dict):
        return None
    variant = "portrait" if orientation == "portrait" else "landscape"
    media_url = str(src.get(variant) or src.get("large") or src.get("original") or "").strip()
    if not trusted_image_url(media_url):
        return None
    who = str(photo.get("photographer") or "").strip()[:120]
    attribution = (f"Foto de {who} no Pexels" if who else "Foto do Pexels")
    width = photo.get("width")
    height = photo.get("height")
    width = width if isinstance(width, int) and not isinstance(width, bool) and width > 0 else None
    height = height if isinstance(height, int) and not isinstance(height, bool) and height > 0 else None
    try:
        return MediaCandidate(
            license=license_text.strip(),
            source_url=source_url[:300],
            url=media_url,
            attribution=attribution,
            author=who,
            media_id=str(photo.get("id") or "")[:64],
            media_type="image",
            width=width,
            height=height,
            cost_usd=Decimal("0"),
        )
    except ValueError:
        return None


class PexelsMediaSearch:
    """Implementação da porta ``MediaSearch`` sobre a API de busca do Pexels."""

    name = "pexels"

    def __init__(self, model: str, api_key: str, *, license_text: str = LICENSE,
                 transport: httpx.BaseTransport | None = None, timeout: float = 20.0):
        if not (api_key or "").strip():
            raise ProviderNotFound("media search provider requires PEXELS_API_KEY")
        if not (license_text or "").strip():
            raise ProviderNotFound("media search provider requires a known license")
        self.model, self._key, self._license = model, api_key.strip(), license_text.strip()
        self._transport, self._timeout = transport, timeout

    def search(self, query: str, *, media_type: str = "image", orientation: str = "landscape",
               per_page: int = 10) -> list[MediaCandidate]:
        if media_type != "image":
            raise ModelUnavailable("Pexels media search supports images only")
        if orientation not in ORIENTATIONS:
            raise ModelUnavailable("invalid media search orientation")
        if not isinstance(per_page, int) or isinstance(per_page, bool) or not (1 <= per_page <= 80):
            raise ModelUnavailable("per_page must be an integer between 1 and 80")
        text = (query or "").strip()[:MAX_QUERY]
        if not text:
            return []
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout, trust_env=False) as client:
                found = client.get(SEARCH_URL, headers={"Authorization": self._key},
                                   params={"query": text, "orientation": orientation, "per_page": per_page})
                found.raise_for_status()
                photos = found.json().get("photos") or []
                return [candidate for candidate in (_candidate_from_photo(photo, orientation, self._license)
                                                   for photo in photos)
                        if candidate is not None]
        except ModelUnavailable:
            raise
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError, AttributeError) as exc:
            status = f" (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else ""
            raise ModelUnavailable(f"Pexels media search failed: {type(exc).__name__}{status}") from None


class PexelsMediaFetcher:
    """Materializa um candidato do Pexels em bytes (adapter da porta ``MediaFetcher``, W4.4).

    Só baixa de host confiável do provedor e devolve ``ImageResult`` com a licença/atribuição/
    proveniência **do candidato** — o núcleo recusa um resultado sem licença, nunca a inventa.
    """

    name = "pexels"

    def __init__(self, model: str = "", *, transport: httpx.BaseTransport | None = None, timeout: float = 20.0):
        self.model, self._transport, self._timeout = model, transport, timeout

    def fetch(self, candidate: MediaCandidate) -> ImageResult:
        if not trusted_image_url(candidate.url):
            raise ModelUnavailable("candidate media url is not on a trusted host")
        try:
            buffer = bytearray()
            with httpx.Client(transport=self._transport, timeout=self._timeout, trust_env=False) as client:
                with client.stream("GET", candidate.url) as image:
                    image.raise_for_status()
                    mime = image.headers.get("content-type", "").split(";")[0].strip().lower()
                    for chunk in image.iter_bytes():
                        buffer += chunk
                        if len(buffer) > MAX_BYTES:
                            raise ModelUnavailable("candidate media is larger than 20 MB")
            return ImageResult(
                data=bytes(buffer),
                mime=mime,
                license=candidate.license,
                attribution=candidate.attribution,
                source_url=candidate.source_url,
                usage=UsageEntry(step="image", provider=self.name, model=self.model or candidate.media_id,
                                 cost_usd=float(candidate.cost_usd or 0)),
            )
        except ModelUnavailable:
            raise
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError, AttributeError) as exc:
            status = f" (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else ""
            raise ModelUnavailable(f"Pexels media fetch failed: {type(exc).__name__}{status}") from None
