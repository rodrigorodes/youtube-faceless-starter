"""HTTP F9: página de Analytics, coleta, decisão de recomendação e experimentos.

Contra o Studio real (Postgres descartável), com o contrato de UX canônico aplicado. O que se
prova: a tela entra pela casca aprovada, o vazio é explícito, a decisão não altera o canal e
a coleta sem publicação não grava número.
"""
import base64
import re
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.studio.adapters.postgres.analytics_learning_repo import (
    PostgresAnalyticsLearningRepository,
)
from app.studio.adapters.postgres.db import migrate
from app.studio.api.routes import make_router
from app.studio.composition import Settings, Studio
from app.studio.domain.analytics_learning import (
    MetricMeasurement,
    MissingVersionLink,
    VersionAttribution,
)
from app.studio.domain.insight import MetricObservation, MetricWindow
from conftest import verified_test_connect

from test_ux_contract import assert_ux_contract

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
POST_HEADERS = {**AUTH_HEADER, "Origin": "http://testserver"}

PROJECT = "1" * 32
VIDEOS = ("2" * 32, "3" * 32, "4" * 32)
CATEGORY = "5" * 32
CHANNEL = "UC1234567890abcdefghij"


def now():
    return datetime.now(timezone.utc)


@pytest.fixture()
def env(conn, dsn, tmp_path):
    migrate(conn)
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "conn": conn, "dsn": dsn, "studio": studio,
            "tmp": tmp_path}


def create_project(env, videos=(), *, published=True):
    conn = env["conn"]
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'Canal Real')", (PROJECT,))
    conn.execute("INSERT INTO studio.project_categories(id, project_id, name) "
                 "VALUES (%s, %s, 'Finanças')", (CATEGORY, PROJECT))
    for index, video_id in enumerate(videos):
        conn.execute("INSERT INTO studio.videos(id, project_id, topic, format, status) "
                     "VALUES (%s, %s, %s, 'long', 'PUBLISHED')",
                     (video_id, PROJECT, f"Tema real {index + 1}"))
        conn.execute("INSERT INTO studio.scripts(id, video_id, version, text) "
                     "VALUES (%s, %s, 1, 'roteiro')", (f"{index + 6:032x}", video_id))
        if published:
            conn.execute("INSERT INTO studio.publications(id, video_id, youtube_video_id, status) "
                         "VALUES (%s, %s, %s, 'UPLOADED')",
                         (f"{index + 9:032x}", video_id, f"AbCdEf1234{index}"))
    conn.execute("INSERT INTO studio.channel_youtube_channels "
                 "(project_id, channel_id, scopes, oauth_status) VALUES (%s, %s, %s, 'CONNECTED')",
                 (PROJECT, CHANNEL, '["yt-analytics.readonly"]'))
    conn.commit()


def seed_views(env, video_ids=VIDEOS, values=(100.0, 200.0, 300.0)):
    proof = __import__("os").environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    repo = PostgresAnalyticsLearningRepository(lambda: verified_test_connect(env["dsn"], proof))
    end = now() - timedelta(hours=1)
    window = MetricWindow(start_at=end - timedelta(days=1), end_at=end)
    rows = []
    for index, (video_id, value) in enumerate(zip(video_ids, values)):
        missing = (MissingVersionLink(kind="brief", reason="briefing não persistido"),
                   MissingVersionLink(kind="packaging", reason="embalagem não persistida"))
        attribution = VersionAttribution(
            video_id=video_id, script_version=1,
            publication_id=f"{index + 9:032x}", youtube_video_id=f"AbCdEf1234{index}",
            missing=missing)
        observation = MetricObservation(
            observation_id=f"{index + 20:032x}", metric="views", unit="count",
            window=window, source="API YouTube Analytics", collected_at=end,
            state="measured", value=value)
        rows.append(MetricMeasurement(observation=observation,
                                      origin="youtube_analytics_api",
                                      attribution=attribution, pillar_id=CATEGORY))
    repo.save_measurements(PROJECT, rows)


