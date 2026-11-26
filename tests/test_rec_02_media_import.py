"""REC-02.03 & REC-02.04 — External Media Import Security, Deduplication & CAS Persistence.

Test-First (Red -> Green) suite covering:
- R06 / REC-02.03: Real ffprobe + 1-frame ffmpeg decode for MP4/WebM, Pillow verify+load+bounds for PNG/JPEG/WebP,
  coherent extensions (.mp4 vs .webm), verifiable license/provenance policy, and security negatives.
- R07 / REC-02.04: Content+scope deduplication (no filename in key, no cross-project/cross-license leak),
  real CAS expected_asset_id with StateConflict, atomic compensation, restart durability,
  2-thread Postgres CAS concurrency, and Import -> Associate -> Render consumer proof.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.studio.adapters.media_probe import FfmpegMediaProbe
from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.editorial_repo import PostgresScriptRepository
from app.studio.adapters.postgres.media_repo import PostgresAssetRepository
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.adapters.storage import FileAssetStore
from app.studio.application.editorial import StateConflict, VideoNotFound
from app.studio.application.media import AssetRefused, ImportExternalMedia, SceneNotFound
from app.studio.domain.audio_dsp import generate_synthetic_tone, save_pcm_as_wav
from app.studio.domain.contracts import AssetKind, Scene as StoryboardRow, VideoFormat
from app.studio.application.ports import RenderSpec
from conftest import verified_test_connect

PROJECT_A = "a" * 32
PROJECT_B = "b" * 32
VIDEO_A = "1" * 32
VIDEO_B = "2" * 32
SCENE_A1 = "3" * 32
SCENE_A2 = "4" * 32
SCENE_B1 = "5" * 32

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


def _make_importer(dsn: str, proof: str, storage_root: Path):
    connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731
    videos = PostgresVideoRepository(connect)
    scripts = PostgresScriptRepository(connect)
    assets = PostgresAssetRepository(connect)
    store = FileAssetStore(storage_root)
    probe = FfmpegMediaProbe()
    importer = ImportExternalMedia(videos=videos, scripts=scripts, assets=assets, store=store, probe=probe)
    return importer, videos, scripts, assets, store


@pytest.fixture
def db_env(conn, dsn, tmp_path: Path):
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'Canal A'), (%s, 'Canal B')", (PROJECT_A, PROJECT_B))
    conn.execute(
        "INSERT INTO studio.videos(id, project_id, topic, format) VALUES "
        "(%s, %s, 'Tema A', 'short'), (%s, %s, 'Tema B', 'short')",
        (VIDEO_A, PROJECT_A, VIDEO_B, PROJECT_B),
    )
    conn.execute(
        "INSERT INTO studio.scenes(id, video_id, idx, narration, image_prompt) VALUES "
        "(%s, %s, 1, 'Cena A1', 'Prompt visual da cena A1'), "
        "(%s, %s, 2, 'Cena A2', 'Prompt visual da cena A2'), "
        "(%s, %s, 1, 'Cena B1', 'Prompt visual da cena B1')",
        (SCENE_A1, VIDEO_A, SCENE_A2, VIDEO_A, SCENE_B1, VIDEO_B),
    )
    conn.commit()
    storage_root = tmp_path / "storage"
    importer, videos, scripts, assets, store = _make_importer(dsn, proof, storage_root)
    return {
        "dsn": dsn,
        "proof": proof,
        "storage_root": storage_root,
        "importer": importer,
        "videos": videos,
        "scripts": scripts,
        "assets": assets,
        "store": store,
    }


def _png_bytes(width: int = 120, height: int = 160, color=(20, 120, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(width: int = 120, height: int = 160, color=(200, 80, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _webp_bytes(width: int = 120, height: int = 160, color=(40, 190, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="WEBP")
    return buf.getvalue()


def _ffmpeg_mp4_bytes(tmp_path: Path, name: str = "sample.mp4", color: str = "red", duration_s: float = 1.0) -> bytes:
    out = tmp_path / name
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=320x240:r=24:d={duration_s}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out.read_bytes()


def _ffmpeg_webm_bytes(tmp_path: Path, name: str = "sample.webm", color: str = "blue", duration_s: float = 1.0) -> bytes:
    out = tmp_path / name
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=320x240:r=24:d={duration_s}",
        "-c:v", "libvpx", "-b:v", "200k",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out.read_bytes()


def _ffprobe_json(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# REC-02.03 (R06): Real Probe/Decode, Coherent Extensions, License & Negatives
# ---------------------------------------------------------------------------

@needs_ffmpeg
def test_rec02_03_import_real_mp4_and_webm_coherent_extensions(db_env, tmp_path: Path):
    importer = db_env["importer"]
    storage_root = db_env["storage_root"]

    mp4_bytes = _ffmpeg_mp4_bytes(tmp_path, "clip.mp4")
    webm_bytes = _ffmpeg_webm_bytes(tmp_path, "clip.webm")

    mp4_asset = importer.execute(
        video_id=VIDEO_A,
        data=mp4_bytes,
        filename="clip.mp4",
        mime="video/mp4",
        license="CC0-1.0",
    )
    assert mp4_asset.kind == AssetKind.video
    assert mp4_asset.path.endswith(".mp4")
    assert (storage_root / mp4_asset.path).is_file()

    webm_asset = importer.execute(
        video_id=VIDEO_A,
        data=webm_bytes,
        filename="clip.webm",
        mime="video/webm",
        license="OWN_ORIGINAL",
    )
    assert webm_asset.kind == AssetKind.video
    assert webm_asset.path.endswith(".webm"), f"WebM must be stored as .webm, got {webm_asset.path}"
    assert (storage_root / webm_asset.path).is_file()


def test_rec02_03_import_real_png_jpeg_webp(db_env):
    importer = db_env["importer"]
    storage_root = db_env["storage_root"]

    for fname, mime, payload in [
        ("pic.png", "image/png", _png_bytes()),
        ("pic.jpg", "image/jpeg", _jpeg_bytes()),
        ("pic.webp", "image/webp", _webp_bytes()),
    ]:
        asset = importer.execute(
            video_id=VIDEO_A,
            data=payload,
            filename=fname,
            mime=mime,
            license="CC-BY-4.0",
            attribution="Studio Creator",
        )
        assert asset.kind == AssetKind.image
        assert (storage_root / asset.path).is_file()


@needs_ffmpeg
def test_rec02_03_rejects_fake_ftyp_zeros_and_arbitrary_bytes(db_env):
    importer = db_env["importer"]

    fake_ftyp = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 64
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, fake_ftyp, "fake.mp4", "video/mp4", "CC0")

    garbage = b"this is definitely not a valid video stream at all" * 4
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, garbage, "garbage.mp4", "video/mp4", "CC0")
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, garbage, "garbage.webm", "video/webm", "CC0")


@needs_ffmpeg
def test_rec02_03_rejects_truncated_mp4_and_truncated_png(db_env, tmp_path: Path):
    importer = db_env["importer"]

    valid_mp4 = _ffmpeg_mp4_bytes(tmp_path)
    truncated_mp4 = valid_mp4[: max(32, len(valid_mp4) // 3)]
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, truncated_mp4, "trunc.mp4", "video/mp4", "CC0")

    valid_png = _png_bytes(200, 200)
    truncated_png = valid_png[: len(valid_png) // 2]
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, truncated_png, "trunc.png", "image/png", "CC0")


@needs_ffmpeg
def test_rec02_03_rejects_false_mime_and_polyglot_zip(db_env, tmp_path: Path):
    importer = db_env["importer"]

    png = _png_bytes()
    webm = _ffmpeg_webm_bytes(tmp_path)
    mp4 = _ffmpeg_mp4_bytes(tmp_path)

    # PNG declared as video/mp4
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, png, "lie.mp4", "video/mp4", "CC0")

    # WebM declared as video/mp4 (and MP4 declared as video/webm)
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, webm, "lie.mp4", "video/mp4", "CC0")
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, mp4, "lie.webm", "video/webm", "CC0")

    # ZIP masquerading as PNG / WebP
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("payload.txt", "not an image")
    zip_bytes = zbuf.getvalue()
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, zip_bytes, "poly.png", "image/png", "CC0")
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, zip_bytes, "poly.webp", "image/webp", "CC0")


def test_rec02_03_rejects_oversized_and_decompression_bomb_before_disk_write(db_env):
    importer = db_env["importer"]
    storage_root = db_env["storage_root"]

    # Oversized payload (> 100MB)
    oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (100 * 1024 * 1024 + 1)
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, oversized, "huge.png", "image/png", "CC0")

    # Decompression bomb / huge dimensions (> 25 MP)
    bomb_buf = io.BytesIO()
    Image.new("RGB", (6000, 5000), color=(0, 0, 0)).save(bomb_buf, format="PNG")
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, bomb_buf.getvalue(), "bomb.png", "image/png", "CC0")

    assert not (storage_root / "cache").exists()


def test_rec02_03_path_traversal_and_nul_byte_protection(db_env):
    importer = db_env["importer"]
    storage_root = db_env["storage_root"]
    png = _png_bytes()

    for bad_name in ("../../etc/passwd.png", "..\\evil.png", "sub/../../evil.png"):
        asset = importer.execute(VIDEO_A, png, bad_name, "image/png", "CC0")
        resolved = (storage_root / asset.path).resolve()
        assert storage_root.resolve() in resolved.parents
        assert ".." not in resolved.parts

    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, png, "evil\x00.png", "image/png", "CC0")


def test_rec02_03_license_and_provenance_policy_and_invalid_ids(db_env):
    importer = db_env["importer"]
    png = _png_bytes()

    # Unknown / arbitrary / missing license rejected
    for bad_lic in ("", "   ", "unknown", "my-random-license", "stolen-from-web", "proprietary"):
        with pytest.raises(AssetRefused):
            importer.execute(VIDEO_A, png, "a.png", "image/png", bad_lic)

    # Attribution-required license without attribution or source_url rejected
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, png, "a.png", "image/png", "CC-BY-4.0")

    # Invalid video_id / missing scene_id / cross-project scene_id rejected
    with pytest.raises(VideoNotFound):
        importer.execute("9" * 32, png, "a.png", "image/png", "CC0")
    with pytest.raises(SceneNotFound):
        importer.execute(VIDEO_A, png, "a.png", "image/png", "CC0", scene_id="9" * 32)
    with pytest.raises(SceneNotFound):
        importer.execute(VIDEO_A, png, "a.png", "image/png", "CC0", scene_id=SCENE_B1)

    # Invalid source_url schemes rejected
    for bad_url in ("file:///etc/passwd", "javascript:alert(1)", "ftp://example.com/a.png"):
        with pytest.raises(AssetRefused):
            importer.execute(VIDEO_A, png, "a.png", "image/png", "CC0", source_url=bad_url)


@needs_ffmpeg
def test_rec02_03_rejects_unsupported_video_codec_and_audio_only_mp4(db_env, tmp_path: Path):
    importer = db_env["importer"]

    # Real MP4 encoded with disallowed legacy mpeg4 codec
    mpeg4_out = tmp_path / "legacy_mpeg4.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:r=24:d=1.0",
            "-c:v", "mpeg4", str(mpeg4_out),
        ],
        check=True,
    )
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, mpeg4_out.read_bytes(), "mpeg4.mp4", "video/mp4", "CC0")

    # Real audio-only MP4 (no video stream)
    audio_out = tmp_path / "audio_only.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
            "-c:a", "aac", str(audio_out),
        ],
        check=True,
    )
    with pytest.raises(AssetRefused):
        importer.execute(VIDEO_A, audio_out.read_bytes(), "audio.mp4", "video/mp4", "CC0")


# ---------------------------------------------------------------------------
# REC-02.04 (R07): Dedup by Content+Scope, CAS, Compensation, Concurrency, Render
# ---------------------------------------------------------------------------

@needs_ffmpeg
def test_rec02_04_dedup_by_content_and_scope_no_cross_project_or_license_leak(db_env, tmp_path: Path):
    importer = db_env["importer"]
    storage_root = db_env["storage_root"]
    mp4_bytes = _ffmpeg_mp4_bytes(tmp_path)

    # Same bytes, different filenames, SAME project + SAME license -> deduplicates!
    a1 = importer.execute(VIDEO_A, mp4_bytes, "first_name.mp4", "video/mp4", "CC0-1.0")
    a2 = importer.execute(VIDEO_A, mp4_bytes, "second_name.mp4", "video/mp4", "CC0-1.0")
    assert a1.id == a2.id
    assert a1.cache_key == a2.cache_key

    # Same bytes, SAME project, DIFFERENT license -> must NOT reuse CC0-1.0 asset
    a_comm = importer.execute(
        VIDEO_A, mp4_bytes, "comm.mp4", "video/mp4", "COMMERCIAL_LICENSED", attribution="Paid Licensor"
    )
    assert a_comm.id != a1.id
    assert a_comm.cache_key != a1.cache_key
    assert a_comm.license == "COMMERCIAL_LICENSED"

    # Same bytes, DIFFERENT project -> must NOT leak Project A's asset row
    b1 = importer.execute(VIDEO_B, mp4_bytes, "first_name.mp4", "video/mp4", "CC0-1.0")
    assert b1.id != a1.id
    assert b1.cache_key != a1.cache_key

    # No orphan extra files for the deduplicated import
    mp4_files = list((storage_root / "cache").rglob("*.mp4"))
    assert len(mp4_files) == 3  # a1/a2 shared, a_comm, b1


def test_rec02_04_cas_conflict_preserves_previous_asset_and_compensates(db_env):
    importer = db_env["importer"]
    scripts = db_env["scripts"]
    storage_root = db_env["storage_root"]

    png_1 = _png_bytes(100, 100, (10, 20, 30))
    png_2 = _png_bytes(100, 100, (200, 50, 10))
    png_3 = _png_bytes(100, 100, (40, 200, 80))

    # Initial link on empty scene (expected_asset_id=None)
    asset_1 = importer.execute(VIDEO_A, png_1, "one.png", "image/png", "CC0", scene_id=SCENE_A1, expected_asset_id=None)
    assert (storage_root / asset_1.path).is_file()

    # Stale CAS (wrong expected_asset_id) MUST raise StateConflict and preserve asset_1
    with pytest.raises(StateConflict):
        importer.execute(
            VIDEO_A, png_2, "two.png", "image/png", "CC0",
            scene_id=SCENE_A1, expected_asset_id="0" * 32,
        )
    # Omitting expected_asset_id when scene already has asset_1 MUST also raise StateConflict
    with pytest.raises(StateConflict):
        importer.execute(VIDEO_A, png_2, "two.png", "image/png", "CC0", scene_id=SCENE_A1)

    scene_now = [s for s in scripts.scenes(VIDEO_A) if s.id == SCENE_A1][0]
    assert scene_now.asset_id == asset_1.id
    assert (storage_root / asset_1.path).is_file()
    # png_2 must NOT be left as an orphan file on disk
    assert len(list((storage_root / "cache").rglob("*.png"))) == 1

    # Valid CAS with expected_asset_id=asset_1.id succeeds
    asset_3 = importer.execute(
        VIDEO_A, png_3, "three.png", "image/png", "CC0",
        scene_id=SCENE_A1, expected_asset_id=asset_1.id,
    )
    scene_after = [s for s in scripts.scenes(VIDEO_A) if s.id == SCENE_A1][0]
    assert scene_after.asset_id == asset_3.id


def test_rec02_04_compensation_on_post_write_cas_race(db_env):
    """If swap_scene_asset returns False after store write (race), compensate and clean up unreferenced file/row."""
    scripts = db_env["scripts"]
    assets = db_env["assets"]
    store = db_env["store"]
    storage_root = db_env["storage_root"]

    png_1 = _png_bytes(100, 100, (11, 22, 33))
    png_race = _png_bytes(100, 100, (99, 88, 77))

    importer = db_env["importer"]
    asset_1 = importer.execute(VIDEO_A, png_1, "base.png", "image/png", "CC0", scene_id=SCENE_A1)

    class RacingAssetsProxy:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def add_and_swap_scene_asset(self, asset, video_id, scene_id, expected_asset_id):
            return asset, False  # simulate atomic rollback on concurrent CAS mismatch

        def swap_scene_asset(self, video_id, scene_id, asset_id, expected_asset_id):
            return False  # simulate concurrent modification between read and swap

    racing_importer = ImportExternalMedia(
        videos=db_env["videos"],
        scripts=scripts,
        assets=RacingAssetsProxy(assets),
        store=store,
        probe=FfmpegMediaProbe(),
    )

    with pytest.raises(StateConflict):
        racing_importer.execute(
            VIDEO_A, png_race, "race.png", "image/png", "CC0",
            scene_id=SCENE_A1, expected_asset_id=asset_1.id,
        )

    # Previous asset & file intact; orphan file & row cleaned up
    scene_now = [s for s in scripts.scenes(VIDEO_A) if s.id == SCENE_A1][0]
    assert scene_now.asset_id == asset_1.id
    assert (storage_root / asset_1.path).is_file()
    assert len(list((storage_root / "cache").rglob("*.png"))) == 1


def test_rec02_04_restart_durability_and_concurrent_cas(db_env):
    importer = db_env["importer"]
    storage_root = db_env["storage_root"]

    png_base = _png_bytes(100, 100, (5, 5, 5))
    base_asset = importer.execute(VIDEO_A, png_base, "base.png", "image/png", "CC0", scene_id=SCENE_A1)

    # Two concurrent threads racing to replace SCENE_A1 with expected_asset_id=base_asset.id
    png_t1 = _png_bytes(100, 100, (250, 0, 0))
    png_t2 = _png_bytes(100, 100, (0, 250, 0))
    barrier = threading.Barrier(2)
    results: list[tuple[str, object]] = []
    lock = threading.Lock()

    def _worker(tag: str, payload: bytes, fname: str):
        imp, *_ = _make_importer(db_env["dsn"], db_env["proof"], storage_root)
        barrier.wait(timeout=5)
        try:
            res = imp.execute(
                VIDEO_A, payload, fname, "image/png", "CC0",
                scene_id=SCENE_A1, expected_asset_id=base_asset.id,
            )
            with lock:
                results.append(("ok", res))
        except StateConflict as exc:
            with lock:
                results.append(("conflict", exc))

    t1 = threading.Thread(target=_worker, args=("t1", png_t1, "t1.png"))
    t2 = threading.Thread(target=_worker, args=("t2", png_t2, "t2.png"))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    oks = [r for kind, r in results if kind == "ok"]
    conflicts = [r for kind, r in results if kind == "conflict"]
    assert len(oks) == 1, f"Expected exactly 1 CAS winner, got {results}"
    assert len(conflicts) == 1, f"Expected exactly 1 CAS conflict, got {results}"
    winner = oks[0]

    # Restart durability: brand-new repository instances read persisted state
    _, _, fresh_scripts, fresh_assets, _ = _make_importer(db_env["dsn"], db_env["proof"], storage_root)
    persisted_scene = [s for s in fresh_scripts.scenes(VIDEO_A) if s.id == SCENE_A1][0]
    assert persisted_scene.asset_id == winner.id
    persisted_asset = fresh_assets.get(winner.id)
    assert persisted_asset is not None
    assert (storage_root / persisted_asset.path).is_file()
    # Orphan cleanup: only base_asset and winner PNG files remain on disk
    assert len(list((storage_root / "cache").rglob("*.png"))) == 2


def test_rec02_04_cas_conflict_on_shared_cache_key_preserves_existing_file_and_concurrent_same_content(db_env):
    """CAS conflict on an already-shared cache_key must NEVER delete the shared row/file,
    and concurrent same-content imports (one failing CAS, one succeeding) preserve intact state."""
    importer = db_env["importer"]
    scripts = db_env["scripts"]
    assets = db_env["assets"]
    storage_root = db_env["storage_root"]

    png_base = _png_bytes(100, 100, (12, 34, 56))
    png_shared = _png_bytes(100, 100, (210, 120, 30))

    base_asset = importer.execute(VIDEO_A, png_base, "base.png", "image/png", "CC0", scene_id=SCENE_A1)
    shared_asset = importer.execute(VIDEO_A, png_shared, "shared.png", "image/png", "CC0")
    assert (storage_root / shared_asset.path).is_file()

    # Stale CAS using the same content as shared_asset must fail WITHOUT deleting shared_asset or its file
    with pytest.raises(StateConflict):
        importer.execute(
            VIDEO_A, png_shared, "shared_again.png", "image/png", "CC0",
            scene_id=SCENE_A1, expected_asset_id="0" * 32,
        )
    assert assets.get(shared_asset.id) is not None
    assert (storage_root / shared_asset.path).is_file()

    # Now race two threads with identical NEW content (same cache_key):
    # Thread 1 targets SCENE_A1 with stale expected_asset_id (loses CAS)
    # Thread 2 targets SCENE_A2 with expected_asset_id=None (succeeds)
    png_concurrent = _png_bytes(100, 100, (77, 188, 222))
    barrier = threading.Barrier(2)
    outcome: dict[str, object] = {}

    def _loser():
        imp, *_ = _make_importer(db_env["dsn"], db_env["proof"], storage_root)
        barrier.wait(timeout=5)
        try:
            imp.execute(
                VIDEO_A, png_concurrent, "loser.png", "image/png", "CC0",
                scene_id=SCENE_A1, expected_asset_id="0" * 32,
            )
            outcome["loser"] = "unexpected_ok"
        except StateConflict:
            outcome["loser"] = "conflict"

    def _winner():
        imp, *_ = _make_importer(db_env["dsn"], db_env["proof"], storage_root)
        barrier.wait(timeout=5)
        outcome["winner"] = imp.execute(
            VIDEO_A, png_concurrent, "winner.png", "image/png", "CC0",
            scene_id=SCENE_A2, expected_asset_id=None,
        )

    t1 = threading.Thread(target=_loser)
    t2 = threading.Thread(target=_winner)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert outcome.get("loser") == "conflict"
    win_asset = outcome.get("winner")
    assert win_asset is not None
    assert (storage_root / win_asset.path).is_file()
    scene_a1 = [s for s in scripts.scenes(VIDEO_A) if s.id == SCENE_A1][0]
    scene_a2 = [s for s in scripts.scenes(VIDEO_A) if s.id == SCENE_A2][0]
    assert scene_a1.asset_id == base_asset.id
    assert scene_a2.asset_id == win_asset.id


@needs_ffmpeg
def test_rec02_04_import_associate_render_consumer_proof(db_env, tmp_path: Path):
    """End-to-end consumer proof: Import real MP4 + real PNG -> Associate to scenes -> Render via PlanFfmpegRenderer."""
    importer = db_env["importer"]
    scripts = db_env["scripts"]
    assets = db_env["assets"]
    storage_root = db_env["storage_root"]

    mp4_bytes = _ffmpeg_mp4_bytes(tmp_path, "scene1.mp4", color="green", duration_s=1.2)
    png_bytes = _png_bytes(1080, 1920, (25, 60, 180))

    a_vid = importer.execute(VIDEO_A, mp4_bytes, "scene1.mp4", "video/mp4", "CC0-1.0", scene_id=SCENE_A1)
    a_img = importer.execute(VIDEO_A, png_bytes, "scene2.png", "image/png", "OWN_ORIGINAL", scene_id=SCENE_A2)

    scenes = scripts.scenes(VIDEO_A)
    assert len(scenes) == 2
    s1_asset = assets.get(scenes[0].asset_id)
    s2_asset = assets.get(scenes[1].asset_id)
    assert s1_asset is not None and s1_asset.id == a_vid.id
    assert s2_asset is not None and s2_asset.id == a_img.id

    speech_1 = save_pcm_as_wav(generate_synthetic_tone(1.0, freq_hz=220.0, gain_db=-24.0), tmp_path / "s1.wav")
    speech_2 = save_pcm_as_wav(generate_synthetic_tone(1.0, freq_hz=330.0, gain_db=-24.0), tmp_path / "s2.wav")

    work = tmp_path / "render_work"
    work.mkdir()
    rows = [
        StoryboardRow(
            id=scenes[0].id, video_id=VIDEO_A, idx=scenes[0].idx,
            narration=scenes[0].narration, image_prompt=scenes[0].image_prompt,
            asset_id=s1_asset.id, label="",
        ),
        StoryboardRow(
            id=scenes[1].id, video_id=VIDEO_A, idx=scenes[1].idx,
            narration=scenes[1].narration, image_prompt=scenes[1].image_prompt,
            asset_id=s2_asset.id, label="",
        ),
    ]
    spec = RenderSpec(
        scenes=rows,
        images=[storage_root / s1_asset.path, storage_root / s2_asset.path],
        speech_wavs=[speech_1, speech_2],
        scene_seconds=[1.2, 1.2],
        cues=[],
        format=VideoFormat.short,
        music=False,
        disclosure="REC-02.04 Consumer Proof",
        work_dir=work,
    )
    out_mp4 = tmp_path / "final_consumer.mp4"
    PlanFfmpegRenderer(cycle=("none",)).render(spec, out_mp4)

    assert out_mp4.is_file()
    info = _ffprobe_json(out_mp4)
    vstreams = [s for s in info["streams"] if s.get("codec_type") == "video"]
    assert len(vstreams) == 1
    assert vstreams[0]["codec_name"] == "h264"
    assert int(vstreams[0]["width"]) == 1080
    assert int(vstreams[0]["height"]) == 1920
    assert float(info["format"]["duration"]) >= 2.0
