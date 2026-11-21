"""Organização, papéis e BYOK (F11-01/02/04) — regras puras, sem I/O.

O produto atual é mono-usuário: este módulo modela o caminho de tenancy e autorização para que
o runtime possa adotá-lo sem reescrever a regra. Nada aqui toca banco, cofre, mídia ou SDK.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

_SCOPE = re.compile(r"^[A-Za-z0-9._:-]+$")
_PROVIDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SECRET_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SaasError(ValueError):
    """Erro de domínio com mensagem genérica (nunca inclui valor de segredo)."""


class UnknownRole(SaasError):
    pass


class AuthorizationDenied(SaasError):
    pass


class CrossTenantAccess(SaasError):
    pass


class MembershipInvalid(SaasError):
    pass


class MembershipNotFound(MembershipInvalid):
    pass


class OrganizationNotFound(SaasError):
    pass


class LastOwnerRequired(MembershipInvalid):
    pass


class DuplicateMembership(MembershipInvalid):
    pass


class KeyInvalid(SaasError):
    pass


class KeyNotFound(SaasError):
    pass


class KeyRevoked(SaasError):
    pass


class DuplicateProviderKey(SaasError):
    pass


class Role(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class MembershipStatus(str, Enum):
    ACTIVE = "active"
    INVITED = "invited"


class Permission(str, Enum):
    VIEW = "view"
    VIEW_COSTS = "view_costs"
    CREATE_VIDEO = "create_video"
    EDIT_VIDEO = "edit_video"
    APPROVE_SCRIPT = "approve_script"
    APPROVE_PREVIEW = "approve_preview"
    PUBLISH = "publish"
    CONFIGURE_PROVIDERS = "configure_providers"
    USE_PROVIDER = "use_provider"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_KEYS = "manage_keys"


_READ = frozenset({Permission.VIEW, Permission.VIEW_COSTS})
_EDITOR = _READ | frozenset({
    Permission.CREATE_VIDEO,
    Permission.EDIT_VIDEO,
    Permission.CONFIGURE_PROVIDERS,
    Permission.USE_PROVIDER,
    Permission.PUBLISH,
})
_REVIEWER = _READ | frozenset({Permission.APPROVE_SCRIPT, Permission.APPROVE_PREVIEW})

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.EDITOR: frozenset(_EDITOR),
    Role.REVIEWER: frozenset(_REVIEWER),
    Role.VIEWER: frozenset(_READ),
}

ROLE_DESCRIPTIONS: dict[Role, str] = {
    Role.OWNER: "Administra organização, membros, chaves e orçamento. Único papel que altera papéis.",
    Role.EDITOR: "Cria e edita vídeos, canais e configuração de provider. Não gerencia membros nem chaves.",
    Role.REVIEWER: "Aprova roteiro e preview e recusa. Não publica nem edita configuração.",
    Role.VIEWER: "Só leitura: acompanha estado, custos e relatórios.",
}


@dataclass(frozen=True)
class Membership:
    id: str
    organization_id: str
    user_id: str
    role: Role
    status: MembershipStatus = MembershipStatus.ACTIVE
    created_at: datetime | None = None


def role_from(value: Role | str | None) -> Role:
    if isinstance(value, Role):
        return value
    if isinstance(value, str):
        try:
            return Role(value.strip().lower())
        except ValueError:
            pass
    raise UnknownRole("unknown role")


def can(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role_from(role)]


def require(role: Role, permission: Permission) -> None:
    """Falha sem citar papel nem permissão — a mensagem não vira oráculo de autorização."""
    if not can(role, permission):
        raise AuthorizationDenied("operation not permitted for this membership")


def assert_same_tenant(scope_organization_id: str, resource_organization_id: str | None) -> str:
    if not resource_organization_id or resource_organization_id != scope_organization_id:
        raise CrossTenantAccess("resource belongs to another organization")
    return resource_organization_id


def ensure_owner_remains(current_role: Role, new_role: Role | None, owner_count: int) -> None:
    """Troca de papel ou remoção não pode zerar os owners da organização."""
    current_role = role_from(current_role)
    new_role = role_from(new_role) if new_role is not None else None
    if current_role is not Role.OWNER or new_role is Role.OWNER:
        return
    if owner_count <= 1:
        raise LastOwnerRequired("the organization must keep at least one owner")


def normalize_email(value: str) -> str:
    if not isinstance(value, str):
        raise MembershipInvalid("invalid e-mail")
    email = value.strip().lower()
    if len(email) > 320 or not _EMAIL.match(email):
        raise MembershipInvalid("invalid e-mail")
    return email


def validate_provider(value: str) -> str:
    if not isinstance(value, str) or not _PROVIDER.match(value):
        raise KeyInvalid("invalid provider")
    return value


def validate_byok_value(value: str) -> str:
    """Chave do cliente: sem espaços/controle, 8..512 caracteres. Nunca ecoa o valor."""
    if not isinstance(value, str):
        raise KeyInvalid("invalid key value")
    if value != value.strip() or not 8 <= len(value) <= 512:
        raise KeyInvalid("invalid key value")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise KeyInvalid("invalid key value")
    return value


def mask_secret(value: str) -> str:
    """Máscara para UI: no máximo os 4 últimos caracteres; valores curtos ficam inteiros mascarados."""
    value = value if isinstance(value, str) else ""
    if len(value) <= 12:
        return "••••••••"
    return f"…••••{value[-4:]}"


def fingerprint(value: str) -> str:
    """Impressão sha256 da chave: identifica rotação sem guardar o valor."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def secret_scope(organization_id: str) -> str:
    if not isinstance(organization_id, str) or not _SCOPE.match(organization_id) or ".." in organization_id:
        raise KeyInvalid("invalid organization")
    return f"byok:{organization_id}"


def secret_name(provider: str, key_id: str) -> str:
    name = f"{provider}_{key_id}"
    if not _SECRET_NAME.match(name):
        raise KeyInvalid("invalid secret name")
    return name


class ByokStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class KeyAuditAction(str, Enum):
    CREATED = "created"
    ROTATED = "rotated"
    REVOKED = "revoked"
    USED = "used"


@dataclass(frozen=True)
class ByokKey:
    """Metadados da chave: o valor vive só no SecretStore, nunca neste registro."""

    id: str
    organization_id: str
    provider: str
    mask: str
    fingerprint: str
    secret_scope: str
    secret_name: str
    status: ByokStatus = ByokStatus.ACTIVE
    created_at: datetime | None = None
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    created_by: str | None = None

    @property
    def active(self) -> bool:
        return self.status is ByokStatus.ACTIVE and self.revoked_at is None


def new_byok_key(*, key_id: str, organization_id: str, provider: str, value: str,
                 created_by: str | None = None, now: datetime) -> ByokKey:
    provider = validate_provider(provider)
    value = validate_byok_value(value)
    return ByokKey(
        id=key_id,
        organization_id=organization_id,
        provider=provider,
        mask=mask_secret(value),
        fingerprint=fingerprint(value),
        secret_scope=secret_scope(organization_id),
        secret_name=secret_name(provider, key_id),
        created_at=now,
        created_by=created_by,
    )