"""VE-08.1–VE-08.7 — comportamento do storyboard e da produção sobre o backend simulado (sem custo de mídia)."""
from __future__ import annotations

import pytest

from app.studio.application.ports import LatestRun
from app.studio.domain.contracts import VideoStatus

from .harness import FakeStudio, install, workspace_html

pytest.importorskip("pytest_playwright")  # a mesma sessão do Playwright dos demais testes de navegador


@pytest.fixture
def ctx(browser):
    c = browser.new_context(viewport={"width": 1440, "height": 1000}, service_workers="block")
    yield c
    c.close()


def open_page(ctx, studio, **kw):
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    url = install(page, studio, lambda: workspace_html(studio, **kw))
    page.goto(url)
    page.evaluate("window.__marker = 'same-page'")
    page.errors = errors
    return page


def texts(page):
    return page.eval_on_selector_all('.scene textarea', 'els => els.map(e => e.value)')


def settle(page, studio=None):
    page.evaluate("window.__sbFlush()")
    page.wait_for_function("document.getElementById('storyboard-feedback').textContent.startsWith('Altera') || "
                           "document.getElementById('storyboard-feedback').textContent.startsWith('Salvo') || "
                           "document.getElementById('storyboard-feedback').textContent.startsWith('N')")


def edit(page, i, value):
    box = page.locator('.scene textarea').nth(i)
    box.click()
    box.fill(value)
    page.locator('body').click(position={'x': 5, 'y': 5})  # blur -> change
    settle(page)


def test_all_scene_cards_are_on_the_bench_in_script_order(ctx):
    st = FakeStudio()
    page = open_page(ctx, st)
    assert page.locator('.scene').count() == 3
    assert page.locator('#cena-em-foco, #seletor-cenas, .btn-cena-pill').count() == 0
    assert [t.split('\n')[0] for t in page.locator('.scene .num').all_inner_texts()] == [
        'CENA 1 · GANCHO', 'CENA 2 · MECANISMO', 'CENA 3 · CONVERSÃO']
    assert 'Storyboard integrado' in page.inner_text('#storyboard')
    assert page.errors == []


def test_each_scene_edits_independently_and_persists(ctx):
    st = FakeStudio()
    page = open_page(ctx, st)
    edit(page, 1, "Os fótons liberam elétrons no silício da célula solar.")
    assert st.scenes[1]['narration'].startswith('Os fótons liberam')
    assert st.scenes[0]['narration'].startswith('Você sabia') and st.scenes[2]['narration'].startswith('O inversor')
    assert page.locator('[data-count]').nth(1).inner_text().startswith('9 palavras')
    page.reload()
    assert texts(page)[1].startswith('Os fótons liberam')


def test_undo_redo_text_media_and_redo_is_invalidated_by_new_edit(ctx):
    st = FakeStudio()
    page = open_page(ctx, st)
    original = texts(page)[0]
    assert page.locator('#btn-undo-cenas').is_disabled() and page.locator('#btn-redo-cenas').is_disabled()
    edit(page, 0, "Texto novo da primeira cena, bem diferente do original.")
    # o backend limpa a mídia de uma cena editada; a UI espelha isso
    assert st.scenes[0]['asset_id'] is None
    assert 'Sem mídia ainda' in page.locator('.scene').nth(0).inner_text()
    page.click('#btn-undo-cenas'); settle(page)
    assert texts(page)[0] == original and st.scenes[0]['narration'] == original
    assert st.scenes[0]['asset_id'] == 'asset-0'          # mídia religada ao desfazer
    assert page.locator('.scene').nth(0).locator('img').count() == 1
    assert page.locator('#btn-redo-cenas').is_enabled()
    page.click('#btn-redo-cenas'); settle(page)
    assert texts(page)[0].startswith('Texto novo') and st.scenes[0]['narration'].startswith('Texto novo')
    page.click('#btn-undo-cenas'); settle(page)
    edit(page, 2, "Outra edição na terceira cena invalida o refazer.")
    assert page.locator('#btn-redo-cenas').is_disabled()
    assert page.errors == []


def test_broll_toggle_and_note_are_per_scene_and_persist(ctx):
    st = FakeStudio()
    page = open_page(ctx, st)
    btn = page.locator('[data-a=broll]').nth(1)
    assert btn.inner_text() == '+ B-roll' and btn.get_attribute('aria-pressed') == 'false'
    btn.click(); settle(page)
    assert btn.inner_text() == 'B-roll ativo' and btn.get_attribute('aria-pressed') == 'true'
    assert page.locator('input[data-a=brollnote]').count() == 1
    note = page.locator('.scene').nth(1).locator('input[data-a=brollnote]')
    note.fill('Imagens de arquivo de painéis solares'); page.locator('body').click(position={'x': 5, 'y': 5}); settle(page)
    assert st.scenes[1]['broll_enabled'] and st.scenes[1]['broll_note'] == 'Imagens de arquivo de painéis solares'
    assert not st.scenes[0]['broll_enabled'] and not st.scenes[2]['broll_enabled']
    page.reload()
    assert page.locator('[data-a=broll]').nth(1).inner_text() == 'B-roll ativo'
    assert page.locator('input[data-a=brollnote]').input_value() == 'Imagens de arquivo de painéis solares'
    page.locator('[data-a=broll]').nth(1).click(); settle(page)
    assert page.locator('input[data-a=brollnote]').count() == 0 and not st.scenes[1]['broll_enabled']
    page.click('#btn-undo-cenas'); settle(page)
    assert st.scenes[1]['broll_enabled'] is True


