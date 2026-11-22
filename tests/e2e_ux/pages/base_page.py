"""Page Object para a casca V3 do Faceless Studio (Shell)."""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


class BasePage:
    """Modela a barra lateral (7 itens canônicos), cabeçalho e utilitários globais."""

    def __init__(self, page: Page, base_url: str = "http://localhost:8000") -> None:
        self.page = page
        self.base_url = base_url

    def goto_home(self) -> None:
        self.page.goto(f"{self.base_url}/studio/panel")
        self.page.wait_for_load_state("domcontentloaded")

    def nav_container(self) -> Locator:
        return self.page.locator('nav[aria-label="Principal"]')

    def nav_item(self, label: str) -> Locator:
        return self.nav_container().get_by_role("link", name=label)

    def navigate_to(self, label: str) -> None:
        item = self.nav_item(label)
        expect(item).to_be_visible()
        item.click()
        self.page.wait_for_load_state("domcontentloaded")

    def get_active_nav_label(self) -> str:
        active_link = self.nav_container().locator('a[aria-current="page"]')
        expect(active_link).to_be_visible()
        return active_link.inner_text().strip()

    def get_all_nav_labels(self) -> list[str]:
        links = self.nav_container().locator("a").all()
        return [link.inner_text().strip() for link in links]

    def get_channel_select(self) -> Locator:
        return self.page.locator("#canal-ativo")

    def get_active_channel_text(self) -> str:
        select = self.get_channel_select()
        return select.evaluate("el => el.options[el.selectedIndex]?.text || ''")

    def open_new_channel_dialog(self) -> Locator:
        btn = self.page.locator("#btn-novo-canal")
        expect(btn).to_be_visible()
        btn.click()
        dialog = self.page.locator("#dlg-canal")
        expect(dialog).to_be_visible()
        return dialog

    def toggle_theme(self) -> None:
        btn = self.page.locator("#btn-tema")
        if not btn.is_visible():
            # Pode estar no DOM e ser desocultado se light-dark for suportado
            btn = self.page.locator("#theme-toggle")
        expect(btn).to_be_visible()
        btn.click()

    def get_current_theme(self) -> str:
        return self.page.evaluate("() => document.documentElement.getAttribute('data-theme') || ''")
