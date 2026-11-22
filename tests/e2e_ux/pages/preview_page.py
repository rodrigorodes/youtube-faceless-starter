"""Page Object para a tela de Prévia e Aprovação Unificada (/studio/videos/{id}/preview)."""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


class PreviewPage:
    def __init__(self, page: Page, base_url: str = "http://localhost:8000") -> None:
        self.page = page
        self.base_url = base_url

    def goto_preview(self, video_id: str) -> None:
        self.page.goto(f"{self.base_url}/studio/videos/{video_id}/preview")
        self.page.wait_for_load_state("domcontentloaded")

    def heading(self) -> Locator:
        return self.page.locator("h1")

    def review_form(self) -> Locator:
        return self.page.locator("#review")

    def is_in_review(self) -> bool:
        return self.review_form().is_visible()

    def approve_button(self) -> Locator:
        return self.page.locator("#approve")

    def reject_button(self) -> Locator:
        return self.page.locator("#reject")

    def approve_video(self) -> None:
        btn = self.approve_button()
        expect(btn).to_be_visible()
        btn.click()
        # Aguarda feedback ou atualização de status
        self.page.wait_for_selector("#result", state="attached")

    def reject_video(self, reason: str = "") -> None:
        if reason:
            self.page.locator("#reject_reason").fill(reason)
        btn = self.reject_button()
        expect(btn).to_be_visible()
        btn.click()
        self.page.wait_for_selector("#result", state="attached")
