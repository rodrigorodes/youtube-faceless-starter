"""PC-05.02 — Real Browser E2E for Persistent SQL Asset Tags, Search, and Channel Media Library.

Proves in Chromium browser against isolated stack (port 8100):
1. Create channel & video -> load storyboard.
2. Import an asset on Scene 0 -> appears in channel media library.
3. Open media modal -> switch to "Do canal" tab.
4. Add tag 'historia' -> tag pill '#historia' appears in the UI.
5. Search by tag 'historia' -> asset displayed.
6. Search by non-existent tag -> empty state ("Nenhuma mídia disponível neste escopo.").
7. Clear search -> asset reappears.
8. Reload page -> reopen modal -> "Do canal" -> tag '#historia' persists across full reload.
9. Remove tag '#historia' -> tag pill is removed, search by tag reflects removal.
10. Pick asset from channel library into scene -> modal closes and scene is updated.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from PIL import Image

try:
    from playwright.sync_api import Browser, Page, expect
except ImportError:
    Browser = Page = expect = None

pytest_plugins = ["tests.e2e_full.conftest"]

from tests.e2e_full.conftest import Journey
from tests.e2e_full.test_journey_piloto import create_channel, create_video, wait_for_scenes

pytestmark = pytest.mark.skipif(Browser is None, reason="Playwright não instalado")


def _make_png(path: Path, color: tuple[int, int, int] = (40, 120, 200)) -> Path:
    Image.new("RGB", (720, 1280), color=color).save(path, format="PNG")
    return path


def _flush_sb(page: Page) -> None:
    page.evaluate("() => window.__sbFlush ? window.__sbFlush() : Promise.resolve()")


def test_pc05_browser_asset_tags_and_channel_library(journey: Journey, tmp_path: Path):
    j, page = journey, journey.page
    suffix = str(int(time.time()))[-6:]

    png_asset = _make_png(tmp_path / "acervo1.png", (45, 130, 210))

    page.set_viewport_size({"width": 1280, "height": 800})
    create_channel(j, f"Canal PC05 Tags {suffix}")
    video_id = create_video(j, f"Acervo PC05 Tags {suffix}", mode="piloto")
    wait_for_scenes(j, minimum=3)

    card0 = page.locator(".scene").first
    sid0 = card0.get_attribute("data-sid")
    assert sid0

    # 1. Import initial media to scene 0 so that channel has at least one asset
    panel0 = card0.locator("details.assisted-import-panel")
    panel0.locator("summary").click()
    panel0.locator('[data-f="import-file"]').set_input_files(str(png_asset))
    panel0.locator('[data-f="import-license"]').select_option("CC0-1.0")
    with page.expect_response(lambda r: "/import-media" in r.url and r.request.method == "POST") as resp1:
        panel0.locator('[data-a="submit-import"]').click()
    assert resp1.value.status == 200
    _flush_sb(page)
    aid = resp1.value.json()["asset"]["id"]
    assert aid

    # 2. Open media modal on Scene 0
    m_btn = card0.locator('[data-a="media"]').first
    m_btn.click()
    dlg = page.locator("#dlg-media")
    expect(dlg).to_be_visible()

    # 3. Switch to 'Do canal' tab
    tab_chan = dlg.locator('[data-a="media-tab"][data-v="channel"]')
    with page.expect_response(lambda r: "/assets/library" in r.url):
        tab_chan.click()

    # Wait for channel library controls and asset card
    media_body = dlg.locator("#media-body")
    search_q = media_body.locator('[data-f="channel-search-q"]')
    search_tag = media_body.locator('[data-f="channel-search-tag"]')
    expect(search_q).to_be_visible()
    expect(search_tag).to_be_visible()

    asset_card = media_body.locator(f'.channel-asset-card[data-asset-id="{aid}"]')
    expect(asset_card).to_be_visible()

    # 4. Add tag 'historia' to the asset
    new_tag_input = asset_card.locator('input[data-f="new-tag-input"]')
    add_tag_btn = asset_card.locator('[data-a="add-asset-tag"]')
    new_tag_input.fill("historia")
    with page.expect_response(lambda r: f"/assets/{aid}/tags" in r.url and r.request.method == "POST") as tag_post:
        add_tag_btn.click()
    assert tag_post.value.status == 200

    # Tag pill appears
    tag_pill = asset_card.locator('.tag-pill:has-text("#historia")')
    expect(tag_pill).to_be_visible()

    # 5. Search by tag 'historia' -> asset stays visible
    search_tag.fill("historia")
    with page.expect_response(lambda r: "/assets/library" in r.url):
        media_body.locator('[data-a="channel-search-btn"]').click()
    expect(asset_card).to_be_visible()

    # 6. Search by non-existent tag -> empty state
    search_tag.fill("inexistente999")
    with page.expect_response(lambda r: "/assets/library" in r.url):
        media_body.locator('[data-a="channel-search-btn"]').click()
    empty_p = media_body.locator("text=Nenhuma mídia disponível neste escopo")
    expect(empty_p).to_be_visible()

    # 7. Clear search -> asset reappears
    with page.expect_response(lambda r: "/assets/library" in r.url):
        media_body.locator('[data-a="channel-clear-btn"]').click()
    expect(asset_card).to_be_visible()
    expect(tag_pill).to_be_visible()

    # 8. Reload page to verify persistence across reload
    page.reload()
    _flush_sb(page)
    card0 = page.locator(".scene").first
    card0.locator('[data-a="media"]').first.click()
    expect(dlg).to_be_visible()

    # Switch to 'Do canal' tab again
    with page.expect_response(lambda r: "/assets/library" in r.url):
        dlg.locator('[data-a="media-tab"][data-v="channel"]').click()
    asset_card = media_body.locator(f'.channel-asset-card[data-asset-id="{aid}"]')
    expect(asset_card).to_be_visible()
    tag_pill = asset_card.locator('.tag-pill:has-text("#historia")')
    expect(tag_pill).to_be_visible()

    # 9. Remove tag 'historia'
    remove_tag_btn = asset_card.locator(f'[data-a="remove-asset-tag"][data-tag="historia"]')
    with page.expect_response(lambda r: f"/assets/{aid}/tags/historia" in r.url and r.request.method == "DELETE") as tag_del:
        remove_tag_btn.click()
    assert tag_del.value.status == 200

    # Tag pill is gone
    expect(tag_pill).not_to_be_visible()

    # Search by 'historia' now returns empty
    search_tag = media_body.locator('[data-f="channel-search-tag"]')
    search_tag.fill("historia")
    with page.expect_response(lambda r: "/assets/library" in r.url):
        media_body.locator('[data-a="channel-search-btn"]').click()
    expect(empty_p).to_be_visible()

    # Clear search
    with page.expect_response(lambda r: "/assets/library" in r.url):
        media_body.locator('[data-a="channel-clear-btn"]').click()
    expect(asset_card).to_be_visible()

    # 10. Pick asset into scene 0
    pick_btn = asset_card.locator(f'[data-a="pickmedia"][data-asset="{aid}"]')
    pick_btn.click()
    expect(dlg).not_to_be_visible()

    # Card 0 thumb reflects asset
    thumb0 = card0.locator('[data-f="thumb"]')
    expect(thumb0).to_be_visible()
