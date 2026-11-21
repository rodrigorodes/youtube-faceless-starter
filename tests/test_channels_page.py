"""Tela de Canais (F10) no painel: consome o backend da fatia H com honestidade.

Fonte de verdade visual: `produto/tela-canais.html` (aprovado em 2026-11-20). As regras canônicas
de UX vivem em `test_ux_contract.assert_ux_contract` e são aplicadas à tela inteira. Onde o mockup
mostra dado ilustrativo, a tela renderiza dado real do Studio ou estado vazio explícito.
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
from psycopg.types.json import Jsonb  # noqa: E402

from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from test_ux_contract import assert_ux_contract  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
POST_HEADER = {**AUTH_HEADER, "Origin": "http://testserver"}


def _app(conn, dsn, tmp_path, *, with_project: bool = True):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal H", niche="História", language="pt-BR") if with_project else None
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path, paid_image_usd=0.31),
                    environ={"STUDIO_TEXT": "demo"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "videos": videos, "project": project, "conn": conn,
            "dsn": dsn, "connect": connect}


@pytest.fixture()
def env(conn, dsn, tmp_path):
    return _app(conn, dsn, tmp_path)


@pytest.fixture()
def env_empty(conn, dsn, tmp_path):
    return _app(conn, dsn, tmp_path, with_project=False)


def page(env, project_id=None):
    pid = project_id if project_id is not None else env["project"].id
    return env["client"].get(f"/studio/canais?project_id={pid}", headers=AUTH_HEADER)


def page_text(html: str) -> str:
    stripped = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", stripped).split())


def nav_items(html: str):
    match = re.search(r'<nav class="nav" aria-label="Principal">(.*?)</nav>', html, re.S)
    assert match is not None, "navegação principal ausente"
    return re.findall(r"<li>(.*?)</li>", match.group(1), re.S)


def _nav_text(item: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", item).split())


def _seed_profile(env, **changes):
    payload = {"name": "História", "strategy": "Narrativa cronológica",
               "language": "pt-BR", "audience": "Adultos curiosos",
               "pillars": ["Roma", "Egito"], "visual_identity": "Grafite e âmbar",
               "voice": "piper:pt_BR-faber-medium"}
    payload.update(changes)
    r = env["client"].post(f"/studio/projects/{env['project'].id}/channels", json=payload,
                           headers=POST_HEADER)
    assert r.status_code == 201, r.text
    return r.json()


def _seed_usage(env):
    conn = env["conn"]
    video = env["videos"].create_video(env["project"].id, "Tema com custo", VideoFormat.short)
    rows = (
        ("ACTUAL", 0.11, 0.11),
        ("ESTIMATE", 0.03, 0.03),
        ("FREE", 0.0, 0.0),
    )
    for kind, cost, confirmed in rows:
        conn.execute(
            "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd, "
            "cost_confirmation_kind, cost_confirmed_amount, cost_confirmation_reference, "
            "cost_confirmed_by, cost_confirmed_at) "
            "VALUES (%s, 'text', 'demo', 'demo', %s, %s, %s, 'ref', 'tester', now())",
            (video.id, cost, kind, confirmed),
        )
    conn.execute(
        "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
        "VALUES (%s, 'text', 'legado', 'legado', 0)",
        (video.id,),
    )
    conn.commit()


# ------------------------------------------------------------------ contrato UX


def test_channels_empty_state_satisfies_the_ux_contract(env):
    r = page(env)
    assert r.status_code == 200, r.text
    assert_ux_contract(r.text, page="canais/vazio")


def test_channels_page_with_real_data_satisfies_the_ux_contract(env):
    _seed_profile(env)
    env["client"].put(f"/studio/projects/{env['project'].id}/budget",
                      json={"hard_monthly_usd": "20", "soft_monthly_usd": "10",
                            "hard_video_usd": "4", "soft_video_usd": "2"},
                      headers=POST_HEADER)
    env["client"].put(f"/studio/projects/{env['project'].id}/youtube-channel",
                      json={"channel_id": "UC123", "title": "Canal H",
                            "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
                            "refresh_token": "1//refresh-secret"},
                      headers=POST_HEADER)
    _seed_usage(env)
    r = page(env)
    assert r.status_code == 200, r.text
    assert_ux_contract(r.text, page="canais/com-dados")


def test_channels_state_badges_carry_real_text_not_only_an_icon(env):
    _seed_profile(env)
    html = page(env).text
    bodies = re.findall(r'<span class="state s-[a-z]+"[^>]*>(.*?)</span>', html, re.S)
    assert bodies
    for body in bodies:
        assert re.search(r"[A-Za-zÀ-ÿ]{3,}", body), body


def test_channels_page_uses_the_approved_shell(env):
    html = page(env).text
    items = nav_items(html)
    active = [item for item in items if 'aria-current="page"' in item]
    assert len(active) == 1
    assert "Canais" in _nav_text(active[0])
    assert active[0].lstrip().startswith("<a ")
    assert 'href="/studio/canais"' in active[0]
    assert html.count('aria-current="page"') == 1
    assert html.count("<h1") == 1
    assert "<h1" in html and "Canais" in re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1)


def test_channels_page_marks_unavailable_nav_items_as_non_focusable(env):
    html = page(env).text
    for item in nav_items(html):
        if 'aria-disabled="true"' in item:
            assert not item.lstrip().startswith(("<a ", "<button")), item


# ------------------------------------------------------------------ identidade


def test_channels_without_profile_shows_explicit_empty_state(env):
    html = page(env).text
    visible = page_text(html)
    assert "Nenhum perfil de canal registrado" in visible
    assert "channel_v" not in visible
    for forbidden in ("Finanças pessoais explicadas sem jargão", "Adultos curiosos, sem formação técnica",
                      "Paleta grafite+violeta", "Educação long-form (8–12 min)",
                      "pt-BR · Piper"):
        assert forbidden not in visible


def test_channels_renders_real_profile_and_version(env):
    profile = _seed_profile(env)
    html = page(env).text
    visible = page_text(html)
    assert profile["id"][:4] in html  # id real só na seção avançada
    assert "História" in visible
    assert "channel_v1" in visible
    assert 'value="Narrativa cronológica"' in html
    assert 'value="Roma, Egito"' in html
    assert 'value="Grafite e âmbar"' in html
    assert 'value="piper:pt_BR-faber-medium"' in html
    assert "Cada alteração cria uma versão auditável" in visible

    patched = env["client"].patch(f"/studio/channels/{profile['id']}",
                                  json={"expected_version": 1, "changes": {'strategy': 'Diálogo comparado',
                                                                           'target_duration_s': 480}},
                                  headers=POST_HEADER)
    assert patched.status_code == 200, patched.text
    updated_html = page(env).text
    assert "channel_v2" in page_text(updated_html)
    assert 'value="Diálogo comparado"' in updated_html


def test_channels_shows_niche_as_read_only_and_does_not_fake_editable_field(env):
    html = page(env).text
    visible = page_text(html)
    assert "História" in visible  # nicho do projeto é real
    assert "Definido na criação do canal" in visible
    assert 'id="nicho"' not in html


# -------------------------------------------------------------------- providers


def test_providers_show_capability_cost_rate_limit_and_honest_availability(env):
    html = page(env).text
    visible = page_text(html)
    assert "Providers por tarefa" in visible
    # disponível de verdade: o catálogo registra a implementação local validada
    assert "Disponível" in visible
    assert "Capability" in visible
    assert "text.generate" in visible
    assert "Sem custo" in visible
    # sem implementação validada: UNAVAILABLE com motivo explícito, nunca fingindo
    assert "Indisponível" in visible
    assert "OPENCODE_BRIDGE_TOKEN ausente" in visible
    assert "Custo estimado não é preço cobrado" in visible


def test_unavailable_provider_test_command_is_not_focusable(env):
    html = page(env).text
    # o provider de imagem (opencode sem bridge) está indisponível: sem botão focável
    segment = re.search(r'data-provider-kind="image".*?(?=data-provider-kind="voice")', html, re.S)
    assert segment is not None
    assert "Testar conexão" in segment.group(0)
    assert "<button" not in segment.group(0)
    assert 'aria-disabled="true"' in segment.group(0)


def test_available_provider_has_a_real_connection_test_control(env):
    html = page(env).text
    segment = re.search(r'data-provider-kind="text".*?(?=data-provider-kind="image")', html, re.S)
    assert segment is not None
    assert 'data-test-provider="text"' in segment.group(0)
    assert "/providers/test" in html


def test_routing_is_derived_from_the_economic_profile(env):
    env["client"].put(f"/studio/projects/{env['project'].id}/budget",
                      json={"hard_monthly_usd": "20", "soft_monthly_usd": "10",
                            "hard_video_usd": "4", "soft_video_usd": "2",
                            "economic_profile": "ECONOMY"},
                      headers=POST_HEADER)
    visible = page_text(page(env).text)
    assert "ECONOMY" in visible
    assert "Escolha no perfil" in visible
    assert "demo" in visible


# ---------------------------------------------------------------------- budget


def test_budget_without_persisted_row_is_explicit_and_never_zero(env):
    html = page(env).text
    visible = page_text(html)
    assert "Nenhum limite de canal persistido" in visible
    assert "padrão do servidor" in visible
    assert "Sem registro de uso" in visible
    assert "US$ 0,00" not in html
    assert "role=\"progressbar\"" not in html


def test_budget_renders_real_limits_and_roundtrips(env):
    r = env["client"].put(f"/studio/projects/{env['project'].id}/budget",
                          json={"hard_monthly_usd": "20", "soft_monthly_usd": "10",
                                "hard_video_usd": "4", "soft_video_usd": "2"},
                          headers=POST_HEADER)
    assert r.status_code == 200, r.text
    html = page(env).text
    visible = page_text(html)
    assert "20,00" in visible and "10,00" in visible and "4,00" in visible and "2,00" in visible
    assert "Limite hard mensal" in visible and "Limite soft mensal" in visible
    assert "US$ 0,00" not in html


def test_budget_summary_keeps_real_estimate_free_and_unknown_apart(env):
    _seed_usage(env)
    visible = page_text(page(env).text)
    assert "Real US$ 0,11" in visible
    assert "Estimado US$ 0,03" in visible
    assert "Sem custo em 1 chamada(s)" in visible
    assert "Desconhecido em 1 chamada(s)" in visible


# --------------------------------------------------------------------- youtube


def test_youtube_disconnected_state_and_unimplemented_oauth_are_explicit(env):
    html = page(env).text
    visible = page_text(html)
    assert "Sem associação" in visible
    assert "DISCONNECTED" in html
    assert "OAuth" in visible
    assert "não está implementado" in visible
    # sem botão de reautorizar fingindo um fluxo que não existe
    assert "Ir para o consentimento" not in visible


def test_youtube_status_never_exposes_the_secret(env):
    assoc = env["client"].put(
        f"/studio/projects/{env['project'].id}/youtube-channel",
        json={"channel_id": "UC123", "title": "Canal H",
              "scopes": ["https://www.googleapis.com/auth/youtube.upload",
                         "https://www.googleapis.com/auth/yt-analytics.readonly"],
              "access_token": "ya29.synthetic-access-value",
              "refresh_token": "1//refresh-secret"},
        headers=POST_HEADER)
    assert assoc.status_code == 200, assoc.text
    html = page(env).text
    visible = page_text(html)
    assert "Conectado" in visible
    assert "UC123" in html and "Canal H" in visible
    assert "youtube.upload" in visible and "yt-analytics.readonly" in visible
    for secret in ("ya29.", "refresh-secret"):
        assert secret not in html
    # a máscara do mockup não existe no backend: nenhum valor de credencial é inventado
    assert "••••" not in html and "7f2a" not in html
    assert "nenhum valor de credencial" in visible.lower()


def test_youtube_expired_token_is_reported_by_state(env):
    env["client"].put(
        f"/studio/projects/{env['project'].id}/youtube-channel",
        json={"channel_id": "UC123", "title": "Canal H", "refresh_token": "1//refresh-secret",
              "token_expires_at": "2020-01-01T00:00:00+00:00"},
        headers=POST_HEADER)
    visible = page_text(page(env).text)
    assert "Expirado" in visible


# ------------------------------------------------------------------ config/segredos


def test_project_config_is_sanitized_and_advanced_details_is_closed(env):
    env["conn"].execute(
        "UPDATE studio.projects SET config = %s WHERE id = %s",
        (Jsonb({"text": "demo", "OPENAI_API_KEY": "sk-live-LEAK-VALUE"}), env["project"].id),
    )
    env["conn"].commit()
    html = page(env).text
    assert "sk-live-LEAK-VALUE" not in html and "OPENAI_API_KEY" not in html
    assert "demo" in html
    assert "<details open" not in html
    assert 'class="advanced"' in html


# ------------------------------------------------------------------ higiene/erros


def test_channels_page_escapes_xss_from_real_data(env):
    _seed_profile(env, name="Canal <script>alert(1)</script>", strategy="<b>forte</b>")
    html = page(env).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<b>forte</b>" not in html


def test_channels_page_preserves_csp_and_no_store(env):
    r = page(env)
    assert r.status_code == 200
    assert "nonce-" in r.headers["Content-Security-Policy"]
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_channels_page_without_any_project_is_explicit(env_empty):
    r = env_empty["client"].get("/studio/canais", headers=AUTH_HEADER)
    assert r.status_code == 200, r.text
    assert "Nenhum canal cadastrado" in page_text(r.text)
    assert_ux_contract(r.text, page="canais/sem-canal")


def test_channels_page_requires_authentication(env):
    assert env["client"].get("/studio/canais").status_code == 401


def test_unknown_project_id_is_404(env):
    r = env["client"].get("/studio/canais?project_id=" + "0" * 32, headers=AUTH_HEADER)
    assert r.status_code == 404


def test_channels_page_never_leaks_illustrative_mockup_text(env):
    _seed_profile(env)
    html = page(env).text
    for leaked in ("Finanças Descomplicadas", "1,2 mi views", "run_7f31", "840 mil views",
                   "8–12 min", "Educação long-form", "Shorts de descoberta",
                   "Finanças pessoais explicadas sem jargão", "Adultos curiosos, sem formação técnica",
                   "Paleta grafite+violeta", "pt-BR-faber-medium", "gpt-5-mini", "51 min", "7f2a"):
        assert leaked not in html, leaked