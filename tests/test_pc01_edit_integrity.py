"""PC-01.01 & PC-01.02 — Edit Integrity, Single-Transaction Base Replace, CAS, Concurrency & Selective Cache."""
from __future__ import annotations

import hashlib
import io
import math
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.studio.adapters.media_probe import FfmpegMediaProbe
from app.studio.adapters.postgres.editorial_repo import PostgresEditorialRepository
from app.studio.adapters.postgres.media_repo import PostgresAssetRepository
from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.api.routes import make_router
from app.studio.application.editorial import StateConflict
from app.studio.application.media import AssetRefused, ImportExternalMedia
from app.studio.application.render_cache import PlanRegeneration
from app.studio.composition.settings import Settings
from app.studio.composition.wiring import Studio
from app.studio.application.ports import RenderSpec, SceneDraft
from app.studio.domain.contracts import Asset, AssetKind, VideoFormat, VideoStatus
from app.studio.domain.render_cache import plan_graph


def _ck(label: str) -> str:
    return hashlib.sha256(f"{label}-{uuid.uuid4().hex}".encode()).hexdigest()


def _png_bytes(color: tuple[int, int, int] = (20, 80, 160), size: tuple[int, int] = (360, 640)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _mp4_bytes(tmp_path: Path, name: str = "clip.mp4", duration_s: float = 2.0, color: str = "teal") -> bytes:
    out = tmp_path / name
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=360x640:r=24:d={duration_s}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(out),
        ],
        check=True,
    )
    return out.read_bytes()


def _setup_video(dsn: str, tmp_path: Path):
    conn = psycopg.connect(dsn)
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    e_repo = PostgresEditorialRepository(connect)
    a_repo = PostgresAssetRepository(connect)

    proj = v_repo.create_project("Projeto PC01")
    video = v_repo.create_video(proj.id, "Tema PC01", VideoFormat.short)
    drafts = [
        SceneDraft(
            narration="Cena um com narração de abertura.",
            caption="Legenda cena um",
            label="Abertura",
            image_prompt="prompt visual cena um detalhado",
            claim_ids=[],
        ),
        SceneDraft(
            narration="Cena dois com narração de desenvolvimento.",
            caption="Legenda cena dois",
            label="Desenvolvimento",
            image_prompt="prompt visual cena dois detalhado",
            claim_ids=[],
        ),
    ]
    e_repo.save_and_advance(
        video.id,
        "\n".join(d.narration for d in drafts),
        drafts,
        [],
        VideoStatus.IDEA,
        VideoStatus.SCRIPTED,
    )
    scenes = e_repo.scenes(video.id)
    with psycopg.connect(dsn) as c:
        c.execute(
            "UPDATE studio.videos SET status = %s WHERE id = %s",
            (VideoStatus.ASSETS_READY.value, video.id),
        )

    studio = Studio(
        Settings(
            database_url=dsn,
            storage_root=tmp_path,
            publication_enabled=False,
            budget_guard=True,
            max_cost_video=0.0,
            max_cost_month=0.0,
        )
    )
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})
    return proj, video, scenes, studio, client, e_repo, a_repo


