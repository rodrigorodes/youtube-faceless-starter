"""Busca de mídia no Pixabay (adapter da porta ``MediaSearch``).

Traduz respostas da API de imagens e vídeos do Pixabay para ``MediaCandidate``.
Licença e proveniência são obrigatórias; itens sem página de origem ou URL segura são recusados.
Higienização de segurança: credenciais nunca são expostas em erros ou logs.
"""
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from ..application.config import ProviderNotFound
from ..application.ports import ImageResult, MediaCandidate, ModelUnavailable
from ..domain.contracts import UsageEntry
from .image_stock import MAX_BYTES

DEFAULT_LICENSE = "Pixabay Content License"
IMAGE_SEARCH_URL = "https://pixabay.com/api/"
VIDEO_SEARCH_URL = "https://pixabay.com/api/videos/"
MEDIA_TYPES = frozenset({"image", "video"})
ORIENTATION_MAP = {
    "landscape": "horizontal",
    "portrait": "vertical",
}
MAX_QUERY = 100


def _is_https_url(url: object) -> bool:
    """Valida se a URL é https válida e estruturada."""
    if not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean.startswith("https://"):
        return False
    if any(c in clean for c in " \t\r\n\\"):
        return False
    try:
        parts = urlsplit(clean)
        return parts.scheme == "https" and bool(parts.netloc)
    except Exception:
        return False


def _candidate_from_image_hit(hit: object, license_text: str) -> MediaCandidate | None:
    """Converte um hit de imagem do Pixabay em MediaCandidate; None se inválido."""
    if not isinstance(hit, dict):
        return None
    url = hit.get("largeImageURL") or hit.get("webformatURL")
    source_url = hit.get("pageURL")
    if not (_is_https_url(url) and _is_https_url(source_url)):
        return None

    raw_tags = hit.get("tags")
    tags = tuple(t.strip() for t in str(raw_tags or "").split(",") if t.strip())

    user = str(hit.get("user") or "").strip()[:120]
    attribution = f"Foto de {user} no Pixabay" if user else "Foto do Pixabay"

    w = hit.get("imageWidth")
    h = hit.get("imageHeight")
    width = w if isinstance(w, int) and not isinstance(w, bool) and w > 0 else None
    height = h if isinstance(h, int) and not isinstance(h, bool) and h > 0 else None

    media_id = str(hit.get("id") or "")[:64]

    try:
        return MediaCandidate(
            license=license_text,
            source_url=str(source_url)[:300],
            url=str(url),
            attribution=attribution,
            author=user,
            media_id=media_id,
            media_type="image",
            width=width,
            height=height,
            cost_usd=Decimal("0"),
            tags=tags,
        )
    except ValueError:
        return None


def _candidate_from_video_hit(hit: object, license_text: str) -> MediaCandidate | None:
    """Converte um hit de vídeo do Pixabay em MediaCandidate; None se inválido."""
    if not isinstance(hit, dict):
        return None
    videos = hit.get("videos")
    if not isinstance(videos, dict):
        return None

    selected = videos.get("large") or videos.get("medium") or videos.get("small")
    if not isinstance(selected, dict):
        return None

    url = selected.get("url")
    source_url = hit.get("pageURL")
    if not (_is_https_url(url) and _is_https_url(source_url)):
        return None

    w = selected.get("width")
    h = selected.get("height")
    width = w if isinstance(w, int) and not isinstance(w, bool) and w > 0 else None
    height = h if isinstance(h, int) and not isinstance(h, bool) and h > 0 else None

    raw_duration = hit.get("duration")
    duration_s = None
    if raw_duration is not None and not isinstance(raw_duration, bool):
        try:
            val = float(raw_duration)
            if val > 0:
                duration_s = val
        except (ValueError, TypeError):
            duration_s = None

    raw_tags = hit.get("tags")
    tags = tuple(t.strip() for t in str(raw_tags or "").split(",") if t.strip())

    user = str(hit.get("user") or "").strip()[:120]
    attribution = f"Vídeo de {user} no Pixabay" if user else "Vídeo do Pixabay"

    media_id = str(hit.get("id") or "")[:64]

    try:
        return MediaCandidate(
            license=license_text,
            source_url=str(source_url)[:300],
            url=str(url),
            attribution=attribution,
            author=user,
            media_id=media_id,
            media_type="video",
            width=width,
            height=height,
            cost_usd=Decimal("0"),
            duration_s=duration_s,
            tags=tags,
        )
    except ValueError:
        return None


