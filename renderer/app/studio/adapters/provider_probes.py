"""Sondas de conexão de provider (F10-03). Vivem em adapters: o core nunca fala com a rede.

`LocalProviderProbe` confirma que a implementação local responde. `HttpReachableProbe` só verifica
que o endpoint aceita conexão TCP/HTTP (qualquer status HTTP serve; erro de conexão não). Nenhuma
sonda devolve credencial.
"""
from __future__ import annotations

from ..domain.provider import ProviderKind, ProviderProbeResult


class LocalProviderProbe:
    def probe(self, kind: ProviderKind, spec: str) -> ProviderProbeResult:
        return ProviderProbeResult(ok=True, detail="implementação local disponível")


class HttpReachableProbe:
    def __init__(self, url: str, timeout: float = 3.0):
        self.url = url
        self.timeout = timeout

    def probe(self, kind: ProviderKind, spec: str) -> ProviderProbeResult:
        import httpx

        try:
            httpx.request("GET", self.url, timeout=self.timeout)
        except httpx.HTTPError:
            return ProviderProbeResult(ok=False, detail="endpoint do provider inalcançável")
        return ProviderProbeResult(ok=True, detail="endpoint do provider alcançável")