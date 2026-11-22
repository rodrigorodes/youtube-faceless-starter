"""Smoke test E2E: valida conectividade básica e ausência de IDs duplicados na home."""
from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow


def test_studio_home_loads_and_has_clean_dom(auth_page: Page, studio_config: dict[str, str]) -> None:
    base_url = studio_config["base_url"]
    auth_page.goto(f"{base_url}/studio/panel")

    # Espera a página e o título carregarem
    expect(auth_page).to_have_title("Faceless Studio — Início")

    # A casca lateral e o h1 principal devem estar visíveis
    h1 = auth_page.locator("h1")
    expect(h1).to_be_visible()

    # Validação do contrato do DOM vivo
    assert_no_duplicate_ids(auth_page, context_desc="Home Inicial")
    assert_no_horizontal_overflow(auth_page, context_desc="Home Inicial (Desktop)")
