"""Jornada J1 E2E: Criação de canal e criação de novo vídeo com validação de DOM e isolamento."""
from __future__ import annotations

import re
import uuid
from playwright.sync_api import Page, expect

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow
from tests.e2e_ux.pages.base_page import BasePage
from tests.e2e_ux.pages.channels_page import ChannelsPage
from tests.e2e_ux.pages.new_video_page import NewVideoPage


def test_journey_create_channel_and_verify_active(auth_page: Page, studio_config: dict[str, str]) -> None:
    shell = BasePage(auth_page, studio_config["base_url"])
    shell.goto_home()

    channel_name = f"Canal E2E {uuid.uuid4().hex[:6]}"
    channels = ChannelsPage(auth_page, studio_config["base_url"])
    resulting_url = channels.create_channel(channel_name, niche="Ciência e Tecnologia", language="pt-BR")

    assert "project_id=" in resulting_url
    expect(auth_page.locator("#canal-ativo")).to_contain_text(channel_name)

    assert_no_duplicate_ids(auth_page, context_desc="Pós criação de canal")
    assert_no_horizontal_overflow(auth_page, context_desc="Pós criação de canal")


def test_journey_create_video_and_open_workspace(auth_page: Page, studio_config: dict[str, str]) -> None:
    shell = BasePage(auth_page, studio_config["base_url"])
    shell.goto_home()

    # Cria canal isolado para o vídeo
    channel_name = f"Canal E2E Video {uuid.uuid4().hex[:6]}"
    channels = ChannelsPage(auth_page, studio_config["base_url"])
    channels.create_channel(channel_name, niche="História Antiga")

    # Inicia criação do vídeo
    shell.navigate_to("Criar vídeo")
    assert_no_duplicate_ids(auth_page, context_desc="Tela Novo Vídeo (Etapa 1)")

    video_topic = f"As Grandes Invenções de Roma {uuid.uuid4().hex[:4]}"
    new_video = NewVideoPage(auth_page, studio_config["base_url"])
    new_video.fill_concept(video_topic, format_choice="short")

    # Confirmação e submissão
    video_href = new_video.confirm_and_create()
    assert "/studio/panel/videos/" in video_href

    # Criar já abre o vídeo no workspace (storyboard)
    auth_page.wait_for_load_state("domcontentloaded")

    # O workspace deve exibir o tópico do vídeo
    expect(auth_page.locator("h1")).to_contain_text(video_topic)
    assert_no_duplicate_ids(auth_page, context_desc="Workspace Inicial do Vídeo")
