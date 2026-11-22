from pathlib import Path
from playwright.sync_api import sync_playwright, expect

URL = (Path(__file__).parent / "index.html").resolve().as_uri()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1360, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    page.fill("#homeTopic", "Uma história que não deve desaparecer")
    page.click('[data-a=chmode][data-v=diretor]')
    assert page.input_value("#homeTopic") == "Uma história que não deve desaparecer"
    page.click('[data-a=quickv2]')
    assert page.locator(".scene").count() > 0
    page.click('[data-a=tab][data-v=composicao]')
    page.click('[data-a=comp][data-v=cima]')
    assert page.evaluate("vid().comp.subPos") == "cima"
    assert page.locator(".tabs .tab").count() == 5
    page.goto(URL + "#/channel/new")
    page.fill("#w1", "Canal sem fricção")
    page.locator('[data-keep=channel-2] summary').click()
    page.fill("#w6", "História, Ciência")
    page.locator("#w7").click()
    assert page.evaluate("Array.isArray(S.wiz.d.pillars)")
    page.click('[data-a=wcreate]')
    page.wait_for_url("**#/home")
    expect(page.locator("#chsel option:checked")).to_have_text("Canal sem fricção")
    page.fill("#homeTopic", "Vídeo em um clique")
    page.click('[data-a=quickv2]')
    page.wait_for_selector("[data-a=approve]:enabled", timeout=15000)
    page.click('[data-a=approve]')
    page.wait_for_selector("[data-a=publish]")
    page.goto(URL + "#/video/v4/publicacao")
    assert page.evaluate("S.ch === vid().ch && !ytOn()")
    page.goto(URL + "#/video/v3/cenas")
    page.locator(".scene textarea").first.fill("Nova edição do vídeo publicado")
    assert page.locator("[data-a=render]").count() == 1
    page.goto(URL + "#/new")
    page.fill("#ntopic", "Rascunho preservado")
    page.evaluate("S.modal={t:'contextproviders'};S.contextReturn=true;render()")
    page.click('[data-a=editprov][data-id=vc2]')
    page.fill("#mf4", "referencia-ficticia")
    page.click("[data-a=saveprov]")
    page.click("[data-a=closecontext]")
    assert page.input_value("#ntopic") == "Rascunho preservado"
    page.set_viewport_size({"width": 390, "height": 844})
    for route in ["home", "channel/new", "videos", "library"]:
        page.goto(URL + "#/" + route)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), route
    assert not errors, errors
    browser.close()
print("PASS: jornadas rápida/diretor, canal, providers, estado, cinco abas e mobile.")
