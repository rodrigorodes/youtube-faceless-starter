"""Jornada de ponta a ponta contra a stack ISOLADA (`docker-compose.e2e.yml`), sem custo e sem tocar nos dados de uso.

Esta suíte CRIA canais e vídeos e RODA produção de verdade (Piper + ffmpeg). Por isso ela só roda quando
`scripts/run-e2e-full.sh` (ou quem a chame) declara `STUDIO_E2E_ISOLATED=1` e aponta uma URL que NÃO é a da
stack de uso diário (porta 8000). Rodar sem isso é recusado, nunca "tentado".

Provedores da stack: texto `demo`, imagem `placeholder`, voz Piper local, render ffmpeg local. A publicação no
YouTube fica fora do escopo: a jornada termina em "aprovado, pendente de publicar".
"""
from __future__ import annotations

import os
import re
import time
from typing import Callable, Generator
from urllib.parse import urlparse

import pytest
try:
    from playwright.sync_api import Browser, BrowserContext, Page, expect
except ImportError:
    Browser = BrowserContext = Page = expect = None

BASE_URL = os.environ.get("STUDIO_E2E_BASE_URL", "http://127.0.0.1:8100")
USER = os.environ.get("STUDIO_E2E_USER", "e2e")
PASSWORD = os.environ.get("STUDIO_E2E_PASSWORD", "e2e-senha-descartavel")

# Texto-fonte da jornada: números e nomes que o roteiro e as edições podem citar (lastro nas fontes).
SOURCE_LINK = "https://pt.wikipedia.org/wiki/Queda_de_Constantinopla"
SOURCE_TEXT = (
    "Constantinopla caiu em 29 de maio de 1453 depois de um cerco de 53 dias. O sultão Mehmed II comandava "
    "cerca de 80 mil soldados otomanos. A cidade era defendida por aproximadamente 7 mil homens sob o imperador "
    "Constantino XI. Os otomanos usaram canhões enormes para abrir brechas nas muralhas de Teodósio. "
    "A queda de Constantinopla marcou o fim do Império Bizantino, que durou mais de mil anos. "
    "Depois da conquista a cidade passou a se chamar Istambul."
)


def pytest_collection_modifyitems(config, items):
    guard = _guard_message()
    if guard:
        skip = pytest.mark.skip(reason=guard)
        for item in items:
            if "e2e_full" in str(item.fspath):
                item.add_marker(skip)


def _guard_message() -> str:
    if Browser is None:
        return "Playwright não instalado: suíte E2E completa pulada."
    if os.environ.get("STUDIO_E2E_ISOLATED") != "1":
        return "E2E completo só roda pela stack isolada: use scripts/run-e2e-full.sh (STUDIO_E2E_ISOLATED=1)."
    if urlparse(BASE_URL).port == 8000 and os.environ.get("STUDIO_E2E_ALLOW_DEV") != "1":
        return "STUDIO_E2E_BASE_URL aponta para a porta 8000 (stack de uso diário). Recusado."
    return ""


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL.rstrip("/")


@pytest.fixture()
def ctx(browser: Browser) -> Generator[BrowserContext, None, None]:
    context = browser.new_context(http_credentials={"username": USER, "password": PASSWORD},
                                  viewport={"width": 1360, "height": 1000})
    yield context
    context.close()


class Journey:
    """Página + coletor de problemas: erro de JS, diálogo nativo do navegador e resposta 5xx quebram a jornada."""

    def __init__(self, page: Page, base_url: str) -> None:
        self.page, self.base = page, base_url
        self.page_errors: list[str] = []
        self.native_dialogs: list[str] = []
        self.server_errors: list[str] = []
        self.expected_5xx: list[str] = []  # recusas provocadas de propósito (ex.: texto sem lastro nas fontes)
        page.on("pageerror", lambda exc: self.page_errors.append(str(exc)))
        page.on("dialog", lambda d: (self.native_dialogs.append(f"{d.type}: {d.message[:80]}"), d.dismiss()))
        page.on("response", lambda r: self.server_errors.append(f"{r.status} {r.request.method} {r.url}")
                if r.status >= 500 else None)

    def api(self, path: str):
        response = self.page.request.get(self.base + path)
        return response.status, (response.json() if response.ok else None)

    def video_status(self, video_id: str) -> str:
        return self.api(f"/studio/videos/{video_id}")[1]["status"]

    def wait_for(self, check: Callable[[], bool], *, timeout: float = 120, reload: bool = False,
                 what: str = "condição") -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if check():
                return
            time.sleep(2)
            if reload:
                self.page.reload()
                self.page.wait_for_load_state("domcontentloaded")
        raise AssertionError(f"tempo esgotado esperando: {what} (em {self.page.url})")

    def video_id(self) -> str:
        match = re.search(r"/videos/([0-9a-f]{32})", self.page.url)
        assert match, self.page.url
        return match.group(1)

    def assert_clean(self) -> None:
        assert not self.page_errors, f"erros de JavaScript: {self.page_errors}"
        assert not self.native_dialogs, f"diálogo nativo do navegador (fora do tema): {self.native_dialogs}"
        unexpected = [e for e in self.server_errors if not any(marker in e for marker in self.expected_5xx)]
        assert not unexpected, f"respostas 5xx: {unexpected}"


@pytest.fixture()
def journey(ctx: BrowserContext, base_url: str) -> Generator[Journey, None, None]:
    page = ctx.new_page()
    page.set_default_timeout(15000)
    yield Journey(page, base_url)
    page.close()


__all__ = ["Journey", "SOURCE_LINK", "SOURCE_TEXT", "expect"]