class PixabayMediaSearch:
    """Implementação da porta ``MediaSearch`` sobre a API do Pixabay."""

    name = "pixabay"

    def __init__(
        self,
        api_key: str,
        *,
        license_text: str = DEFAULT_LICENSE,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ):
        if not (api_key or "").strip():
            raise ProviderNotFound("media search provider requires PIXABAY_API_KEY")
        if not (license_text or "").strip():
            raise ProviderNotFound("media search provider requires a known license")
        self._key = api_key.strip()
        self._license = license_text.strip()
        self._transport = transport
        self._timeout = timeout

    def search(
        self,
        query: str,
        *,
        media_type: str = "image",
        orientation: str = "landscape",
        per_page: int = 10,
    ) -> list[MediaCandidate]:
        if media_type not in MEDIA_TYPES:
            raise ModelUnavailable("Pixabay media search supports 'image' and 'video' only")
        if orientation not in ORIENTATION_MAP:
            raise ModelUnavailable(
                f"Pixabay media search orientation must be 'landscape' or 'portrait', got '{orientation}'"
            )
        if not isinstance(per_page, int) or isinstance(per_page, bool) or not (1 <= per_page <= 80):
            raise ModelUnavailable("per_page must be an integer between 1 and 80")

        text = (query or "").strip()[:MAX_QUERY]
        if not text:
            return []

        pixabay_orientation = ORIENTATION_MAP[orientation]

        safe_per_page = max(3, min(per_page, 80))
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout, trust_env=False) as client:
                if media_type == "video":
                    params = {
                        "key": self._key,
                        "q": text,
                        "video_type": "all",
                        "orientation": pixabay_orientation,
                        "per_page": safe_per_page,
                        "safesearch": "true",
                    }
                    response = client.get(VIDEO_SEARCH_URL, params=params)
                    response.raise_for_status()
                    hits = response.json().get("hits") or []
                    return [
                        candidate
                        for candidate in (_candidate_from_video_hit(hit, self._license) for hit in hits)
                        if candidate is not None
                    ]
                else:
                    params = {
                        "key": self._key,
                        "q": text,
                        "image_type": "photo",
                        "orientation": pixabay_orientation,
                        "per_page": safe_per_page,
                        "safesearch": "true",
                    }
                    response = client.get(IMAGE_SEARCH_URL, params=params)
                    response.raise_for_status()
                    hits = response.json().get("hits") or []
                    return [
                        candidate
                        for candidate in (_candidate_from_image_hit(hit, self._license) for hit in hits)
                        if candidate is not None
                    ]
        except ModelUnavailable:
            raise
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError, AttributeError) as exc:
            status = f" (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else ""
            msg = f"Pixabay media search failed: {type(exc).__name__}{status}"
            if self._key:
                msg = msg.replace(self._key, "[REDACTED]")
            raise ModelUnavailable(msg) from None


def trusted_pixabay_url(url: object) -> bool:
    """Valida se a URL é https em host confiável do Pixabay."""
    if not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean.startswith("https://") or any(c in clean for c in " \t\r\n\\"):
        return False
    try:
        parts = urlsplit(clean)
        if parts.scheme != "https" or not parts.netloc:
            return False
        host = parts.netloc.split(":")[0].lower()
        trusted_hosts = {"pixabay.com", "cdn.pixabay.com"}
        return host in trusted_hosts or host.endswith(".pixabay.com")
    except Exception:
        return False


class PixabayMediaFetcher:
    """Materializa um candidato do Pixabay em bytes (adapter da porta ``MediaFetcher``).

    Só baixa de host confiável do Pixabay (*.pixabay.com) e devolve ``ImageResult``
    com a licença/atribuição/proveniência do candidato.
    """

    name = "pixabay"

    def __init__(self, model: str = "", *, transport: httpx.BaseTransport | None = None, timeout: float = 20.0):
        self.model, self._transport, self._timeout = model, transport, timeout

    def fetch(self, candidate: MediaCandidate) -> ImageResult:
        if not trusted_pixabay_url(candidate.url):
            raise ModelUnavailable("candidate media url is not on a trusted Pixabay host")
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
            raise ModelUnavailable(f"Pixabay media fetch failed: {type(exc).__name__}{status}") from None
