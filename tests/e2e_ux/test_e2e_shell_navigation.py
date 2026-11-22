"""Testes E2E da casca V3 (Shell): navegação de 7 itens, estado ativo e tema."""
from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow
from tests.e2e_ux.pages.base_page import BasePage

CANONICAL_7_NAV_ITEMS = [
    "Início",
    "Criar vídeo",
    "Vídeos",
    "Tendências e ideias",
    "Desempenho",
    "Biblioteca",
    "Configurações",
]


def test_shell_has_all_seven_canonical_nav_items(auth_page: Page, studio_config: dict[str, str]) -> None:
    shell = BasePage(auth_page, studio_config["base_url"])
    shell.goto_home()

    labels = shell.get_all_nav_labels()
    for expected in CANONICAL_7_NAV_ITEMS:
        assert any(expected in label for label in labels), f"Item ausente no menu V3: {expected}. Encontrados: {labels}"

    assert "Início" in shell.get_active_nav_label()
    assert_no_duplicate_ids(auth_page, context_desc="Shell Inicial")
    assert_no_horizontal_overflow(auth_page, context_desc="Shell Inicial")


def test_shell_navigation_transitions_maintain_active_state(auth_page: Page, studio_config: dict[str, str]) -> None:
    shell = BasePage(auth_page, studio_config["base_url"])
    shell.goto_home()

    # Navega para Tendências e ideias (preserva ?project_id=...)
    shell.navigate_to("Tendências e ideias")
    expect(auth_page).to_have_url(re.compile(r".*/studio/panel/tendencias(\?.*)?$"), timeout=5000)
    assert "Tendências e ideias" in shell.get_active_nav_label()
    assert_no_duplicate_ids(auth_page, context_desc="Tela de Tendências")

    # Navega para Configurações (leva para /studio/canais)
    shell.navigate_to("Configurações")
    expect(auth_page).to_have_url(re.compile(r".*/studio/(canais|configuracoes|panel).*"), timeout=5000)
    assert "Configurações" in shell.get_active_nav_label()
    assert_no_duplicate_ids(auth_page, context_desc="Tela de Configurações")

    # Retorna para Início
    shell.navigate_to("Início")
    expect(auth_page).to_have_url(re.compile(r".*/studio/panel(\?.*)?$"), timeout=5000)
    assert "Início" in shell.get_active_nav_label()


def test_theme_toggle_is_interactive_if_supported(auth_page: Page, studio_config: dict[str, str]) -> None:
    shell = BasePage(auth_page, studio_config["base_url"])
    shell.goto_home()

    btn_tema = auth_page.locator("#btn-tema")
    if btn_tema.is_visible():
        initial_theme = shell.get_current_theme()
        btn_tema.click()
        new_theme = shell.get_current_theme()
        assert new_theme != initial_theme, f"O tema deveria alternar de {initial_theme!r}, mas continuou {new_theme!r}"
