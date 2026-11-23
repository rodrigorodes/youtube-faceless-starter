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

# Decisão V3 (`panel_video_nav.VIDEO_AREAS`): o workspace tem 5 áreas; `visao-geral`/`narracao` são legadas
# e caem em Cenas. Cada item é (rótulo, trecho da URL).
CANONICAL_VIDEO_AREAS = [
    ("Cenas & Storyboard", "/cenas"),
    ("Composição & Legendas", "/composicao"),
    ("Qualidade & Aprovação", "/qualidade"),
    ("Publicação YouTube", "/publicacao"),
    ("Fontes & Evidências", "/fontes"),
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

    # 1. Verifica presença das 5 áreas canônicas; a área padrão do rascunho é Cenas
    all_areas = workspace.get_all_area_labels()
    assert [a.splitlines()[0].strip() for a in all_areas] == [label for label, _ in CANONICAL_VIDEO_AREAS], all_areas

    # A rota legada "visao-geral" cai com segurança na área padrão
    assert "Cenas & Storyboard" in workspace.get_active_area_label()
    assert_no_duplicate_ids(auth_page, context_desc="Workspace - Cenas (área padrão)")
    assert_no_horizontal_overflow(auth_page, context_desc="Workspace - Cenas (área padrão)")

    # 2. Percorre cada área: URL própria, aba ativa e DOM sem ids duplicados
    for label, path in CANONICAL_VIDEO_AREAS:
        workspace.switch_area(label)
        expect(auth_page).to_have_url(re.compile(rf".*{path}(\?.*)?$"), timeout=5000)
        assert label in workspace.get_active_area_label()
        assert_no_duplicate_ids(auth_page, context_desc=f"Workspace - {label}")

    # 3. A honestidade das fontes aparece na área Fontes
    expect(auth_page.locator("#fontes-honestidade")).to_be_visible()
