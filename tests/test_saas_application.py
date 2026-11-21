"""F11 — casos de uso de equipe e BYOK (aplicação, sem banco e sem cofre real).

Prova o que a tela pode mostrar e o que ela nunca recebe: só máscara e metadados; o valor da
chave fica no `SecretStore`. A autorização é checada aqui, não no HTML.
"""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.panel import CostBreakdown, cost_breakdown  # noqa: E402
from app.studio.application.saas import (  # noqa: E402
    BuildTeamView,
    ChangeMemberRole,
    DuplicateProviderKey,
    InviteMember,
    MemberRecord,
    MembershipNotFound,
    RecordKeyUse,
    RegisterByokKey,
    RemoveMember,
    RevokeByokKey,
    RotateByokKey,
)
from app.studio.domain.saas import (  # noqa: E402
    AuthorizationDenied,
    ByokKey,
    ByokStatus,
    DuplicateMembership,
    KeyAuditAction,
    KeyInvalid,
    KeyNotFound,
    KeyRevoked,
    LastOwnerRequired,
    MembershipInvalid,
    MembershipStatus,
    OrganizationNotFound,
    Role,
    mask_secret,
    new_byok_key,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
ORG = "a" * 32
OTHER_ORG = "b" * 32
RAW = "synthetic-byok-value-0123456789abcdef"


class FakeSecretStore:
    def __init__(self):
        self.data: dict[tuple[str, str], str] = {}
        self.fail_set = False

    def get(self, scope, key):
        return self.data.get((scope, key))

    def set(self, scope, key, value):
        if self.fail_set:
            raise RuntimeError("store unavailable")
        self.data[(scope, key)] = value

    def delete(self, scope, key):
        self.data.pop((scope, key), None)

    def names(self, scope):
        return tuple(k for s, k in self.data if s == scope)


class FakeRepo:
    def __init__(self, *, with_org=True):
        self.orgs = {ORG: "Organização A", OTHER_ORG: "Organização B"} if with_org else {}
        self.workspaces = {ORG: "Produção", OTHER_ORG: "Produção"}
        self.users = {}      # user_id -> (email, display_name)
        self.member_rows = {}  # membership_id -> MemberRecord
        self.key_rows = {}   # key_id -> ByokKey
        self.audit = []
        self._counter = 0
        self._usage: dict[str, list] = {}

    # organização
    def organizations(self):
        return list(self.orgs.items())

    def organization(self, org_id):
        return self.orgs.get(org_id)

    def workspace(self, org_id):
        return self.workspaces.get(org_id)

    # membros
    def members(self, org_id):
        return [m for m in self.member_rows.values() if m.organization_id == org_id]

    def member(self, org_id, membership_id):
        m = self.member_rows.get(membership_id)
        return m if m is not None and m.organization_id == org_id else None

    def member_by_user(self, org_id, user_id):
        return next((m for m in self.member_rows.values()
                     if m.organization_id == org_id and m.user_id == user_id), None)

    def owner_count(self, org_id):
        return sum(1 for m in self.member_rows.values()
                   if m.organization_id == org_id and m.role is Role.OWNER
                   and m.status is MembershipStatus.ACTIVE)

    def find_user(self, email):
        return next(((uid, name) for uid, (mail, name) in self.users.items() if mail == email), None)

    def insert_user(self, user_id, email, display_name):
        self.users[user_id] = (email, display_name)

    def insert_membership(self, membership_id, org_id, user_id, role, status):
        email, name = self.users[user_id]
        self.member_rows[membership_id] = MemberRecord(
            membership_id=membership_id, organization_id=org_id, user_id=user_id,
            display_name=name, email=email, role=role, status=status, created_at=NOW)

    def update_membership_role(self, org_id, membership_id, role):
        m = self.member(org_id, membership_id)
        if m is None:
            return False
        self.member_rows[membership_id] = MemberRecord(
            membership_id=m.membership_id, organization_id=m.organization_id, user_id=m.user_id,
            display_name=m.display_name, email=m.email, role=role, status=m.status, created_at=m.created_at)
        return True

    def delete_membership(self, org_id, membership_id):
        if self.member(org_id, membership_id) is None:
            return False
        del self.member_rows[membership_id]
        return True

    # chaves
    def keys(self, org_id):
        return [k for k in self.key_rows.values() if k.organization_id == org_id]

    def key(self, org_id, key_id):
        k = self.key_rows.get(key_id)
        return k if k is not None and k.organization_id == org_id else None

    def insert_key(self, key):
        if any(k for k in self.key_rows.values()
               if k.organization_id == key.organization_id and k.provider == key.provider and k.active):
            raise DuplicateProviderKey("provider already has an active key")
        self.key_rows[key.id] = key

    def update_key_rotation(self, org_id, key_id, mask, fingerprint, secret_name, rotated_at):
        k = self.key(org_id, key_id)
        if k is None:
            return False
        import dataclasses
        self.key_rows[key_id] = dataclasses.replace(
            k, mask=mask, fingerprint=fingerprint, secret_name=secret_name, rotated_at=rotated_at)
        return True

    def revoke_key(self, org_id, key_id, revoked_at):
        k = self.key(org_id, key_id)
        if k is None or not k.active:
            return False
        import dataclasses
        self.key_rows[key_id] = dataclasses.replace(k, status=ByokStatus.REVOKED, revoked_at=revoked_at)
        return True

    def mark_key_used(self, org_id, key_id, used_at):
        k = self.key(org_id, key_id)
        if k is not None:
            import dataclasses
            self.key_rows[key_id] = dataclasses.replace(k, last_used_at=used_at)

    def audit_key(self, org_id, key_id, actor_user_id, action):
        self.audit.append((org_id, key_id, actor_user_id, action))

    # consumo (registros já atribuídos ao tenant; atribuição em runtime ainda não existe)
    def usage_rows(self, org_id):
        return list(self._usage.get(org_id, []))

    _usage: dict


def seed_owner(repo):
    repo.insert_user("1" * 32, "owner@example.test", "Owner Real")
    repo.insert_membership("2" * 32, ORG, "1" * 32, Role.OWNER, MembershipStatus.ACTIVE)
    return "2" * 32


def seed_key(repo, org=ORG, provider="openai", value=RAW):
    key = new_byok_key(key_id=uuid.uuid4().hex, organization_id=org, provider=provider,
                       value=value, now=NOW)
    repo.key_rows[key.id] = key
    return key


def test_team_view_without_organization_has_an_explicit_empty_state():
    repo = FakeRepo(with_org=False)
    repo._usage = {}
    view = BuildTeamView(repo, lambda: NOW).execute()
    assert view.organization is None
    assert view.members == ()
    assert view.keys == ()
    assert view.tenant_cost.calls == 0
    assert view.member_costs == ()
    assert view.organizations == ()


def test_team_view_shows_real_members_keys_masks_and_usage():
    repo = FakeRepo()
    repo._usage = {ORG: [("Owner Real", "openai", "gpt", 0.42, "ACTUAL")]}
    seed_owner(repo)
    key = seed_key(repo)
    view = BuildTeamView(repo, lambda: NOW).execute()

    assert view.organization is not None and view.organization.name == "Organização A"
    assert view.workspace_name == "Produção"
    assert [m.display_name for m in view.members] == ["Owner Real"]
    assert [k.provider for k in view.keys] == ["openai"]
    assert view.keys[0].mask == key.mask
    assert view.tenant_cost.real_usd == pytest.approx(0.42)
    assert view.member_costs[0].label == "Owner Real"
    # a visão pública não carrega o valor nem em atributo, nem em repr
    assert RAW not in repr(view)


def test_team_view_is_scoped_to_the_selected_organization():
    repo = FakeRepo()
    repo._usage = {}
    seed_owner(repo)
    seed_key(repo)
    repo.insert_user("3" * 32, "b@example.test", "Pessoa B")
    repo.insert_membership("4" * 32, OTHER_ORG, "3" * 32, Role.OWNER, MembershipStatus.ACTIVE)
    seed_key(repo, org=OTHER_ORG, provider="elevenlabs", value="other-synthetic-value-987654321")

    view = BuildTeamView(repo, lambda: NOW).execute(org_id=OTHER_ORG)
    assert view.organization.name == "Organização B"
    assert [m.display_name for m in view.members] == ["Pessoa B"]
    assert [k.provider for k in view.keys] == ["elevenlabs"]
    assert "Owner Real" not in repr(view)

    with pytest.raises(OrganizationNotFound):
        BuildTeamView(repo, lambda: NOW).execute(org_id="c" * 32)


def test_usage_without_member_attribution_is_named_not_invented():
    repo = FakeRepo()
    repo._usage = {ORG: [(None, "openai", "gpt", 0.0, None)]}
    seed_owner(repo)
    view = BuildTeamView(repo, lambda: NOW).execute()
    assert view.member_costs[0].label == "sem membro atribuído"
    assert view.member_costs[0].cost.unknown_calls == 1
    assert view.member_costs[0].cost.real_usd == 0.0


def test_invite_requires_owner_and_never_mutates_when_denied():
    repo = FakeRepo()
    repo._usage = {}
    seed_owner(repo)
    use = InviteMember(repo, lambda: NOW)
    for role in (Role.EDITOR, Role.REVIEWER, Role.VIEWER):
        with pytest.raises(AuthorizationDenied):
            use.execute(actor_role=role, organization_id=ORG,
                        email="new@example.test", role=Role.VIEWER)
    assert len(repo.member_rows) == 1


def test_owner_invites_new_member_as_pending_without_duplicating_user():
    repo = FakeRepo()
    repo._usage = {}
    seed_owner(repo)
    use = InviteMember(repo, lambda: NOW)
    member = use.execute(actor_role=Role.OWNER, organization_id=ORG,
                         email="Nova@Example.Test ", role=Role.REVIEWER)
    assert member.email == "nova@example.test"
    assert member.status is MembershipStatus.INVITED
    assert member.role is Role.REVIEWER
    assert len(repo.users) == 2
    with pytest.raises(DuplicateMembership):
        use.execute(actor_role=Role.OWNER, organization_id=ORG,
                    email="nova@example.test", role=Role.VIEWER)
    with pytest.raises(MembershipInvalid):
        use.execute(actor_role=Role.OWNER, organization_id=ORG,
                    email="not-an-email", role=Role.VIEWER)


def test_change_role_is_owner_only_last_owner_safe_and_tenant_scoped():
    repo = FakeRepo()
    repo._usage = {}
    owner_id = seed_owner(repo)
    repo.insert_user("3" * 32, "b@example.test", "Pessoa B")
    repo.insert_membership("4" * 32, OTHER_ORG, "3" * 32, Role.OWNER, MembershipStatus.ACTIVE)
    use = ChangeMemberRole(repo)

    with pytest.raises(AuthorizationDenied):
        use.execute(actor_role=Role.EDITOR, organization_id=ORG,
                    membership_id=owner_id, role=Role.VIEWER)
    with pytest.raises(LastOwnerRequired):
        use.execute(actor_role=Role.OWNER, organization_id=ORG,
                    membership_id=owner_id, role=Role.VIEWER)
    with pytest.raises(MembershipNotFound):
        use.execute(actor_role=Role.OWNER, organization_id=ORG,
                    membership_id="4" * 32, role=Role.VIEWER)

    repo.insert_user("5" * 32, "second@example.test", "Segundo Owner")
    repo.insert_membership("6" * 32, ORG, "5" * 32, Role.OWNER, MembershipStatus.ACTIVE)
    changed = use.execute(actor_role=Role.OWNER, organization_id=ORG,
                          membership_id=owner_id, role=Role.EDITOR)
    assert changed.role is Role.EDITOR


def test_remove_member_never_removes_the_last_owner():
    repo = FakeRepo()
    repo._usage = {}
    owner_id = seed_owner(repo)
    with pytest.raises(LastOwnerRequired):
        RemoveMember(repo).execute(actor_role=Role.OWNER, organization_id=ORG,
                                   membership_id=owner_id)


def test_register_key_requires_owner_and_stores_value_only_in_the_secret_store():
    repo = FakeRepo()
    repo._usage = {}
    seed_owner(repo)
    store = FakeSecretStore()
    use = RegisterByokKey(repo, store, lambda: NOW)

    for role in (Role.EDITOR, Role.REVIEWER, Role.VIEWER):
        with pytest.raises(AuthorizationDenied):
            use.execute(actor_role=role, organization_id=ORG, provider="openai", value=RAW)
    assert store.data == {}

    key = use.execute(actor_role=Role.OWNER, organization_id=ORG,
                      provider="openai", value=RAW, actor_user_id="1" * 32)
    assert key.mask == mask_secret(RAW)
    assert RAW not in repr(key)
    assert store.data[(key.secret_scope, key.secret_name)] == RAW
    assert repo.key_rows[key.id].fingerprint == key.fingerprint
    assert repo.audit == [(ORG, key.id, "1" * 32, KeyAuditAction.CREATED)]


def test_register_key_rejects_duplicate_provider_invalid_values_and_compensates_failures():
    repo = FakeRepo()
    repo._usage = {}
    seed_owner(repo)
    store = FakeSecretStore()
    use = RegisterByokKey(repo, store, lambda: NOW)

    first = use.execute(actor_role=Role.OWNER, organization_id=ORG, provider="openai", value=RAW)
    with pytest.raises(DuplicateProviderKey):
        use.execute(actor_role=Role.OWNER, organization_id=ORG, provider="openai",
                    value="another-synthetic-value-123456")
    assert len(store.data) == 1

    with pytest.raises(KeyInvalid):
        use.execute(actor_role=Role.OWNER, organization_id=ORG, provider="openai",
                    value="has space 123456789")
    with pytest.raises(KeyInvalid):
        use.execute(actor_role=Role.OWNER, organization_id=ORG, provider="../etc",
                    value=RAW)

    repo.key_rows.clear()
    store.data.clear()
    original = repo.insert_key
    repo.insert_key = lambda key: (_ for _ in ()).throw(RuntimeError("db down"))
    with pytest.raises(RuntimeError):
        use.execute(actor_role=Role.OWNER, organization_id=ORG, provider="openai", value=RAW)
    assert store.data == {}, "cofre não pode ficar com valor órfão quando o metadado falha"
    repo.insert_key = original
    assert first.id not in repo.key_rows


def test_rotate_keeps_key_id_changes_mask_and_removes_old_secret():
    repo = FakeRepo()
    repo._usage = {}
    seed_owner(repo)
    store = FakeSecretStore()
    use = RegisterByokKey(repo, store, lambda: NOW)
    key = use.execute(actor_role=Role.OWNER, organization_id=ORG, provider="openai", value=RAW)
    old_name = key.secret_name
    newer = "rotated-synthetic-value-abcdef123456"

    rotated = RotateByokKey(repo, store, lambda: NOW).execute(
        actor_role=Role.OWNER, organization_id=ORG, key_id=key.id, value=newer)
    assert rotated.id == key.id
    assert rotated.mask == mask_secret(newer)
    assert rotated.fingerprint != key.fingerprint
    assert old_name not in [name for _, name in store.data]
    assert store.data[(rotated.secret_scope, rotated.secret_name)] == newer
    assert (ORG, key.id, None, KeyAuditAction.ROTATED) in repo.audit


def test_revoke_is_tenant_scoped_deletes_secret_and_is_not_repeatable():
    repo = FakeRepo()
    repo._usage = {}
    seed_owner(repo)
    store = FakeSecretStore()
    register = RegisterByokKey(repo, store, lambda: NOW)
    key = register.execute(actor_role=Role.OWNER, organization_id=ORG, provider="openai", value=RAW)

    with pytest.raises(KeyNotFound):
        RevokeByokKey(repo, store, lambda: NOW).execute(
            actor_role=Role.OWNER, organization_id=OTHER_ORG, key_id=key.id)

    revoked = RevokeByokKey(repo, store, lambda: NOW).execute(
        actor_role=Role.OWNER, organization_id=ORG, key_id=key.id)
    assert revoked.status is ByokStatus.REVOKED
    assert store.data == {}
    assert (ORG, key.id, None, KeyAuditAction.REVOKED) in repo.audit
    with pytest.raises(KeyNotFound):
        RevokeByokKey(repo, store, lambda: NOW).execute(
            actor_role=Role.OWNER, organization_id=ORG, key_id=key.id)


def test_record_use_requires_permission_and_refuses_revoked_key():
    repo = FakeRepo()
    repo._usage = {}
    seed_owner(repo)
    key = seed_key(repo)
    use = RecordKeyUse(repo, lambda: NOW)

    for role in (Role.VIEWER, Role.REVIEWER):
        with pytest.raises(AuthorizationDenied):
            use.execute(actor_role=role, organization_id=ORG, key_id=key.id)
    use.execute(actor_role=Role.EDITOR, organization_id=ORG, key_id=key.id)
    assert repo.key_rows[key.id].last_used_at == NOW
    assert (ORG, key.id, None, KeyAuditAction.USED) in repo.audit

    repo.key_rows[key.id] = ByokKey(**{**key.__dict__, "status": ByokStatus.REVOKED, "revoked_at": NOW})
    with pytest.raises(KeyRevoked):
        use.execute(actor_role=Role.OWNER, organization_id=ORG, key_id=key.id)


def test_cost_breakdown_used_by_view_never_turns_absence_into_zero():
    breakdown = cost_breakdown([])
    assert breakdown == CostBreakdown()
    assert breakdown.calls == 0