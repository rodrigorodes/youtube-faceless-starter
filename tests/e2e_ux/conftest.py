"""Fixtures compartilhadas para a suíte E2E do Faceless Studio com Playwright."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Generator
from urllib.parse import urlparse

import pytest
try:
    from playwright.sync_api import Browser, BrowserContext, Page
except ImportError:
    Browser = BrowserContext = Page = None


def pytest_collection_modifyitems(config, items):
    if Browser is None:
        skip = pytest.mark.skip(reason="Playwright não instalado; suíte E2E UX pulada")
        for item in items:
            if "e2e_ux" in str(item.fspath):
                item.add_marker(skip)


def _validate_destination(base_url: str):
    port = urlparse(base_url).port
    if port == 8000 and os.environ.get("STUDIO_E2E_ALLOW_DEV") != "1":
        raise ValueError(
            "Destino recusado: STUDIO_BASE_URL aponta para a porta 8000 (stack de desenvolvimento em uso). "
            "Para proteger seus dados, aponte para a stack isolada (ex: porta 8100) ou defina STUDIO_E2E_ALLOW_DEV=1."
        )


def _load_env_credentials() -> tuple[str, str, str]:
    """Lê as credenciais do Studio do ambiente ou do arquivo .env."""
    user = os.environ.get("STUDIO_BROWSER_USER", "")
    password = os.environ.get("STUDIO_BROWSER_PASSWORD", "")
    base_url = os.environ.get("STUDIO_BASE_URL", "http://localhost:8100")
    _validate_destination(base_url)

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.is_file() and (not user or not password):
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key == "STUDIO_BROWSER_USER" and not user:
                user = val
            elif key == "STUDIO_BROWSER_PASSWORD" and not password:
                password = val

    user = user or "studio"
    password = password or "studio-pass-2026"
    return user, password, base_url


@pytest.fixture(scope="session")
def studio_config() -> dict[str, str]:
    user, password, base_url = _load_env_credentials()
    return {
        "user": user,
        "password": password,
        "base_url": base_url,
    }


@pytest.fixture(scope="function")
def authenticated_context(browser: Browser, studio_config: dict[str, str]) -> Generator[BrowserContext, None, None]:
    context = browser.new_context(
        http_credentials={
            "username": studio_config["user"],
            "password": studio_config["password"],
        },
        viewport={"width": 1280, "height": 800},
    )
    yield context
    context.close()


@pytest.fixture(scope="function")
def auth_page(authenticated_context: BrowserContext, studio_config: dict[str, str]) -> Generator[Page, None, None]:
    page = authenticated_context.new_page()
    page.set_default_timeout(10000)
    yield page
    page.close()
