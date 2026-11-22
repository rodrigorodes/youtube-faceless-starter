"""Testes E2E de Configurações: Canais, Produção/Orçamento e Equipe."""
from __future__ import annotations

import re
import uuid
from playwright.sync_api import Page, expect

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow
from tests.e2e_ux.pages.base_page import BasePage
from tests.e2e_ux.pages.channels_page import ChannelsPage
from tests.e2e_ux.pages.settings_page import SettingsPage


def test_settings_channels_page_clean_dom(auth_page: Page, studio_config: dict[str, str]) -> None:
    settings = SettingsPage(auth_page, studio_config["base_url"])
    settings.goto_channels()

    expect(auth_page.locator("h1")).to_be_visible()
    assert_no_duplicate_ids(auth_page, context_desc="Configurações - Canais")
    assert_no_horizontal_overflow(auth_page, context_desc="Configurações - Canais")


def test_settings_economic_profile_cards_interactive(auth_page: Page, studio_config: dict[str, str]) -> None:
    shell = BasePage(auth_page, studio_config["base_url"])
    shell.goto_home()

    # Cria canal isolado para testar perfil de orçamento
    channel_name = f"Canal Budget E2E {uuid.uuid4().hex[:6]}"
    channels = ChannelsPage(auth_page, studio_config["base_url"])
    channels.create_channel(channel_name)

    settings = SettingsPage(auth_page, studio_config["base_url"])
    settings.goto_production_budget()

    # 1. Verifica presença dos três perfis econômicos em cartões (ECONOMY, BALANCED, PREMIUM)
    for profile in ("ECONOMY", "BALANCED", "PREMIUM"):
        radio = auth_page.locator(f'input[name="economic_profile"][value="{profile}"]')
        expect(radio).to_be_attached()

    # 2. Seleciona ECONOMY
    settings.select_economic_profile("ECONOMY")
    assert settings.get_selected_economic_profile() == "ECONOMY"

    # 3. Salva os limites
    settings.save_budget_limits()

    assert_no_duplicate_ids(auth_page, context_desc="Configurações - Produção e Orçamento")
    assert_no_horizontal_overflow(auth_page, context_desc="Configurações - Produção e Orçamento")


def test_settings_team_page_roles_matrix(auth_page: Page, studio_config: dict[str, str]) -> None:
    settings = SettingsPage(auth_page, studio_config["base_url"])
    settings.goto_team()

    # A página de equipe deve exibir a tabela de matriz de papéis (owner, editor, reviewer, viewer)
    page_text = auth_page.content().lower()
    for role in ("owner", "editor", "reviewer", "viewer"):
        assert role in page_text, f"Papel canônico {role} não encontrado na página de equipe"

    assert_no_duplicate_ids(auth_page, context_desc="Configurações - Equipe")
    assert_no_horizontal_overflow(auth_page, context_desc="Configurações - Equipe")
