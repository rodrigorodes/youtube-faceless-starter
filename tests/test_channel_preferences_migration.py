import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))
psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate


def test_migration_0047_applies_and_creates_columns(conn):
    applied = migrate(conn)
    assert "0047_channel_preferences_and_production_mode" in applied or not applied  # se já rodou

    # Conferir colunas em channel_profiles
    cols_cp = [r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='studio' AND table_name='channel_profiles'"
    ).fetchall()]
    assert "default_mode" in cols_cp
    assert "default_format" in cols_cp

    # Conferir coluna em videos
    cols_v = [r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='studio' AND table_name='videos'"
    ).fetchall()]
    assert "production_mode" in cols_v

    # Conferir tabela de idempotência de canais
    tables = [r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='studio'"
    ).fetchall()]
    assert "channel_creation_requests" in tables


def test_migration_0047_constraints_and_defaults(conn):
    migrate(conn)

    project_id = "0" * 32
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p') ON CONFLICT DO NOTHING", (project_id,))

    # channel_profiles default values
    profile_id = "1" * 32
    conn.execute(
        "INSERT INTO studio.channel_profiles(id, project_id, name) VALUES (%s, %s, 'canal')",
        (profile_id, project_id),
    )
    conn.commit()

    row = conn.execute(
        "SELECT default_mode, default_format FROM studio.channel_profiles WHERE id = %s",
        (profile_id,),
    ).fetchone()
    assert row == ("piloto", "short")

    # invalid default_mode
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "UPDATE studio.channel_profiles SET default_mode = 'invalido' WHERE id = %s",
            (profile_id,),
        )
    conn.rollback()

    # invalid default_format
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "UPDATE studio.channel_profiles SET default_format = 'reels' WHERE id = %s",
            (profile_id,),
        )
    conn.rollback()

    # videos default production_mode
    video_id = "2" * 32
    conn.execute(
        "INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'topico', 'short')",
        (video_id, project_id),
    )
    conn.commit()

    row_v = conn.execute(
        "SELECT production_mode FROM studio.videos WHERE id = %s",
        (video_id,),
    ).fetchone()
    assert row_v == ("piloto",)

    # invalid video production_mode
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "UPDATE studio.videos SET production_mode = 'invalido' WHERE id = %s",
            (video_id,),
        )
    conn.rollback()

    # channel_creation_requests insertion and key constraint
    key = "req-123_abc.def:456"
    conn.execute(
        "INSERT INTO studio.channel_creation_requests(idempotency_key, project_id, request_hash) VALUES (%s, %s, 'hash1')",
        (key, project_id),
    )
    conn.commit()

    req_row = conn.execute(
        "SELECT idempotency_key, project_id, request_hash FROM studio.channel_creation_requests WHERE idempotency_key = %s",
        (key,),
    ).fetchone()
    assert req_row == (key, project_id, "hash1")

    # invalid idempotency_key
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO studio.channel_creation_requests(idempotency_key, project_id, request_hash) VALUES (%s, %s, 'hash2')",
            ("INVALID KEY!", project_id),
        )
    conn.rollback()