def _seed_overlay(client: TestClient, video_id: str, scene_id: str, asset_id: str, *, position: int,
                  start_s: float = 0.2, end_s: float = 2.0, motion: str = "zoom_in",
                  transition_kind: str = "fade", transition_duration_s: float = 0.4) -> dict:
    r = client.post(
        f"/studio/videos/{video_id}/scenes/{scene_id}/assets",
        json={
            "asset_id": asset_id,
            "position": position,
            "start_s": start_s,
            "end_s": end_s,
            "role": "overlay",
            "motion": motion,
            "transition_kind": transition_kind,
            "transition_duration_s": transition_duration_s,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_replace_base_without_and_with_trim_preserves_overlays_and_revision(conn, dsn, tmp_path):
    _proj, video, scenes, _studio, client, e_repo, a_repo = _setup_video(dsn, tmp_path)
    s0 = scenes[0]

    # Import initial base PNG
    base_png_1 = _png_bytes((10, 20, 30))
    r1 = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("base1.png", base_png_1, "image/png")},
        data={"license": "OWN_ORIGINAL"},
    )
    assert r1.status_code == 200, r1.text
    rev1 = r1.json()["edit_revision"]
    aid1 = r1.json()["asset"]["id"]
    assert rev1 == 2

    # Create 2 overlay assets (1 PNG + 1 MP4 PiP)
    ov_png = Asset(
        id=uuid.uuid4().hex, kind=AssetKind.image, cache_key=_ck("ov-png"),
        path="ov1.png", provider="import", model="manual", license="OWN_ORIGINAL",
    )
    ov_mp4 = Asset(
        id=uuid.uuid4().hex, kind=AssetKind.video, cache_key=_ck("ov-mp4"),
        path="ov2.mp4", provider="import", model="manual", license="OWN_ORIGINAL",
    )
    a_repo.add(ov_png)
    a_repo.add(ov_mp4)

    ov1 = _seed_overlay(client, video.id, s0.id, ov_png.id, position=1, start_s=0.1, end_s=1.8,
                        motion="zoom_in", transition_kind="fade", transition_duration_s=0.35)
    ov2 = _seed_overlay(client, video.id, s0.id, ov_mp4.id, position=2, start_s=0.5, end_s=2.2,
                        motion="pan_left", transition_kind="none", transition_duration_s=0.0)
    r_broll = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/broll",
        json={"enabled": True, "note": "B-roll preservado"},
    )
    assert r_broll.status_code == 200

    # Replace base WITHOUT trim
    base_png_2 = _png_bytes((40, 120, 200))
    r2 = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("base2.png", base_png_2, "image/png")},
        data={"license": "CC0-1.0", "expected_asset_id": aid1, "expected_edit_revision": "4"},
    )
    assert r2.status_code == 200, r2.text
    aid2 = r2.json()["asset"]["id"]
    rev2 = r2.json()["edit_revision"]
    assert rev2 == 5

    rows_after_no_trim = e_repo.get_scene_assets(s0.id)
    assert [r.id for r in rows_after_no_trim] == [ov1["id"], ov2["id"]]
    assert [r.role for r in rows_after_no_trim] == ["overlay", "overlay"]
    assert [r.motion for r in rows_after_no_trim] == ["zoom_in", "pan_left"]
    assert [r.transition_kind for r in rows_after_no_trim] == ["fade", "none"]

    # Replace base WITH trim on real 3s MP4
    base_mp4 = _mp4_bytes(tmp_path, "base3.mp4", duration_s=3.0)
    r3 = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("base3.mp4", base_mp4, "video/mp4")},
        data={
            "license": "OWN_ORIGINAL",
            "expected_asset_id": aid2,
            "expected_edit_revision": str(rev2),
            "trim_start_s": "0.25",
            "trim_end_s": "1.50",
        },
    )
    assert r3.status_code == 200, r3.text
    aid3 = r3.json()["asset"]["id"]
    rev3 = r3.json()["edit_revision"]
    assert rev3 == rev2 + 1

    rows_after_trim = e_repo.get_scene_assets(s0.id)
    assert len(rows_after_trim) == 3
    base_rows = [r for r in rows_after_trim if r.role == "base"]
    ov_rows = [r for r in rows_after_trim if r.role == "overlay"]
    assert len(base_rows) == 1
    assert base_rows[0].asset_id == aid3
    assert base_rows[0].start_s == pytest.approx(0.25)
    assert base_rows[0].end_s == pytest.approx(1.50)
    assert [r.id for r in ov_rows] == [ov1["id"], ov2["id"]]
    assert [r.motion for r in ov_rows] == ["zoom_in", "pan_left"]

    sc_now = next(s for s in e_repo.scenes(video.id) if s.id == s0.id)
    assert sc_now.caption == "Legenda cena um"
    assert sc_now.edit_revision == rev3


