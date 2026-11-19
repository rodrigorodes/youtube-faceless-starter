"""ImageModel de banco de imagens (Pexels): licença e atribuição gravadas. São fotos reais e genéricas, buscadas pelo
tema do prompt; não use para ilustrar um evento específico."""
from urllib.parse import urlsplit

import httpx

from ..application.config import ProviderNotFound
from ..application.ports import ImageResult, ModelUnavailable
from ..domain.contracts import UsageEntry
from ..domain.media import strip_style

SEARCH_URL = "https://api.pexels.com/v1/search"
MAX_BYTES = 20 * 1024 * 1024


def _trusted_image_url(url: object) -> bool:
    try:
        if not isinstance(url, str) or url != url.strip() or any(c in url for c in " \t\r\n\\"):
            return False
        parts = urlsplit(url)
        host = (parts.hostname or "") if parts else ""
        return bool(parts) and parts.scheme == "https" and (host == "pexels.com" or host.endswith(".pexels.com"))
    except ValueError:
        return False


class PexelsImage:
    name = "stock"

    def __init__(self, model: str, api_key: str, transport: httpx.BaseTransport | None = None, timeout: float = 20.0):
        if not (api_key or "").strip():
            raise ProviderNotFound("stock image provider requires PEXELS_API_KEY")
        self.model, self._key, self._transport, self._timeout = model, api_key.strip(), transport, timeout

    def cost_estimate(self, prompt: str) -> float:
        return 0.0

    def generate(self, prompt: str, *, aspect: str = "9:16") -> ImageResult:
        orientation, variant = ("portrait", "portrait") if aspect == "9:16" else ("landscape", "landscape")
        query = strip_style(prompt).strip()[:100]
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout, trust_env=False) as client:
                found = client.get(SEARCH_URL, headers={"Authorization": self._key},
                                   params={"query": query, "orientation": orientation, "per_page": 1})
                found.raise_for_status()
                photos = found.json().get("photos") or []
                if not photos:
                    raise ModelUnavailable("no stock result for this prompt")
                photo = photos[0]
                url = photo["src"][variant]
                if not _trusted_image_url(url):
                    raise ModelUnavailable("stock image url is not on a trusted host")
                buffer = bytearray()
                with client.stream("GET", url) as image:
                    image.raise_for_status()
                    mime = image.headers.get("content-type", "").split(";")[0].strip().lower()
                    for chunk in image.iter_bytes():
                        buffer += chunk
                        if len(buffer) > MAX_BYTES:
                            raise ModelUnavailable("stock image is larger than 20 MB")
            who, profile = str(photo.get("photographer") or "").strip()[:120], str(photo.get("photographer_url") or "").strip()[:200]
            return ImageResult(data=bytes(buffer), mime=mime, license="Pexels License",
                               attribution=(f"Foto de {who} no Pexels" if who else "Foto do Pexels") + (f" ({profile})" if profile else ""),
                               source_url=str(photo.get("url") or "")[:300] if str(photo.get("url") or "").startswith("https://") else "",
                               usage=UsageEntry(step="image", provider=self.name, model=self.model, cost_usd=0.0))
        except ModelUnavailable:
            raise
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError, AttributeError) as exc:
            status = f" (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else ""
            raise ModelUnavailable(f"Pexels request failed: {type(exc).__name__}{status}") from None
