"""Tela de Conexões (YT-04b) no painel: conta → canais, confirmar antes de vincular, revogar isolado.

O contrato de UX (`test_ux_contract.assert_ux_contract`) é aplicado à tela inteira. A página é
somente leitura no servidor: o dado vem do mesmo `list_connections` do `GET /connections`, e as
ações (conectar, vincular, desvincular, revogar) chamam a API existente por `fetch`. A confirmação
do canal (nome + id) aparece **antes** do controle de vínculo (§5.4), e as ações destrutivas passam
por um `<dialog>` nativo com o efeito explícito.
"""
import base64
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio import composition  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.youtube_oauth import (  # noqa: E402
    DEFAULT_SCOPES, OAuthIdentity, OAuthTokenResponse, authorization_url,
)
from test_ux_contract import assert_ux_contract  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
WORKER_HEADER = {"Authorization": "Bearer test-worker-token"}
ACCESS = "ya29.SYNTHETIC_api_access_value"
REFRESH = "1//SYNTHETIC_api_refresh_value"


class OAuthFake:
    """Duplo do `OAuthClient`: nenhuma rede; a identidade (canal + e-mail) é ajustável."""

    def __init__(self):
        self.identity_value = OAuthIdentity(channel_id="UC_principal", title="Canal principal",
                                            email="EU@gmail.com")

    def authorization_url(self, redirect_uri, scopes, state, code_challenge):
        return authorization_url(client_id="client-id.apps.googleusercontent.com", redirect_uri=redirect_uri,
                                 scopes=scopes, state=state, code_challenge=code_challenge,
                                 allowed_redirect_uris=("http://localhost:8000/studio/oauth/callback",))

    def exchange_code(self, code, redirect_uri, code_verifier):
        return OAuthTokenResponse(access_token=ACCESS, refresh_token=REFRESH, expires_in=3600,
                                  scopes=DEFAULT_SCOPES)

    def refresh(self, refresh_token):  # pragma: no cover
        raise AssertionError("refresh não deveria ser chamado")

    def revoke(self, token):  # pragma: no cover
        pass

    def identity(self, access_token):
        return self.identity_value


@pytest.fixture()
def env(conn, dsn, tmp_path, monkeypatch):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)  # noqa: E731
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal H", niche="História", language="pt-BR")
    oauth = OAuthFake()
    monkeypatch.setattr(composition, "build_google_oauth", lambda settings: oauth)
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ={"STUDIO_TEXT": "demo"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "project_id": project.id, "oauth": oauth}


def _connect(env, *, code="code-123"):
    client = env["client"]
    started = client.post("/studio/connections/oauth/start", headers=WORKER_HEADER)
    assert started.status_code == 200, started.text
    state = started.json()["state"]
    done = client.post("/studio/connections/oauth/callback", json={"code": code, "state": state},
                       headers=WORKER_HEADER)
    assert done.status_code == 200, done.text
    return done.json()


def _link_studio_channel(env, profile_id, youtube_channel_id="UC_principal", version=1):
    linked = env["client"].patch(f"/studio/channels/{profile_id}",
                                 json={"expected_version": version, "changes": {"youtube_channel_id": youtube_channel_id}},
                                 headers=WORKER_HEADER)
    assert linked.status_code == 200, linked.text
    return linked.json()


def page(env):
    return env["client"].get("/studio/panel/conexoes", headers=AUTH_HEADER)


def page_text(html: str) -> str:
    stripped = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", stripped).split())


def _without_style_and_script(html: str) -> str:
    return re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)


def nav_items(html: str):
    """Itens da navegação principal da casca V3 (`<nav aria-label="Principal">`)."""
    markup = _without_style_and_script(html)
    match = re.search(r'<nav aria-label="Principal">(.*?)</nav>', markup, re.S)
    assert match is not None, "navegação principal ausente"
    return re.findall(r"<li>(.*?)</li>", match.group(1), re.S)


