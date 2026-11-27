"""PC-05.02 — Persistent SQL Asset Tags, Scoped Search/Pagination, Provenance/License Safety & Studio UI.

Test Matrix:
1. Positive CRUD & Persistence:
   - Add tag, list tags, remove tag (idempotent add and remove).
   - Tags persist across repository reconnection / process restart.
2. Search & Scoped Filtering:
   - Search by tag filter (exact tag matching).
   - Search by term (q) matching tag, filename/path, license, attribution/origin, scene label.
   - Escaped wildcard matching (% and _) proving literal matching without SQL wildcard expansion.
   - Deterministic pagination (limit, offset, total count directly in PostgreSQL).
3. Negative & Hardening:
   - Empty, whitespace, overlong (>64 chars), and illegal characters rejected (422 / AssetTagInvalid).
   - Max 20 tags per asset limit enforced (422 / AssetTagInvalid on 21st tag).
   - Cross-project tag mutation blocked (403 / AssetAccessDenied).
   - Cross-project search isolation: zero rows leaked from other projects.
4. Dedup & Provenance Integrity:
   - Identical content bytes with distinct licenses retain distinct assets and isolated tags/provenance.
5. Concurrency:
   - 2 real database connections using threading.Barrier(2) concurrently mutating overlapping tags:
     zero deadlocks, zero 500s, consistent final tag set.
6. API Endpoints:
   - Full REST verification for /projects/{pid}/assets, /channels/{cid}/assets, /videos/{vid}/assets/library.
"""
from __future__ import annotations

import hashlib
import io
import threading
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.studio.adapters.media_probe import FfmpegMediaProbe
from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.editorial_repo import PostgresEditorialRepository
from app.studio.adapters.postgres.media_repo import PostgresAssetRepository
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.api.routes import make_router
from app.studio.application.media import ImportExternalMedia, ManageAssetTags, SearchProjectAssets
from app.studio.application.ports import SceneDraft
from app.studio.composition.settings import Settings
from app.studio.composition.wiring import Studio
from app.studio.domain.asset_tags import AssetAccessDenied, AssetNotFound, AssetTagInvalid
from app.studio.domain.contracts import Asset, AssetKind, VideoFormat, VideoStatus


def _ck(label: str) -> str:
    return hashlib.sha256(f"{label}-{uuid.uuid4().hex}".encode()).hexdigest()


