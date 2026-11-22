"""Page Object para o Workspace do Vídeo (8 abas/áreas de produção)."""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


class WorkspacePage:
    def __init__(self, page: Page, base_url: str = "http://localhost:8000") -> None:
        self.page = page
        self.base_url = base_url

    def goto_workspace(self, video_id: str, area: str = "visao-geral") -> None:
        self.page.goto(f"{self.base_url}/studio/panel/videos/{video_id}/{area}")
        self.page.wait_for_load_state("domcontentloaded")

    def areas_nav(self) -> Locator:
        return self.page.locator('nav[aria-label="Áreas do vídeo"]')

    def switch_area(self, area_label: str) -> None:
        tab = self.areas_nav().get_by_role("link", name=area_label)
        expect(tab).to_be_visible()
        tab.click()
        self.page.wait_for_load_state("domcontentloaded")

    def get_active_area_label(self) -> str:
        active_tab = self.areas_nav().locator('a[aria-current="page"]')
        expect(active_tab).to_be_visible()
        return active_tab.inner_text().strip()

    def get_all_area_labels(self) -> list[str]:
        tabs = self.areas_nav().locator("a").all()
        return [tab.inner_text().strip() for tab in tabs]

    def goto_script_page(self, video_id: str) -> None:
        self.page.goto(f"{self.base_url}/studio/panel/videos/{video_id}/roteiro")
        self.page.wait_for_load_state("domcontentloaded")