def settings_nav_items(html: str):
    """Itens da navegação da área de Configurações (Canais/Estilos/Conexões/Equipe)."""
    markup = _without_style_and_script(html)
    match = re.search(r'<nav aria-label="Seções de configuração">(.*?)</nav>', markup, re.S)
    assert match is not None, "navegação de configurações ausente"
    return re.findall(r"<li>(.*?)</li>", match.group(1), re.S)


def _nav_text(item: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", item).split())


# ------------------------------------------------------------------ contrato


def test_connections_empty_state_teaches_the_next_step(env):
    r = page(env)
    assert r.status_code == 200, r.text
    visible = page_text(r.text)
    assert "Nenhuma conta conectada" in visible
    assert "Conectar conta Google" in visible
    # §6: o vazio diz o que será pedido (os escopos, em linguagem clara)
    assert "youtube.upload" in visible and "youtube.readonly" in visible
    assert "O que será pedido" in visible
    assert_ux_contract(r.text, page="conexoes/vazio")


def test_connections_page_with_real_data_satisfies_the_ux_contract(env):
    consent = _connect(env)
    created = env["client"].post(f"/studio/projects/{env['project_id']}/channels",
                                 json={"name": "História"}, headers=WORKER_HEADER)
    assert created.status_code == 201, created.text
    _link_studio_channel(env, created.json()["id"])
    r = page(env)
    assert r.status_code == 200, r.text
    assert_ux_contract(r.text, page="conexoes/com-dados")
    assert consent["grant_id"]


# ------------------------------------------------------- conta → canais


def test_connections_page_shows_account_channels_and_studio_destination(env):
    _connect(env)
    created = env["client"].post(f"/studio/projects/{env['project_id']}/channels",
                                 json={"name": "História"}, headers=WORKER_HEADER)
    _link_studio_channel(env, created.json()["id"])
    visible = page_text(page(env).text)
    assert "EU@gmail.com" in visible
    assert "Canal principal" in visible and "UC_principal" in visible
    assert "Conectado" in visible
    assert "Publica em:" in visible and "História" in visible


def test_connections_page_empty_account_says_no_channel_authorized(env):
    _connect(env)
    visible = page_text(page(env).text)
    assert "EU@gmail.com" in visible
    # sem canal do estúdio vinculado, o destino é dito — nunca inventado
    assert "Nenhum canal do estúdio publica aqui ainda." in visible


def test_connections_page_never_invents_preview_or_percentage(env):
    _connect(env)
    html = page(env).text
    visible = page_text(html)
    assert "preview" not in visible.lower()
    assert "%" not in visible
    assert 'role="progressbar"' not in html and "<progress" not in html


def test_connections_page_escapes_xss_from_real_data(env):
    env["oauth"].identity_value = OAuthIdentity(channel_id="UC_xss", title="Nome <script>alert(1)</script>",
                                                email="EU@gmail.com")
    _connect(env)
    html = page(env).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# ------------------------------------------------------------------- menu


def test_connections_page_keeps_the_active_channel_in_the_topbar(env):
    html = page(env).text
    assert 'id="canal-ativo"' in html
    assert "Canal H" in html
    assert "Nenhum canal cadastrado" not in html


def test_connections_page_menu_has_conexoes_active_in_gestao(env):
    html = page(env).text
    items = nav_items(html)
    # W1.5: menu do protótipo (rótulos novos + Biblioteca) e nenhum item falso-ativo nesta tela.
    assert [_nav_text(i) for i in items] == ["Início", "Criar vídeo", "Vídeos", "Tendências e ideias",
                                            "Desempenho", "Biblioteca"]
    assert not [item for item in items if 'aria-current="page"' in item]
    # A entrada ativa é Configurações, no rodapé da casca.
    config_nav = re.search(r'<nav aria-label="Configuração">(.*?)</nav>', html, re.S).group(1)
    config_active = re.search(r'<a href="/studio/configuracoes/canais[^"]*" aria-current="page"', config_nav)
    assert config_active is not None
    # A tela Conexões é o item ativo da navegação de configurações.
    sections = settings_nav_items(html)
    section_active = [item for item in sections if 'aria-current="page"' in item]
    assert len(section_active) == 1 and "Conexões" in _nav_text(section_active[0])
    assert re.search(r'href="/studio/panel/conexoes(?:\?project_id=[^"]+)?"', section_active[0])
    assert _without_style_and_script(html).count('aria-current="page"') == 2
    # As sete seções do protótipo seguem como destinos reais; nada de "Configurações — em breve".
    assert [_nav_text(item) for item in sections] == [
        "Canais", "Estratégia editorial", "Marca e estilo", "Produção e orçamento",
        "Conexões e providers", "Conta e equipe", "Avançado e diagnóstico"]
    assert "em breve" not in html
    assert not any('aria-disabled="true"' in item for item in items + sections)


# -------------------------------------------------- confirmação antes do vínculo


def test_connections_page_confirms_the_channel_before_linking(env):
    _connect(env)
    html = page(env).text
    # A confirmação (nome + id do canal do YouTube) aparece ANTES do controle de vínculo.
    confirm_marker = "Confira o destino antes de vincular"
    assert confirm_marker in html
    assert html.index(confirm_marker) < html.index("data-link")
    confirm_index = html.index(confirm_marker)
    tail = html[confirm_index:html.index("data-link")]
    assert "Canal principal" in tail and "UC_principal" in tail
    # O vínculo é uma seleção rotulada, não um formulário solto.
    assert 'for="sel-UC_principal"' in html
    assert 'aria-describedby="sel-UC_principal-hint"' in html


def test_connections_page_destructive_actions_confirm_in_a_dialog(env):
    _connect(env)
    created = env["client"].post(f"/studio/projects/{env['project_id']}/channels",
                                 json={"name": "História"}, headers=WORKER_HEADER)
    _link_studio_channel(env, created.json()["id"])
    html = page(env).text
    assert "<dialog" in html and 'id="confirm-dialog"' in html
    assert 'role="status"' in html and 'aria-live="polite"' in html
    # Revogar e desvincular existem, e ambos passam pela confirmação (ação destrutiva).
    assert "data-revoke" in html and "Revogar autorização" in html
    assert "data-unlink" in html and "Desvincular" in html
    # O botão seguro recebe o foco inicial; a confirmação só destrói com escolha explícita.
    assert 'value="cancel" class="btn autofocus' in html or 'class="btn" autofocus' in html
    assert 'value="confirm"' in html


# --------------------------------------------------- retorno do OAuth na página


def test_connections_page_treats_the_oauth_return_via_query_string(env):
    html = page(env).text
    # A página conclui o consentimento pela API e trata o retorno (query string) — sem echo do code/state.
    assert "/studio/connections/oauth/callback" in html
    assert "connections/oauth/start" in html
    assert "URLSearchParams" in html and "location.search" in html
    assert "conectado" in html


def test_connections_page_links_through_the_existing_route(env):
    _connect(env)
    html = page(env).text
    # O vínculo usa o `PATCH /channels` já existente; não há rota nova para vincular.
    assert "'/studio/channels/' + encodeURIComponent(profileId)" in html
    assert "expected_version" in html


# ------------------------------------------------------------------ higiene


def test_connections_page_never_leaks_tokens(env):
    _connect(env)
    html = page(env).text
    assert ACCESS not in html and REFRESH not in html


def test_connections_page_preserves_csp_and_no_store(env):
    r = page(env)
    assert r.status_code == 200
    assert "nonce-" in r.headers["Content-Security-Policy"]
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_connections_page_requires_authentication(env):
    assert env["client"].get("/studio/panel/conexoes").status_code == 401