def test_position_zero_overlay_regression_no_unique_violation(conn, dsn, tmp_path):
    """P2-PC00-2: overlay at position=0 must shift cleanly via two-step offset without UniqueViolation."""
    _proj, video, scenes, _studio, client, e_repo, a_repo = _setup_video(dsn, tmp_path)
    s0 = scenes[0]

    ov_a = Asset(
        id=uuid.uuid4().hex, kind=AssetKind.image, cache_key=_ck("p0-a"),
        path="p0a.png", provider="import", model="manual", license="OWN_ORIGINAL",
    )
    ov_b = Asset(
        id=uuid.uuid4().hex, kind=AssetKind.image, cache_key=_ck("p0-b"),
        path="p0b.png", provider="import", model="manual", license="OWN_ORIGINAL",
    )
    a_repo.add(ov_a)
    a_repo.add(ov_b)

    # Seed overlays directly at position=0 and position=1 (no base row yet!)
    r_ov0 = _seed_overlay(client, video.id, s0.id, ov_a.id, position=0, start_s=0.0, end_s=1.0)
    r_ov1 = _seed_overlay(client, video.id, s0.id, ov_b.id, position=1, start_s=0.5, end_s=1.5)

    mp4 = _mp4_bytes(tmp_path, "p0_base.mp4", duration_s=2.5)
    r_imp = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("p0_base.mp4", mp4, "video/mp4")},
        data={"license": "OWN_ORIGINAL", "trim_start_s": "0.1", "trim_end_s": "1.2"},
    )
    assert r_imp.status_code == 200, r_imp.text

    rows = e_repo.get_scene_assets(s0.id)
    assert [(r.role, r.position) for r in rows] == [("base", 0), ("overlay", 1), ("overlay", 2)]
    assert [r.id for r in rows if r.role == "overlay"] == [r_ov0["id"], r_ov1["id"]]


def test_same_asset_distinct_trim_invalidates_only_affected_scene_cache(conn, dsn, tmp_path):
    _proj, video, scenes, studio, client, e_repo, _a_repo = _setup_video(dsn, tmp_path)
    s0, s1 = scenes[0], scenes[1]

    mp4 = _mp4_bytes(tmp_path, "shared.mp4", duration_s=3.0)
    png = _png_bytes((90, 90, 90))

    r_s1 = client.post(
        f"/studio/videos/{video.id}/scenes/{s1.id}/media/import",
        files={"file": ("s1.png", png, "image/png")},
        data={"license": "OWN_ORIGINAL"},
    )
    assert r_s1.status_code == 200

    # First trim on scene 0
    r_s0_a = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("s0.mp4", mp4, "video/mp4")},
        data={"license": "OWN_ORIGINAL", "trim_start_s": "0.1", "trim_end_s": "1.0"},
    )
    assert r_s0_a.status_code == 200
    aid0 = r_s0_a.json()["asset"]["id"]

    uc = studio.use_cases()
    j1 = uc.rendering.start.execute(video.id)
    loaded_scenes_1 = e_repo.scenes(video.id)
    assets_map = {sc.id: uc.media.swap.assets.get(sc.asset_id) for sc in loaded_scenes_1}
    renderer = PlanFfmpegRenderer(
        cache_root=tmp_path / "cache",
    )
    spec1 = RenderSpec(
        scenes=loaded_scenes_1,
        images=[Path(uc.media.import_media.store.root) / assets_map[sc.id].path for sc in loaded_scenes_1],
        speech_wavs=[tmp_path / "w0.wav", tmp_path / "w1.wav"],
        scene_seconds=[3.0, 3.0],
        cues=[],
        format=video.format,
        music=True,
        work_dir=tmp_path / "w1",
        voice_id="piper:pt_BR-faber-medium",
    )
    plan1 = renderer._build_plan(spec1)
    g1 = {n.node: n.fingerprint for n in plan_graph(plan1).nodes}

    # Replace scene 0 with SAME MP4 bytes but DISTINCT trim
    r_s0_b = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("s0.mp4", mp4, "video/mp4")},
        data={
            "license": "OWN_ORIGINAL",
            "expected_asset_id": aid0,
            "expected_edit_revision": str(r_s0_a.json()["edit_revision"]),
            "trim_start_s": "0.5",
            "trim_end_s": "1.8",
        },
    )
    assert r_s0_b.status_code == 200
    assert r_s0_b.json()["asset"]["id"] == aid0

    # Cancel j1 so StartRender can enqueue j2
    with psycopg.connect(dsn) as c:
        c.execute("UPDATE studio.render_jobs SET status = 'FAILED' WHERE id = %s", (j1.id,))
    j2 = uc.rendering.start.execute(video.id)
    assert j2.input_hash != j1.input_hash

    loaded_scenes_2 = e_repo.scenes(video.id)
    spec2 = RenderSpec(
        scenes=loaded_scenes_2,
        images=[Path(uc.media.import_media.store.root) / assets_map[sc.id].path for sc in loaded_scenes_2],
        speech_wavs=[tmp_path / "w0.wav", tmp_path / "w1.wav"],
        scene_seconds=[3.0, 3.0],
        cues=[],
        format=video.format,
        music=True,
        work_dir=tmp_path / "w2",
        voice_id="piper:pt_BR-faber-medium",
    )
    plan2 = renderer._build_plan(spec2)
    g2 = {n.node: n.fingerprint for n in plan_graph(plan2).nodes}

    vis_nodes_1 = {k: v for k, v in g1.items() if k.kind == "visual"}
    vis_nodes_2 = {k: v for k, v in g2.items() if k.kind == "visual"}
    s0_vis = [k for k in vis_nodes_1 if s0.id in k.key]
    s1_vis = [k for k in vis_nodes_1 if s1.id in k.key]
    assert s0_vis and s1_vis
    assert vis_nodes_1[s0_vis[0]] != vis_nodes_2[s0_vis[0]]  # affected scene invalidated
    assert vis_nodes_1[s1_vis[0]] == vis_nodes_2[s1_vis[0]]  # untouched scene cache hit!