def _png_bytes(color: tuple[int, int, int] = (20, 80, 160)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (360, 640), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _setup_studio_harness(dsn: str, tmp_path: Path):
    with psycopg.connect(dsn) as conn:
        migrate(conn)

    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    e_repo = PostgresEditorialRepository(connect)
    a_repo = PostgresAssetRepository(connect)

    proj_a = v_repo.create_project("Canal História")
    video_a = v_repo.create_video(proj_a.id, "Tema História", VideoFormat.short)
    drafts_a = [
        SceneDraft(
            narration="Cena 1 sobre a fundação de Roma.",
            caption="Fundação de Roma",
            label="Origens",
            image_prompt="antiga roma imperial coliseu",
            claim_ids=[],
        ),
        SceneDraft(
            narration="Cena 2 sobre a expansão da República.",
            caption="Expansão da República",
            label="Expansão",
            image_prompt="senado romano tribunos debate",
            claim_ids=[],
        ),
    ]
    e_repo.save_and_advance(
        video_a.id,
        "\n".join(d.narration for d in drafts_a),
        drafts_a,
        [],
        VideoStatus.IDEA,
        VideoStatus.SCRIPTED,
    )
    scenes_a = e_repo.scenes(video_a.id)

    proj_b = v_repo.create_project("Canal Culinária")
    video_b = v_repo.create_video(proj_b.id, "Tema Receitas", VideoFormat.short)
    drafts_b = [
        SceneDraft(
            narration="Cena culinária sobre massa fresca.",
            caption="Massa Fresca",
            label="Preparo",
            image_prompt="farinha ovos bancada italiana",
            claim_ids=[],
        ),
    ]
    e_repo.save_and_advance(
        video_b.id,
        "\n".join(d.narration for d in drafts_b),
        drafts_b,
        [],
        VideoStatus.IDEA,
        VideoStatus.SCRIPTED,
    )
    scenes_b = e_repo.scenes(video_b.id)

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

    return {
        "dsn": dsn,
        "connect": connect,
        "v_repo": v_repo,
        "e_repo": e_repo,
        "a_repo": a_repo,
        "proj_a": proj_a,
        "video_a": video_a,
        "scenes_a": scenes_a,
        "proj_b": proj_b,
        "video_b": video_b,
        "scenes_b": scenes_b,
        "studio": studio,
        "client": client,
        "tmp_path": tmp_path,
    }


def _seed_asset(h: dict, *, project_id: str, video_id: str, scene_id: str,
                label: str = "img", license: str = "CC0-1.0",
                attribution: str = "Autor Teste", source_url: str = "https://example.com/asset.png",
                path: str = "storage/assets/test.png") -> Asset:
    aid = uuid.uuid4().hex
    ck = _ck(f"{project_id}-{label}")
    with h["connect"]() as conn:
        conn.execute(
            "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license, attribution, source_url, cost_usd) "
            "VALUES (%s, 'image', %s, %s, 'import', 'manual_upload', %s, %s, %s, 0.0)",
            (aid, ck, path, license, attribution, source_url),
        )
        conn.execute(
            "UPDATE studio.scenes SET asset_id = %s WHERE id = %s AND video_id = %s",
            (aid, scene_id, video_id),
        )
    return h["a_repo"].get(aid)


def test_asset_tags_crud_positive(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    asset1 = _seed_asset(h, project_id=h["proj_a"].id, video_id=h["video_a"].id, scene_id=h["scenes_a"][0].id)
    a_repo: PostgresAssetRepository = h["a_repo"]

    # 1. Add tag
    tags1 = a_repo.add_asset_tag(asset1.id, "historia", project_id=h["proj_a"].id)
    assert tags1 == ["historia"]

    # 2. Add 2nd tag (sorted deterministically)
    tags2 = a_repo.add_asset_tag(asset1.id, "computacao", project_id=h["proj_a"].id)
    assert tags2 == ["computacao", "historia"]

    # 3. Idempotent add: duplicate tag does not error or duplicate
    tags3 = a_repo.add_asset_tag(asset1.id, "historia", project_id=h["proj_a"].id)
    assert tags3 == ["computacao", "historia"]

    # 4. List tags
    listed = a_repo.list_asset_tags(asset1.id, project_id=h["proj_a"].id)
    assert listed == ["computacao", "historia"]

    # 5. Asset model loaded by get() includes tags
    loaded = a_repo.get(asset1.id)
    assert loaded is not None
    assert loaded.tags == ["computacao", "historia"]

    # 6. Remove tag
    remaining = a_repo.remove_asset_tag(asset1.id, "historia", project_id=h["proj_a"].id)
    assert remaining == ["computacao"]

    # 7. Idempotent remove: removing already-removed tag succeeds without error
    remaining2 = a_repo.remove_asset_tag(asset1.id, "historia", project_id=h["proj_a"].id)
    assert remaining2 == ["computacao"]

    # 8. Persistence across fresh repository connection / restart
    fresh_repo = PostgresAssetRepository(lambda: psycopg.connect(dsn))
    reloaded = fresh_repo.get(asset1.id)
    assert reloaded is not None
    assert reloaded.tags == ["computacao"]


def test_search_project_assets_by_tag(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    asset1 = _seed_asset(h, project_id=h["proj_a"].id, video_id=h["video_a"].id, scene_id=h["scenes_a"][0].id, label="a1")
    asset2 = _seed_asset(h, project_id=h["proj_a"].id, video_id=h["video_a"].id, scene_id=h["scenes_a"][1].id, label="a2")
    a_repo: PostgresAssetRepository = h["a_repo"]

    a_repo.add_asset_tag(asset1.id, "historia", project_id=h["proj_a"].id)
    a_repo.add_asset_tag(asset1.id, "roma", project_id=h["proj_a"].id)
    a_repo.add_asset_tag(asset2.id, "geografia", project_id=h["proj_a"].id)
    a_repo.add_asset_tag(asset2.id, "roma", project_id=h["proj_a"].id)

    # Search tag="historia" -> only asset1
    res1, total1 = a_repo.search_project_assets(project_id=h["proj_a"].id, tag="historia")
    assert total1 == 1
    assert [a.id for a in res1] == [asset1.id]
    assert res1[0].tags == ["historia", "roma"]

    # Search tag="geografia" -> only asset2
    res2, total2 = a_repo.search_project_assets(project_id=h["proj_a"].id, tag="geografia")
    assert total2 == 1
    assert [a.id for a in res2] == [asset2.id]
    assert res2[0].tags == ["geografia", "roma"]

    # Search tag="roma" -> both assets
    res3, total3 = a_repo.search_project_assets(project_id=h["proj_a"].id, tag="roma")
    assert total3 == 2
    assert {a.id for a in res3} == {asset1.id, asset2.id}

    # Search non-existent tag -> empty
    res4, total4 = a_repo.search_project_assets(project_id=h["proj_a"].id, tag="inexistente")
    assert total4 == 0
    assert res4 == []


def test_search_project_assets_by_term_q(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    asset1 = _seed_asset(
        h,
        project_id=h["proj_a"].id,
        video_id=h["video_a"].id,
        scene_id=h["scenes_a"][0].id,
        path="storage/assets/coliseu_romano.png",
        license="CC-BY-4.0",
        attribution="Museu Capitolino",
        source_url="https://museu.it/coliseu.png",
    )
    a_repo: PostgresAssetRepository = h["a_repo"]
    a_repo.add_asset_tag(asset1.id, "arqueologia", project_id=h["proj_a"].id)

    # 1. Match by tag
    res, total = a_repo.search_project_assets(project_id=h["proj_a"].id, query="arqueologia")
    assert total == 1
    assert res[0].id == asset1.id

    # 2. Match by path/filename
    res, total = a_repo.search_project_assets(project_id=h["proj_a"].id, query="coliseu_romano")
    assert total == 1
    assert res[0].id == asset1.id

    # 3. Match by license
    res, total = a_repo.search_project_assets(project_id=h["proj_a"].id, query="cc-by-4.0")
    assert total == 1
    assert res[0].id == asset1.id

    # 4. Match by attribution
    res, total = a_repo.search_project_assets(project_id=h["proj_a"].id, query="capitolino")
    assert total == 1
    assert res[0].id == asset1.id

    # 5. Match by scene label (scene 0 label is 'Origens')
    res, total = a_repo.search_project_assets(project_id=h["proj_a"].id, query="origens")
    assert total == 1
    assert res[0].id == asset1.id

    # 6. Non-matching term
    res, total = a_repo.search_project_assets(project_id=h["proj_a"].id, query="astronomia")
    assert total == 0
    assert res == []


def test_search_wildcard_escaping(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    # Asset with literal '%' in attribution
    asset_pct = _seed_asset(
        h,
        project_id=h["proj_a"].id,
        video_id=h["video_a"].id,
        scene_id=h["scenes_a"][0].id,
        attribution="Desconto 50% Especial",
        path="storage/assets/pct.png",
    )
    # Asset with '500' in attribution (would match '50%' if % were not escaped as literal!)
    asset_num = _seed_asset(
        h,
        project_id=h["proj_a"].id,
        video_id=h["video_a"].id,
        scene_id=h["scenes_a"][1].id,
        attribution="Desconto 500 Reais",
        path="storage/assets/num.png",
    )
    a_repo: PostgresAssetRepository = h["a_repo"]

    # Search '50%' -> MUST only match asset_pct, NOT asset_num!
    res, total = a_repo.search_project_assets(project_id=h["proj_a"].id, query="50%")
    assert total == 1
    assert res[0].id == asset_pct.id

    # Asset with literal '_' in path
    asset_underscore = _seed_asset(
        h,
        project_id=h["proj_a"].id,
        video_id=h["video_a"].id,
        scene_id=h["scenes_a"][0].id,
        path="storage/assets/test_file.png",
        attribution="Unico Test Underscore",
    )
    asset_anychar = _seed_asset(
        h,
        project_id=h["proj_a"].id,
        video_id=h["video_a"].id,
        scene_id=h["scenes_a"][1].id,
        path="storage/assets/testxfile.png",
        attribution="Unico Test XFile",
    )

    # Search 'test_file' -> MUST only match asset_underscore, NOT asset_anychar!
    res, total = a_repo.search_project_assets(project_id=h["proj_a"].id, query="test_file")
    assert total == 1
    assert res[0].id == asset_underscore.id


def test_search_pagination_deterministic(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    a_repo: PostgresAssetRepository = h["a_repo"]

    # Seed 12 assets in Project A attached to Scene 0
    created_ids = []
    with h["connect"]() as conn:
        for i in range(12):
            aid = f"{i:032x}"
            ck = f"c{i:063x}"
            conn.execute(
                "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license, attribution, source_url, cost_usd) "
                "VALUES (%s, 'image', %s, %s, 'import', 'test', 'CC0-1.0', %s, '', 0.0)",
                (aid, ck, f"storage/assets/{i}.png", f"Item {i:02d}"),
            )
            # Add scene_asset layer linking asset to Scene 0 of Project A
            conn.execute(
                "INSERT INTO studio.scene_assets(id, scene_id, asset_id, position, start_s, end_s, role, motion, transition_kind, transition_duration_s) "
                "VALUES (gen_random_uuid(), %s, %s, %s, 0.0, 2.0, 'overlay', 'none', 'none', 0.0)",
                (h["scenes_a"][0].id, aid, i + 10),
            )
            created_ids.append(aid)

    # Page 1: limit 5, offset 0
    page1, total1 = a_repo.search_project_assets(project_id=h["proj_a"].id, limit=5, offset=0)
    assert total1 >= 12
    assert len(page1) == 5

    # Page 2: limit 5, offset 5
    page2, total2 = a_repo.search_project_assets(project_id=h["proj_a"].id, limit=5, offset=5)
    assert total2 == total1
    assert len(page2) == 5

    # Page 3: limit 5, offset 10
    page3, total3 = a_repo.search_project_assets(project_id=h["proj_a"].id, limit=5, offset=10)
    assert total3 == total1
    assert len(page3) >= 2

    # Verify no overlaps between pages
    ids_p1 = [a.id for a in page1]
    ids_p2 = [a.id for a in page2]
    ids_p3 = [a.id for a in page3]
    assert set(ids_p1).isdisjoint(set(ids_p2))
    assert set(ids_p2).isdisjoint(set(ids_p3))
    assert set(ids_p1).isdisjoint(set(ids_p3))

    # Offset beyond total -> empty page with total count preserved
    page_out, total_out = a_repo.search_project_assets(project_id=h["proj_a"].id, limit=5, offset=1000)
    assert page_out == []
    assert total_out == total1


def test_tag_validation_and_max_limit_negative(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    asset = _seed_asset(h, project_id=h["proj_a"].id, video_id=h["video_a"].id, scene_id=h["scenes_a"][0].id)
    a_repo: PostgresAssetRepository = h["a_repo"]

    # 1. Invalid empty / whitespace
    with pytest.raises(AssetTagInvalid):
        a_repo.add_asset_tag(asset.id, "", project_id=h["proj_a"].id)
    with pytest.raises(AssetTagInvalid):
        a_repo.add_asset_tag(asset.id, "   ", project_id=h["proj_a"].id)

    # 2. Overlong tag (> 64 chars)
    with pytest.raises(AssetTagInvalid):
        a_repo.add_asset_tag(asset.id, "a" * 65, project_id=h["proj_a"].id)

    # 3. Illegal characters (control chars, spaces, special symbols, leading dash)
    for bad in ["has space", "tag!", "tag@domain", "drop;table", "-leading-dash", "tag\nnewline"]:
        with pytest.raises(AssetTagInvalid):
            a_repo.add_asset_tag(asset.id, bad, project_id=h["proj_a"].id)

    # 4. Uppercase is normalized to lowercase safely
    tags = a_repo.add_asset_tag(asset.id, "HISTORIA-BRASIL", project_id=h["proj_a"].id)
    assert "historia-brasil" in tags

    # 5. Max tags per asset limit (20)
    # Already has 1 tag ("historia-brasil"). Add 19 more up to 20:
    for i in range(1, 20):
        a_repo.add_asset_tag(asset.id, f"tag-{i:02d}", project_id=h["proj_a"].id)

    loaded = a_repo.get(asset.id)
    assert len(loaded.tags) == 20

    # 21st tag exceeds limit -> raises AssetTagInvalid
    with pytest.raises(AssetTagInvalid, match="maximum 20 tags"):
        a_repo.add_asset_tag(asset.id, "tag-overflow-21", project_id=h["proj_a"].id)

    # Re-adding an existing tag does NOT error (idempotent):
    tags_again = a_repo.add_asset_tag(asset.id, "tag-01", project_id=h["proj_a"].id)
    assert len(tags_again) == 20


def test_cross_project_isolation(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    asset_a = _seed_asset(h, project_id=h["proj_a"].id, video_id=h["video_a"].id, scene_id=h["scenes_a"][0].id, label="asset_a")
    asset_b = _seed_asset(h, project_id=h["proj_b"].id, video_id=h["video_b"].id, scene_id=h["scenes_b"][0].id, label="asset_b")
    a_repo: PostgresAssetRepository = h["a_repo"]

    # Tag assets in their respective projects
    a_repo.add_asset_tag(asset_a.id, "segredo-a", project_id=h["proj_a"].id)
    a_repo.add_asset_tag(asset_b.id, "segredo-b", project_id=h["proj_b"].id)

    # 1. Project B cannot mutate tags of Project A's asset -> raises AssetAccessDenied (403)
    with pytest.raises(AssetAccessDenied):
        a_repo.add_asset_tag(asset_a.id, "hacked", project_id=h["proj_b"].id)

    with pytest.raises(AssetAccessDenied):
        a_repo.remove_asset_tag(asset_a.id, "segredo-a", project_id=h["proj_b"].id)

    with pytest.raises(AssetAccessDenied):
        a_repo.list_asset_tags(asset_a.id, project_id=h["proj_b"].id)

    # 2. Project A cannot mutate tags of Project B's asset
    with pytest.raises(AssetAccessDenied):
        a_repo.add_asset_tag(asset_b.id, "hacked", project_id=h["proj_a"].id)

    # 3. Search in Project B returns ZERO assets from Project A (0 leaked rows!)
    res_b, total_b = a_repo.search_project_assets(project_id=h["proj_b"].id)
    b_ids = [a.id for a in res_b]
    assert asset_b.id in b_ids
    assert asset_a.id not in b_ids

    # Search with tag "segredo-a" in Project B returns 0 rows
    res_leak, total_leak = a_repo.search_project_assets(project_id=h["proj_b"].id, tag="segredo-a")
    assert total_leak == 0
    assert res_leak == []

    # 4. Unknown asset ID raises AssetNotFound
    with pytest.raises(AssetNotFound):
        a_repo.add_asset_tag(uuid.uuid4().hex, "tag", project_id=h["proj_a"].id)


def test_dedup_license_and_provenance_integrity(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    client: TestClient = h["client"]
    video_id = h["video_a"].id
    scene_id = h["scenes_a"][0].id
    png_data = _png_bytes((70, 140, 210))

    # 1. Import same content data under CC0-1.0
    r1 = client.post(
        f"/studio/videos/{video_id}/scenes/{scene_id}/media/import",
        files={"file": ("photo.png", png_data, "image/png")},
        data={"license": "CC0-1.0", "attribution": "Autor CC0", "source_url": "https://cc0.example/photo.png"},
    )
    assert r1.status_code == 200, r1.text
    aid1 = r1.json()["asset"]["id"]
    lic1 = r1.json()["asset"]["license"]

    # 2. Import same content data into Scene 1 under OWN_ORIGINAL
    scene_id_2 = h["scenes_a"][1].id
    r2 = client.post(
        f"/studio/videos/{video_id}/scenes/{scene_id_2}/media/import",
        files={"file": ("photo.png", png_data, "image/png")},
        data={"license": "OWN_ORIGINAL", "attribution": "Minha Autoria", "source_url": ""},
    )
    assert r2.status_code == 200, r2.text
    aid2 = r2.json()["asset"]["id"]
    lic2 = r2.json()["asset"]["license"]

    # Invariant: Different licenses for identical content data MUST produce distinct asset rows!
    assert aid1 != aid2
    assert lic1 == "CC0-1.0"
    assert lic2 == "OWN_ORIGINAL"

    # Add tag to aid1: does NOT affect aid2
    client.post(f"/studio/projects/{h['proj_a'].id}/assets/{aid1}/tags", json={"tag": "public-domain"})
    tags1 = client.get(f"/studio/projects/{h['proj_a'].id}/assets/{aid1}/tags").json()["tags"]
    tags2 = client.get(f"/studio/projects/{h['proj_a'].id}/assets/{aid2}/tags").json()["tags"]

    assert "public-domain" in tags1
    assert "public-domain" not in tags2


def test_concurrency_barrier(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    asset = _seed_asset(h, project_id=h["proj_a"].id, video_id=h["video_a"].id, scene_id=h["scenes_a"][0].id)
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def worker_1():
        try:
            repo = PostgresAssetRepository(lambda: psycopg.connect(dsn))
            barrier.wait(timeout=10)
            for tg in ["alpha", "beta", "gamma", "shared"]:
                repo.add_asset_tag(asset.id, tg, project_id=h["proj_a"].id)
            repo.remove_asset_tag(asset.id, "alpha", project_id=h["proj_a"].id)
        except Exception as exc:
            errors.append(exc)

    def worker_2():
        try:
            repo = PostgresAssetRepository(lambda: psycopg.connect(dsn))
            barrier.wait(timeout=10)
            for tg in ["delta", "shared", "epsilon"]:
                repo.add_asset_tag(asset.id, tg, project_id=h["proj_a"].id)
            repo.remove_asset_tag(asset.id, "delta", project_id=h["proj_a"].id)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=worker_1)
    t2 = threading.Thread(target=worker_2)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert errors == [], f"Concurrency errors encountered: {errors}"

    # Final tag set check
    final_tags = h["a_repo"].list_asset_tags(asset.id, project_id=h["proj_a"].id)
    assert "shared" in final_tags
    assert "beta" in final_tags
    assert "gamma" in final_tags
    assert "epsilon" in final_tags
    assert "alpha" not in final_tags
    assert "delta" not in final_tags


def test_api_rest_endpoints(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    client: TestClient = h["client"]
    asset = _seed_asset(h, project_id=h["proj_a"].id, video_id=h["video_a"].id, scene_id=h["scenes_a"][0].id)
    pid = h["proj_a"].id
    vid = h["video_a"].id

    # 1. POST /projects/{pid}/assets/{aid}/tags
    r_add = client.post(f"/studio/projects/{pid}/assets/{asset.id}/tags", json={"tag": "historia"})
    assert r_add.status_code == 200, r_add.text
    assert r_add.json()["ok"] is True
    assert "historia" in r_add.json()["tags"]

    # 2. GET /projects/{pid}/assets/{aid}/tags
    r_get_tags = client.get(f"/studio/projects/{pid}/assets/{asset.id}/tags")
    assert r_get_tags.status_code == 200
    assert r_get_tags.json()["tags"] == ["historia"]

    # 3. GET /projects/{pid}/assets
    r_list = client.get(f"/studio/projects/{pid}/assets?tag=historia")
    assert r_list.status_code == 200
    data = r_list.json()
    assert data["total"] >= 1
    assert any(a["id"] == asset.id for a in data["assets"])
    # Verify backward-compatible fields: origin, provenance, license, tags
    matched = next(a for a in data["assets"] if a["id"] == asset.id)
    assert matched["license"] == "CC0-1.0"
    assert "origin" in matched
    assert "provenance" in matched
    assert matched["tags"] == ["historia"]

    # 4. DELETE /projects/{pid}/assets/{aid}/tags/{tag}
    r_del = client.delete(f"/studio/projects/{pid}/assets/{asset.id}/tags/historia")
    assert r_del.status_code == 200
    assert "historia" not in r_del.json()["tags"]

    # 5. GET /videos/{vid}/assets/library
    r_vid_lib = client.get(f"/studio/videos/{vid}/assets/library")
    assert r_vid_lib.status_code == 200
    assert r_vid_lib.json()["project_id"] == pid

    # 6. POST /videos/{vid}/assets/{aid}/tags
    r_vid_tag = client.post(f"/studio/videos/{vid}/assets/{asset.id}/tags", json={"tag": "video-tag"})
    assert r_vid_tag.status_code == 200
    assert "video-tag" in r_vid_tag.json()["tags"]

    # 7. DELETE /videos/{vid}/assets/{aid}/tags/{tag}
    r_vid_untag = client.delete(f"/studio/videos/{vid}/assets/{asset.id}/tags/video-tag")
    assert r_vid_untag.status_code == 200
    assert "video-tag" not in r_vid_untag.json()["tags"]

    # 8. Negative: invalid tag (e.g. empty or illegal chars) -> 422
    r_bad_tag = client.post(f"/studio/projects/{pid}/assets/{asset.id}/tags", json={"tag": "bad@char!"})
    assert r_bad_tag.status_code == 422

    # 9. Negative: cross-project mutation -> 403
    r_cross = client.post(f"/studio/projects/{h['proj_b'].id}/assets/{asset.id}/tags", json={"tag": "hack"})
    assert r_cross.status_code == 403


def test_channel_profile_assets_endpoints(dsn: str, tmp_path: Path):
    h = _setup_studio_harness(dsn, tmp_path)
    client: TestClient = h["client"]
    connect = h["connect"]
    from app.studio.adapters.postgres.channel_repo import PostgresChannelProfileRepository
    c_repo = PostgresChannelProfileRepository(connect)

    pid = h["proj_a"].id
    channel = c_repo.create(pid, "Canal História Oficial")
    assert channel.id != pid

    asset = _seed_asset(h, project_id=pid, video_id=h["video_a"].id, scene_id=h["scenes_a"][0].id)

    # GET /channels/{cid}/assets
    r_chan_list = client.get(f"/studio/channels/{channel.id}/assets")
    assert r_chan_list.status_code == 200, r_chan_list.text
    data = r_chan_list.json()
    assert any(a["id"] == asset.id for a in data["assets"])

    # POST /channels/{cid}/assets/{aid}/tags
    r_chan_tag = client.post(f"/studio/channels/{channel.id}/assets/{asset.id}/tags", json={"tag": "canal-historia"})
    assert r_chan_tag.status_code == 200, r_chan_tag.text
    assert "canal-historia" in r_chan_tag.json()["tags"]

    # GET /channels/{cid}/assets/{aid}/tags
    r_chan_get_tags = client.get(f"/studio/channels/{channel.id}/assets/{asset.id}/tags")
    assert r_chan_get_tags.status_code == 200, r_chan_get_tags.text
    assert "canal-historia" in r_chan_get_tags.json()["tags"]

    # GET /videos/{vid}/assets/{aid}/tags
    r_vid_get_tags = client.get(f"/studio/videos/{h['video_a'].id}/assets/{asset.id}/tags")
    assert r_vid_get_tags.status_code == 200, r_vid_get_tags.text
    assert "canal-historia" in r_vid_get_tags.json()["tags"]

    # DELETE /channels/{cid}/assets/{aid}/tags/{tag}
    r_chan_untag = client.delete(f"/studio/channels/{channel.id}/assets/{asset.id}/tags/canal-historia")
    assert r_chan_untag.status_code == 200, r_chan_untag.text
    assert "canal-historia" not in r_chan_untag.json()["tags"]


def test_shared_asset_cross_project_tag_isolation(dsn: str, tmp_path: Path):
    """P1-PC0502-1: Prove that two projects linking the exact same asset_id
    do not leak tags across projects, and Project B cannot delete Project A's tags.
    """
    h = _setup_studio_harness(dsn, tmp_path)
    a_repo: PostgresAssetRepository = h["a_repo"]
    pid_a = h["proj_a"].id
    pid_b = h["proj_b"].id
    vid_a = h["video_a"].id
    vid_b = h["video_b"].id

    # Create an asset linked to BOTH scenes in video A and video B
    asset = _seed_asset(h, project_id=pid_a, video_id=vid_a, scene_id=h["scenes_a"][0].id)
    # Link the same asset to video B scene
    with h["connect"]() as conn:
        conn.execute("UPDATE studio.scenes SET asset_id = %s WHERE id = %s", (asset.id, h["scenes_b"][0].id))

    # Project A adds tag "segredo-cliente-a"
    a_repo.add_asset_tag(asset.id, "segredo-cliente-a", project_id=pid_a)

    # Project B adds tag "publico-cliente-b"
    a_repo.add_asset_tag(asset.id, "publico-cliente-b", project_id=pid_b)

    # Verify Project A lists ONLY Project A tags
    tags_a = a_repo.list_asset_tags(asset.id, project_id=pid_a)
    assert tags_a == ["segredo-cliente-a"]

    # Verify Project B lists ONLY Project B tags
    tags_b = a_repo.list_asset_tags(asset.id, project_id=pid_b)
    assert tags_b == ["publico-cliente-b"]

    # Search in Project B for Project A's tag must return 0 results
    assets_b, total_b = a_repo.search_project_assets(project_id=pid_b, tag="segredo-cliente-a")
    assert total_b == 0
    assert len(assets_b) == 0

    # Search in Project A for Project A's tag returns 1 result
    assets_a, total_a = a_repo.search_project_assets(project_id=pid_a, tag="segredo-cliente-a")
    assert total_a >= 1
    assert any(a.id == asset.id for a in assets_a)

    # Project B attempts to remove "segredo-cliente-a" with project_id=pid_b
    a_repo.remove_asset_tag(asset.id, "segredo-cliente-a", project_id=pid_b)

    # Project A's tag MUST STILL EXIST
    tags_a_after = a_repo.list_asset_tags(asset.id, project_id=pid_a)
    assert "segredo-cliente-a" in tags_a_after
