"""ImageModel via bridge local do OpenCode. O bridge escolhe o modelo (OPENCODE_IMAGE_MODEL) e gera sempre 9:16;
`model` identifica a chamada no ledger e define a estimativa de custo (só ':free' custa 0)."""
import base64

import httpx

from ..application.config import ProviderNotFound
from ..application.ports import ImageResult, ModelUnavailable
from ..domain.contracts import UsageEntry


class OpenCodeImage:
    name = "opencode"

    def __init__(self, model: str, token: str, base_url: str = "http://host.docker.internal:8787",
                 transport: httpx.BaseTransport | None = None, timeout: float = 120.0, paid_estimate_usd: float = 0.05):
        if not (token or "").strip():
            raise ProviderNotFound("opencode image provider requires OPENCODE_BRIDGE_TOKEN")
        self.model, self._token, self._base = model, token.strip(), base_url.rstrip("/")
        self._transport, self._timeout, self._paid = transport, timeout, paid_estimate_usd
        self._verified = False

    def cost_estimate(self, prompt: str) -> float:
        return 0.0 if self.model.split("#", 1)[0].endswith(":free") else self._paid

    def _check_bridge(self, client: httpx.Client) -> None:
        """O bridge escolhe o modelo real (OPENCODE_IMAGE_MODEL). Custo, licença e cache usam o rótulo daqui,
        então só gera se o bridge declarar exatamente o mesmo modelo."""
        if self._verified:
            return
        try:
            declared = client.get(f"{self._base}/health").json().get("image_model")
        except (httpx.HTTPError, ValueError, AttributeError):
            declared = None
        if declared != self.model:
            raise ModelUnavailable(f"bridge image model ({declared or 'not declared'}) differs from the configured {self.model}; "
                                   "update scripts/opencode-bridge.py and OPENCODE_IMAGE_MODEL")
        self._verified = True

    def generate(self, prompt: str, *, aspect: str = "9:16") -> ImageResult:
        free = self.cost_estimate(prompt) == 0.0
        last: Exception | None = None
        for _ in range(2 if free else 1):
            # Retry só para modelo gratuito: um timeout de leitura pode ter gerado (e cobrado) no bridge.
            try:
                with httpx.Client(transport=self._transport, timeout=self._timeout, trust_env=False) as client:
                    self._check_bridge(client)
                    response = client.post(f"{self._base}/image", headers={"Authorization": f"Bearer {self._token}"}, json={"prompt": prompt})
                    response.raise_for_status()
                    payload = response.json()
                    raw = base64.b64decode(payload["data"], validate=True)
                    mime = payload.get("mime", "image/png")
                return ImageResult(data=raw, mime=mime if isinstance(mime, str) else "", license=f"ai-generated:{self.model}",
                                   usage=UsageEntry(step="image", provider=self.name, model=self.model, cost_usd=self.cost_estimate(prompt)))
            except ModelUnavailable:
                raise
            except httpx.HTTPStatusError as exc:
                last = exc
                if exc.response.status_code < 500:
                    break
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last = exc  # nada foi enviado: seguro repetir
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                last = exc
                break
        status = f" (HTTP {last.response.status_code})" if isinstance(last, httpx.HTTPStatusError) else ""
        raise ModelUnavailable(f"OpenCode image failed: {type(last).__name__}{status}; is scripts/opencode-bridge.py running?") from None
