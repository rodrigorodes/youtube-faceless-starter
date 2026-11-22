"""Page Object para criação de novos vídeos (fluxo de 3 etapas)."""
from __future__ import annotations

import re
from playwright.sync_api import Locator, Page, expect


class NewVideoPage:
    def __init__(self, page: Page, base_url: str = "http://localhost:8000") -> None:
        self.page = page
        self.base_url = base_url

    def goto_new_video(self, project_id: str | None = None) -> None:
        url = f"{self.base_url}/studio/panel/novo-video"
        if project_id:
            url += f"?project_id={project_id}"
        self.page.goto(url)
        self.page.wait_for_load_state("domcontentloaded")

    def fill_concept(self, topic: str, format_choice: str = "short") -> None:
        tema_input = self.page.locator("#tema-novo")
        if not tema_input.is_visible():
            tema_input = self.page.get_by_label("Sobre o que é o vídeo?")
        if not tema_input.is_visible():
            tema_input = self.page.locator("#tema")
        expect(tema_input).to_be_visible()
        tema_input.fill(topic)

        # Seleciona formato (short ou long)
        radio = self.page.locator(f'input[name="formato-novo"][value="{format_choice}"]')
        if radio.is_visible():
            radio.check()

        continuar_btn = self.page.locator("#btn-para-revisao")
        expect(continuar_btn).to_be_enabled()
        continuar_btn.click()

    def confirm_and_create(self) -> str:
        """Confirma a revisão na Etapa 2 e cria o vídeo. Retorna o ID ou link do vídeo criado."""
        etapa_2 = self.page.locator("#etapa-2")
        expect(etapa_2).to_be_visible()

        btn_criar = self.page.locator("#btn-criar")
        expect(btn_criar).to_be_enabled()
        btn_criar.click()

        # Aguarda etapa 3 de sucesso
        etapa_3 = self.page.locator("#etapa-3")
        expect(etapa_3).to_be_visible(timeout=10000)

        link_abrir = self.page.locator("#link-abrir-video")
        expect(link_abrir).to_be_visible()
        href = link_abrir.get_attribute("href") or ""
        return href
