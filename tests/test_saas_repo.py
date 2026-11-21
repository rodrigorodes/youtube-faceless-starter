"""F11 — repositório Postgres de tenancy/BYOK e o caminho de isolamento no schema.

Requer `STUDIO_TEST_DSN` e `STUDIO_BUDGET_TEST_PROOF_FILE` (Postgres descartável). O teste
cross-tenant roda de verdade contra o banco: a fronteira é o filtro obrigatório por organização.
"""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.saas_repo import PostgresSaasRepository  # noqa: E402
from app.studio.domain.saas import (  # noqa: E402
    ByokStatus,
    DuplicateMembership,
    DuplicateProviderKey,
    KeyAuditAction,
    MembershipStatus,
    Role,
    new_byok_key,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
ORG = "a" * 32
ORG_B = "b" * 32
USER = "1" * 32
USER_B = "2" * 32
MEMBERSHIP = "3" * 32
MEMBERSHIP_B = "4" * 32
PROJECT = "5" * 32
RAW = "synthetic-repo-value-0123456789abcdef"


def table_exists(conn, name):
    return conn.execute("SELECT to_regclass(%s)", (f"studio.{name}",)).fetchone()[0] is not None


def column_exists(conn, table, column):
    return conn.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema='studio' AND table_name=%s AND column_name=%s",
        (table, column)).fetchone() is not None


def seed_org(conn, org_id=ORG, name="Organização"):
    conn.execute("INSERT INTO studio.organizations(id, name) VALUES (%s, %s)", (org_id, name))
    conn.execute("INSERT INTO studio.workspaces(id, organization_id, name) VALUES (%s, %s, 'Produção')",
                 (uuid.uuid4().hex, org_id))
    conn.commit()


def seed_member(conn, org_id=ORG, user_id=USER, membership_id=MEMBERSHIP,
                email="owner@example.test", name="Owner", role="owner", status="active"):
    conn.execute("INSERT INTO studio.users(id, email, display_name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                 (user_id, email, name))
    conn.execute("INSERT INTO studio.memberships(id, organization_id, user_id, role, status) "
                 "VALUES (%s, %s, %s, %s, %s)", (membership_id, org_id, user_id, role, status))
    conn.commit()


@pytest.fixture()
def repo(dsn, conn):
    migrate(conn)
    return PostgresSaasRepository(lambda: psycopg.connect(dsn))


def test_migration_creates_saas_tables_and_nullable_tenant_path(conn):
    migrate(conn)
    for table in ("organizations", "workspaces", "users", "memberships", "byok_keys", "byok_key_audit"):
        assert table_exists(conn, table), table
    # O caminho está modelado; ainda não é aplicado em runtime (colunas anuláveis).
    assert column_exists(conn, "projects", "organization_id")
    assert column_exists(conn, "usage_ledger", "organization_id")
    assert column_exists(conn, "usage_ledger", "member_id")
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'sem tenant')", (PROJECT,))
    assert conn.execute("SELECT organization_id FROM studio.projects WHERE id=%s", (PROJECT,)).fetchone()[0] is None