def test_reimport_dedup_same_bytes_distinct_license(conn, dsn, tmp_path):
    _proj, video, scenes, _studio, client, _e_repo, _a_repo = _setup_video(dsn, tmp_path)
    s0 = scenes[0]
    png = _png_bytes((55, 66, 77))

    r1 = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("a.png", png, "image/png")},
        data={"license": "CC0-1.0"},
    )
    assert r1.status_code == 200
    a1 = r1.json()["asset"]

    r2 = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("a.png", png, "image/png")},
        data={
            "license": "CC-BY-4.0",
            "attribution": "Autor Teste",
            "expected_asset_id": a1["id"],
            "expected_edit_revision": str(r1.json()["edit_revision"]),
        },
    )
    assert r2.status_code == 200
    a2 = r2.json()["asset"]
    assert a2["id"] != a1["id"]
    assert a2["license"] == "CC-BY-4.0"


def test_negative_trim_validation_and_cross_project_isolation(conn, dsn, tmp_path):
    proj1, video1, scenes1, _studio, client, e_repo, a_repo = _setup_video(dsn, tmp_path)
    s0 = scenes1[0]
    mp4 = _mp4_bytes(tmp_path, "two_sec.mp4", duration_s=2.0)

    # Seed initial base + overlay
    r_init = client.post(
        f"/studio/videos/{video1.id}/scenes/{s0.id}/media/import",
        files={"file": ("init.png", _png_bytes(), "image/png")},
        data={"license": "OWN_ORIGINAL"},
    )
    assert r_init.status_code == 200
    init_aid = r_init.json()["asset"]["id"]
    init_rev = r_init.json()["edit_revision"]

    for bad_start, bad_end in [("-0.5", "1.0"), ("NaN", "1.0"), ("0.0", "inf"), ("1.5", "1.0"), ("0.0", "9.9")]:
        r_bad = client.post(
            f"/studio/videos/{video1.id}/scenes/{s0.id}/media/import",
            files={"file": ("two_sec.mp4", mp4, "video/mp4")},
            data={
                "license": "OWN_ORIGINAL",
                "expected_asset_id": init_aid,
                "expected_edit_revision": str(init_rev),
                "trim_start_s": bad_start,
                "trim_end_s": bad_end,
            },
        )
        assert r_bad.status_code == 422, f"Expected 422 for ({bad_start}, {bad_end}), got {r_bad.status_code}: {r_bad.text}"

    # Previous state untouched
    sc_after = next(s for s in e_repo.scenes(video1.id) if s.id == s0.id)
    assert sc_after.asset_id == init_aid
    assert sc_after.edit_revision == init_rev

    # Cross-project isolation on /scenes/{sid}/assets
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    proj2 = v_repo.create_project("Projeto Alheio")
    video2 = v_repo.create_video(proj2.id, "Video Alheio", VideoFormat.short)
    e_repo.save_and_advance(
        video2.id,
        "Cena alheia isolada.",
        [SceneDraft(narration="Cena alheia isolada.", caption="c", label="L", image_prompt="prompt alheio valido", claim_ids=[])],
        [],
        VideoStatus.IDEA,
        VideoStatus.SCRIPTED,
    )
    scenes2 = e_repo.scenes(video2.id)
    other_asset = Asset(
        id=uuid.uuid4().hex, kind=AssetKind.image, cache_key=_ck("other"),
        path="other.png", provider="import", model="manual", license="OWN_ORIGINAL",
    )
    a_repo.add(other_asset)
    a_repo.swap_scene_asset(video2.id, scenes2[0].id, other_asset.id, None)

    r_cross_scene = client.post(
        f"/studio/videos/{video1.id}/scenes/{scenes2[0].id}/assets",
        json={"asset_id": init_aid, "position": 1, "start_s": 0.0, "end_s": 1.0, "role": "overlay"},
    )
    assert r_cross_scene.status_code == 404

    r_cross_asset = client.post(
        f"/studio/videos/{video1.id}/scenes/{s0.id}/assets",
        json={"asset_id": other_asset.id, "position": 1, "start_s": 0.0, "end_s": 1.0, "role": "overlay"},
    )
    assert r_cross_asset.status_code == 403

    r_cross_swap = client.post(
        f"/studio/videos/{video1.id}/scenes/{s0.id}/media",
        json={"asset_id": other_asset.id},
    )
    assert r_cross_swap.status_code == 403


