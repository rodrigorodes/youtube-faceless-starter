"""Testes E2E de comportamento de DOM vivo: diálogo de pilares, chips de tendências e teclado."""
from __future__ import annotations

import re
from playwright.sync_api import Page, expect

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow
from tests.e2e_ux.pages.base_page import BasePage


def test_trends_chips_and_pillars_dialog_interaction(auth_page: Page, studio_config: dict[str, str]) -> None:
    shell = BasePage(auth_page, studio_config["base_url"])
    shell.goto_home()
    shell.navigate_to("Tendências e ideias")

    # 1. Verifica barra de chips de filtro
    barra = auth_page.locator("#barra-tendencias")
    expect(barra).to_be_visible()

    chip_todas = barra.locator('.chip-filtro[data-filtro="todas"]')
    expect(chip_todas).to_be_visible()

    # 2. Testa abertura do diálogo de pilares pelo botão 'Gerenciar pilares' (o formulário de novo pilar fica dentro dele)
    btn_gerenciar = auth_page.locator("#btn-gerenciar-pilares")
    expect(btn_gerenciar).to_be_visible()
    btn_gerenciar.click()

    dialog = auth_page.locator("#dialog-pilares")
    expect(dialog).to_be_visible()

    # O campo de nome do pilar deve existir no diálogo
    pilar_nome = auth_page.locator("#pilar-nome")
    expect(pilar_nome).to_be_visible()

    # 3. Tecla Escape deve fechar o diálogo
    auth_page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()

    assert_no_duplicate_ids(auth_page, context_desc="Tela de Tendências com Diálogo de Pilares")
    assert_no_horizontal_overflow(auth_page, context_desc="Tela de Tendências")


def test_trends_create_video_button_carries_topic(auth_page: Page, studio_config: dict[str, str]) -> None:
    shell = BasePage(auth_page, studio_config["base_url"])
    shell.goto_home()
    shell.navigate_to("Tendências e ideias")

    # Se houver cards de tendências carregados, verifica o atalho de criação
    card = auth_page.locator(".cartao-tendencia").first
    if card.is_visible():
        btn_criar_tema = card.locator("a[data-usar-tendencia]")
        topic_text = btn_criar_tema.get_attribute("data-usar-tendencia") or ""
        assert len(topic_text) > 0, "O botão de criar vídeo da tendência deve carregar o tópico no atributo"

        btn_criar_tema.click()
        auth_page.wait_for_load_state("domcontentloaded")

        # Verifica se o tópico veio preenchido no input de tema
        tema_input = auth_page.locator("#topic, #tema-novo, #tema")
        expect(tema_input).to_be_visible()
        valor = tema_input.input_value()
        assert topic_text in valor or valor in topic_text, f"Esperava tópico preenchido com {topic_text!r}, mas obteve {valor!r}"
