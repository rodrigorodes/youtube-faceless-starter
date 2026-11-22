"""Page Object para as seções de Configurações (Canais, Produção/Orçamento e Equipe)."""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


class SettingsPage:
    def __init__(self, page: Page, base_url: str = "http://localhost:8000") -> None:
        self.page = page
        self.base_url = base_url

    def goto_channels(self, project_id: str | None = None) -> None:
        url = f"{self.base_url}/studio/canais"
        if project_id:
            url += f"?project_id={project_id}"
        self.page.goto(url)
        self.page.wait_for_load_state("domcontentloaded")

    def goto_production_budget(self, project_id: str | None = None) -> None:
        url = f"{self.base_url}/studio/configuracoes/producao"
        if project_id:
            url += f"?project_id={project_id}"
        self.page.goto(url)
        self.page.wait_for_load_state("domcontentloaded")

    def goto_team(self, project_id: str | None = None) -> None:
        url = f"{self.base_url}/studio/panel/equipe"
        if project_id:
            url += f"?project_id={project_id}"
        self.page.goto(url)
        self.page.wait_for_load_state("domcontentloaded")

    def select_economic_profile(self, profile: str) -> None:
        """Seleciona um perfil econômico ('ECONOMY', 'BALANCED', 'PREMIUM')."""
        radio = self.page.locator(f'input[name="economic_profile"][value="{profile}"]')
        expect(radio).to_be_attached()
        radio.check()

    def get_selected_economic_profile(self) -> str:
        radio = self.page.locator('input[name="economic_profile"]:checked')
        return radio.get_attribute("value") or ""

    def save_budget_limits(self) -> None:
        btn = self.page.get_by_role("button", name="Salvar limites")
        expect(btn).to_be_visible()
        btn.click()
        # Aguarda feedback de salvamento
        self.page.wait_for_timeout(1000)

    def roles_matrix_table(self) -> Locator:
        return self.page.locator("table.matrix")
