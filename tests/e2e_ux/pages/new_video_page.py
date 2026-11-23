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
        """Preenche o tema e escolhe formato e modo na tela única de criação.

        Usa o Modo Diretor: ele só cria o rascunho. O piloto automático inicia uma produção (provedores
        pagos) assim que o vídeo é criado, o que um teste de interface não deve disparar.
        """
        tema_input = self.page.locator("#tema-novo")
        expect(tema_input).to_be_visible()
        tema_input.fill(topic)

        # Formato fica em "Personalizar este vídeo", recolhido por padrão.
        self.page.locator("#video-custom > summary").click()
        self.page.locator(f'label.seg-btn:has(input[name="formato-novo"][value="{format_choice}"])').click()
        self.page.locator("#card-modo-diretor").click()
        expect(self.page.locator('input[name="modo-producao"][value="diretor"]')).to_be_checked()

    def confirm_and_create(self) -> str:
        """Envia o formulário. Criar abre o vídeo no storyboard; devolve o link do vídeo (sem a aba)."""
        btn_criar = self.page.locator("#btn-criar-abrir")
        expect(btn_criar).to_be_enabled()
        btn_criar.click()

        self.page.wait_for_url(re.compile(r".*/studio/panel/videos/[0-9a-f]{32}/cenas.*"), timeout=15000)
        match = re.search(r"(/studio/panel/videos/[0-9a-f]{32})", self.page.url)
        assert match, self.page.url
        return match.group(1)
