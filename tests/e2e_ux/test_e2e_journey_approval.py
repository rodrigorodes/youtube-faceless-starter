"""Jornada J3 E2E: Prévia, checklist de QA, honestidade de custo e navegação."""
from __future__ import annotations

import re
import uuid
from playwright.sync_api import Page, expect

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow
from tests.e2e_ux.pages.base_page import BasePage
from tests.e2e_ux.pages.channels_page import ChannelsPage
from tests.e2e_ux.pages.new_video_page import NewVideoPage
from tests.e2e_ux.pages.preview_page import PreviewPage


def test_journey_preview_page_structure_and_cost_honesty(auth_page: Page, studio_config: dict[str, str]) -> None:
    shell = BasePage(auth_page, studio_config["base_url"])
    shell.goto_home()

    # Cria canal e vídeo
    channel_name = f"Canal Preview E2E {uuid.uuid4().hex[:6]}"
    channels = ChannelsPage(auth_page, studio_config["base_url"])
    channels.create_channel(channel_name)

    video_topic = f"A Filosofia Estoica e a Mente {uuid.uuid4().hex[:4]}"
    shell.navigate_to("Criar vídeo")
    new_video = NewVideoPage(auth_page, studio_config["base_url"])
    new_video.fill_concept(video_topic, format_choice="short")
    video_href = new_video.confirm_and_create()
    video_id = video_href.rstrip("/").split("/")[-1]

    # Navega para a página de Prévia
    preview = PreviewPage(auth_page, studio_config["base_url"])
    preview.goto_preview(video_id)

    # 1. Validação estrutural do DOM e layout
    expect(auth_page).to_have_title(re.compile(r".*Prévia.*"))
    assert_no_duplicate_ids(auth_page, context_desc="Página de Prévia")
    assert_no_horizontal_overflow(auth_page, context_desc="Página de Prévia")

    # 2. Honestidade de custo: nunca exibir "US$ 0,00" quando não há custo medido
    page_content = auth_page.content()
    assert "US$ 0,00" not in page_content, "Regra R3 violada: ausência de custo não pode ser renderizada como US$ 0,00"

    # 3. Navegação de volta para o workspace pelo link da crumb
    back_link = auth_page.get_by_role("link", name=re.compile(r".*Voltar ao vídeo.*"))
    expect(back_link).to_be_visible()
    back_link.click()
    auth_page.wait_for_load_state("domcontentloaded")

    # Confirma retorno ao workspace do vídeo
    expect(auth_page).to_have_url(re.compile(rf".*/studio/panel/videos/{video_id}.*"))
