"""TextModel via bridge local do OpenCode (login OAuth do usuário; sem cobrança por chamada).

O bridge escolhe o modelo configurado nele (OPENCODE_MODEL); `model` aqui só identifica a chamada no ledger.
O bridge não suporta saída estruturada, então `json_schema` é ignorado e a resposta é validada pelo caso de uso.
"""
import httpx

from ..application.config import ProviderNotFound
from ..application.ports import ModelUnavailable, TextResult
from ..domain.contracts import UsageEntry


class OpenCodeText:
    name = "opencode"

    def __init__(self, model: str, token: str, base_url: str = "http://host.docker.internal:8787",
                 transport: httpx.BaseTransport | None = None, timeout: float = 100.0):
        if not (token or "").strip():
            raise ProviderNotFound("opencode text provider requires OPENCODE_BRIDGE_TOKEN")
        self.model, self._token, self._base = model, token.strip(), base_url.rstrip("/")
        self._transport, self._timeout = transport, timeout

    def cost_estimate(self, prompt: str) -> float:
        return 0.0  # assinatura OAuth do usuário: sem custo marginal por chamada

    def complete(self, prompt: str, *, json_schema: dict | None = None) -> TextResult:
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout, trust_env=False) as client:
                response = client.post(f"{self._base}/generate", headers={"Authorization": f"Bearer {self._token}"}, json={"prompt": prompt})
                response.raise_for_status()
                text = response.json()["text"]
            if not isinstance(text, str):
                raise TypeError("text is not a string")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            status = f" (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else ""
            raise ModelUnavailable(f"OpenCode bridge failed: {type(exc).__name__}{status}; is scripts/opencode-bridge.py running?") from None
        return TextResult(text=text, usage=UsageEntry(step="text", provider=self.name, model=self.model, cost_usd=0.0))