def test_constraints_reject_invalid_tenant_rows(conn):
    migrate(conn)
    for sql, params in (
        ("INSERT INTO studio.organizations(id, name) VALUES (%s, '  ')", ("a" * 32,)),
        ("INSERT INTO studio.organizations(id, name) VALUES ('not-hex', 'x')", ()),
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(sql, params)
        conn.rollback()

    seed_org(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        seed_member(conn, role="admin")
    conn.rollback()

    seed_member(conn)
    with pytest.raises(psycopg.errors.UniqueViolation):
        seed_member(conn, membership_id="9" * 32)


def test_repository_is_scoped_by_organization_a_to_b(conn, repo):
    seed_org(conn, ORG, "Organização A")
    seed_org(conn, ORG_B, "Organização B")
    seed_member(conn)
    seed_member(conn, ORG_B, USER_B, MEMBERSHIP_B, email="b@example.test", name="Pessoa B")
    key_a = new_byok_key(key_id="6" * 32, organization_id=ORG, provider="openai", value=RAW, now=NOW)
    key_b = new_byok_key(key_id="7" * 32, organization_id=ORG_B, provider="elevenlabs",
                         value="other-synthetic-value-987654321", now=NOW)
    repo.insert_key(key_a)
    repo.insert_key(key_b)

    assert [m.display_name for m in repo.members(ORG)] == ["Owner"]
    assert [m.display_name for m in repo.members(ORG_B)] == ["Pessoa B"]
    assert [k.id for k in repo.keys(ORG)] == [key_a.id]
    assert repo.key(ORG, key_b.id) is None
    assert repo.key(ORG_B, key_a.id) is None
    assert repo.organization(ORG) == "Organização A"
    assert repo.workspace(ORG) == "Produção"


def test_repository_member_mutations_are_owner_safe_inputs_and_tenant_scoped(conn, repo):
    seed_org(conn)
    seed_org(conn, ORG_B)
    seed_member(conn)
    seed_member(conn, ORG_B, USER_B, MEMBERSHIP_B, email="b@example.test", name="Pessoa B")

    assert repo.member_by_user(ORG, USER).membership_id == MEMBERSHIP
    assert repo.member_by_user(ORG, USER_B) is None
    assert repo.owner_count(ORG) == 1
    assert repo.update_membership_role(ORG_B, MEMBERSHIP, Role.VIEWER) is False
    assert repo.update_membership_role(ORG, MEMBERSHIP, Role.EDITOR) is True
    assert repo.member(ORG, MEMBERSHIP).role is Role.EDITOR
    assert repo.delete_membership(ORG_B, MEMBERSHIP) is False


def test_duplicate_active_key_per_provider_but_revocation_frees_it(conn, repo):
    seed_org(conn)
    key = new_byok_key(key_id="6" * 32, organization_id=ORG, provider="openai", value=RAW, now=NOW)
    repo.insert_key(key)
    with pytest.raises(DuplicateProviderKey):
        repo.insert_key(new_byok_key(key_id="7" * 32, organization_id=ORG, provider="openai",
                                     value="another-synthetic-value-123456", now=NOW))
    assert repo.revoke_key(ORG, key.id, NOW) is True
    assert repo.key(ORG, key.id).status is ByokStatus.REVOKED
    assert repo.revoke_key(ORG, key.id, NOW) is False
    repo.insert_key(new_byok_key(key_id="8" * 32, organization_id=ORG, provider="openai",
                                 value="another-synthetic-value-123456", now=NOW))
    assert len(repo.keys(ORG)) == 2


def test_key_metadata_never_contains_the_secret_value_and_audit_is_written(conn, repo):
    seed_org(conn)
    seed_member(conn)
    key = new_byok_key(key_id="6" * 32, organization_id=ORG, provider="openai", value=RAW, now=NOW)
    repo.insert_key(key)
    repo.audit_key(ORG, key.id, USER, KeyAuditAction.CREATED)
    repo.audit_key(ORG, key.id, USER, KeyAuditAction.ROTATED)

    row = conn.execute("SELECT mask, fingerprint, secret_scope, secret_name FROM studio.byok_keys WHERE id=%s",
                       (key.id,)).fetchone()
    assert RAW not in repr(row)
    assert row[0] == key.mask
    actions = [r[0] for r in conn.execute(
        "SELECT action FROM studio.byok_key_audit WHERE organization_id=%s ORDER BY id", (ORG,)).fetchall()]
    assert actions == ["created", "rotated"]
    assert repo.keys(ORG)[0].mask == key.mask


def test_rotation_updates_metadata_and_keeps_id(conn, repo):
    seed_org(conn)
    key = new_byok_key(key_id="6" * 32, organization_id=ORG, provider="openai", value=RAW, now=NOW)
    repo.insert_key(key)
    newer = "rotated-synthetic-value-abcdef123456"
    assert repo.update_key_rotation(ORG, key.id, "…••••3456", "f" * 64, "openai_rotated", NOW) is True
    updated = repo.key(ORG, key.id)
    assert updated.id == key.id
    assert updated.secret_name == "openai_rotated"
    assert updated.fingerprint == "f" * 64
    assert repo.update_key_rotation(ORG_B, key.id, "…••••3456", "f" * 64, "openai_rotated", NOW) is False
    assert RAW not in repr(updated)


def test_usage_aggregation_only_counts_rows_attributed_to_the_tenant_and_member(conn, repo):
    migrate(conn)
    seed_org(conn)
    seed_org(conn, ORG_B)
    seed_member(conn)
    seed_member(conn, ORG_B, USER_B, MEMBERSHIP_B, email="b@example.test", name="Pessoa B")
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd, "
                 "organization_id, member_id) VALUES ('text', 'openai', 'gpt', 0.25, %s, %s)",
                 (ORG, USER))
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd, "
                 "organization_id, member_id) VALUES ('text', 'openai', 'gpt', 0.10, %s, %s)",
                 (ORG_B, USER_B))
    conn.commit()

    rows = repo.usage_rows(ORG)
    assert rows == [("Owner", "openai", "gpt", 0.25, None)]
    assert repo.usage_rows(ORG_B) == [("Pessoa B", "openai", "gpt", 0.1, None)]
