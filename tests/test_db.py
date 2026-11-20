import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402

V, P = "a" * 32, "b" * 32


def table_exists(conn, name):
    return conn.execute("SELECT to_regclass(%s)", (f"studio.{name}",)).fetchone()[0] is not None


def seed_video(conn, video_id=V):
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p') ON CONFLICT DO NOTHING", (P,))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'ADE 2026', 'short')", (video_id, P))
    conn.commit()


def test_migrate_applies_once(conn):
    assert migrate(conn) == ["0001_init", "0002_editorial", "0003_fact_check_version", "0004_asset_credits", "0005_license_nonblank", "0006_render", "0007_publish", "0008_publication_attempt_base", "0010_approval_render", "0011_trends"]
    assert migrate(conn) == []


def test_failed_migration_rolls_back_and_is_not_recorded(conn, tmp_path):
    (tmp_path / "0001_broken.sql").write_text("CREATE TABLE studio.half_done(x int);\nSELECT 1/0;")
    with pytest.raises(psycopg.Error):
        migrate(conn, tmp_path)
    conn.rollback()
    assert not table_exists(conn, "half_done")
    # a transação inteira reverteu: nada aplicado e nada registrado (nem a tabela de controle sobra)
    assert not table_exists(conn, "schema_migrations") or conn.execute("SELECT count(*) FROM studio.schema_migrations").fetchone()[0] == 0
    assert migrate(conn) == ["0001_init", "0002_editorial", "0003_fact_check_version", "0004_asset_credits", "0005_license_nonblank", "0006_render", "0007_publish", "0008_publication_attempt_base", "0010_approval_render", "0011_trends"]  # e uma migração boa roda normalmente depois


def test_creates_all_tables(conn):
    migrate(conn)
    for t in ("projects", "videos", "scripts", "scenes", "assets", "render_jobs", "publications",
              "source_snapshots", "step_runs", "usage_ledger", "video_metrics", "fact_checks", "trend_topics"):
        assert table_exists(conn, t), t


def test_publication_unique_per_video(conn):
    migrate(conn)
    seed_video(conn)
    conn.execute("INSERT INTO studio.publications(id, video_id) VALUES (%s, %s)", ("c" * 32, V))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO studio.publications(id, video_id) VALUES (%s, %s)", ("d" * 32, V))


@pytest.mark.parametrize("sql,params,error", [
    ("INSERT INTO studio.projects(id, name) VALUES ('x', 'y')", (), psycopg.errors.CheckViolation),
    ("INSERT INTO studio.videos(id, project_id, topic, format, status) VALUES (%s, %s, 'abc', 'short', 'NOPE')", ("e" * 32, P), psycopg.errors.CheckViolation),
    ("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd) VALUES ('s', 'p', 'm', -1)", (), psycopg.errors.CheckViolation),
    ("INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) VALUES (%s, 'image', %s, 'x', 'p', 'm', '')", ("f" * 32, "1" * 64), psycopg.errors.CheckViolation),
    ("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'abc', 'short')", ("e" * 32, "9" * 32), psycopg.errors.ForeignKeyViolation),
])
def test_constraints_reject_bad_rows(conn, sql, params, error):
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p')", (P,))
    with pytest.raises(error):
        conn.execute(sql, params)


def test_new_video_defaults_to_private_idea(conn):
    migrate(conn)
    seed_video(conn)
    assert conn.execute("SELECT status, privacy FROM studio.videos WHERE id=%s", (V,)).fetchone() == ("IDEA", "private")


def test_scene_index_and_cache_key_unique(conn):
    migrate(conn)
    seed_video(conn)
    ins = "INSERT INTO studio.scenes(id, video_id, idx, narration, image_prompt) VALUES (%s, %s, 0, 'narração', 'prompt de imagem')"
    conn.execute(ins, ("1" * 32, V))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(ins, ("2" * 32, V))


def test_fact_check_override_needs_reason_in_db(conn):
    migrate(conn)
    seed_video(conn)
    ins = "INSERT INTO studio.fact_checks(id, video_id, passed, overridden, override_reason, report) VALUES (%s, %s, true, %s, %s, '{}')"
    conn.execute(ins, ("1" * 32, V, False, None))
    conn.execute(ins, ("2" * 32, V, True, "revisado"))
    for reason in (None, "", "   "):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(ins, ("3" * 32, V, True, reason))
        conn.rollback()


def test_scene_claim_ids_and_snapshot_dedupe(conn):
    migrate(conn)
    seed_video(conn)
    conn.execute("INSERT INTO studio.scenes(id, video_id, idx, narration, image_prompt, claim_ids) VALUES (%s, %s, 0, 'narração', 'prompt de imagem', '[\"abc\"]')", ("4" * 32, V))
    snap = "INSERT INTO studio.source_snapshots(id, video_id, url, content_sha256, text) VALUES (%s, %s, 'https://x.example', %s, 't')"
    conn.execute(snap, ("5" * 32, V, "a" * 64))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(snap, ("6" * 32, V, "a" * 64))


def test_asset_license_blank_rejected_and_credits_stored(conn):
    migrate(conn)
    ins = "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license, attribution, source_url) VALUES (%s, 'image', %s, 'x', 'p', 'm', %s, %s, %s)"
    conn.execute(ins, ("1" * 32, "a" * 64, "Pexels License", "Foto de Fulano", "https://x.example"))
    for lic in ("", "   "):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(ins, ("2" * 32, "b" * 64, lic, "", ""))
        conn.rollback()
        migrate(conn)