def test_stale_edit_revision_and_aba_race_rejected_409(conn, dsn, tmp_path):
    _proj, video, scenes, _studio, client, _e_repo, _a_repo = _setup_video(dsn, tmp_path)
    s0 = scenes[0]

    r_a = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("a.png", _png_bytes((1, 2, 3)), "image/png")},
        data={"license": "OWN_ORIGINAL"},
    )
    assert r_a.status_code == 200
    aid_a, rev_a = r_a.json()["asset"]["id"], r_a.json()["edit_revision"]

    r_b = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("b.png", _png_bytes((4, 5, 6)), "image/png")},
        data={"license": "OWN_ORIGINAL", "expected_asset_id": aid_a, "expected_edit_revision": str(rev_a)},
    )
    assert r_b.status_code == 200
    rev_b = r_b.json()["edit_revision"]

    # Swap back to A (ABA!)
    r_a2 = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media",
        json={"asset_id": aid_a, "expected_edit_revision": rev_b},
    )
    assert r_a2.status_code == 200
    assert r_a2.json()["edit_revision"] == rev_b + 1

    # Stale writer holding (aid_a, rev_a) must STILL get 409 Conflict despite asset_id == aid_a!
    r_aba = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("c.png", _png_bytes((7, 8, 9)), "image/png")},
        data={"license": "OWN_ORIGINAL", "expected_asset_id": aid_a, "expected_edit_revision": str(rev_a)},
    )
    assert r_aba.status_code == 409


