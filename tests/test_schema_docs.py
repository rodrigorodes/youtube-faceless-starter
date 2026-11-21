"""O modelo de dados e o DDL gerados não podem divergir do código (snapshot versionado).

O DDL é verificado **offline** (é a concatenação das migrações). O modelo exige banco,
porque é introspecção — logo aquele teste é pulado sem `STUDIO_TEST_DSN`, como o resto
da suíte de persistência.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))
sys.path.insert(0, str(ROOT / "scripts"))

import export_schema  # noqa: E402


def test_committed_ddl_matches_migrations():
    """O DDL commitado é exatamente as migrações, verbatim e em ordem."""
    content = export_schema.render_ddl()
    assert (ROOT / export_schema.DDL_REL).read_text(encoding="utf-8") == content, (
        f"{export_schema.DDL_REL} desatualizado: rode scripts/export_schema.py --build"
    )


def test_ddl_contains_every_migration_verbatim():
    ddl = export_schema.render_ddl()
    for path in export_schema.migration_files():
        body = path.read_text(encoding="utf-8").rstrip("\n")
        assert body in ddl, f"migração {path.name} não está no DDL"


def test_committed_model_matches_database(conn):
    """O modelo commitado é o que o banco realmente tem depois das migrações."""
    pytest.importorskip("psycopg")
    from app.studio.adapters.postgres.db import migrate  # noqa: E402

    migrate(conn)
    conn.commit()
    model = export_schema.introspect(conn)
    doc = export_schema.render_doc(model)
    assert (ROOT / export_schema.DOC_REL).read_text(encoding="utf-8") == doc, (
        f"{export_schema.DOC_REL} desatualizado: rode scripts/export_schema.py --build"
    )


def test_check_mode_detects_drift(tmp_path):
    assert export_schema.main(check=True, root=tmp_path) == 1
