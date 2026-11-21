"""Repositório Postgres de tenancy/BYOK (F11-01..04).

Toda consulta recebe a organização do ator e a filtra no `WHERE`: um id de outra organização
simplesmente não é encontrado (a fronteira não depende do chamador lembrar de filtrar no Python).
O valor da chave nunca é lido nem gravado aqui — só máscara, impressão e coordenada do cofre.
"""
from __future__ import annotations

from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from ...application.ports import MemberRecord
from ...domain.ids import check_id
from ...domain.saas import (
    ByokKey,
    ByokStatus,
    DuplicateMembership,
    DuplicateProviderKey,
    KeyAuditAction,
    MembershipStatus,
    OrganizationNotFound,
    Role,
)
from .editorial_repo import _Base
from .repo import _translated

_KEY_COLS = ("id, organization_id, provider, mask, fingerprint, secret_scope, secret_name, "
             "created_by, created_at, rotated_at, revoked_at, last_used_at")
_MEMBER_COLS = ("m.id AS membership_id, m.organization_id, m.user_id, u.display_name, u.email, "
                "m.role, m.status, m.created_at")


def _key(row) -> ByokKey:
    return ByokKey(
        id=row["id"],
        organization_id=row["organization_id"],
        provider=row["provider"],
        mask=row["mask"],
        fingerprint=row["fingerprint"],
        secret_scope=row["secret_scope"],
        secret_name=row["secret_name"],
        status=ByokStatus.REVOKED if row["revoked_at"] is not None else ByokStatus.ACTIVE,
        created_at=row["created_at"],
        rotated_at=row["rotated_at"],
        revoked_at=row["revoked_at"],
        last_used_at=row["last_used_at"],
        created_by=row["created_by"],
    )


def _member(row) -> MemberRecord:
    return MemberRecord(
        membership_id=row["membership_id"],
        organization_id=row["organization_id"],
        user_id=row["user_id"],
        display_name=row["display_name"],
        email=row["email"],
        role=Role(row["role"]),
        status=MembershipStatus(row["status"]),
        created_at=row["created_at"],
    )