def page(env, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return env["client"].get("/studio/panel/analytics" + (f"?{query}" if query else ""),
                             headers=AUTH_HEADER)


def test_page_requires_auth_and_host_guard(env):
    create_project(env, videos=VIDEOS[:1])
    assert env["client"].get("/studio/panel/analytics").status_code == 401
    assert env["client"].get("/studio/panel/analytics",
                             headers={**AUTH_HEADER, "Host": "evil.com"}).status_code == 403


def test_empty_page_is_explicit_and_satisfies_the_ux_contract(env):
    create_project(env, videos=VIDEOS[:1], published=False)
    r = page(env)
    assert r.status_code == 200
    assert_ux_contract(r.text, page="painel/analytics")
    assert re.search(r"<h1[^>]*>Desempenho</h1>", r.text)

    # UX V3: sem medição a tela é um vazio explícito — nunca 0, estimativa ou percentual.
    assert 'id="desempenho-vazio"' in r.text
    assert "Sem medição neste período" in r.text
    assert "Publique um vídeo e conecte o canal" in r.text
    assert "US$ 0,00" not in r.text


def test_page_never_leaks_mockup_text_or_invents_global_origin(env):
    create_project(env, videos=VIDEOS[:1])
    text = page(env).text
    for leaked in ("1,2 mi views", "840 mil views", "run_7f31", "Finanças Descomplicadas",
                   "dados ilustrativos", "Global"):
        assert leaked not in text, leaked
    assert "US$ 0,00" not in text
    assert "Traceback (most recent call last)" not in text
    assert "<details open" not in text


def _main_nav(html: str) -> str:
    """A navegação principal da casca V3 (`<nav aria-label="Principal">`, sem a classe antiga).

    O CSS também cita `aria-current="page"`; a contagem vale para a marcação, então o
    `<style>`/`<script>` sai antes de contar.
    """
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S)
    match = re.search(r'<nav aria-label="Principal">(.*?)</nav>', markup, re.S)
    assert match is not None, "navegação principal ausente"
    return match.group(1)


def test_page_is_reached_through_the_approved_shell(env):
    create_project(env, videos=VIDEOS[:1])
    r = page(env)
    # UX V3: a casca aprovada é `<aside class="side">` + `<main class="main">`.
    assert '<aside class="side"' in r.text and '<main class="main">' in r.text
    nav = _main_nav(r.text)
    assert nav.count('aria-current="page"') == 1
    active = re.search(r'<a href="/studio/panel/analytics[^"]*" aria-current="page">(.*?)</a>',
                       nav, re.S).group(1)
    assert "Desempenho" in active
    assert 'href="/studio/panel/analytics' in nav


def test_seeded_measurements_render_real_numbers_and_attribution(env):
    create_project(env, videos=VIDEOS)
    seed_views(env)
    r = page(env)
    assert r.status_code == 200
    assert_ux_contract(r.text, page="painel/analytics")
    assert "600" in r.text  # soma de 100+200+300, um formato comparável
    assert "Origem: API YouTube Analytics" in r.text
    assert "Roteiro v1" in r.text
    assert "Briefing não registrado" in r.text
    assert "última coleta" in r.text.lower()
    assert "Amostra insuficiente" not in r.text
    assert "Requer revisão humana" in r.text


def test_short_and_long_are_not_summed_on_the_page(env):
    create_project(env, videos=VIDEOS[:2])
    seed_views(env, video_ids=VIDEOS[:2], values=(10.0, 20.0))
    env["conn"].execute("UPDATE studio.videos SET format='short' WHERE id=%s", (VIDEOS[1],))
    env["conn"].commit()
    r = page(env)
    assert r.status_code == 200
    assert "Long-form" in r.text and "Short" in r.text
    assert ">30<" not in r.text  # a soma proibida entre formatos não aparece


def test_filters_validate_and_reject_foreign_video(env):
    create_project(env, videos=VIDEOS[:1])
    assert page(env, days=14).status_code == 422
    assert page(env, project="bad-id").status_code == 422
    assert page(env, project=PROJECT, video="a" * 32).status_code == 404
    assert page(env, project=PROJECT, video=VIDEOS[0]).status_code == 200


def test_decision_endpoint_records_review_and_never_touches_the_channel(env):
    create_project(env, videos=VIDEOS)
    seed_views(env)
    r = page(env)
    match = re.search(r'data-recommendation-id="([0-9a-f]{32})"', r.text)
    assert match, "recomendação com id determinístico ausente"
    recommendation_id = match.group(1)
    before = env["conn"].execute("SELECT count(*) FROM studio.channel_profiles").fetchone()[0]

    response = env["client"].post(
        f"/studio/panel/analytics/recommendations/{recommendation_id}/decision",
        headers=POST_HEADERS,
        json={"project_id": PROJECT, "decision": "rejected"})
    assert response.status_code == 200
    assert response.json()["applied"] is False
    assert response.json()["decision"] == "rejected"

    after = env["conn"].execute("SELECT count(*) FROM studio.channel_profiles").fetchone()[0]
    assert before == after == 0
    assert "recusada" in page(env).text
    assert "Requer revisão humana" not in page(env).text


def test_decision_endpoint_refuses_invalid_decision_and_unknown_recommendation(env):
    create_project(env, videos=VIDEOS)
    response = env["client"].post(
        "/studio/panel/analytics/recommendations/" + "a" * 32 + "/decision",
        headers=POST_HEADERS, json={"project_id": PROJECT, "decision": "applied"})
    assert response.status_code == 422
    response = env["client"].post(
        "/studio/panel/analytics/recommendations/curto/decision",
        headers=POST_HEADERS, json={"project_id": PROJECT, "decision": "rejected"})
    assert response.status_code == 422