def test_new_scene_adds_a_card_without_navigation_and_persists(ctx):
    st = FakeStudio()
    page = open_page(ctx, st)
    page.click('#btn-nova-cena'); settle(page)
    assert page.evaluate('window.__marker') == 'same-page'
    assert page.locator('.scene').count() == 4
    assert page.locator('.scene .num').nth(3).inner_text().startswith('CENA 4 · NOVA CENA')
    assert page.locator('#dock-count').inner_text() == '4 cenas'
    assert len(st.scenes) == 4 and st.scenes[3]['narration'] == 'Escreva aqui o texto da narração desta cena.'
    assert page.locator('.scene textarea').nth(3).evaluate('e => e === document.activeElement')
    page.reload()
    assert page.locator('.scene').count() == 4          # persistida; o histórico é só da sessão da página
    assert page.locator('#btn-undo-cenas').is_disabled()
    page.click('#btn-nova-cena'); settle(page)
    page.click('#btn-undo-cenas'); settle(page)
    assert page.locator('.scene').count() == 4 and len(st.scenes) == 4


def test_delete_and_reorder_are_undoable_and_keep_media(ctx):
    st = FakeStudio()
    page = open_page(ctx, st)
    page.locator('[data-a=mv][data-d="1"]').nth(0).click(); settle(page)
    assert [s['label'] for s in st.scenes] == ['Mecanismo', 'Gancho', 'Conversão']
    assert page.locator('.scene .num').first.inner_text().startswith('CENA 1 · MECANISMO')
    page.click('#btn-undo-cenas'); settle(page)
    assert [s['label'] for s in st.scenes] == ['Gancho', 'Mecanismo', 'Conversão']
    page.locator('[data-a=delscene]').nth(0).click(); settle(page)
    assert [s['label'] for s in st.scenes] == ['Mecanismo', 'Conversão']
    page.click('#btn-undo-cenas'); settle(page)
    assert [s['label'] for s in st.scenes] == ['Gancho', 'Mecanismo', 'Conversão']
    assert st.scenes[0]['asset_id'] == 'asset-0'            # a mídia volta junto com a cena
    assert page.errors == []


def test_media_modal_changes_only_the_target_scene(ctx):
    st = FakeStudio()
    page = open_page(ctx, st)
    page.locator('[data-a=media]').nth(2).click()
    page.wait_for_selector('#dlg-media[open]')
    assert page.inner_text('#t-media') == 'Mídia para esta cena'
    assert page.locator('#media-tabs button').all_inner_texts() == ['Deste vídeo', 'Do canal', 'Meus arquivos', 'Stock', 'Gerar']
    page.locator('[data-a=pickmedia]').first.click(); settle(page)
    assert st.scenes[2]['asset_id'] == 'asset-0' and st.scenes[1]['asset_id'] is None
    assert page.locator('.scene').nth(2).locator('img').count() == 1
    assert page.locator('[data-a=media]').nth(2).inner_text() == 'Trocar mídia'
    assert page.locator('[data-a=media]').nth(1).inner_text() == 'Escolher mídia'


def test_failed_save_rolls_back_to_the_last_saved_state(ctx):
    st = FakeStudio(fail_on='script/scenes/')
    page = open_page(ctx, st)
    original = texts(page)[1]
    edit(page, 1, "Texto que o servidor vai recusar nesta tentativa.")
    assert 'Não foi possível salvar' in page.inner_text('#storyboard-feedback')
    assert texts(page)[1] == original


def test_render_button_asks_impact_starts_once_and_follows_real_progress(ctx):
    st = FakeStudio()
    page = open_page(ctx, st)
    page.click('#btn-render')
    page.wait_for_selector('#dlg-impacto[open]')
    assert page.inner_text('#t-impacto') == 'Atualizar esta versão'
    assert page.inner_text('#impact-n') == '2'
    page.click('#btn-confirmar-render')
    page.wait_for_selector('#progress-card')
    assert page.locator('#btn-render').is_disabled()
    page.wait_for_function("document.querySelector('#progress-card [data-f=count]').textContent.startsWith('1/9')", timeout=8000)
    posts = [c for c in st.calls if c[0] == 'POST' and c[1] == 'production-runs']
    assert len(posts) == 1
    assert page.evaluate('window.__marker') == 'same-page'


def test_progress_survives_reload_without_restarting(ctx):
    st = FakeStudio()
    st.runs['r' * 32] = {'polls': 1}
    run = LatestRun(run_id='r' * 32, state='RUNNING')
    stages = ['research', 'script', 'factcheck', 'storyboard', 'assets', 'render', 'qa', 'approval', 'publish']
    states = ['SUCCEEDED', 'SUCCEEDED', 'RUNNING'] + ['PENDING'] * 6
    html = workspace_html(st, status=VideoStatus.STORYBOARDED, latest_run=run, run_stages=list(zip(stages, states)))
    assert '2/9 etapas' in html and 'id="progress-card"' in html            # renderizado pelo servidor, sem JS
    page = open_page(ctx, st, status=VideoStatus.STORYBOARDED, latest_run=run, run_stages=list(zip(stages, states)))
    page.wait_for_function("document.querySelector('#progress-card [data-f=count]').textContent.startsWith('3/9')", timeout=8000)
    assert page.locator('#btn-render').is_disabled()
    assert not [c for c in st.calls if c[0] == 'POST' and c[1] == 'production-runs']   # recarregar não inicia outra
