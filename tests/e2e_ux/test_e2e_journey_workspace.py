"""Jornada J2 E2E: Workspace do vídeo, 8 abas de produção e integridade de áreas."""
from __future__ import annotations

import re
import uuid
from playwright.sync_api import Page, expect

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow
from tests.e2e_ux.pages.base_page import BasePage
from tests.e2e_ux.pages.channels_page import ChannelsPage
from tests.e2e_ux.pages.new_video_page import NewVideoPage
from tests.e2e_ux.pages.workspace_page import WorkspacePage

CANONICAL_8_VIDEO_AREAS = [
    "Visão geral",
    "Fontes e roteiro",
    "Narração",
    "Cenas e mídias",
    "Composição",
    "Qualidade",
    "Publicação",
    "Produção",
]


def test_journey_workspace_all_areas_navigable_and_clean_dom(auth_page: Page, studio_config: dict[str, str]) -> None:
    shell = BasePage(auth_page, studio_config["base_url"])
    shell.goto_home()

    # Cria canal e vídeo para inspecionar o workspace
    channel_name = f"Canal Workspace E2E {uuid.uuid4().hex[:6]}"
    channels = ChannelsPage(auth_page, studio_config["base_url"])
    channels.create_channel(channel_name)

    shell.navigate_to("Criar vídeo")
    new_video = NewVideoPage(auth_page, studio_config["base_url"])
    new_video.fill_concept(f"Revolução Científica {uuid.uuid4().hex[:4]}", format_choice="long")
    video_href = new_video.confirm_and_create()

    # Extrai video_id do href
    video_id = video_href.rstrip("/").split("/")[-1]
    workspace = WorkspacePage(auth_page, studio_config["base_url"])
    workspace.goto_workspace(video_id)

    # 1. Verifica presença das 8 áreas canônicas
    all_areas = workspace.get_all_area_labels()
    for expected in CANONICAL_8_VIDEO_AREAS:
        assert any(expected in a for a in all_areas), f"Área ausente no workspace: {expected}. Encontradas: {all_areas}"

    assert "Visão geral" in workspace.get_active_area_label()
    assert_no_duplicate_ids(auth_page, context_desc="Workspace - Visão Geral")
    assert_no_horizontal_overflow(auth_page, context_desc="Workspace - Visão Geral")

    # 2. Testa transição para 'Fontes e roteiro' e aviso de honestidade
    workspace.switch_area("Fontes e roteiro")
    expect(auth_page).to_have_url(re.compile(r".*/fontes(\?.*)?$"), timeout=5000)
    assert "Fontes e roteiro" in workspace.get_active_area_label()
    expect(auth_page.locator("#fontes-honestidade")).to_be_visible()
    assert_no_duplicate_ids(auth_page, context_desc="Workspace - Fontes")

    # 3. Testa transição para 'Cenas e mídias'
    workspace.switch_area("Cenas e mídias")
    expect(auth_page).to_have_url(re.compile(r".*/cenas(\?.*)?$"), timeout=5000)
    assert "Cenas e mídias" in workspace.get_active_area_label()
    assert_no_duplicate_ids(auth_page, context_desc="Workspace - Cenas")

    # 4. Testa transição para 'Qualidade'
    workspace.switch_area("Qualidade")
    expect(auth_page).to_have_url(re.compile(r".*/qualidade(\?.*)?$"), timeout=5000)
    assert "Qualidade" in workspace.get_active_area_label()
    assert_no_duplicate_ids(auth_page, context_desc="Workspace - Qualidade")

    # 5. Testa transição para 'Publicação'
    workspace.switch_area("Publicação")
    expect(auth_page).to_have_url(re.compile(r".*/publicacao(\?.*)?$"), timeout=5000)
    assert "Publicação" in workspace.get_active_area_label()
    assert_no_duplicate_ids(auth_page, context_desc="Workspace - Publicação")
