"""Casos de uso de equipe, papéis e BYOK (F11-01/02/04/05 / L2).

As mutações recebem o papel do ator e o `actor_user_id`; a rota resolve o ator a partir do
operador autenticado do painel (o vínculo ativo dele na organização) e passa o papel verdadeiro.
A autorização é o RBAC do domínio (`require`); o audit registra quem executou. O valor da chave
nunca entra nestes objetos: só a máscara, a impressão digital e a coordenada do `SecretStore`.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime

from ..domain.saas import (
    ByokKey,
    ByokStatus,
    AuthorizationDenied,
    DuplicateMembership,
    DuplicateProviderKey,
    KeyAuditAction,
    KeyNotFound,
    KeyRevoked,
    KeyAuditAction as Audit,
    MembershipNotFound,
    MembershipStatus,
    OrganizationNotFound,
    Permission,
    Role,
    ROLE_DESCRIPTIONS,
    MembershipAuditAction,
    ensure_owner_remains,
    mask_secret,
    fingerprint,
    new_byok_key,
    normalize_email,
    require,
    role_from,
    secret_name,
    validate_byok_value,
    validate_provider,
)
from .errors import ServiceUnavailable
from .panel import CostBreakdown, cost_breakdown
from .ports import MemberRecord, SaasRepository, SecretStore

RUNTIME_NOTE = (
    "Organização, papéis e chaves estão modelados no banco e as mutações são executadas pela rota, "
    "autorizadas pelo papel do operador autenticado no domínio. O login por SSO/OIDC (F11-02) ainda "
    "não é a fonte de identidade e o isolamento em runtime segue mono-usuário."
)
ACTIONS_UNAVAILABLE_NOTE = (
    "Indisponível: login por SSO/OIDC (F11-02), envio de e-mail de convite, cobrança/créditos e "
    "isolamento de runtime por tenant. O que existe é executado pela rota; nada aqui finge além disso."
)


def _store_set(store: SecretStore, scope: str, name: str, value: str) -> None:
    try:
        store.set(scope, name, value)
    except Exception as exc:  # a porta não declara erro próprio; o cofre é infraestrutura
        raise ServiceUnavailable("secret store unavailable") from exc


def _store_delete(store: SecretStore, scope: str, name: str) -> None:
    try:
        store.delete(scope, name)
    except Exception as exc:
        raise ServiceUnavailable("secret store unavailable") from exc


@dataclass(frozen=True)
class OrganizationView:
    id: str
    name: str


@dataclass(frozen=True)
class KeyView:
    id: str
    provider: str
    mask: str
    fingerprint: str
    status: ByokStatus
    created_at: datetime | None
    rotated_at: datetime | None
    revoked_at: datetime | None
    usage: CostBreakdown = field(default_factory=CostBreakdown)


@dataclass(frozen=True)
class MemberUsageView:
    label: str
    cost: CostBreakdown


@dataclass(frozen=True)
class TeamView:
    now: datetime
    organizations: tuple[tuple[str, str], ...]
    organization: OrganizationView | None
    workspace_name: str | None
    members: tuple[MemberRecord, ...]
    keys: tuple[KeyView, ...]
    tenant_cost: CostBreakdown
    member_costs: tuple[MemberUsageView, ...]
    roles: tuple[tuple[Role, str], ...]
    runtime_note: str = RUNTIME_NOTE
    actions_note: str = ACTIONS_UNAVAILABLE_NOTE

    @property
    def has_organization(self) -> bool:
        return self.organization is not None


class BuildTeamView:
    """Monta a visão da Equipe com dado real. Sem organização, devolve o estado vazio explícito."""
    def __init__(self, repo: SaasRepository, clock: Callable[[], datetime]):
        self.repo = repo
        self.clock = clock

    def execute(self, org_id: str | None = None) -> TeamView:
        now = self.clock()
        organizations = tuple(self.repo.organizations())
        if org_id is None:
            org_id = organizations[0][0] if organizations else None
        if org_id is None:
            return TeamView(now=now, organizations=organizations, organization=None, workspace_name=None,
                            members=(), keys=(), tenant_cost=CostBreakdown(), member_costs=(),
                            roles=tuple(ROLE_DESCRIPTIONS.items()))

        name = self.repo.organization(org_id)
        if name is None:
            raise OrganizationNotFound("organization not found")

        rows = self.repo.usage_rows(org_id)
        tenant_cost = cost_breakdown((provider, model, cost_usd, kind)
                                     for _, provider, model, cost_usd, kind in rows)

        by_member: dict[str, list[tuple[str, str, float, str | None]]] = {}
        by_provider: dict[str, list[tuple[str, str, float, str | None]]] = {}
        for member, provider, model, cost_usd, kind in rows:
            label = member or "sem membro atribuído"
            by_member.setdefault(label, []).append((provider, model, cost_usd, kind))
            by_provider.setdefault(provider, []).append((provider, model, cost_usd, kind))

        member_costs = tuple(
            MemberUsageView(label=label, cost=cost_breakdown(items))
            for label, items in sorted(by_member.items(), key=lambda kv: (kv[0] == "sem membro atribuído", kv[0]))
        )
        keys = tuple(
            KeyView(id=key.id, provider=key.provider, mask=key.mask, fingerprint=key.fingerprint,
                    status=key.status,
                    created_at=key.created_at, rotated_at=key.rotated_at, revoked_at=key.revoked_at,
                    usage=cost_breakdown(by_provider.get(key.provider, [])))
            for key in sorted(self.repo.keys(org_id), key=lambda k: (k.created_at or now, k.id))
        )

        return TeamView(
            now=now,
            organizations=organizations,
            organization=OrganizationView(id=org_id, name=name),
            workspace_name=self.repo.workspace(org_id),
            members=tuple(self.repo.members(org_id)),
            keys=keys,
            tenant_cost=tenant_cost,
            member_costs=member_costs,
            roles=tuple(ROLE_DESCRIPTIONS.items()),
        )


@dataclass(frozen=True)
class Actor:
    """Quem executa a mutação: o operador autenticado do painel, resolvido no domínio.

    O identificador e o papel vêm do vínculo ativo do operador na organização — não de um campo
    livre da requisição. É o que permite aplicar o RBAC de verdade sem OIDC.
    """

    user_id: str
    email: str
    role: Role


class ResolveActor:
    """Resolve o principal autenticado no vínculo ativo dele dentro da organização.

    Sem vínculo ativo (ou de outra organização), a autorização é negada: a fronteira é o vínculo,
    não o que o cliente afirma. Nunca cria usuário nem vínculo: identificar não é cadastrar.
    """

    def __init__(self, repo: SaasRepository):
        self.repo = repo

    def execute(self, *, organization_id: str, principal: str) -> Actor:
        principal = (principal or "").strip()
        if not principal:
            raise AuthorizationDenied("actor not identified")
        user_id = None
        if len(principal) == 32 and all(ch in "0123456789abcdef" for ch in principal.lower()):
            user_id = principal.lower()
        else:
            found = self.repo.find_user(principal.lower())
            user_id = found[0] if found else None
        member = self.repo.member_by_user(organization_id, user_id) if user_id else None
        if member is None or member.status is not MembershipStatus.ACTIVE:
            raise AuthorizationDenied("actor has no active membership in this organization")
        return Actor(user_id=member.user_id, email=member.email, role=member.role)


class InviteMember:
    """Convida por e-mail; o usuário é criado uma vez e o vínculo nasce `invited`."""

    def __init__(self, repo: SaasRepository, clock: Callable[[], datetime]):
        self.repo = repo
        self.clock = clock

    def execute(self, *, actor_role: Role, organization_id: str, email: str, role: Role,
                display_name: str | None = None, actor_user_id: str | None = None) -> MemberRecord:
        require(role_from(actor_role), Permission.MANAGE_MEMBERS)
        email = normalize_email(email)
        role = role_from(role)
        found = self.repo.find_user(email)
        if found is None:
            user_id = uuid.uuid4().hex
            name = (display_name or "").strip() or email.split("@", 1)[0]
            self.repo.insert_user(user_id, email, name[:120])
        else:
            user_id, name = found
        if self.repo.member_by_user(organization_id, user_id) is not None:
            raise DuplicateMembership("user already belongs to the organization")
        membership_id = uuid.uuid4().hex
        self.repo.insert_membership(membership_id, organization_id, user_id, role, MembershipStatus.INVITED)
        self.repo.audit_membership(organization_id, membership_id, actor_user_id,
                                  MembershipAuditAction.INVITED, role)
        return MemberRecord(membership_id=membership_id, organization_id=organization_id, user_id=user_id,
                            display_name=name, email=email, role=role,
                            status=MembershipStatus.INVITED, created_at=self.clock())


class ChangeMemberRole:
    def __init__(self, repo: SaasRepository):
        self.repo = repo

    def execute(self, *, actor_role: Role, organization_id: str, membership_id: str, role: Role,
                actor_user_id: str | None = None) -> MemberRecord:
        require(role_from(actor_role), Permission.MANAGE_MEMBERS)
        target = self.repo.member(organization_id, membership_id)
        if target is None:
            raise MembershipNotFound("membership not found")
        new_role = role_from(role)
        ensure_owner_remains(target.role, new_role, self.repo.owner_count(organization_id))
        if not self.repo.update_membership_role(organization_id, membership_id, new_role):
            raise MembershipNotFound("membership not found")
        self.repo.audit_membership(organization_id, membership_id, actor_user_id,
                                  MembershipAuditAction.ROLE_CHANGED, new_role)
        return replace(target, role=new_role)


class RemoveMember:
    def __init__(self, repo: SaasRepository):
        self.repo = repo

    def execute(self, *, actor_role: Role, organization_id: str, membership_id: str,
                actor_user_id: str | None = None) -> MemberRecord:
        require(role_from(actor_role), Permission.MANAGE_MEMBERS)
        target = self.repo.member(organization_id, membership_id)
        if target is None:
            raise MembershipNotFound("membership not found")
        ensure_owner_remains(target.role, None, self.repo.owner_count(organization_id))
        if not self.repo.delete_membership(organization_id, membership_id):
            raise MembershipNotFound("membership not found")
        self.repo.audit_membership(organization_id, membership_id, actor_user_id,
                                  MembershipAuditAction.REMOVED, target.role)
        return target


class RegisterByokKey:
    """Cadastra a chave: valor só no cofre; banco guarda máscara, impressão e coordenada."""

    def __init__(self, repo: SaasRepository, store: SecretStore, clock: Callable[[], datetime]):
        self.repo = repo
        self.store = store
        self.clock = clock

    def execute(self, *, actor_role: Role, organization_id: str, provider: str, value: str,
                actor_user_id: str | None = None) -> ByokKey:
        require(role_from(actor_role), Permission.MANAGE_KEYS)
        provider = validate_provider(provider)
        validate_byok_value(value)
        if any(k.provider == provider and k.active for k in self.repo.keys(organization_id)):
            raise DuplicateProviderKey("provider already has an active key")
        key = new_byok_key(key_id=uuid.uuid4().hex, organization_id=organization_id,
                           provider=provider, value=value, created_by=actor_user_id, now=self.clock())
        _store_set(self.store, key.secret_scope, key.secret_name, value)
        try:
            self.repo.insert_key(key)
        except BaseException:
            try:
                self.store.delete(key.secret_scope, key.secret_name)
            except Exception:
                pass
            raise
        self.repo.audit_key(organization_id, key.id, actor_user_id, Audit.CREATED)
        return key


class RotateByokKey:
    """Troca o valor sem trocar o id da chave; o segredo anterior é removido do cofre."""

    def __init__(self, repo: SaasRepository, store: SecretStore, clock: Callable[[], datetime]):
        self.repo = repo
        self.store = store
        self.clock = clock

    def execute(self, *, actor_role: Role, organization_id: str, key_id: str, value: str,
                actor_user_id: str | None = None) -> ByokKey:
        require(role_from(actor_role), Permission.MANAGE_KEYS)
        key = self.repo.key(organization_id, key_id)
        if key is None:
            raise KeyNotFound("key not found")
        if not key.active:
            raise KeyRevoked("key is revoked")
        validate_byok_value(value)
        now = self.clock()
        new_name = secret_name(key.provider, f"{key.id}_{uuid.uuid4().hex[:12]}")
        _store_set(self.store, key.secret_scope, new_name, value)
        if not self.repo.update_key_rotation(organization_id, key.id, mask_secret(value),
                                             fingerprint(value), new_name, now):
            try:
                self.store.delete(key.secret_scope, new_name)
            except Exception:
                pass
            raise KeyNotFound("key not found")
        self.repo.audit_key(organization_id, key.id, actor_user_id, Audit.ROTATED)
        try:
            self.store.delete(key.secret_scope, key.secret_name)
        except ServiceUnavailable:
            # O metadado e a auditoria já apontam para o segredo novo; o arquivo antigo órfão
            # não é usado por nenhum caminho. A limpeza pode ser repetida com segurança.
            pass
        return replace(key, mask=mask_secret(value), fingerprint=fingerprint(value),
                       secret_name=new_name, rotated_at=now)


class RevokeByokKey:
    def __init__(self, repo: SaasRepository, store: SecretStore, clock: Callable[[], datetime]):
        self.repo = repo
        self.store = store
        self.clock = clock

    def execute(self, *, actor_role: Role, organization_id: str, key_id: str,
                actor_user_id: str | None = None) -> ByokKey:
        require(role_from(actor_role), Permission.MANAGE_KEYS)
        key = self.repo.key(organization_id, key_id)
        if key is None:
            raise KeyNotFound("key not found")
        now = self.clock()
        if not self.repo.revoke_key(organization_id, key.id, now):
            raise KeyNotFound("key not found")
        self.repo.audit_key(organization_id, key.id, actor_user_id, Audit.REVOKED)
        _store_delete(self.store, key.secret_scope, key.secret_name)
        return replace(key, status=ByokStatus.REVOKED, revoked_at=now)


class RecordKeyUse:
    """Uso autorizado de provider: papel precisa poder usar e a chave precisa estar ativa."""

    def __init__(self, repo: SaasRepository, clock: Callable[[], datetime]):
        self.repo = repo
        self.clock = clock

    def execute(self, *, actor_role: Role, organization_id: str, key_id: str) -> ByokKey:
        require(role_from(actor_role), Permission.USE_PROVIDER)
        key = self.repo.key(organization_id, key_id)
        if key is None:
            raise KeyNotFound("key not found")
        if not key.active:
            raise KeyRevoked("key is revoked")
        now = self.clock()
        self.repo.mark_key_used(organization_id, key.id, now)
        self.repo.audit_key(organization_id, key.id, None, Audit.USED)
        return replace(key, last_used_at=now)


# Reexports explícitos usados pelos adaptadores/testes de contrato.
__all__ = [
    "ACTIONS_UNAVAILABLE_NOTE",
    "Actor",
    "BuildTeamView",
    "ChangeMemberRole",
    "InviteMember",
    "KeyView",
    "MemberUsageView",
    "OrganizationView",
    "RUNTIME_NOTE",
    "RecordKeyUse",
    "RegisterByokKey",
    "RemoveMember",
    "ResolveActor",
    "RevokeByokKey",
    "RotateByokKey",
    "TeamView",
]