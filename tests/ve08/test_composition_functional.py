"""VE-08.8/9 — Composição (`tabComp`): preview, timeline de 5 trilhas, parâmetros e estados vazios honestos."""
from __future__ import annotations

import pytest

from .harness import FakeStudio, install, workspace_html

pytest.importorskip("pytest_playwright")  # a mesma sessão do Playwright dos demais testes de navegador


def open_comp(browser, studio, width=1440, height=1000):
    ctx = browser.new_context(viewport={"width": width, "height": height}, service_workers="block")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(install(page, studio, lambda: workspace_html(studio, area="composicao"), area="composicao"))
    page.errors = errors
    return page


def test_composition_has_prototype_structure_and_real_timeline(browser):
    st = FakeStudio()
    st.scenes[1]["broll_enabled"], st.scenes[1]["broll_note"] = True, "Painéis solares de arquivo"
    page = open_comp(browser, st)
    assert page.locator('.two > .stack > .card h3').all_inner_texts()[:2] == ['Prévia da composição', 'Linha do tempo']
    assert page.locator('.track > span').all_inner_texts() == ['Mídia base', 'B-roll', 'Narração', 'Música', 'Legendas']
    base = page.locator('.track').nth(0).inner_text()
    assert 'Cena 1 (Arte IA) → Cena 2 (sem mídia) → Cena 3 (sem mídia)' in base
    assert 'Mecanismo: Painéis solares de arquivo' in page.locator('.track').nth(1).inner_text()
    assert 'Narração contínua · Voz Aria · ~' in page.locator('.track').nth(2).inner_text()
    assert page.locator('aside.card h3').inner_text() == 'Parâmetros'
    labels = page.locator('aside.card label, aside.card .lbl').all_inner_texts()
    for expected in ('Fonte da legenda', 'Estilo da legenda', 'Posição', 'Resolução', 'Quadros/s', 'Transição',
                     'Movimento', 'Estilo visual do vídeo'):
        assert any(l.startswith(expected) for l in labels), expected
    assert page.locator('#frame.r916').count() == 1
    assert page.errors == []


def test_composition_preview_follows_parameters_before_saving(browser):
    page = open_comp(browser, FakeStudio())
    page.locator('label.seg-btn', has_text='Topo').click()
    assert page.eval_on_selector('#cap', 'e => e.style.top') == '12%'
    page.select_option('#composicao-caption-style', 'simple')
    assert page.eval_on_selector('#cap', 'e => e.style.background') == ''
    page.select_option('#composicao-motion', 'estatico')
    assert page.eval_on_selector('#frame', 'e => e.classList.contains("static")')
    page.fill('#composicao-font-size', '60')
    page.dispatch_event('#composicao-font-size', 'input')
    assert page.inner_text('#composicao-font-size-v') == '60'
    assert 'Texto simples' in page.inner_text('#track-legendas') and 'topo' in page.inner_text('#track-legendas')


def test_composition_saves_through_the_existing_style_patch_endpoint(browser):
    st = FakeStudio()
    page = open_comp(browser, st)
    page.select_option('#composicao-caption-font', 'roboto')
    page.click('#btn-salvar-composicao')
    page.wait_for_function("document.getElementById('composicao-feedback').textContent.includes('sucesso')")
    patch = st.patches[0]['patch']
    assert patch['caption']['font_family'] == 'roboto'


def test_composition_without_scenes_is_honest(browser):
    st = FakeStudio(seed=())
    page = open_comp(browser, st)
    assert 'Sem cenas no roteiro' in page.inner_text('main')
    assert page.locator('.track').count() == 0
    assert 'Prévia aproximada das legendas — não é o vídeo renderizado.' in page.inner_text('main')


@pytest.mark.parametrize("width,height", [(768, 1000), (390, 844)])
def test_composition_has_no_horizontal_overflow_on_small_screens(browser, width, height):
    page = open_comp(browser, FakeStudio(), width, height)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
