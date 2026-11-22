"""Page Object para gerenciamento e criação de Canais."""
from __future__ import annotations

import re
from playwright.sync_api import Locator, Page, expect


class ChannelsPage:
    def __init__(self, page: Page, base_url: str = "http://localhost:8000") -> None:
        self.page = page
        self.base_url = base_url

    def goto_channels(self) -> None:
        self.page.goto(f"{self.base_url}/studio/canais")
        self.page.wait_for_load_state("domcontentloaded")

    def open_new_channel_dialog(self) -> Locator:
        # Botão na topbar ou botão de criar canal na página
        btn = self.page.locator("#btn-novo-canal")
        if not btn.is_visible():
            btn = self.page.locator("#btn-criar-canal")
        expect(btn).to_be_visible()
        btn.click()
        dialog = self.page.locator("#dlg-canal")
        expect(dialog).to_be_visible()
        return dialog

    def create_channel(self, name: str, niche: str = "Geral", language: str = "pt-BR") -> str:
        """Abre o diálogo, preenche os dados e cria um novo canal.

        Retorna a URL resultante após o redirecionamento.
        """
        self.open_new_channel_dialog()

        nome_input = self.page.locator("#dlg-canal-nome")
        expect(nome_input).to_be_visible()
        nome_input.fill(name)

        if niche:
            self.page.locator("#dlg-canal-nicho").fill(niche)

        if language:
            self.page.locator("#dlg-canal-idioma").select_option(language)

        salvar_btn = self.page.locator("#dlg-btn-salvar-canal")
        expect(salvar_btn).to_be_enabled()
        salvar_btn.click()

        # Aguarda o redirecionamento para o estúdio com o canal ativo
        self.page.wait_for_url(re.compile(r".*/studio/panel\?project_id=.*"), timeout=10000)
        return self.page.url