def test_collect_without_publication_returns_an_honest_not_ready_state(env):
    create_project(env, videos=VIDEOS[:1], published=False)
    response = env["client"].post("/studio/analytics/collect", headers=POST_HEADERS,
                                  json={"video_id": VIDEOS[0], "days": 7})
    assert response.status_code == 200
    payload = response.json()
    assert payload["collected"] is False and payload["saved"] == 0
    assert payload["readiness"]["ready"] is False
    assert payload["readiness"]["scope"] == "yt-analytics.readonly"
    assert any("publica" in reason for reason in payload["readiness"]["reasons"])
    assert page(env).status_code == 200
    assert env["conn"].execute(
        "SELECT count(*) FROM studio.metric_observations").fetchone()[0] == 0


def test_experiment_registration_shows_history_and_refuses_platform_ab(env):
    create_project(env, videos=VIDEOS[:1])
    response = env["client"].post("/studio/analytics/experiments", headers=POST_HEADERS, json={
        "project_id": PROJECT, "video_id": VIDEOS[0], "kind": "title", "status": "planned",
        "variants": [{"variant_id": "controle", "label": "Título atual", "is_control": True},
                     {"variant_id": "b", "label": "Título em pergunta"}]})
    assert response.status_code == 201, response.text
    assert response.json()["applied"] is False
    r = page(env)
    assert r.status_code == 200
    assert_ux_contract(r.text, page="painel/analytics/experimento")
    assert "Histórico de experimentos" in r.text
    assert "Planejado" in r.text and "Título atual (controle)" in r.text
    assert "não expõe experimentos A/B" in r.text

    bad = env["client"].post("/studio/analytics/experiments", headers=POST_HEADERS, json={
        "project_id": PROJECT, "video_id": VIDEOS[0], "kind": "title", "status": "planned",
        "platform_ab_supported": True,
        "variants": [{"variant_id": "a", "label": "A", "is_control": True},
                     {"variant_id": "b", "label": "B"}]})
    assert bad.status_code == 422


def test_finished_experiment_without_conclusion_is_refused(env):
    create_project(env, videos=VIDEOS[:1])
    response = env["client"].post("/studio/analytics/experiments", headers=POST_HEADERS, json={
        "project_id": PROJECT, "video_id": VIDEOS[0], "kind": "thumbnail", "status": "finished",
        "variants": [{"variant_id": "a", "label": "A", "is_control": True},
                     {"variant_id": "b", "label": "B"}]})
    assert response.status_code == 422
    assert "Traceback" not in response.text

def test_channel_selector_lists_real_projects_and_switches(env):
    create_project(env, videos=VIDEOS[:1])
    env["conn"].execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'Outro Canal')",
                        ("6" * 32,))
    env["conn"].commit()
    r = page(env)
    # O seletor de canal é o da casca (`#canal-ativo`), não um segundo seletor dentro da página.
    assert 'id="canal-ativo"' in r.text
    assert 'id="analytics-project"' not in r.text
    assert "Canal Real" in r.text and "Outro Canal" in r.text
    # A casca troca o canal por `project_id`; a tela aceita o parâmetro e o endereço antigo.
    other = page(env, project_id="6" * 32)
    assert other.status_code == 200
    assert "Outro Canal" in other.text
    assert "Nenhum vídeo" in other.text or "Nenhuma publicação" in other.text


def test_filters_form_lets_the_user_narrow_by_video_and_pillar(env):
    """ACH-05: os filtros de vídeo/pilar voltaram a ser renderizados e o servidor os aplica."""
    create_project(env, videos=VIDEOS[:2])
    r = page(env)
    assert 'aria-label="Filtrar o dashboard"' in r.text
    assert 'id="analytics-video"' in r.text and 'id="analytics-pillar"' in r.text
    assert 'name="project"' in r.text
    filtered = page(env, video=VIDEOS[0], pillar=CATEGORY)
    assert filtered.status_code == 200
    assert f'<option value="{VIDEOS[0]}" selected>' in filtered.text
    assert f'<option value="{CATEGORY}" selected>' in filtered.text


def test_collect_with_publication_but_no_token_is_refused_by_the_adapter(env):
    create_project(env, videos=VIDEOS[:1])
    response = env["client"].post("/studio/analytics/collect", headers=POST_HEADERS,
                                  json={"video_id": VIDEOS[0], "days": 7})
    assert response.status_code == 200
    payload = response.json()
    assert payload["collected"] is False and payload["saved"] == 0
    assert payload["readiness"]["ready"] is True
    assert "token" in (payload["reason"] or "").lower()
    assert env["conn"].execute(
        "SELECT count(*) FROM studio.metric_observations").fetchone()[0] == 0
