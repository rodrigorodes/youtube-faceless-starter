"""REC-03.01 & REC-03.02 — Studio External Media Import Routes, Preview MIME & Assisted Mode.

Test-First (Red -> Green) suite covering:
- R08 / REC-03.01:
  - Real authenticated endpoints: POST /studio/videos/{vid}/scenes/{sid}/import-media
    and POST /studio/videos/{vid}/scenes/{sid}/media/import.
  - Ownership & auth guards (401 unauthenticated, 403 origin, 404 nonexistent video/scene ownership).
  - Validation: 422 for unverified/missing license or corrupt payload; 413 for oversized payload (>100MB).
  - CAS precondition: 409 Conflict on stale expected_asset_id.
  - Coherent MIME serving on GET .../asset and GET .../preview (image/png, video/mp4) with Accept-Ranges.
  - Scene isolation: editing scene 1 leaves scene 2 narration and assets completely untouched.
  - GAI-02 Assisted Mode integration in storyboard workspace and removal of disabled stub message.
  - PlanFfmpegRenderer consumer proof on imported MP4/PNG.
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.api.panel_video_workspace import render_video_workspace
from app.studio.api.routes import make_router
from app.studio.composition.settings import Settings
from app.studio.composition.wiring import Studio
from app.studio.domain.audio_dsp import generate_synthetic_tone, save_pcm_as_wav
from app.studio.domain.contracts import AssetKind, Scene as StoryboardRow, Video, VideoFormat, VideoStatus
from app.studio.application.ports import RenderSpec
from conftest import verified_test_connect

PROJECT_ID = "a" * 32
VIDEO_ID = "1" * 32
OTHER_VIDEO_ID = "2" * 32
SCENE_1_ID = "3" * 32
SCENE_2_ID = "4" * 32
OTHER_SCENE_ID = "5" * 32

AUTH_USER = "test-user"
AUTH_PASS = "test-browser-password"
WORKER_TOKEN = "test-worker-token"

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe required for real media import tests",
)


@pytest.fixture
def dsn():
    val = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not val or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável não configurado")
    return val


@pytest.fixture
def conn(dsn):
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    c = verified_test_connect(dsn, proof)
    try:
        c.execute("DROP SCHEMA IF EXISTS studio CASCADE")
        c.commit()
        yield c
    finally:
        c.close()


def _png_bytes(width: int = 720, height: int = 1280, color: tuple[int, int, int] = (40, 80, 160)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _ffmpeg_mp4_bytes(tmp_path: Path, name: str = "sample.mp4", color: str = "green", duration_s: float = 1.0) -> bytes:
    out = tmp_path / name
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=720x1280:r=24:d={duration_s}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out.read_bytes()


@pytest.fixture
def studio_app(conn, dsn, tmp_path: Path):
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    migrate(conn)

    # Setup project and videos
    conn.execute(
        "INSERT INTO studio.projects(id, name) VALUES (%s, 'Canal Teste')",
        (PROJECT_ID,),
    )
    conn.execute(
        "INSERT INTO studio.videos(id, project_id, topic, format, status) VALUES "
        "(%s, %s, 'Vídeo Principal', 'short', 'SCRIPTED'), "
        "(%s, %s, 'Vídeo Secundário', 'short', 'SCRIPTED')",
        (VIDEO_ID, PROJECT_ID, OTHER_VIDEO_ID, PROJECT_ID),
    )
    conn.execute(
        "INSERT INTO studio.scenes(id, video_id, idx, narration, image_prompt) VALUES "
        "(%s, %s, 0, 'Narração da cena um sobre inovação tecnológica.', 'Prompt da cena um: laboratório futurista.'), "
        "(%s, %s, 1, 'Narração da cena dois sobre resultados surpreendentes.', 'Prompt da cena dois: cientista sorrindo.'), "
        "(%s, %s, 0, 'Narração de outro vídeo isolado.', 'Prompt outro vídeo isolado.')",
        (SCENE_1_ID, VIDEO_ID, SCENE_2_ID, VIDEO_ID, OTHER_SCENE_ID, OTHER_VIDEO_ID),
    )
    conn.execute(
        "INSERT INTO studio.scripts(id, video_id, version, text) VALUES (%s, %s, 1, 'Roteiro de teste')",
        ("c" * 32, VIDEO_ID),
    )
    conn.commit()

    env = {
        "STUDIO_BROWSER_USER": AUTH_USER,
        "STUDIO_BROWSER_PASSWORD": AUTH_PASS,
        "STUDIO_WORKER_TOKEN": WORKER_TOKEN,
        "STUDIO_ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
        "STUDIO_TEXT": "demo:test",
        "STUDIO_IMAGE": "placeholder:test",
    }
    settings = Settings(database_url=dsn, storage_root=tmp_path, max_cost_video=10.0)
    studio = Studio(settings, environ=env)

    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))

    return {
        "app": app,
        "studio": studio,
        "storage_root": tmp_path,
        "conn": conn,
    }


def _worker_client(app: FastAPI) -> TestClient:
    return TestClient(
        app,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
    )


def _browser_client(app: FastAPI) -> TestClient:
    basic = base64.b64encode(f"{AUTH_USER}:{AUTH_PASS}".encode()).decode()
    return TestClient(
        app,
        base_url="http://testserver",
        headers={"Authorization": f"Basic {basic}", "Origin": "http://testserver"},
    )


# ---------------------------------------------------------------------------
# Test Cases — Red Phase First
# ---------------------------------------------------------------------------

def test_import_media_unauthenticated_is_401(studio_app):
    client = TestClient(studio_app["app"], base_url="http://testserver")
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
    )
    assert resp.status_code == 401


def test_import_media_cross_origin_browser_is_403(studio_app):
    basic = base64.b64encode(f"{AUTH_USER}:{AUTH_PASS}".encode()).decode()
    client = TestClient(
        studio_app["app"],
        base_url="http://testserver",
        headers={"Authorization": f"Basic {basic}", "Origin": "https://malicious.example.com"},
    )
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
    )
    assert resp.status_code == 403


def test_import_media_nonexistent_video_is_404(studio_app):
    client = _worker_client(studio_app["app"])
    fake_vid = "9" * 32
    png_data = _png_bytes()
    resp = client.post(
        f"/studio/videos/{fake_vid}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("test.png", png_data, "image/png")},
    )
    assert resp.status_code == 404


def test_import_media_scene_ownership_mismatch_is_404(studio_app):
    client = _worker_client(studio_app["app"])
    # OTHER_SCENE_ID belongs to OTHER_VIDEO_ID, not VIDEO_ID
    png_data = _png_bytes()
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{OTHER_SCENE_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("test.png", png_data, "image/png")},
    )
    assert resp.status_code == 404


def test_import_media_missing_or_invalid_license_is_422(studio_app):
    client = _worker_client(studio_app["app"])
    png_data = _png_bytes()

    # Invalid license
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "UNKNOWN_PIRATED_MEDIA"},
        files={"file": ("test.png", png_data, "image/png")},
    )
    assert resp.status_code == 422
    assert "recusada" in resp.json()["detail"].lower() or "license" in resp.json()["detail"].lower()

    # License requiring attribution without attribution or source_url
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC-BY-4.0"},
        files={"file": ("test.png", png_data, "image/png")},
    )
    assert resp.status_code == 422


def test_import_media_corrupt_or_fake_file_is_422(studio_app):
    client = _worker_client(studio_app["app"])
    fake_png = b"NOT_A_REAL_PNG_DATA"
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("fake.png", fake_png, "image/png")},
    )
    assert resp.status_code == 422


def test_import_media_oversized_payload_is_413(studio_app):
    client = _worker_client(studio_app["app"])
    huge_header = {"Content-Length": str(105 * 1024 * 1024)}
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("large.bin", b"0" * 100, "application/octet-stream")},
        headers=huge_header,
    )
    assert resp.status_code == 413
    assert "excede" in resp.json()["detail"].lower() or "limit" in resp.json()["detail"].lower()


def test_import_media_streaming_chunked_oversized_is_413(studio_app, monkeypatch):
    import app.studio.api.routes as routes_mod
    monkeypatch.setattr(routes_mod, "MAX_IMPORT_BYTES", 500)
    client = _worker_client(studio_app["app"])
    # Send payload larger than 500 bytes without Content-Length (chunked generator)
    def _gen_chunks():
        for _ in range(10):
            yield b"X" * 100

    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        content=_gen_chunks(),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 413
    assert "excede" in resp.json()["detail"].lower() or "limit" in resp.json()["detail"].lower()


def test_import_media_valid_png_updates_scene_and_serves_preview(studio_app):
    client = _browser_client(studio_app["app"])
    png_data = _png_bytes(width=720, height=1280, color=(10, 50, 100))

    # Test POST /studio/videos/{vid}/scenes/{sid}/import-media
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0", "author": "Equipe Criativa"},
        files={"file": ("art.png", png_data, "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scene_id"] == SCENE_1_ID
    assert data["changed"] is True
    assert data["asset"] is not None
    asset_id = data["asset"]["id"]
    assert data["asset"]["kind"] == "image"
    assert data["asset"]["license"] == "CC0-1.0"

    # Preview MIME verification: GET /studio/videos/{vid}/scenes/{sid}/asset
    preview_resp = client.get(f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/asset")
    assert preview_resp.status_code == 200
    assert preview_resp.headers["content-type"].startswith("image/png")
    assert preview_resp.headers.get("accept-ranges") == "bytes"
    assert len(preview_resp.content) > 0
    # verify valid image
    img = Image.open(io.BytesIO(preview_resp.content))
    assert img.format == "PNG"

    # Also test GET /studio/videos/{vid}/scenes/{sid}/preview alias
    preview_alias = client.get(f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/preview")
    assert preview_alias.status_code == 200
    assert preview_alias.headers["content-type"].startswith("image/png")

    # Assert Scene 2 narration & state remain completely untouched
    conn = studio_app["conn"]
    row_scene2 = conn.execute("SELECT narration, asset_id FROM studio.scenes WHERE id = %s", (SCENE_2_ID,)).fetchone()
    assert row_scene2[0] == "Narração da cena dois sobre resultados surpreendentes."
    assert row_scene2[1] is None


def test_import_media_cas_expected_asset_id_conflict_is_409(studio_app):
    client = _worker_client(studio_app["app"])
    png_data = _png_bytes()

    # 1. First import successfully links asset 1
    resp1 = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("first.png", png_data, "image/png")},
    )
    assert resp1.status_code == 200
    asset_1_id = resp1.json()["asset"]["id"]

    # 2. Second import with wrong expected_asset_id -> 409 Conflict
    png_data_2 = _png_bytes(color=(200, 50, 50))
    stale_asset_id = "f" * 32
    resp_conflict = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0", "expected_asset_id": stale_asset_id},
        files={"file": ("second.png", png_data_2, "image/png")},
    )
    assert resp_conflict.status_code == 409
    assert "changed underneath" in resp_conflict.json()["detail"].lower()

    # Verify original asset is still linked
    conn = studio_app["conn"]
    curr_asset = conn.execute("SELECT asset_id FROM studio.scenes WHERE id = %s", (SCENE_1_ID,)).fetchone()[0]
    assert curr_asset == asset_1_id

    # 3. Third import with CORRECT expected_asset_id succeeds (CAS update)
    resp_ok = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/media/import",
        data={"license": "CC0-1.0", "expected_asset_id": asset_1_id},
        files={"file": ("third.png", png_data_2, "image/png")},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["asset"]["id"] != asset_1_id


@needs_ffmpeg
def test_import_media_real_mp4_serves_video_preview_and_renders(studio_app, tmp_path: Path):
    client = _browser_client(studio_app["app"])
    mp4_data = _ffmpeg_mp4_bytes(tmp_path, name="clip_real.mp4", color="blue", duration_s=4.0)

    # Import real MP4 to scene 2 via POST /media/import alias
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_2_ID}/media/import",
        data={
            "license": "OWN_ORIGINAL",
            "trim_start_s": "0.1",
            "trim_end_s": "2.4",
        },
        files={"file": ("scene2_clip.mp4", mp4_data, "video/mp4")},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["scene_id"] == SCENE_2_ID
    assert res_data["asset"]["kind"] == "video"
    asset_id = res_data["asset"]["id"]

    # Preview MIME verification: must be video/mp4 with Accept-Ranges
    prev = client.get(f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_2_ID}/asset")
    assert prev.status_code == 200
    assert prev.headers["content-type"].startswith("video/mp4")
    assert prev.headers.get("accept-ranges") == "bytes"
    assert len(prev.content) == len(mp4_data)

    # Consumer proof: PlanFfmpegRenderer can render storyboard with imported MP4
    storage_root = studio_app["storage_root"]
    wav_path = storage_root / "audio.wav"
    save_pcm_as_wav(generate_synthetic_tone(duration_s=2.5, freq_hz=440.0), wav_path)

    asset_path = storage_root / res_data["asset"]["path"]
    work = storage_root / "work_test"
    work.mkdir(parents=True, exist_ok=True)

    spec = RenderSpec(
        scenes=[
            StoryboardRow(
                id=SCENE_2_ID,
                video_id=VIDEO_ID,
                idx=0,
                narration="Cena com MP4 importado.",
                image_prompt="Prompt detalhado da cena com vídeo importado.",
                asset_id=asset_id,
                duration_s=2.5,
            ),
        ],
        images=[asset_path],
        speech_wavs=[wav_path],
        scene_seconds=[2.5],
        cues=[],
        format=VideoFormat.short,
        music=False,
        disclosure="REC-03 Consumer Proof",
        work_dir=work,
    )
    out_mp4 = tmp_path / "final_rendered.mp4"
    PlanFfmpegRenderer(cycle=("none",)).render(spec, out_mp4)
    assert out_mp4.is_file()
    assert out_mp4.stat().st_size > 1000


def test_storyboard_workspace_has_assisted_import_panel_and_no_disabled_stub(studio_app):
    video = Video(
        id=VIDEO_ID,
        project_id=PROJECT_ID,
        topic="Vídeo de Teste",
        format=VideoFormat.short,
        status=VideoStatus.SCRIPTED,
    )
    scenes = [
        StoryboardRow(
            id=SCENE_1_ID,
            video_id=VIDEO_ID,
            idx=0,
            narration="Texto da cena um.",
            image_prompt="Laboratório com iluminação azul cinematográfica.",
            duration_s=4.0,
        )
    ]
    res = render_video_workspace(video, "cenas", scenes=scenes)
    html = res[0]

    # Must contain assisted import panel / controls
    assert 'data-assisted-import' in html
    assert 'data-scene-id' in html or f'data-sid="{SCENE_1_ID}"' in html
    assert '<input type="file"' in html
    assert 'accept="image/png,image/jpeg,image/webp,video/mp4,video/webm"' in html
    assert 'OWN_ORIGINAL' in html or 'CC0-1.0' in html

    # Stale stub message must be gone
    assert "O envio de arquivos ainda não existe no servidor" not in html
    assert "Importação real depende do backend" not in html


def test_asset_file_scoped_by_video_and_project(studio_app):
    client = _browser_client(studio_app["app"])
    png_data = _png_bytes(width=640, height=360)

    # 1. Import asset to Scene 1 of VIDEO_ID
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("scope_test.png", png_data, "image/png")},
    )
    assert resp.status_code == 200
    asset_id = resp.json()["asset"]["id"]

    # 2. Access with valid video_id scope -> 200 OK
    res_vid = client.get(f"/studio/assets/{asset_id}/file?video_id={VIDEO_ID}")
    assert res_vid.status_code == 200
    assert res_vid.headers["content-type"].startswith("image/png")
    assert res_vid.headers.get("accept-ranges") == "bytes"
    assert len(res_vid.content) > 0
    img = Image.open(io.BytesIO(res_vid.content))
    assert img.format == "PNG"

    # 3. Access with valid project_id scope alone -> 200 OK
    res_proj_only = client.get(f"/studio/assets/{asset_id}/file?project_id={PROJECT_ID}")
    assert res_proj_only.status_code == 200
    assert res_proj_only.headers["content-type"].startswith("image/png")

    # 4. Access with valid video_id and project_id -> 200 OK
    res_proj = client.get(f"/studio/assets/{asset_id}/file?video_id={VIDEO_ID}&project_id={PROJECT_ID}")
    assert res_proj.status_code == 200


def test_asset_file_unscoped_or_cross_scope_is_403(studio_app):
    client = _browser_client(studio_app["app"])
    png_data = _png_bytes()

    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("art.png", png_data, "image/png")},
    )
    assert resp.status_code == 200
    asset_id = resp.json()["asset"]["id"]

    # 1. Unscoped (no video_id, no project_id) -> 403 Forbidden
    res_unscoped = client.get(f"/studio/assets/{asset_id}/file")
    assert res_unscoped.status_code == 403

    # 2. Cross-scope video (OTHER_VIDEO_ID does not own this scene asset) -> 403 Forbidden
    res_cross = client.get(f"/studio/assets/{asset_id}/file?video_id={OTHER_VIDEO_ID}")
    assert res_cross.status_code == 403

    # 3. Cross-scope project -> 403 Forbidden
    other_pid = "b" * 32
    conn = studio_app["conn"]
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'Outro Canal') ON CONFLICT DO NOTHING", (other_pid,))
    conn.commit()
    res_cross_proj = client.get(f"/studio/assets/{asset_id}/file?project_id={other_pid}")
    assert res_cross_proj.status_code == 403

    # 4. Nonexistent asset with valid scope -> 403 Forbidden (same code as cross-scope, no existence oracle!)
    fake_aid = "f" * 32
    res_fake_asset = client.get(f"/studio/assets/{fake_aid}/file?video_id={VIDEO_ID}")
    assert res_fake_asset.status_code == 403

    # 5. Nonexistent video -> 404 Not Found
    fake_vid = "e" * 32
    res_fake = client.get(f"/studio/assets/{asset_id}/file?video_id={fake_vid}")
    assert res_fake.status_code == 404


def test_asset_file_traversal_or_nul_is_404(studio_app):
    client = _browser_client(studio_app["app"])

    # Path traversal in asset_id URL -> 404
    res_trav = client.get(f"/studio/assets/../../etc/passwd/file?video_id={VIDEO_ID}")
    assert res_trav.status_code == 404

    # NUL character in asset_id URL -> 404
    res_nul = client.get(f"/studio/assets/abc%00def/file?video_id={VIDEO_ID}")
    assert res_nul.status_code == 404


def test_asset_file_db_traversal_escape_is_404(studio_app):
    client = _browser_client(studio_app["app"])
    png_data = _png_bytes()

    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("esc_test.png", png_data, "image/png")},
    )
    assert resp.status_code == 200
    asset_id = resp.json()["asset"]["id"]

    # Normal access works
    assert client.get(f"/studio/assets/{asset_id}/file?video_id={VIDEO_ID}").status_code == 200

    # Tamper path in DB to escape root
    conn = studio_app["conn"]
    conn.execute("UPDATE studio.assets SET path = '../../etc/passwd' WHERE id = %s", (asset_id,))
    conn.commit()

    # Access is rejected with 404
    res_esc = client.get(f"/studio/assets/{asset_id}/file?video_id={VIDEO_ID}")
    assert res_esc.status_code == 404


def test_import_media_filename_traversal_and_nul_is_422(studio_app):
    client = _worker_client(studio_app["app"])
    png_data = _png_bytes()

    # Filename with NUL character -> 422
    resp_nul = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("bad\x00file.png", png_data, "image/png")},
    )
    assert resp_nul.status_code == 422

    # Filename with dot-dot traversal -> 422
    resp_dot = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("..", png_data, "image/png")},
    )
    assert resp_dot.status_code == 422


def test_import_media_crlf_content_type_is_400(studio_app):
    client = _worker_client(studio_app["app"])
    crlf_ct = "multipart/form-data; boundary=xyz\r\nInjected-Header: evil"
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        content=b"--xyz\r\nContent-Disposition: form-data; name=\"license\"\r\n\r\nCC0-1.0\r\n--xyz--",
        headers={"Content-Type": crlf_ct},
    )
    assert resp.status_code == 400


def test_import_media_text_plain_declared_is_422(studio_app):
    client = _worker_client(studio_app["app"])
    png_data = _png_bytes()

    # Sending real PNG bytes but declaring text/plain MUST NOT be silently rewritten to image/png
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("test.png", png_data, "text/plain")},
    )
    assert resp.status_code == 422


def test_reimport_without_trim_clears_stale_scene_assets_and_revokes_old_asset(studio_app):
    client = _browser_client(studio_app["app"])
    png_data = _png_bytes()

    # 1. First import Scene 1 with trim (1.5, 4.0)
    resp1 = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0", "trim_start_s": "1.5", "trim_end_s": "4.0"},
        files={"file": ("first.png", png_data, "image/png")},
    )
    assert resp1.status_code == 200
    asset_1_id = resp1.json()["asset"]["id"]

    # Verify asset 1 is accessible
    res_a1 = client.get(f"/studio/assets/{asset_1_id}/file?video_id={VIDEO_ID}")
    assert res_a1.status_code == 200

    # Verify workspace shows trim 1.5 and 4.0
    ws1 = client.get(f"/studio/panel/videos/{VIDEO_ID}/cenas")
    assert ws1.status_code == 200
    assert 'value="1.5"' in ws1.text
    assert 'value="4.0"' in ws1.text

    # 2. Re-import Scene 1 WITHOUT trim (passing expected_asset_id=asset_1_id for CAS)
    resp2 = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "OWN_ORIGINAL", "expected_asset_id": asset_1_id},
        files={"file": ("second.png", png_data, "image/png")},
    )
    assert resp2.status_code == 200
    asset_2_id = resp2.json()["asset"]["id"]
    assert asset_2_id != asset_1_id

    # Verify new asset 2 is accessible
    res_a2 = client.get(f"/studio/assets/{asset_2_id}/file?video_id={VIDEO_ID}")
    assert res_a2.status_code == 200

    # Old asset 1 access is now REVOKED (403 Forbidden)
    res_a1_revoked = client.get(f"/studio/assets/{asset_1_id}/file?video_id={VIDEO_ID}")
    assert res_a1_revoked.status_code == 403

    # Workspace reload does NOT hydrate stale trim 1.5/4.0
    ws2 = client.get(f"/studio/panel/videos/{VIDEO_ID}/cenas")
    assert ws2.status_code == 200
    assert 'data-f="trim-start" data-sid="' + SCENE_1_ID + '" value="1.5"' not in ws2.text


def test_import_media_non_finite_trim_is_422(studio_app):
    client = _worker_client(studio_app["app"])
    png_data = _png_bytes()

    # NaN in trim_start_s
    resp_nan = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0", "trim_start_s": "NaN", "trim_end_s": "4.0"},
        files={"file": ("nan.png", png_data, "image/png")},
    )
    assert resp_nan.status_code == 422

    # Inf in trim_end_s
    resp_inf = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0", "trim_start_s": "1.0", "trim_end_s": "Infinity"},
        files={"file": ("inf.png", png_data, "image/png")},
    )
    assert resp_inf.status_code == 422


def test_import_media_declared_mp4_with_png_body_is_422(studio_app):
    client = _worker_client(studio_app["app"])
    png_data = _png_bytes()

    # Declaring video/mp4 but passing PNG data -> probe fails
    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0"},
        files={"file": ("fake.mp4", png_data, "video/mp4")},
    )
    assert resp.status_code == 422


def test_import_media_malformed_json_is_422(studio_app):
    client = _worker_client(studio_app["app"])

    # Malformed JSON syntax
    resp1 = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        content=b"{invalid_json: true,",
        headers={"Content-Type": "application/json"},
    )
    assert resp1.status_code == 422

    # Non-dict JSON (array)
    resp2 = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        content=b"[1, 2, 3]",
        headers={"Content-Type": "application/json"},
    )
    assert resp2.status_code == 422


def test_import_media_invalid_source_url_is_422(studio_app):
    client = _worker_client(studio_app["app"])
    png_data = _png_bytes()

    resp = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC-BY-4.0", "author": "Criador", "source_url": "javascript:alert(1)"},
        files={"file": ("test.png", png_data, "image/png")},
    )
    assert resp.status_code == 422


def test_import_media_trim_validation_and_reimport_persists(studio_app):
    client = _worker_client(studio_app["app"])
    png_data = _png_bytes()

    # 1. Invalid non-numeric trim -> 422 (never 500)
    resp_nan = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0", "trim_start_s": "not-a-number", "trim_end_s": "2.0"},
        files={"file": ("t.png", png_data, "image/png")},
    )
    assert resp_nan.status_code == 422

    # 2. Inverted range (end <= start) -> 422
    resp_inv = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0", "trim_start_s": "3.0", "trim_end_s": "1.0"},
        files={"file": ("t.png", png_data, "image/png")},
    )
    assert resp_inv.status_code == 422

    # 3. Negative start -> 422
    resp_neg = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0", "trim_start_s": "-0.5", "trim_end_s": "2.0"},
        files={"file": ("t.png", png_data, "image/png")},
    )
    assert resp_neg.status_code == 422

    # 4. Valid trim import 1 -> 200 OK and persists in DB
    resp_ok1 = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0", "trim_start_s": "0.5", "trim_end_s": "2.5"},
        files={"file": ("t.png", png_data, "image/png")},
    )
    assert resp_ok1.status_code == 200
    aid1 = resp_ok1.json()["asset"]["id"]

    conn = studio_app["conn"]
    sa_row = conn.execute("SELECT asset_id, start_s, end_s FROM studio.scene_assets WHERE scene_id = %s", (SCENE_1_ID,)).fetchone()
    assert sa_row is not None
    assert sa_row[0] == aid1
    assert float(sa_row[1]) == 0.5
    assert float(sa_row[2]) == 2.5

    # 5. Second import on SAME scene with updated trim -> replaces cleanly without UniqueViolation!
    png_data_2 = _png_bytes(color=(50, 150, 50))
    resp_ok2 = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC0-1.0", "expected_asset_id": aid1, "trim_start_s": "1.0", "trim_end_s": "3.5"},
        files={"file": ("t2.png", png_data_2, "image/png")},
    )
    assert resp_ok2.status_code == 200
    aid2 = resp_ok2.json()["asset"]["id"]

    sa_row2 = conn.execute("SELECT asset_id, start_s, end_s FROM studio.scene_assets WHERE scene_id = %s", (SCENE_1_ID,)).fetchall()
    assert len(sa_row2) == 1
    assert sa_row2[0][0] == aid2
    assert float(sa_row2[0][1]) == 1.0
    assert float(sa_row2[0][2]) == 3.5


def test_import_media_cc_by_4_with_and_without_attribution(studio_app):
    client = _worker_client(studio_app["app"])
    png_data = _png_bytes()

    # CC-BY-4.0 without attribution or source_url -> 422
    resp_no_att = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC-BY-4.0"},
        files={"file": ("test.png", png_data, "image/png")},
    )
    assert resp_no_att.status_code == 422
    assert "attribution" in resp_no_att.json()["detail"].lower() or "source_url" in resp_no_att.json()["detail"].lower()

    # CC-BY-4.0 with attribution -> 200 OK
    resp_att = client.post(
        f"/studio/videos/{VIDEO_ID}/scenes/{SCENE_1_ID}/import-media",
        data={"license": "CC-BY-4.0", "attribution": "Artista Independente", "source_url": "https://example.com/art"},
        files={"file": ("test.png", png_data, "image/png")},
    )
    assert resp_att.status_code == 200
    assert resp_att.json()["asset"]["license"] == "CC-BY-4.0"
    assert resp_att.json()["asset"]["attribution"] == "Artista Independente"


def test_assisted_mode_workspace_has_attribution_and_source_url_inputs_and_no_mute_audio(studio_app):
    video = Video(
        id=VIDEO_ID,
        project_id=PROJECT_ID,
        topic="Vídeo de Teste",
        format=VideoFormat.short,
        status=VideoStatus.SCRIPTED,
    )
    scenes = [
        StoryboardRow(
            id=SCENE_1_ID,
            video_id=VIDEO_ID,
            idx=0,
            narration="Texto da cena um.",
            image_prompt="Laboratório azul.",
            duration_s=4.0,
        )
    ]
    html = render_video_workspace(video, "cenas", scenes=scenes)[0]
    # UI must include attribution and source_url inputs for CC-BY-4.0
    assert 'data-f="import-attribution"' in html
    assert 'data-f="import-source-url"' in html

    # mute_audio dead stub control must be completely removed from UI
    assert 'data-f="mute-audio"' not in html
    assert 'Mudo' not in html
