"""L2 — mutações da tela de Equipe expostas na rota, com RBAC do domínio e sem vazar a chave.

O ator é o operador autenticado do painel (Basic auth, `STUDIO_BROWSER_USER`); o papel é o do
vínculo ativo dele na organização (domínio F11). Papel insuficiente recebe 403 e a segredo nunca
aparece na resposta nem em log.
"""
import base64
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402

ORG = "a" * 32
OWNER = "1" * 32
VIEWER = "2" * 32
OWNER_MEMBERSHIP = "3" * 32
VIEWER_MEMBERSHIP = "4" * 32
OWNER_EMAIL = "owner@example.test"
VIEWER_EMAIL = "viewer@example.test"

# Valores inequivocamente sintéticos (nunca parecem credencial real).
RAW = "synthetic-lig-value-0123456789abcdef"
ROTATED = "synthetic-lig-rotated-abcdef0123456789"


def _basic(email):
    return {"Authorization": "Basic " + base64.b64encode(f"{email}:test-browser-password".encode()).decode()}


def _post_headers(email):
    return {**_basic(email), "Origin": "http://testserver"}


@pytest.fixture()
def client(dsn, conn, tmp_path):
    migrate(conn)
    conn.execute("INSERT INTO studio.organizations(id, name) VALUES (%s, 'Organização Lig')", (ORG,))
    conn.execute("INSERT INTO studio.users(id, email, display_name) VALUES (%s, %s, 'Dono Real')",
                 (OWNER, OWNER_EMAIL))
    conn.execute("INSERT INTO studio.users(id, email, display_name) VALUES (%s, %s, 'Só Leitura')",
                 (VIEWER, VIEWER_EMAIL))
    conn.execute("INSERT INTO studio.memberships(id, organization_id, user_id, role, status) "
                 "VALUES (%s, %s, %s, 'owner', 'active')", (OWNER_MEMBERSHIP, ORG, OWNER))
    conn.execute("INSERT INTO studio.memberships(id, organization_id, user_id, role, status) "
                 "VALUES (%s, %s, %s, 'viewer', 'active')", (VIEWER_MEMBERSHIP, ORG, VIEWER))
    conn.commit()

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "conn": conn, "storage": tmp_path}


def _register(client, email, *, provider="elevenlabs", value=RAW, org=ORG):
    return client["client"].post("/studio/panel/equipe/keys",
                                 json={"organization_id": org, "provider": provider, "value": value},
                                 headers=_post_headers(email))


def test_mutations_require_authentication(client):
    r = client["client"].post("/studio/panel/equipe/keys",
                              json={"organization_id": ORG, "provider": "elevenlabs", "value": RAW},
                              headers={"Origin": "http://testserver"})
    assert r.status_code == 401


def test_viewer_cannot_register_a_key_but_owner_can(client, monkeypatch):
    monkeypatch.setenv("STUDIO_BROWSER_USER", VIEWER_EMAIL)
    denied = _register(client, VIEWER_EMAIL)
    assert denied.status_code == 403

    monkeypatch.setenv("STUDIO_BROWSER_USER", OWNER_EMAIL)
    allowed = _register(client, OWNER_EMAIL)
    assert allowed.status_code == 201
    data = allowed.json()
    assert data["provider"] == "elevenlabs"
    assert data["mask"] and data["status"] == "active"


def test_key_value_never_reaches_the_response_or_the_log(client, monkeypatch, caplog):
    monkeypatch.setenv("STUDIO_BROWSER_USER", OWNER_EMAIL)
    caplog.set_level(logging.DEBUG)
    r = _register(client, OWNER_EMAIL)
    assert r.status_code == 201

    assert RAW not in r.text
    assert base64.b64encode(RAW.encode()).decode() not in r.text
    assert RAW not in caplog.text, "o valor do segredo não pode ser logado"
    body = r.json()
    assert "value" not in body and "secret_name" not in body

    stored = list((client["storage"] / "secrets").glob("*.json"))
    assert stored and RAW in stored[0].read_text(encoding="utf-8"), "só o cofre guarda o valor"


