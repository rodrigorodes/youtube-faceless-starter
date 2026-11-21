"""F11 — modelo de organização, papéis e fronteira de tenant (domínio puro).

O produto hoje é mono-usuário; este é o caminho modelado. O que estes testes provam é a
**regra** (matriz de permissões, último owner, isolamento), não a aplicação em runtime.
"""
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.saas import (  # noqa: E402
    AuthorizationDenied,
    CrossTenantAccess,
    KeyInvalid,
    LastOwnerRequired,
    MembershipStatus,
    Permission,
    Role,
    UnknownRole,
    assert_same_tenant,
    can,
    ensure_owner_remains,
    fingerprint,
    mask_secret,
    role_from,
    secret_name,
    secret_scope,
    validate_byok_value,
    validate_provider,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
ORG = "a" * 32
OTHER_ORG = "b" * 32


def test_owner_has_every_permission():
    assert can(Role.OWNER, Permission.MANAGE_MEMBERS)
    assert can(Role.OWNER, Permission.MANAGE_KEYS)
    assert can(Role.OWNER, Permission.PUBLISH)
    assert can(Role.OWNER, Permission.VIEW)


def test_viewer_is_read_only_even_for_approval():
    allowed = {p for p in Permission if can(Role.VIEWER, p)}
    assert allowed == {Permission.VIEW, Permission.VIEW_COSTS}
    for denied in (Permission.CREATE_VIDEO, Permission.EDIT_VIDEO, Permission.APPROVE_SCRIPT,
                   Permission.APPROVE_PREVIEW, Permission.PUBLISH, Permission.CONFIGURE_PROVIDERS,
                   Permission.USE_PROVIDER, Permission.MANAGE_MEMBERS, Permission.MANAGE_KEYS):
        assert not can(Role.VIEWER, denied), denied


def test_editor_creates_and_edits_but_never_manages_members_keys_or_approval():
    for allowed in (Permission.VIEW, Permission.VIEW_COSTS, Permission.CREATE_VIDEO,
                    Permission.EDIT_VIDEO, Permission.CONFIGURE_PROVIDERS, Permission.USE_PROVIDER):
        assert can(Role.EDITOR, allowed), allowed
    for denied in (Permission.MANAGE_MEMBERS, Permission.MANAGE_KEYS,
                   Permission.APPROVE_SCRIPT, Permission.APPROVE_PREVIEW):
        assert not can(Role.EDITOR, denied), denied


def test_reviewer_approves_but_does_not_publish_edit_configuration_or_keys():
    assert can(Role.REVIEWER, Permission.APPROVE_SCRIPT)
    assert can(Role.REVIEWER, Permission.APPROVE_PREVIEW)
    for denied in (Permission.PUBLISH, Permission.EDIT_VIDEO, Permission.CONFIGURE_PROVIDERS,
                   Permission.MANAGE_MEMBERS, Permission.MANAGE_KEYS, Permission.USE_PROVIDER):
        assert not can(Role.REVIEWER, denied), denied


def test_role_parsing_rejects_unknown_values():
    assert role_from("owner") is Role.OWNER
    assert role_from(Role.VIEWER) is Role.VIEWER
    with pytest.raises(UnknownRole):
        role_from("admin")
    with pytest.raises(UnknownRole):
        role_from(None)


def test_permission_check_raises_and_does_not_leak_role_details():
    with pytest.raises(AuthorizationDenied) as exc:
        from app.studio.domain.saas import require
        require(Role.VIEWER, Permission.MANAGE_KEYS)
    assert "viewer" not in str(exc.value).lower()
    assert "manage_keys" not in str(exc.value).lower()


def test_cross_tenant_access_is_refused():
    assert assert_same_tenant(ORG, ORG) == ORG
    with pytest.raises(CrossTenantAccess):
        assert_same_tenant(ORG, OTHER_ORG)
    with pytest.raises(CrossTenantAccess):
        assert_same_tenant(ORG, None)


def test_last_owner_cannot_be_demoted_or_removed():
    ensure_owner_remains(Role.OWNER, Role.OWNER, owner_count=1)   # continua owner
    ensure_owner_remains(Role.OWNER, Role.EDITOR, owner_count=2)  # há outro owner
    ensure_owner_remains(Role.EDITOR, Role.VIEWER, owner_count=1) # não é owner
    with pytest.raises(LastOwnerRequired):
        ensure_owner_remains(Role.OWNER, Role.EDITOR, owner_count=1)
    with pytest.raises(LastOwnerRequired):
        ensure_owner_remains(Role.OWNER, None, owner_count=1)


def test_membership_statuses_are_the_canonical_ones():
    assert {s.value for s in MembershipStatus} == {"active", "invited"}


def test_mask_never_contains_the_value_and_keeps_only_the_tail():
    secret = "synthetic-value-for-mask-0123456789abcdef"
    masked = mask_secret(secret)
    assert secret not in masked
    assert masked.endswith(secret[-4:])
    assert masked.count("•") >= 4


def test_short_values_are_fully_masked():
    for secret in ("short", "12345678", "abcdefghijkl"):
        masked = mask_secret(secret)
        assert secret not in masked
        assert set(masked) <= {"•"}, masked


def test_mask_is_not_the_value_even_when_value_is_already_masked():
    assert mask_secret("••••••••") == "••••••••"


def test_fingerprint_is_sha256_and_differs_per_value():
    value = "synthetic-fingerprint-value-0001"
    assert fingerprint(value) == hashlib.sha256(value.encode("utf-8")).hexdigest()
    assert fingerprint(value) != fingerprint(value + "x")


def test_byok_value_validation_is_strict_and_never_echoes_the_value():
    secret = "synthetic-valid-value-0123456789"
    assert validate_byok_value(secret) == secret
    for bad in ("", "   ", "short", "with space 123456789", " leading-space-123456",
                "trailing-space-123456 ", "line\nbreak-123456789"):
        with pytest.raises(KeyInvalid) as exc:
            validate_byok_value(bad)
        assert bad.strip() not in str(exc.value) or not bad.strip()


def test_provider_and_secret_coordinates_are_stable_and_safe():
    assert validate_provider("openai") == "openai"
    assert validate_provider("eleven-labs.v2") == "eleven-labs.v2"
    for bad in ("", "../etc", "with space", "a" * 65, "sk_live/../../x"):
        with pytest.raises(KeyInvalid):
            validate_provider(bad)
    assert secret_scope(ORG) == f"byok:{ORG}"
    assert secret_name("openai", "c" * 32) == "openai_" + "c" * 32