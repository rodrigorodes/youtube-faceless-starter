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
    assert migrate(conn) == ["0001_init"]
    assert migrate(conn) == []


def test_failed_migration_rolls_back_and_is_not_recorded(conn, tmp_path):
    (tmp_path / "0001_broken.sql").write_text("CREATE TABLE studio.half_done(x int);\nSELECT 1/0;")
    with pytest.raises(psycopg.Error):
        migrate(conn, tmp_path)
    conn.rollback()
    assert not table_exists(conn, "half_done")
    # a transação inteira reverteu: nada aplicado e nada registrado (nem a tabela de controle sobra)
    assert not table_exists(conn, "schema_migrations") or conn.execute("SELECT count(*) FROM studio.schema_migrations").fetchone()[0] == 0
    assert migrate(conn) == ["0001_init"]  # e uma migração boa roda normalmente depois


def test_creates_all_tables(conn):
    migrate(conn)
    for t in ("projects", "videos", "scripts", "scenes", "assets", "render_jobs", "publications",
              "source_snapshots", "step_runs", "usage_ledger", "video_metrics"):
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