class PostgresSaasRepository(_Base):
    # --- organização -----------------------------------------------------
    def organizations(self) -> list[tuple[str, str]]:
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, name FROM studio.organizations ORDER BY created_at, id")
            return [(r[0], r[1]) for r in cur.fetchall()]

    def organization(self, organization_id: str) -> str | None:
        org = check_id(organization_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT name FROM studio.organizations WHERE id = %s", (org,))
            row = cur.fetchone()
            return row[0] if row else None

    def workspace(self, organization_id: str) -> str | None:
        org = check_id(organization_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT name FROM studio.workspaces WHERE organization_id = %s "
                        "ORDER BY created_at, id LIMIT 1", (org,))
            row = cur.fetchone()
            return row[0] if row else None

    # --- membros ---------------------------------------------------------
    def members(self, organization_id: str) -> list[MemberRecord]:
        org = check_id(organization_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_MEMBER_COLS} FROM studio.memberships m "
                        "JOIN studio.users u ON u.id = m.user_id "
                        "WHERE m.organization_id = %s ORDER BY m.created_at, m.id", (org,))
            return [_member(row) for row in cur.fetchall()]

    def member(self, organization_id: str, membership_id: str) -> MemberRecord | None:
        org, mid = check_id(organization_id), check_id(membership_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_MEMBER_COLS} FROM studio.memberships m "
                        "JOIN studio.users u ON u.id = m.user_id "
                        "WHERE m.organization_id = %s AND m.id = %s", (org, mid))
            row = cur.fetchone()
            return _member(row) if row else None

    def member_by_user(self, organization_id: str, user_id: str) -> MemberRecord | None:
        org, uid = check_id(organization_id), check_id(user_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_MEMBER_COLS} FROM studio.memberships m "
                        "JOIN studio.users u ON u.id = m.user_id "
                        "WHERE m.organization_id = %s AND m.user_id = %s", (org, uid))
            row = cur.fetchone()
            return _member(row) if row else None

    def owner_count(self, organization_id: str) -> int:
        org = check_id(organization_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM studio.memberships "
                        "WHERE organization_id = %s AND role = 'owner' AND status = 'active'", (org,))
            return int(cur.fetchone()[0])

    def find_user(self, email: str) -> tuple[str, str] | None:
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, display_name FROM studio.users WHERE email = %s", (email,))
            row = cur.fetchone()
            return (row[0], row[1]) if row else None

    def insert_user(self, user_id: str, email: str, display_name: str) -> None:
        uid = check_id(user_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO studio.users(id, email, display_name) VALUES (%s, %s, %s)",
                        (uid, email, display_name))

    def insert_membership(self, membership_id: str, organization_id: str, user_id: str,
                          role: Role, status: MembershipStatus) -> None:
        mid, org, uid = check_id(membership_id), check_id(organization_id), check_id(user_id)
        try:
            with _translated(), self._connect() as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO studio.memberships(id, organization_id, user_id, role, status) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (mid, org, uid, Role(role).value, MembershipStatus(status).value))
        except psycopg.errors.UniqueViolation as exc:
            raise DuplicateMembership("user already belongs to the organization") from exc
        except psycopg.errors.ForeignKeyViolation as exc:
            raise OrganizationNotFound("organization or user not found") from exc

    def update_membership_role(self, organization_id: str, membership_id: str, role: Role) -> bool:
        org, mid = check_id(organization_id), check_id(membership_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE studio.memberships SET role = %s WHERE id = %s AND organization_id = %s",
                        (Role(role).value, mid, org))
            return cur.rowcount == 1

    def delete_membership(self, organization_id: str, membership_id: str) -> bool:
        org, mid = check_id(organization_id), check_id(membership_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM studio.memberships WHERE id = %s AND organization_id = %s", (mid, org))
            return cur.rowcount == 1

    # --- BYOK ------------------------------------------------------------
    def keys(self, organization_id: str) -> list[ByokKey]:
        org = check_id(organization_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_KEY_COLS} FROM studio.byok_keys WHERE organization_id = %s "
                        "ORDER BY created_at, id", (org,))
            return [_key(row) for row in cur.fetchall()]

    def key(self, organization_id: str, key_id: str) -> ByokKey | None:
        org, kid = check_id(organization_id), check_id(key_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_KEY_COLS} FROM studio.byok_keys WHERE id = %s AND organization_id = %s",
                        (kid, org))
            row = cur.fetchone()
            return _key(row) if row else None

    def insert_key(self, key: ByokKey) -> None:
        try:
            with _translated(), self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO studio.byok_keys(id, organization_id, provider, mask, fingerprint, "
                    "secret_scope, secret_name, created_by, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (check_id(key.id), check_id(key.organization_id), key.provider, key.mask,
                     key.fingerprint, key.secret_scope, key.secret_name,
                     key.created_by, key.created_at))
        except psycopg.errors.UniqueViolation as exc:
            raise DuplicateProviderKey("provider already has an active key") from exc
        except psycopg.errors.ForeignKeyViolation as exc:
            raise OrganizationNotFound("organization or user not found") from exc

    def update_key_rotation(self, organization_id: str, key_id: str, mask: str, fingerprint: str,
                            secret_name: str, rotated_at: datetime) -> bool:
        org, kid = check_id(organization_id), check_id(key_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE studio.byok_keys SET mask = %s, fingerprint = %s, secret_name = %s, "
                        "rotated_at = %s WHERE id = %s AND organization_id = %s AND revoked_at IS NULL",
                        (mask, fingerprint, secret_name, rotated_at, kid, org))
            return cur.rowcount == 1

    def revoke_key(self, organization_id: str, key_id: str, revoked_at: datetime) -> bool:
        org, kid = check_id(organization_id), check_id(key_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE studio.byok_keys SET revoked_at = %s "
                        "WHERE id = %s AND organization_id = %s AND revoked_at IS NULL",
                        (revoked_at, kid, org))
            return cur.rowcount == 1

    def mark_key_used(self, organization_id: str, key_id: str, used_at: datetime) -> None:
        org, kid = check_id(organization_id), check_id(key_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE studio.byok_keys SET last_used_at = %s "
                        "WHERE id = %s AND organization_id = %s AND revoked_at IS NULL",
                        (used_at, kid, org))

    def audit_key(self, organization_id: str, key_id: str, actor_user_id: str | None,
                  action: KeyAuditAction) -> None:
        org, kid = check_id(organization_id), check_id(key_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO studio.byok_key_audit(organization_id, key_id, actor_user_id, action) "
                        "VALUES (%s, %s, %s, %s)",
                        (org, kid, check_id(actor_user_id) if actor_user_id else None,
                         KeyAuditAction(action).value))

    # --- consumo ---------------------------------------------------------
    def usage_rows(self, organization_id: str) -> list[tuple[str | None, str, str, float, str | None]]:
        org = check_id(organization_id)
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            # O membro só é rotulado se o vínculo for da MESMA organização do lançamento.
            cur.execute(
                "SELECT u.display_name, l.provider, l.model, l.cost_usd, l.cost_confirmation_kind "
                "FROM studio.usage_ledger l "
                "LEFT JOIN studio.memberships m ON m.user_id = l.member_id AND m.organization_id = l.organization_id "
                "LEFT JOIN studio.users u ON u.id = m.user_id "
                "WHERE l.organization_id = %s ORDER BY l.id", (org,))
            return [(r[0], r[1], r[2], float(r[3]), r[4]) for r in cur.fetchall()]