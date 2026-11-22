from pathlib import Path
from playwright.sync_api import sync_playwright, expect

url = (Path(__file__).parent / "index.html").resolve().as_uri()
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1360, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.evaluate("ch().dur=60;ch().mode='diretor';render()")
    page.click('[data-a=input-kind][data-v=script]')
    script = "Meu roteiro original, sem reescrever.\n\nSegundo parágrafo que precisa permanecer intacto."
    page.fill("#homeTopic", script)
    page.click('[data-a=quickv2]')
    expect(page.locator(".scene")).to_have_count(1)
    assert page.evaluate("vid().scenes.map(s=>s.text)") == script.split("\n\n")
    assert page.evaluate("vid().target") == 60
    page.click('[data-a=delscene]')
    assert page.evaluate("vid().scenes.length") == 1
    page.click('[data-a=undo-v3]')
    assert page.evaluate("vid().scenes.length") == 2
    page.click('[data-a=redo-v3]')
    assert page.evaluate("vid().scenes.length") == 1
    page.click('[data-a=undo-v3]')
    page.click('[data-a=regen]')
    page.click('[data-a=audio-history]')
    page.click('[data-a=restore-audio]')
    assert page.evaluate("vid().scenes.find(s=>s.id===V3.selected).audio") == "ok"
    page.click('[data-a=media]')
    page.click('[data-a=media-tab][data-v=stock]')
    page.locator('[data-a=pickmedia]').first.click()
    assert page.evaluate("vid().scenes.find(s=>s.id===V3.selected).media.kind") == "stock"
    page.click('[data-a=render]')
    expect(page.locator("#v3-dialog-title")).to_have_text("Atualizar esta versão")
    page.click('[data-a=confirm-render]')
    page.wait_for_selector("[data-a=approve]:enabled", timeout=15000)
    page.click('[data-a=approve]')
    page.wait_for_selector("#pm5")
    page.fill("#pm5", "2099-12-20T18:30")
    page.locator("#pm1").click()
    page.click('[data-a=publish]')
    assert page.evaluate("vid().state") == "scheduled"
    assert page.evaluate("vid().pub") is None
    page.fill("#pm5", "2000-01-01T12:00")
    page.locator("#pm1").click()
    page.click('[data-a=publish]')
    expect(page.locator("#toast")).to_contain_text("data futura")
    page.goto(url+"#/home")
    page.fill("#homeTopic", "Uma ideia curta")
    page.evaluate("ch().mode='piloto';render()")
    page.click('[data-a=quickv2]')
    page.wait_for_selector("[data-a=approve]:enabled", timeout=15000)
    page.click('[data-a=approve]')
    page.click('[data-a=publish]')
    assert page.evaluate("vid().state") == "published"
    for route in ["home", "channel/new", "new", "videos", "ideas", "analytics", "library", "settings", "video/v1/cenas", "video/v1/composicao", "video/v1/qualidade", "video/v1/publicacao", "video/v1/fontes", "video/v1/producao"]:
        page.goto(url+"#/"+route)
        expect(page.locator("#view")).not_to_be_empty()
    page.set_viewport_size({"width": 390, "height": 844})
    for route in ["home", "channel/new", "video/v1/cenas", "video/v1/qualidade"]:
        page.goto(url+"#/"+route)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), route
    assert not errors, errors
    browser.close()
print("PASS V3: roteiro literal, herança, desfazer/refazer, voz, mídia, impacto, QA, publicação, agendamento, rotas e mobile.")
