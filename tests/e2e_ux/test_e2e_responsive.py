"""Testes E2E de Responsividade nos 3 Breakpoints Canônicos: 390px, 768px e 1280px (A27)."""
from __future__ import annotations

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow

VIEWPORTS = [
    ("mobile", 390, 844),
    ("tablet", 768, 1024),
    ("desktop", 1280, 800),
]


@pytest.mark.parametrize("vp_name,width,height", VIEWPORTS)
def test_home_page_responsive_no_overflow(
    browser: Browser,
    studio_config: dict[str, str],
    vp_name: str,
    width: int,
    height: int,
) -> None:
    context = browser.new_context(
        http_credentials={
            "username": studio_config["user"],
            "password": studio_config["password"],
        },
        viewport={"width": width, "height": height},
    )
    page = context.new_page()
    try:
        page.goto(f"{studio_config['base_url']}/studio/panel")
        page.wait_for_load_state("domcontentloaded")

        expect(page.locator("h1")).to_be_visible()
        assert_no_duplicate_ids(page, context_desc=f"Home ({vp_name})")
        assert_no_horizontal_overflow(page, context_desc=f"Home ({vp_name})")
    finally:
        context.close()


@pytest.mark.parametrize("vp_name,width,height", VIEWPORTS)
def test_new_video_page_responsive_no_overflow(
    browser: Browser,
    studio_config: dict[str, str],
    vp_name: str,
    width: int,
    height: int,
) -> None:
    context = browser.new_context(
        http_credentials={
            "username": studio_config["user"],
            "password": studio_config["password"],
        },
        viewport={"width": width, "height": height},
    )
    page = context.new_page()
    try:
        page.goto(f"{studio_config['base_url']}/studio/panel/novo-video")
        page.wait_for_load_state("domcontentloaded")

        expect(page.locator("h1")).to_be_visible()
        assert_no_duplicate_ids(page, context_desc=f"Novo Vídeo ({vp_name})")
        assert_no_horizontal_overflow(page, context_desc=f"Novo Vídeo ({vp_name})")
    finally:
        context.close()


@pytest.mark.parametrize("vp_name,width,height", VIEWPORTS)
def test_channels_settings_responsive_no_overflow(
    browser: Browser,
    studio_config: dict[str, str],
    vp_name: str,
    width: int,
    height: int,
) -> None:
    context = browser.new_context(
        http_credentials={
            "username": studio_config["user"],
            "password": studio_config["password"],
        },
        viewport={"width": width, "height": height},
    )
    page = context.new_page()
    try:
        page.goto(f"{studio_config['base_url']}/studio/canais")
        page.wait_for_load_state("domcontentloaded")

        expect(page.locator("h1")).to_be_visible()
        assert_no_duplicate_ids(page, context_desc=f"Canais ({vp_name})")
        assert_no_horizontal_overflow(page, context_desc=f"Canais ({vp_name})")
    finally:
        context.close()