def test_fault_injection_rolls_back_tx_and_protects_referenced_files(conn, dsn, tmp_path, monkeypatch):
    _proj, video, scenes, studio, client, e_repo, a_repo = _setup_video(dsn, tmp_path)
    s0 = scenes[0]

    r_init = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("init.png", _png_bytes((11, 22, 33)), "image/png")},
        data={"license": "OWN_ORIGINAL"},
    )
    assert r_init.status_code == 200
    init_aid = r_init.json()["asset"]["id"]
    init_rev = r_init.json()["edit_revision"]

    ov = Asset(
        id=uuid.uuid4().hex, kind=AssetKind.image, cache_key=_ck("fi-ov"),
        path="fi_ov.png", provider="import", model="manual", license="OWN_ORIGINAL",
    )
    a_repo.add(ov)
    ov_row = _seed_overlay(client, video.id, s0.id, ov.id, position=1)

    # Inject DB failure inside add_and_replace_scene_base_media right when touching scene_assets
    orig_connect = a_repo._connect

    class _FaultCursor:
        def __init__(self, inner):
            self._inner = inner

        def execute(self, sql, params=None):
            if "INSERT INTO studio.scene_assets" in str(sql) or "DELETE FROM studio.scene_assets" in str(sql):
                raise psycopg.OperationalError("injected DB fault mid-tx")
            return self._inner.execute(sql, params)

        def fetchone(self):
            return self._inner.fetchone()

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __enter__(self):
            self._inner.__enter__()
            return self

        def __exit__(self, *args):
            return self._inner.__exit__(*args)

    class _FaultConn:
        def __init__(self, inner):
            self._inner = inner

        def cursor(self, *args, **kwargs):
            return _FaultCursor(self._inner.cursor(*args, **kwargs))

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __enter__(self):
            self._inner.__enter__()
            return self

        def __exit__(self, *args):
            return self._inner.__exit__(*args)

    monkeypatch.setattr(a_repo, "_connect", lambda: _FaultConn(orig_connect()))

    st_uc = studio.use_cases()
    uc = ImportExternalMedia(
        videos=st_uc.media.import_media.videos,
        scripts=e_repo,
        assets=a_repo,
        store=st_uc.media.import_media.store,
        probe=FfmpegMediaProbe(),
    )
    new_png = _png_bytes((220, 10, 10))
    with pytest.raises(Exception):
        uc.execute(
            video.id,
            new_png,
            "fault.png",
            "image/png",
            "OWN_ORIGINAL",
            scene_id=s0.id,
            expected_asset_id=init_aid,
            expected_edit_revision=init_rev + 1,
            trim_start_s=0.1,
            trim_end_s=1.0,
        )

    monkeypatch.setattr(a_repo, "_connect", orig_connect)
    # Entire TX rolled back: previous asset_id, edit_revision, and overlay untouched!
    sc_after = next(s for s in e_repo.scenes(video.id) if s.id == s0.id)
    assert sc_after.asset_id == init_aid
    assert sc_after.edit_revision == init_rev + 1
    assert [r.id for r in e_repo.get_scene_assets(s0.id)] == [ov_row["id"]]

    # Verify is_path_referenced protects live file even when cache_key lookup misses
    init_asset = a_repo.get(init_aid)
    assert a_repo.is_path_referenced(init_asset.path) is True


