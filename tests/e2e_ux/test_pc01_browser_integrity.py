"""PC-01.02 — Real Browser E2E (Desktop 1280x800 & Mobile 390x844) on isolated stack (port 8100).

Proves:
1. Create channel & video -> load storyboard in Chromium (0 console/page errors).
2. Add 2 overlays (PNG + MP4 PiP) to Scene 0 via API.
3. Replace base WITHOUT trim via UI file upload -> overlays preserved.
4. Replace base WITH trim (0.2s - 1.4s) via UI MP4 file upload -> overlays preserved.
5. Undo -> Redo -> Reload -> state (base asset, trim, and both overlays) persisted!
6. Run real render -> verify output MP4 via ffprobe.
7. Mobile viewport (390x844) -> clean layout, no horizontal overflow, no duplicate IDs.
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image

try:
    from playwright.sync_api import Browser, Page, expect
except ImportError:
    Browser = Page = expect = None

pytest_plugins = ["tests.e2e_full.conftest"]

from tests.e2e_ux.helpers import assert_no_duplicate_ids, assert_no_horizontal_overflow
from tests.e2e_full.conftest import Journey
from tests.e2e_full.test_journey_piloto import continue_run_until_approval, create_channel, create_video, wait_for_scenes

pytestmark = pytest.mark.skipif(Browser is None, reason="Playwright não instalado")


def _make_png(path: Path, color: tuple[int, int, int] = (30, 100, 200)) -> Path:
    Image.new("RGB", (720, 1280), color=color).save(path, format="PNG")
    return path


def _make_mp4(path: Path, duration_s: float = 3.0, color: str = "teal") -> Path:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=720x1280:r=24:d={duration_s}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(path),
        ],
        check=True,
    )
    return path


def _flush_sb(page: Page) -> None:
    page.evaluate("() => window.__sbFlush ? window.__sbFlush() : Promise.resolve()")


def test_pc01_browser_edit_integrity_desktop_and_mobile(journey: Journey, tmp_path: Path):
    j, page = journey, journey.page
    suffix = str(int(time.time()))[-6:]

    png_base1 = _make_png(tmp_path / "base1.png", (30, 90, 180))
    png_ov1 = _make_png(tmp_path / "ov1.png", (220, 40, 40))
    mp4_base2 = _make_mp4(tmp_path / "base2.mp4", duration_s=10.0, color="navy")
    mp4_ov2 = _make_mp4(tmp_path / "ov2.mp4", duration_s=10.0, color="green")

    page.set_viewport_size({"width": 1280, "height": 800})
    create_channel(j, f"Canal PC01 {suffix}")
    video_id = create_video(j, f"Integridade PC01 {suffix}", mode="piloto")
    wait_for_scenes(j, minimum=3)

    card0 = page.locator(".scene").first
    sid0 = card0.get_attribute("data-sid")
    assert sid0

    # 1. Import initial base PNG on Scene 0
    panel0 = card0.locator("details.assisted-import-panel")
    panel0.locator("summary").click()
    panel0.locator('[data-f="import-file"]').set_input_files(str(png_base1))
    panel0.locator('[data-f="import-license"]').select_option("CC0-1.0")
    with page.expect_response(lambda r: "/import-media" in r.url and r.request.method == "POST") as resp1:
        panel0.locator('[data-a="submit-import"]').click()
    assert resp1.value.status == 200
    _flush_sb(page)
    aid_base1 = resp1.value.json()["asset"]["id"]

    api_headers = {"Authorization": "Bearer e2e-worker-descartavel-distinto-da-senha"}

    # Seed 2 overlay assets on Scene 0 via authenticated API context
    r_ov1_imp = page.request.post(
        f"{j.base}/studio/videos/{video_id}/scenes/{sid0}/media/import",
        headers=api_headers,
        multipart={
            "file": {"name": "ov1.png", "mimeType": "image/png", "buffer": png_ov1.read_bytes()},
            "license": "OWN_ORIGINAL",
            "expected_asset_id": aid_base1,
        },
    )
    assert r_ov1_imp.status == 200
    aid_ov1 = r_ov1_imp.json()["asset"]["id"]

    card1 = page.locator(".scene").nth(1)
    sid1 = card1.get_attribute("data-sid")
    r_ov2_imp = page.request.post(
        f"{j.base}/studio/videos/{video_id}/scenes/{sid1}/media/import",
        headers=api_headers,
        multipart={
            "file": {"name": "ov2.mp4", "mimeType": "video/mp4", "buffer": mp4_ov2.read_bytes()},
            "license": "OWN_ORIGINAL",
        },
    )
    assert r_ov2_imp.status == 200
    aid_ov2 = r_ov2_imp.json()["asset"]["id"]

    # Attach both overlays to Scene 0
    p_ov1 = page.request.post(
        f"{j.base}/studio/videos/{video_id}/scenes/{sid0}/assets",
        headers=api_headers,
        data={"asset_id": aid_ov1, "position": 1, "start_s": 0.1, "end_s": 1.5, "role": "overlay", "motion": "zoom_in"},
    )
    assert p_ov1.status == 201
    ov1_id = p_ov1.json()["id"]

    p_ov2 = page.request.post(
        f"{j.base}/studio/videos/{video_id}/scenes/{sid0}/assets",
        headers=api_headers,
        data={"asset_id": aid_ov2, "position": 2, "start_s": 0.4, "end_s": 2.0, "role": "overlay", "motion": "pan_left"},
    )
    assert p_ov2.status == 201
    ov2_id = p_ov2.json()["id"]

    # Reload so UI has latest edit_revision
    page.reload()
    page.wait_for_selector(".scene")
    card0 = page.locator(".scene").first
    panel0 = card0.locator("details.assisted-import-panel")
    panel0.locator("summary").click()

    # 2. Replace base WITHOUT trim via UI
    panel0.locator('[data-f="import-file"]').set_input_files(str(png_base1))
    panel0.locator('[data-f="import-license"]').select_option("OWN_ORIGINAL")
    with page.expect_response(lambda r: "/import-media" in r.url and r.request.method == "POST") as resp2:
        panel0.locator('[data-a="submit-import"]').click()
    assert resp2.value.status == 200
    _flush_sb(page)

    layers_after_no_trim = page.request.get(
        f"{j.base}/studio/videos/{video_id}/scenes/{sid0}/assets", headers=api_headers
    ).json()
    assert [x["id"] for x in layers_after_no_trim if x["role"] == "overlay"] == [ov1_id, ov2_id], layers_after_no_trim

    # 3. Replace base WITH trim (0.2 - 1.4) via UI MP4 upload
    panel0.locator('[data-f="import-file"]').set_input_files(str(mp4_base2))
    panel0.locator('[data-f="import-license"]').select_option("OWN_ORIGINAL")
    panel0.locator('[data-f="trim-start"]').fill("0.2")
    panel0.locator('[data-f="trim-end"]').fill("1.4")
    with page.expect_response(lambda r: "/import-media" in r.url and r.request.method == "POST") as resp3:
        panel0.locator('[data-a="submit-import"]').click()
    assert resp3.value.status == 200
    _flush_sb(page)
    aid_mp4 = resp3.value.json()["asset"]["id"]

    layers_after_trim = page.request.get(
        f"{j.base}/studio/videos/{video_id}/scenes/{sid0}/assets", headers=api_headers
    ).json()
    assert len(layers_after_trim) == 3
    assert [x["id"] for x in layers_after_trim if x["role"] == "overlay"] == [ov1_id, ov2_id]

    # 4. Undo -> should revert base to PNG and clear trim while preserving overlays
    undo_btn = page.locator("#btn-undo-cenas")
    expect(undo_btn).to_be_enabled()
    with page.expect_response(lambda r: f"/scenes/{sid0}/media" in r.url and r.request.method == "POST") as resp_undo:
        undo_btn.click()
    assert resp_undo.value.status == 200
    _flush_sb(page)
    assert panel0.locator('[data-f="trim-start"]').input_value() == ""

    # 5. Redo -> should restore MP4 + trim (0.2, 1.4) and preserve overlays
    redo_btn = page.locator("#btn-redo-cenas")
    expect(redo_btn).to_be_enabled()
    with page.expect_response(lambda r: f"/scenes/{sid0}/media" in r.url and r.request.method == "POST") as resp_redo:
        redo_btn.click()
    assert resp_redo.value.status == 200
    _flush_sb(page)
    assert panel0.locator('[data-f="trim-start"]').input_value() == "0.2"
    assert panel0.locator('[data-f="trim-end"]').input_value() == "1.4"

    # 6. Reload -> state persisted!
    page.reload()
    page.wait_for_selector(".scene")
    card0 = page.locator(".scene").first
    panel0 = card0.locator("details.assisted-import-panel")
    panel0.locator("summary").click()
    assert panel0.locator('[data-f="trim-start"]').input_value() == "0.2"
    assert panel0.locator('[data-f="trim-end"]').input_value() == "1.4"
    layers_reloaded = page.request.get(
        f"{j.base}/studio/videos/{video_id}/scenes/{sid0}/assets", headers=api_headers
    ).json()
    assert [x["id"] for x in layers_reloaded if x["role"] == "overlay"] == [ov1_id, ov2_id]
    base_reloaded = [x for x in layers_reloaded if x["role"] == "base"]
    assert len(base_reloaded) == 1 and base_reloaded[0]["asset_id"] == aid_mp4

    # 7. Real Render & ffprobe verification (resume production run -> real Piper + FFmpeg render)
    page.goto(f"{j.base}/studio/panel/videos/{video_id}/producao")
    page.get_by_role("link", name="Abrir execução").click()
    page.wait_for_url(re.compile(r".*/production-runs/[0-9a-f]{32}"))
    resume_btn = page.locator("button[data-run-action=resume]").first
    if resume_btn.count() > 0 and resume_btn.is_visible():
        resume_btn.click()

    deadline = time.time() + 120
    render_done = False
    last_state = None
    while time.time() < deadline:
        rj = page.request.get(f"{j.base}/studio/videos/{video_id}/render", headers=api_headers).json()
        job = rj.get("job") or {}
        last_state = (j.video_status(video_id), job)
        if job.get("status") == "SUCCEEDED" or last_state[0] in ("RENDERED", "AWAITING_APPROVAL", "APPROVED"):
            render_done = True
            break
        if job.get("status") == "FAILED":
            raise AssertionError(f"Render job failed: {job}")
        time.sleep(2.0)
    assert render_done, f"Render did not finish within 120s: {last_state}"
    mp4_resp = page.request.get(f"{j.base}/studio/videos/{video_id}/file", headers=api_headers)
    assert mp4_resp.status == 200
    out_mp4 = tmp_path / "rendered_pc01.mp4"
    out_mp4.write_bytes(mp4_resp.body())
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    assert '"codec_type": "video"' in probe.stdout
    assert '"codec_type": "audio"' in probe.stdout

    # 8. Mobile Viewport (390x844)
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{j.base}/studio/panel/videos/{video_id}/cenas")
    page.wait_for_selector(".scene")
    assert_no_duplicate_ids(page)
    assert_no_horizontal_overflow(page)