def test_byok_audit_records_the_authenticated_actor(client, conn, monkeypatch):
    monkeypatch.setenv("STUDIO_BROWSER_USER", OWNER_EMAIL)
    r = _register(client, OWNER_EMAIL)
    assert r.status_code == 201
    key_id = r.json()["id"]
    actor = conn.execute("SELECT actor_user_id, action FROM studio.byok_key_audit WHERE key_id = %s",
                         (key_id,)).fetchone()
    assert actor == (OWNER, "created")


def test_member_mutations_are_authorized_and_audited(client, conn, monkeypatch):
    monkeypatch.setenv("STUDIO_BROWSER_USER", VIEWER_EMAIL)
    denied = client["client"].post("/studio/panel/equipe/members",
                                   json={"organization_id": ORG, "email": "nova@example.test", "role": "editor"},
                                   headers=_post_headers(VIEWER_EMAIL))
    assert denied.status_code == 403
    assert conn.execute("SELECT count(*) FROM studio.memberships WHERE organization_id = %s",
                        (ORG,)).fetchone()[0] == 2

    monkeypatch.setenv("STUDIO_BROWSER_USER", OWNER_EMAIL)
    created = client["client"].post("/studio/panel/equipe/members",
                                    json={"organization_id": ORG, "email": "nova@example.test",
                                          "role": "reviewer", "display_name": "Nova Pessoa"},
                                    headers=_post_headers(OWNER_EMAIL))
    assert created.status_code == 201
    membership_id = created.json()["membership_id"]
    audit = conn.execute("SELECT actor_user_id, action FROM studio.membership_audit "
                         "WHERE membership_id = %s", (membership_id,)).fetchone()
    assert audit == (OWNER, "invited")

    changed = client["client"].patch(f"/studio/panel/equipe/members/{membership_id}",
                                     json={"organization_id": ORG, "role": "editor"},
                                     headers=_post_headers(OWNER_EMAIL))
    assert changed.status_code == 200
    assert changed.json()["role"] == "editor"
    assert conn.execute("SELECT action FROM studio.membership_audit WHERE membership_id = %s "
                        "ORDER BY id DESC LIMIT 1", (membership_id,)).fetchone()[0] == "role_changed"


def test_rotate_and_revoke_are_owner_only_and_never_echo_the_value(client, conn, monkeypatch):
    monkeypatch.setenv("STUDIO_BROWSER_USER", VIEWER_EMAIL)
    assert _register(client, VIEWER_EMAIL).status_code == 403

    monkeypatch.setenv("STUDIO_BROWSER_USER", OWNER_EMAIL)
    key_id = _register(client, OWNER_EMAIL).json()["id"]

    rotated = client["client"].post(f"/studio/panel/equipe/keys/{key_id}/rotate",
                                    json={"organization_id": ORG, "value": ROTATED},
                                    headers=_post_headers(OWNER_EMAIL))
    assert rotated.status_code == 200
    assert ROTATED not in rotated.text
    assert RAW not in rotated.text

    revoked = client["client"].delete(f"/studio/panel/equipe/keys/{key_id}",
                                      params={"organization_id": ORG},
                                      headers=_post_headers(OWNER_EMAIL))
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert RAW not in revoked.text

    actions = [row[0] for row in conn.execute(
        "SELECT action FROM studio.byok_key_audit WHERE key_id = %s ORDER BY id", (key_id,)).fetchall()]
    assert actions == ["created", "rotated", "revoked"]


def test_actor_without_membership_in_the_organization_is_denied(client, conn, monkeypatch):
    conn.execute("INSERT INTO studio.users(id, email, display_name) VALUES (%s, 'outsider@example.test', 'Estranho')",
                 ("9" * 32,))
    conn.commit()
    monkeypatch.setenv("STUDIO_BROWSER_USER", "outsider@example.test")
    r = _register(client, "outsider@example.test")
    assert r.status_code == 403


def test_unknown_role_is_rejected_without_touching_the_repository(client, conn, monkeypatch):
    monkeypatch.setenv("STUDIO_BROWSER_USER", OWNER_EMAIL)
    r = client["client"].post("/studio/panel/equipe/members",
                              json={"organization_id": ORG, "email": "x@example.test", "role": "admin"},
                              headers=_post_headers(OWNER_EMAIL))
    assert r.status_code == 422
    assert conn.execute("SELECT count(*) FROM studio.memberships WHERE organization_id = %s",
                        (ORG,)).fetchone()[0] == 2
