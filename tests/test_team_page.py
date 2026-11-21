"""F11 — Tela de Equipe: contrato de UX, dado real e a chave que nunca aparece.

O mockup aprovado (`produto/tela-equipe.html`) é um modelo com dados ilustrativos e rotulado
"adiada". O produto agora modela o caminho, mas segue mono-usuário: a tela renderiza dado real
ou estado vazio explícito — nomes, e-mails, organização e valores do mockup não embarcam.
"""
import base64
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.secret_store import FileSecretStore  # noqa: E402
from app.studio.api.panel_team import render_team  # noqa: E402
from app.studio.application.saas import BuildTeamView, RegisterByokKey  # noqa: E402
from app.studio.domain.saas import MembershipStatus, Role  # noqa: E402
from test_saas_application import FakeRepo, seed_key, seed_owner  # noqa: E402
from test_ux_contract import assert_ux_contract  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
ORG = "a" * 32
RAW = "synthetic-page-value-0123456789abcdef"

MOCKUP_ONLY = (
    "Ana Ribeiro", "ana@exemplo.com.br", "Bruno Salles", "Carla Nunes", "Diego Prado",
    "Estúdio Exemplo Ltda", "US$ 3,10", "US$ 0,84", "US$ 3,94", "sk-…", "xi-…",
    "1,2 mi views", "run_7f31",
)


def _text(html):
    without = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", without).split())


def _buttons(html):
    return re.findall(r"<button\b[^>]*>.*?</button>", html, re.S)


def _empty_view():
    repo = FakeRepo(with_org=False)
    return render_team(BuildTeamView(repo, lambda: NOW).execute())[0]


def _populated_repo():
    repo = FakeRepo()
    repo._usage = {ORG: [("Owner Real", "openai", "gpt", 0.42, "ACTUAL")]}
    seed_owner(repo)
    seed_key(repo)
    return repo


def test_team_page_without_organization_is_an_explicit_empty_state():
    html = _empty_view()
    assert_ux_contract(html, page="equipe/vazia")
    visible = _text(html)
    assert "Nenhuma organização cadastrada" in visible
    assert "mono-usuário" in visible
    for leaked in MOCKUP_ONLY:
        assert leaked not in visible, leaked
    assert "US$ 0,00" not in html


def test_team_page_renders_real_members_keys_masks_and_cost_labels():
    view = BuildTeamView(_populated_repo(), lambda: NOW).execute()
    html, headers = render_team(view)
    assert_ux_contract(html, page="equipe")
    visible = _text(html)
    assert "Owner Real" in visible
    assert "owner@example.test" in visible
    assert "openai" in visible
    assert "Real US$ 0,42" in visible
    assert view.keys[0].mask in visible
    assert RAW not in html
    assert "Content-Security-Policy" in headers and "no-store" in headers["Cache-Control"]


def test_team_page_has_no_progress_bar_and_no_illustrative_mockup_text():
    html = _empty_view()
    assert "<progress" not in html
    assert 'role="progressbar"' not in html
    for leaked in MOCKUP_ONLY:
        assert leaked not in html, leaked


def test_unavailable_actions_are_not_focusable_and_say_why():
    html = _empty_view()
    disabled = [b for b in _buttons(html) if 'aria-disabled="true"' in b or " disabled" in b]
    assert disabled, "as ações de gestão têm de existir como indisponíveis, não sumir"
    for button in disabled:
        assert " disabled" in button or 'tabindex="-1"' in button, button
    visible = _text(html)
    assert "Indisponível" in visible
    assert "F11-02" in visible


def test_byok_value_never_reaches_the_http_response_even_in_base64(tmp_path):
    repo = _populated_repo()
    store = FileSecretStore(tmp_path / "secrets")
    key = RegisterByokKey(repo, store, lambda: NOW).execute(
        actor_role=Role.OWNER, organization_id=ORG, provider="elevenlabs", value=RAW)

    view = BuildTeamView(repo, lambda: NOW).execute()
    html, headers = render_team(view)

    assert RAW not in html
    for blob in (base64.b64encode(RAW.encode()).decode(),
                 base64.urlsafe_b64encode(RAW.encode()).decode().rstrip("=")):
        assert blob not in html, "o valor não pode vazar nem codificado"
    assert RAW not in repr(view)
    assert RAW not in repr(key)
    assert RAW not in str(headers)

    files = list(store.root.glob("*.json"))
    assert len(files) == 1
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    assert RAW in files[0].read_text(encoding="utf-8"), "o valor tem de estar só no cofre"


def test_team_page_never_mixes_organizations():
    repo = _populated_repo()
    repo.insert_user("3" * 32, "b@example.test", "Pessoa B")
    repo.insert_membership("4" * 32, "b" * 32, "3" * 32, Role.OWNER, MembershipStatus.ACTIVE)
    seed_key(repo, org="b" * 32, provider="elevenlabs", value="other-synthetic-value-987654321")

    html = render_team(BuildTeamView(repo, lambda: NOW).execute(org_id="b" * 32))[0]
    visible = _text(html)
    assert "Pessoa B" in visible
    assert "Owner Real" not in visible
    assert "openai" not in visible


def test_route_serves_the_team_page_from_real_data(conn, dsn, tmp_path):
    pytest.importorskip("psycopg")
    pytest.importorskip("fastapi")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.studio.adapters.postgres.db import migrate
    from app.studio.api.routes import make_router
    from app.studio.composition import Settings, Studio

    migrate(conn)
    conn.execute("INSERT INTO studio.organizations(id, name) VALUES (%s, 'Organização Rota')", (ORG,))
    conn.execute("INSERT INTO studio.users(id, email, display_name) VALUES (%s, 'owner@example.test', 'Owner Rota')",
                 ("1" * 32,))
    conn.execute("INSERT INTO studio.memberships(id, organization_id, user_id, role, status) "
                 "VALUES (%s, %s, %s, 'owner', 'active')", ("3" * 32, ORG, "1" * 32))
    conn.commit()

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    r = TestClient(app).get("/studio/panel/equipe", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Organização Rota" in r.text
    assert "Owner Rota" in r.text
    assert "US$ 0,00" not in r.text
    assert r.headers.get("Cache-Control") == "no-store"