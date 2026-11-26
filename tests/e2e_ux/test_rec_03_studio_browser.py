"""REC-03.02 — Real Browser E2E Suite with Playwright (Desktop 1280x800 & Mobile 390x844).

Executes against isolated Docker Compose stack on port 8100 (or STUDIO_E2E_BASE_URL):
1. Project/video creation -> script generation -> storyboard loaded in real Chromium (0 page errors).
2. GAI-02 Assisted Mode + GAI-01 Real Upload Journey:
   - Copy/edit scene prompt with format context
   - Upload real PNG fixture via <input type="file"> with valid license (CC0-1.0)
   - Assert HTTP 200, <img> preview naturalWidth > 0, served MIME image/png
   - Page reload -> assert imported asset persisted and other scenes untouched!
3. Real MP4 Upload & <video> Preview on Scene 2:
   - Upload FFmpeg-generated MP4 fixture to scene 2 (OWN_ORIGINAL)
   - Assert <video> preview is rendered with readyState >= 1 and videoWidth > 0
   - Assert asset file serves Content-Type video/mp4 and Accept-Ranges: bytes
   - Reload -> assert persisted with readyState >= 1 and videoWidth > 0.
4. Scene Operations — Add and Reorder:
   - Add new scene, await window.__sbFlush()
   - Reorder scenes via ↑ / ↓, await window.__sbFlush()
   - Assert reordered positions and return to original order.
5. Undo / Redo & Reload persistence:
   - Edit scene text -> blur -> await window.__sbFlush()
   - Expect undo button enabled -> click undo -> assert orig_text
   - Expect redo button enabled -> click redo -> assert new_text
   - Page reload -> assert persisted new_text with media intact.
6. "Gerar Faltantes" Action:
   - Click #btn-gerar-faltante -> dialog #dlg-impacto opens
   - Confirm render -> assert HTTP 202 started
   - Assert previously imported assets remain untouched.
7. Browser Negative Tests:
   - CC-BY-4.0 without attribution -> UI displays 422 error, media intact
   - Corrupt payload upload -> UI displays error, media intact
   - Concurrent CAS 409 conflict -> UI rolls back safely, status message announced.
8. Mobile Viewport (390x844):
   - Assert clean rendering with no horizontal overflow, no duplicate IDs,
     and interactive controls intact.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image

try:
    from playwright.sync_api import Browser, BrowserContext, Page, expect
except ImportError:
    Browser = BrowserContext = Page = expect = None

pytest_plugins = ["tests.e2e_full.conftest"]

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow
from tests.e2e_full.conftest import SOURCE_LINK, SOURCE_TEXT, Journey
from tests.e2e_full.test_journey_piloto import create_channel, create_video, wait_for_scenes

pytestmark = pytest.mark.skipif(Browser is None, reason="Playwright não instalado")


def _generate_test_png(path: Path) -> Path:
    img = Image.new("RGB", (720, 1280), color=(30, 90, 180))
    img.save(path, format="PNG")
    return path


def _generate_test_mp4(path: Path, duration_s: float = 3.0) -> Path:
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c=teal:s=720x1280:r=24:d={duration_s}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(path),
    ]
    subprocess.run(cmd, check=True)
    return path


def _create_channel_and_video(j: Journey, suffix: str) -> str:
    create_channel(j, f"Canal E2E {suffix}")
    video_id = create_video(j, f"Inovação na Computação {suffix}", mode="diretor")
    wait_for_scenes(j, minimum=3)
    return video_id


def _flush_sb(page: Page) -> None:
    page.evaluate("() => window.__sbFlush ? window.__sbFlush() : Promise.resolve()")


def test_rec_03_studio_browser_desktop_and_mobile_e2e(journey: Journey, tmp_path: Path):
    j, page = journey, journey.page
    suffix = str(int(time.time()))[-6:]

    # Prepare real media fixtures
    png_fixture = _generate_test_png(tmp_path / "fixture_e2e.png")
    mp4_fixture = _generate_test_mp4(tmp_path / "fixture_e2e.mp4", duration_s=3.0)
    corrupt_fixture = tmp_path / "fixture_corrupt.png"
    corrupt_fixture.write_bytes(b"CORRUPTED_NOT_A_REAL_IMAGE_DATA_000")

    # Set Desktop Viewport (1280x800)
    page.set_viewport_size({"width": 1280, "height": 800})

    # -------------------------------------------------------------------------
    # Step 1: Create channel & video -> load storyboard
    # -------------------------------------------------------------------------
    video_id = _create_channel_and_video(j, suffix)
    assert_no_duplicate_ids(page, context_desc="Storyboard Desktop inicial")
    assert_no_horizontal_overflow(page, context_desc="Storyboard Desktop inicial")
    j.assert_clean()

    # -------------------------------------------------------------------------
    # Step 2: GAI-02 Assisted Mode — Scene 1 Prompt Copy & Real PNG Upload
    # -------------------------------------------------------------------------
    scene_1 = page.locator(".scene").first
    assisted_panel_1 = scene_1.locator("details.assisted-import-panel")
    expect(assisted_panel_1).to_be_visible()

    # Open panel and check pre-filled prompt textarea
    assisted_panel_1.locator("summary").click()
    prompt_ta = assisted_panel_1.locator('textarea[data-f="assisted-prompt"]')
    expect(prompt_ta).to_be_visible()
    prompt_val = prompt_ta.input_value()
    assert len(prompt_val) > 10
    assert "Contexto:" in prompt_val

    # Copy prompt button (CSP-safe click)
    assisted_panel_1.locator('button[data-a="copy-prompt"]').click()
    expect(page.locator(".toast").first).to_contain_text("Prompt copiado")

    # Upload real PNG fixture via <input type="file">
    file_input_1 = assisted_panel_1.locator('input[data-f="import-file"]')
    file_input_1.set_input_files(str(png_fixture))

    # Select valid verified license
    assisted_panel_1.locator('select[data-f="import-license"]').select_option("CC0-1.0")

    # Submit import
    with page.expect_response(lambda r: "/scenes/" in r.url and "/import-media" in r.url and r.status == 200) as resp_info:
        assisted_panel_1.locator('button[data-a="submit-import"]').click()

    _flush_sb(page)
    resp_data = resp_info.value.json()
    assert resp_data["changed"] is True
    assert resp_data["asset"]["kind"] == "image"
    asset_1_id = resp_data["asset"]["id"]

    # Verify <img> preview loads with naturalWidth > 0
    thumb_img_1 = page.locator(".scene").first.locator('[data-f="thumb"] img')
    expect(thumb_img_1).to_be_visible()
    j.wait_for(lambda: thumb_img_1.evaluate("el => el.naturalWidth") > 0, timeout=10, what="imagem carregada no browser")
    img_natural_width = thumb_img_1.evaluate("el => el.naturalWidth")
    assert img_natural_width > 0, "naturalWidth da imagem importada deve ser > 0"

    # Verify image asset MIME type and cache-busting query parameter
    img_src = thumb_img_1.get_attribute("src")
    assert f"?v={asset_1_id}" in img_src
    img_headers = page.evaluate("""async (url) => {
        const resp = await fetch(url);
        return { status: resp.status, contentType: resp.headers.get('content-type') };
    }""", img_src)
    assert img_headers["status"] == 200
    assert "image/png" in img_headers["contentType"]

    # Reload page -> assert persisted with zero loss of other scenes
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    scene_1_reloaded = page.locator(".scene").first
    thumb_img_1_reloaded = scene_1_reloaded.locator('[data-f="thumb"] img')
    expect(thumb_img_1_reloaded).to_be_visible()
    j.wait_for(lambda: thumb_img_1_reloaded.evaluate("el => el.naturalWidth") > 0, timeout=10, what="imagem persistida apos reload")
    assert thumb_img_1_reloaded.evaluate("el => el.naturalWidth") > 0

    # Assert Scene 2 still intact and unchanged
    scene_2 = page.locator(".scene").nth(1)
    expect(scene_2.locator('textarea[data-a="text"]')).to_be_visible()

    # -------------------------------------------------------------------------
    # Step 3: Real MP4 Upload & <video> Preview on Scene 2
    # -------------------------------------------------------------------------
    assisted_panel_2 = scene_2.locator("details.assisted-import-panel")
    assisted_panel_2.locator("summary").click()

    # Upload MP4 fixture with OWN_ORIGINAL license
    assisted_panel_2.locator('input[data-f="import-file"]').set_input_files(str(mp4_fixture))
    assisted_panel_2.locator('select[data-f="import-license"]').select_option("OWN_ORIGINAL")

    with page.expect_response(lambda r: "/scenes/" in r.url and "/import-media" in r.url and r.status == 200) as mp4_resp_info:
        assisted_panel_2.locator('button[data-a="submit-import"]').click()

    mp4_resp_data = mp4_resp_info.value.json()
    assert mp4_resp_data["changed"] is True
    assert mp4_resp_data["asset"]["kind"] == "video"
    asset_2_id = mp4_resp_data["asset"]["id"]

    # Assert <video> preview is rendered with readyState >= 1 and videoWidth > 0
    thumb_video_2 = scene_2.locator('[data-f="thumb"] video')
    expect(thumb_video_2).to_be_visible()
    j.wait_for(lambda: thumb_video_2.evaluate("el => el.readyState >= 1 && el.videoWidth > 0"), timeout=15, what="video carregou metadados (readyState >= 1, videoWidth > 0)")
    assert thumb_video_2.evaluate("el => el.readyState") >= 1, "readyState do vídeo deve ser >= 1 (HAVE_METADATA)"
    assert thumb_video_2.evaluate("el => el.videoWidth") > 0, "videoWidth deve ser > 0"

    # Verify video asset served with MIME video/mp4 and Accept-Ranges: bytes
    vid_src = thumb_video_2.get_attribute("src")
    assert f"?v={asset_2_id}" in vid_src
    vid_headers = page.evaluate("""async (url) => {
        const resp = await fetch(url, { headers: { 'Range': 'bytes=0-1' } });
        return {
            status: resp.status,
            contentType: resp.headers.get('content-type'),
            acceptRanges: resp.headers.get('accept-ranges')
        };
    }""", vid_src)
    assert "video/mp4" in vid_headers["contentType"]
    assert vid_headers["acceptRanges"] == "bytes"

    # Reload page -> assert <video> persisted with readyState >= 1 and videoWidth > 0
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    scene_2_reloaded = page.locator(".scene").nth(1)
    thumb_video_2_reloaded = scene_2_reloaded.locator('[data-f="thumb"] video')
    expect(thumb_video_2_reloaded).to_be_visible()
    j.wait_for(lambda: thumb_video_2_reloaded.evaluate("el => el.readyState >= 1 && el.videoWidth > 0"), timeout=15, what="video persistido apos reload")
    assert thumb_video_2_reloaded.evaluate("el => el.readyState") >= 1
    assert thumb_video_2_reloaded.evaluate("el => el.videoWidth") > 0

    # -------------------------------------------------------------------------
    # Step 4: Scene Operations — Add and Reorder Scenes
    # -------------------------------------------------------------------------
    initial_scene_count = page.locator(".scene").count()
    assert initial_scene_count >= 3

    # Add new scene
    btn_nova_cena = page.locator("#btn-nova-cena")
    expect(btn_nova_cena).to_be_visible()
    btn_nova_cena.click()
    expect(page.locator(".scene")).to_have_count(initial_scene_count + 1)
    _flush_sb(page)

    # Assert added scene persists across page reload
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    expect(page.locator(".scene")).to_have_count(initial_scene_count + 1)

    # Reorder scene 2 (the video scene) up to position 0
    move_up_btn = page.locator(".scene").nth(1).locator('button[data-a="mv"][data-d="-1"]')
    expect(move_up_btn).to_be_enabled()
    move_up_btn.click()
    _flush_sb(page)

    # Now scene 0 has the <video> and scene 1 has the <img>
    expect(page.locator(".scene").nth(0).locator('[data-f="thumb"] video')).to_be_visible()
    expect(page.locator(".scene").nth(1).locator('[data-f="thumb"] img')).to_be_visible()

    # Move it back down
    move_down_btn = page.locator(".scene").nth(0).locator('button[data-a="mv"][data-d="1"]')
    expect(move_down_btn).to_be_enabled()
    move_down_btn.click()
    _flush_sb(page)

    # Verify restored order: scene 0 has <img>, scene 1 has <video>
    expect(page.locator(".scene").nth(0).locator('[data-f="thumb"] img')).to_be_visible()
    expect(page.locator(".scene").nth(1).locator('[data-f="thumb"] video')).to_be_visible()

    # -------------------------------------------------------------------------
    # Step 5: Undo / Redo & Reload persistence with window.__sbFlush()
    # -------------------------------------------------------------------------
    scene_3_curr = page.locator(".scene").nth(2)
    tx_3 = scene_3_curr.locator('textarea[data-a="text"]')
    orig_text = tx_3.input_value()
    # Use grounded text from SOURCE_TEXT so fact-check accepts the edit
    new_text = "Os otomanos usaram canhões enormes para abrir brechas nas muralhas de Teodósio."

    tx_3.focus()
    tx_3.fill(new_text)
    tx_3.blur()
    _flush_sb(page)

    # Undo
    undo_btn = page.locator("#btn-undo-cenas")
    expect(undo_btn).to_be_enabled()
    undo_btn.click()
    assert tx_3.input_value() == orig_text, "Undo deve restaurar exatamente o texto original"
    _flush_sb(page)

    # Redo
    redo_btn = page.locator("#btn-redo-cenas")
    expect(redo_btn).to_be_enabled()
    redo_btn.click()
    assert tx_3.input_value() == new_text, "Redo deve reaplicar exatamente o novo texto"
    _flush_sb(page)

    # Reload page and assert state
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    j.assert_clean()

    # Exact persisted values after reload
    reloaded_tx_3 = page.locator(".scene").nth(2).locator('textarea[data-a="text"]')
    assert reloaded_tx_3.input_value() == new_text, "Novo texto deve persistir após recarregamento"
    # Sibling assets remain intact
    expect(page.locator(".scene").first.locator('[data-f="thumb"] img')).to_be_visible()
    assert page.locator(".scene").first.locator('[data-f="thumb"] img').evaluate("el => el.naturalWidth") > 0
    expect(page.locator(".scene").nth(1).locator('[data-f="thumb"] video')).to_be_visible()
    assert page.locator(".scene").nth(1).locator('[data-f="thumb"] video').evaluate("el => el.readyState") >= 1
    assert page.locator(".scene").nth(1).locator('[data-f="thumb"] video').evaluate("el => el.videoWidth") > 0

    # -------------------------------------------------------------------------
    # Step 6: "Gerar faltantes" Action
    # -------------------------------------------------------------------------
    btn_gerar_faltante = page.locator("#btn-gerar-faltante")
    expect(btn_gerar_faltante).to_be_visible()
    expect(btn_gerar_faltante).to_be_enabled()
    btn_gerar_faltante.click()
    dlg_impacto = page.locator("dialog#dlg-impacto")
    expect(dlg_impacto).to_be_visible()

    with page.expect_response(lambda r: r.url.endswith("/production-runs") and r.request.method == "POST") as started_info:
        page.locator("#btn-confirmar-render").click()

    assert started_info.value.status == 202
    # Verify previously imported assets are not wiped out
    expect(page.locator(".scene").first.locator('[data-f="thumb"] img')).to_be_visible()
    expect(page.locator(".scene").nth(1).locator('[data-f="thumb"] video')).to_be_visible()

    # -------------------------------------------------------------------------
    # Step 7: Browser Negative Tests
    # -------------------------------------------------------------------------
    # Negative A: Invalid license rejection (CC-BY-4.0 without attribution -> 422)
    scene_1_neg = page.locator(".scene").first
    assisted_panel_neg1 = scene_1_neg.locator("details.assisted-import-panel")
    if not assisted_panel_neg1.get_attribute("open"):
        assisted_panel_neg1.locator("summary").click()

    assisted_panel_neg1.locator('input[data-f="import-file"]').set_input_files(str(png_fixture))
    assisted_panel_neg1.locator('select[data-f="import-license"]').select_option("CC-BY-4.0")
    # Clear attribution input to trigger rejection
    attribution_input = assisted_panel_neg1.locator('input[data-f="import-attribution"]')
    expect(attribution_input).to_be_visible()
    attribution_input.fill("")

    assisted_panel_neg1.locator('button[data-a="submit-import"]').click()
    _flush_sb(page)

    err_el_lic = assisted_panel_neg1.locator('[data-f="import-error"]')
    expect(err_el_lic).to_be_visible()
    err_text_lic = err_el_lic.inner_text().lower()
    assert "atribuição" in err_text_lic or "attribution" in err_text_lic or "422" in err_text_lic
    # Prior image still intact
    expect(scene_1_neg.locator('[data-f="thumb"] img')).to_be_visible()

    # Negative B: Corrupt payload upload rejection
    scene_2_neg = page.locator(".scene").nth(1)
    assisted_panel_neg2 = scene_2_neg.locator("details.assisted-import-panel")
    if not assisted_panel_neg2.get_attribute("open"):
        assisted_panel_neg2.locator("summary").click()

    assisted_panel_neg2.locator('input[data-f="import-file"]').set_input_files(str(corrupt_fixture))
    assisted_panel_neg2.locator('select[data-f="import-license"]').select_option("OWN_ORIGINAL")
    assisted_panel_neg2.locator('button[data-a="submit-import"]').click()
    _flush_sb(page)

    err_el_corrupt = assisted_panel_neg2.locator('[data-f="import-error"]')
    expect(err_el_corrupt).to_be_visible()
    err_text_corrupt = err_el_corrupt.inner_text().lower()
    assert "recusada" in err_text_corrupt or "corrupt" in err_text_corrupt or "erro" in err_text_corrupt or "422" in err_text_corrupt
    # Prior <video> still intact
    expect(scene_2_neg.locator('[data-f="thumb"] video')).to_be_visible()

    # Negative C: Concurrent CAS 409 conflict handled gracefully
    # Fetch current server script version and apply an out-of-band edit to increment it
    oob_res = page.evaluate("""async (vid) => {
        const scr = await fetch('/studio/videos/' + encodeURIComponent(vid) + '/script').then(r => r.json());
        const curVer = scr.script ? scr.script.version : 1;
        const prompt = (scr.scenes && scr.scenes[0]) ? scr.scenes[0].image_prompt : 'prompt teste';
        const edit = await fetch('/studio/videos/' + encodeURIComponent(vid) + '/script/scenes/0', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'cas-oob-' + Date.now() },
            body: JSON.stringify({
                narration: 'Depois da conquista a cidade passou a se chamar Istambul.',
                image_prompt: prompt,
                expected_version: curVer
            })
        });
        const editData = await edit.json().catch(() => ({}));
        return { status: edit.status, newVersion: editData.script ? editData.script.version : null };
    }""", video_id)
    assert oob_res["status"] == 200

    # Now edit scene 1 text in the browser: the client's cached expected_version will be stale
    tx_cas = page.locator(".scene").first.locator('textarea[data-a="text"]')
    tx_cas.focus()
    tx_cas.fill("O sultão Mehmed II comandava cerca de 80 mil soldados otomanos.")
    tx_cas.blur()
    _flush_sb(page)

    # Assert status message announces rollback due to conflict
    status_msg = page.locator("#storyboard-feedback")
    expect(status_msg).to_contain_text("Não foi possível salvar")
    # Clean state preserved, zero uncaught browser JS errors
    j.assert_clean()

    # -------------------------------------------------------------------------
    # Step 8: Mobile Viewport (390x844) Responsiveness Check
    # -------------------------------------------------------------------------
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)

    assert_no_horizontal_overflow(page, context_desc="Storyboard Mobile 390x844")
    assert_no_duplicate_ids(page, context_desc="Storyboard Mobile 390x844")

    # Verify scene card and assisted import summary are visible and interactive on mobile
    mobile_scene_1 = page.locator(".scene").first
    expect(mobile_scene_1).to_be_visible()
    mobile_details = mobile_scene_1.locator("details.assisted-import-panel")
    expect(mobile_details).to_be_visible()

    j.assert_clean()