def test_concurrent_two_connections_barrier_race(conn, dsn, tmp_path):
    _proj, video, scenes, _studio, client, e_repo, a_repo = _setup_video(dsn, tmp_path)
    s0 = scenes[0]

    r_init = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("init.png", _png_bytes((30, 30, 30)), "image/png")},
        data={"license": "OWN_ORIGINAL"},
    )
    assert r_init.status_code == 200
    init_aid = r_init.json()["asset"]["id"]
    init_rev = r_init.json()["edit_revision"]

    barrier = threading.Barrier(2)

    def _do_import(color, name):
        # Each thread uses its own TestClient / DB connection
        local_studio = Studio(
            Settings(
                database_url=dsn,
                storage_root=tmp_path,
                publication_enabled=False,
                budget_guard=True,
                max_cost_video=0.0,
                max_cost_month=0.0,
            )
        )
        local_app = FastAPI()
        local_app.include_router(make_router(local_studio.use_cases, local_studio.ping))
        local_client = TestClient(local_app, headers={"Authorization": "Bearer test-worker-token"})
        payload = _png_bytes(color)
        barrier.wait(timeout=10)
        return local_client.post(
            f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
            files={"file": (name, payload, "image/png")},
            data={
                "license": "OWN_ORIGINAL",
                "expected_asset_id": init_aid,
                "expected_edit_revision": str(init_rev),
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_do_import, (100, 10, 10), "race1.png")
        f2 = pool.submit(_do_import, (10, 100, 10), "race2.png")
        codes = sorted([f1.result(), f2.result()])

    assert codes == [200, 409]

    # Case B: import vs overlay edit (add_scene_asset) racing on the same edit_revision
    sc_now = next(s for s in e_repo.scenes(video.id) if s.id == s0.id)
    ov_asset = Asset(
        id=uuid.uuid4().hex, kind=AssetKind.image, cache_key=_ck("race-ov"),
        path="race_ov.png", provider="import", model="manual", license="OWN_ORIGINAL",
    )
    a_repo.add(ov_asset)
    barrier2 = threading.Barrier(2)

    def _race_import():
        local_studio = Studio(
            Settings(
                database_url=dsn, storage_root=tmp_path,
                publication_enabled=False, budget_guard=True, max_cost_video=0.0, max_cost_month=0.0,
            )
        )
        local_app = FastAPI()
        local_app.include_router(make_router(local_studio.use_cases, local_studio.ping))
        lc = TestClient(local_app, headers={"Authorization": "Bearer test-worker-token"})
        payload = _png_bytes((15, 15, 180))
        barrier2.wait(timeout=10)
        return lc.post(
            f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
            files={"file": ("race_b.png", payload, "image/png")},
            data={
                "license": "OWN_ORIGINAL",
                "expected_asset_id": sc_now.asset_id,
                "expected_edit_revision": str(sc_now.edit_revision),
            },
        ).status_code

    def _race_overlay():
        local_studio = Studio(
            Settings(
                database_url=dsn, storage_root=tmp_path,
                publication_enabled=False, budget_guard=True, max_cost_video=0.0, max_cost_month=0.0,
            )
        )
        local_app = FastAPI()
        local_app.include_router(make_router(local_studio.use_cases, local_studio.ping))
        lc = TestClient(local_app, headers={"Authorization": "Bearer test-worker-token"})
        barrier2.wait(timeout=10)
        return lc.post(
            f"/studio/videos/{video.id}/scenes/{s0.id}/assets",
            json={
                "asset_id": ov_asset.id,
                "position": 1,
                "start_s": 0.0,
                "end_s": 1.0,
                "role": "overlay",
                "expected_edit_revision": sc_now.edit_revision,
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        r_imp = pool.submit(_race_import)
        r_ov = pool.submit(_race_overlay)
        results = sorted([r_imp.result(), r_ov.result()])

    assert results in ([200, 409], [201, 409])

    # Case C: Empty-scene legacy race (expected_asset_id=None, omitting expected_edit_revision) on scenes[1]
    s1 = scenes[1]
    barrier3 = threading.Barrier(2)

    def _race_empty(color, name):
        local_studio = Studio(
            Settings(
                database_url=dsn, storage_root=tmp_path,
                publication_enabled=False, budget_guard=True, max_cost_video=0.0, max_cost_month=0.0,
            )
        )
        local_app = FastAPI()
        local_app.include_router(make_router(local_studio.use_cases, local_studio.ping))
        lc = TestClient(local_app, headers={"Authorization": "Bearer test-worker-token"})
        payload = _png_bytes(color)
        barrier3.wait(timeout=10)
        return lc.post(
            f"/studio/videos/{video.id}/scenes/{s1.id}/media/import",
            files={"file": (name, payload, "image/png")},
            data={"license": "OWN_ORIGINAL"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        e1 = pool.submit(_race_empty, (77, 10, 10), "empty1.png")
        e2 = pool.submit(_race_empty, (10, 77, 10), "empty2.png")
        empty_codes = sorted([e1.result(), e2.result()])

    assert empty_codes == [200, 409]


def test_restart_reload_persistence(conn, dsn, tmp_path):
    _proj, video, scenes, _studio, client, _e_repo, _a_repo = _setup_video(dsn, tmp_path)
    s0 = scenes[0]
    mp4 = _mp4_bytes(tmp_path, "persist.mp4", duration_s=2.5)
    r = client.post(
        f"/studio/videos/{video.id}/scenes/{s0.id}/media/import",
        files={"file": ("persist.mp4", mp4, "video/mp4")},
        data={"license": "OWN_ORIGINAL", "trim_start_s": "0.2", "trim_end_s": "1.4"},
    )
    assert r.status_code == 200
    expected_aid = r.json()["asset"]["id"]
    expected_rev = r.json()["edit_revision"]

    # Simulate process restart with fresh Studio instance
    restarted = Studio(
        Settings(
            database_url=dsn,
            storage_root=tmp_path,
            publication_enabled=False,
            budget_guard=True,
            max_cost_video=0.0,
            max_cost_month=0.0,
        )
    )
    r_uc = restarted.use_cases()
    loaded_scenes = r_uc.editorial.get_script.scripts.scenes(video.id)
    sc0 = next(s for s in loaded_scenes if s.id == s0.id)
    assert sc0.asset_id == expected_aid
    assert sc0.edit_revision == expected_rev
    timing = r_uc.media.scene_timing.execute(loaded_scenes)
    assert timing[s0.id] == pytest.approx((0.2, 1.4))
