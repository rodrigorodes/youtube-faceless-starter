"""Migração de constraints de pilares do perfil de canal: banco novo e retrofit da 0016 antiga."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import MIGRATIONS_DIR, migrate  # noqa: E402

PROJECT_A = "a" * 32
PROJECT_B = "b" * 32
PROJECT_C = "c" * 32


def constraint_defs(conn) -> dict[str, str]:
    rows = conn.execute(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'studio.channel_profiles'::regclass",
    ).fetchall()
    return {name: definition for name, definition in rows}


def seed_project(conn, project_id: str) -> None:
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p') ON CONFLICT DO NOTHING", (project_id,))


def insert_profile(conn, profile_id: str, project_id: str, pillars: list) -> None:
    conn.execute(
        "INSERT INTO studio.channel_profiles(id, project_id, name, pillars) VALUES (%s, %s, 'canal', %s)",
        (profile_id, project_id, pillars),
    )


def assert_pillars_guarded(conn) -> None:
    """20 pilares aceitos; 21 e elemento NULL recusados pelo banco."""
    seed_project(conn, PROJECT_A)
    insert_profile(conn, "1" * 32, PROJECT_A, [f"p{i}" for i in range(20)])
    conn.commit()

    seed_project(conn, PROJECT_B)
    conn.commit()
    with pytest.raises(psycopg.errors.CheckViolation):
        insert_profile(conn, "2" * 32, PROJECT_B, [f"p{i}" for i in range(21)])
    conn.rollback()

    seed_project(conn, PROJECT_C)
    conn.commit()
    with pytest.raises(psycopg.errors.CheckViolation):
        insert_profile(conn, "3" * 32, PROJECT_C, [None, "piloto"])
    conn.rollback()


def test_fresh_install_has_single_cardinality_check_and_null_guard(conn):
    migrate(conn)

    defs = constraint_defs(conn)
    cardinality = [name for name, definition in defs.items() if "cardinality(pillars)" in definition]
    null_guards = [name for name, definition in defs.items() if "array_position(pillars" in definition]

    # uma única constraint de cardinalidade, mesmo com a 0016 nova já criando o CHECK
    assert cardinality == ["channel_profiles_pillars_check"]
    assert null_guards == ["channel_profiles_pillars_not_null_check"]
    assert_pillars_guarded(conn)


def test_retrofit_from_old_0016_creates_checks(conn, tmp_path):
    # reconstrói um banco que aplicou a 0016 ANTIGA (sem o CHECK) e registrou a versão
    for path in MIGRATIONS_DIR.glob("*.sql"):
        if path.name[:4] <= "0015":
            (tmp_path / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    old_0016 = (MIGRATIONS_DIR / "0016_channel_profiles.sql").read_text(encoding="utf-8")
    old_0016 = old_0016.replace(" CHECK (cardinality(pillars) <= 20)", "")
    assert "cardinality(pillars)" not in old_0016
    (tmp_path / "0016_channel_profiles.sql").write_text(old_0016, encoding="utf-8")

    applied = migrate(conn, tmp_path)
    assert applied[-1] == "0016_channel_profiles"
    assert "channel_profiles_pillars_check" not in constraint_defs(conn)

    # a falha original: o banco antigo aceitava mais de 20 pilares
    seed_project(conn, PROJECT_A)
    insert_profile(conn, "4" * 32, PROJECT_A, [f"p{i}" for i in range(21)])
    conn.rollback()

    # a árvore nova pula a 0016 (já registrada) e a migração aditiva cria o CHECK
    applied = migrate(conn)
    assert any(version.endswith("_channel_pillars_constraints") for version in applied)
    assert "0016_channel_profiles" not in applied
    assert_pillars_guarded(conn)