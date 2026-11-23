"""Browser contract against the approved reference, not duplicated CSS expectations."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))
from app.studio.api import shell_v3

ROOT = Path(__file__).resolve().parents[1]


pytest.importorskip("pytest_playwright")


def test_shell_matches_reference_geometry_and_navigation(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    ref = context.new_page()
    ref.goto((ROOT / "docs/backlogs/faceless-visual-evolution 2/prototype-v4-v3/index.html").as_uri())
    app = context.new_page()
    app.set_content(shell_v3.render_document(
        title="Test", active="inicio", crumb="Início", body_html="<h1>O que você vai criar hoje?</h1>",
        nonce="test", projects=[("one", "Canal")], project_id="one"))
    for selector in (".side", ".logo", ".top", ".content"):
        for prop in ("y", "x", "width"):
            assert app.locator(selector).bounding_box()[prop] == ref.locator(selector).bounding_box()[prop], (selector, prop)
    assert app.locator(".side nav").inner_text().split() == ref.locator(".side nav").inner_text().split()
    assert app.locator("#btn-tema").count() == 0
    assert app.locator('link[href*="fonts.googleapis"]').count() == 0
    context.close()


def test_mobile_navigation_wraps_like_reference(browser):
    page = browser.new_page(viewport={"width": 390, "height": 1000})
    page.set_content(shell_v3.render_document(
        title="Test", active="inicio", crumb="Início", body_html="<h1>Início</h1>",
        nonce="test", projects=[("one", "Canal")], project_id="one"))
    assert page.locator(".side nav ul").evaluate("(el)=>getComputedStyle(el).flexDirection") == "row"
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")


def test_new_video_progressive_disclosure_preserves_script_and_updates_summary(browser):
    from types import SimpleNamespace
    from app.studio.api.panel_new_video import render_new_video_v3
    from app.studio.api.panel_production import NewVideoView
    view = NewVideoView(projects=[("one", "Canal")], pipeline=(),
                        month=SimpleNamespace(breakdown=SimpleNamespace(calls=0)))
    page = browser.new_page()
    page.set_content(render_new_video_v3(view)[0])
    assert not page.locator("#roteiro-pronto").is_visible()
    page.locator("#usar-roteiro").check()
    page.locator("#roteiro-pronto").fill("Meu roteiro preservado.")
    page.locator("#card-modo-diretor").click()
    assert page.locator("#resumo-modo").inner_text() == "Modo Diretor"
    assert page.locator("#roteiro-pronto").input_value() == "Meu roteiro preservado."
    assert not page.locator("#duracao-alvo").is_visible()
    page.locator("#video-custom > summary").click()
    assert page.locator("#duracao-alvo").is_visible()


def test_channel_page_submits_full_transaction_and_keeps_draft_on_failure(browser):
    from app.studio.api.panel_channel_create import render_channel_create
    from app.studio.application.channels_page import ChannelsPageView
    page = browser.new_page()
    errors, payloads = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("http://studio.test/channel", lambda route: route.fulfill(
        content_type="text/html", body=render_channel_create(ChannelsPageView())[0]))
    def reject(route):
        payloads.append(route.request.post_data_json)
        route.fulfill(status=422, content_type="application/json", body='{"detail":"Limite inválido"}')
    page.route("http://studio.test/studio/channels/transactional", reject)
    page.goto("http://studio.test/channel")
    page.locator("#novo-canal-nome").fill("Canal de teste")
    page.locator("#novo-canal-publico").fill("Público real")
    page.get_by_text("Personalizar · Estratégia", exact=True).click()
    page.locator("#novo-canal-pilares").fill("História, Ciência")
    page.locator("#btn-criar-canal").click()
    from playwright.sync_api import expect
    expect(page.locator("#new-channel-feedback")).to_contain_text("Limite inválido")
    assert payloads[0]["audience"] == "Público real"
    assert payloads[0]["pillars"] == ["História", "Ciência"]
    assert payloads[0]["default_mode"] == "piloto"
    assert page.locator("#novo-canal-nome").input_value() == "Canal de teste"
    assert page.locator("#btn-criar-canal").is_enabled()
    assert not errors
