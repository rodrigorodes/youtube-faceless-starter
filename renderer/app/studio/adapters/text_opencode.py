"""TextModel via bridge local do OpenCode (login OAuth do usuário; sem cobrança por chamada).

O bridge escolhe o modelo configurado nele (OPENCODE_MODEL). O `model` do spec identifica a chamada
no ledger, então o adaptador confere no `/health` do bridge que o modelo declarado é exatamente esse:
config que aponta para um modelo e roda outro não passa em silêncio — a mesma regra do `OpenCodeImage`
(divergência declarada ⇒ `PreEffectFailure`, antes de qualquer geração).
O bridge não suporta saída estruturada, então `json_schema` é ignorado e a resposta é validada pelo caso de uso.
"""
import logging

import httpx

from ..application.budget import PreEffectFailure
from ..application.config import ProviderNotFound
from ..application.ports import ModelUnavailable, TextResult
from ..domain.contracts import UsageEntry


class OpenCodeText:
    name = "opencode"

    def __init__(self, model: str, token: str, base_url: str = "http://host.docker.internal:8787",
                 transport: httpx.BaseTransport | None = None, timeout: float = 100.0, alerts=None):
        if not (token or "").strip():
            raise ProviderNotFound("opencode text provider requires OPENCODE_BRIDGE_TOKEN")
        self.model, self._token, self._base = model, token.strip(), base_url.rstrip("/")
        self._transport, self._timeout = transport, timeout
        self._verified = False
        self._alerts = alerts

    def cost_estimate(self, prompt: str) -> float:
        return 0.0  # assinatura OAuth do usuário: sem custo marginal por chamada

    def _check_bridge(self, client: httpx.Client) -> None:
        """O bridge escolhe o modelo real (OPENCODE_MODEL); o `model` do spec só rotula ledger/analytics.
        Só gera se o bridge declarar exatamente o mesmo modelo no `/health` (como o `OpenCodeImage`)."""
        if self._verified:
            return
        try:
            response = client.get(f"{self._base}/health")
            if self._alerts is not None:
                self._alerts.observe(True)
            declared = response.json().get("model")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            if self._alerts is not None and isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                self._alerts.observe(False)
            return  # inalcançável/ilegível: sem verificação agora; a geração decide o erro (nada em silêncio)
        if declared is None:
            # Bridge antigo, sem o campo: aceita para não quebrar o rollout, mas nunca em silêncio.
            logging.getLogger("studio.alerts").warning('{"event":"bridge_text_model_undeclared"}')
        elif declared != self.model:
            raise PreEffectFailure(f"bridge text model ({declared}) differs from the configured {self.model}; "
                                   "update OPENCODE_MODEL in scripts/opencode-bridge.py to match the project's text spec")
        self._verified = True

    def complete(self, prompt: str, *, json_schema: dict | None = None) -> TextResult:
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout, trust_env=False) as client:
                self._check_bridge(client)
                response = client.post(f"{self._base}/generate", headers={"Authorization": f"Bearer {self._token}"}, json={"prompt": prompt})
                if self._alerts is not None:
                    self._alerts.observe(True)
                response.raise_for_status()
                text = response.json()["text"]
            if not isinstance(text, str):
                raise TypeError("text is not a string")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            if self._alerts is not None and isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                self._alerts.observe(False)
            status = f" (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else ""
            message = f"OpenCode bridge failed: {type(exc).__name__}{status}; is scripts/opencode-bridge.py running?"
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 424:
                # o bridge diz por que o provedor recusou (ex.: limite da assinatura): vai ao operador
                try:
                    message = f"OpenCode provider rejected the request: {str(exc.response.json()['detail'])[:240]}"
                except (ValueError, KeyError, TypeError):
                    pass
            # Requisição recusada (4xx) ou nunca enviada (conexão): nenhum efeito externo pago.
            if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)) or (
                    isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500):
                raise PreEffectFailure(message) from None
            raise ModelUnavailable(message) from None
        return TextResult(text=text, usage=UsageEntry(step="text", provider=self.name, model=self.model, cost_usd=0.0))
