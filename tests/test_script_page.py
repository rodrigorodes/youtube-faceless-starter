"""Tela de Roteiro (F4-07): dado real ou estado vazio explícito, aprovação por versão.

Nenhum texto ilustrativo do mockup pode vazar para o HTML; sem roteiro, o painel
mostra estado vazio, nunca números inventados nem barra de progresso.
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
from app.studio.adapters.postgres.editorial_repo import (  # noqa: E402
    PostgresFactCheckRepository, PostgresScriptRepository, PostgresSnapshotRepository,
)
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.application.ports import SceneDraft  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.claims import extract_claims  # noqa: E402
from app.studio.domain.contracts import FactCheckReport, VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.longform import Block, Chapter, ScriptPlan  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
POST_HEADER = {**AUTH_HEADER, "Origin": "http://testserver"}
H1, H2 = "a" * 64, "b" * 64
SOURCE = "O canal cresceu 42 por cento no ano passado e esse crescimento mudou o mercado inteiro."
CID = extract_claims("s" * 32, SOURCE)[0].id
PLAN = ScriptPlan(words_per_minute=150, target_seconds=480, chapters=(
    Chapter(title="Abertura", block=Block.HOOK, scene_count=2, target_seconds=80),
    Chapter(title="Contexto", block=Block.CONTEXT, scene_count=3, target_seconds=120),
    Chapter(title="Desenvolvimento", block=Block.DEVELOPMENT, scene_count=5, target_seconds=200),
    Chapter(title="Fecho", block=Block.CTA, scene_count=2, target_seconds=80),
))


def drafts(n=12, title="cena"):
    return [SceneDraft(("ha " * 100).strip() + f" {title} {chr(ord('a') + i)}.", "Legenda", "CEN",
                       "wide empty stage with colored lights", [CID]) for i in range(n)]


@pytest.fixture()
def env(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Roteiro")
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "videos": videos, "project": project, "conn": conn,
            "scripts": PostgresScriptRepository(connect), "snaps": PostgresSnapshotRepository(connect),
            "checks": PostgresFactCheckRepository(connect)}


def seed_video(env, topic="Tema longo"):
    return env["videos"].create_video(env["project"].id, topic, VideoFormat.long)


def page_text(html: str) -> str:
    stripped = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", stripped).split())


def test_roteiro_empty_state_is_explicit(env):
    video = seed_video(env)
    r = env["client"].get(f"/studio/videos/{video.id}/roteiro", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Nenhum roteiro registrado para este vídeo" in r.text
    visible = page_text(r.text)
    for forbidden in ("Onde o dinheiro entra", "Assinaturas e API", "1 min 48 s", "8 min 12 s",
                      "US$ 0,07", "script_v1", "2 claims verificados", "62%"):
        assert forbidden not in visible
    assert "%" not in visible
    assert 'role="progressbar"' not in r.text and "<progress" not in r.text


def test_roteiro_renders_real_chapters_durations_and_versions(env):
    video = seed_video(env)
    env["snaps"].add(video.id, "https://example.com/x", SOURCE)
    env["scripts"].save_planned_version(video.id, "texto", drafts(), [CID], PLAN, H1,
                                        VideoStatus.IDEA, VideoStatus.SCRIPTED)
    env["checks"].save(video.id, FactCheckReport(passed=True), advance=True, script_version=1)
    r = env["client"].get(f"/studio/videos/{video.id}/roteiro", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Versão 1" in r.text
    assert "4 capítulos · 12 cenas" in r.text
    for chapter in ("Abertura", "Contexto", "Desenvolvimento", "Fecho"):
        assert chapter in r.text
    assert "Gancho" in r.text and "CTA" in r.text
    assert "8 min 5 s" in r.text or "8 min" in r.text  # duração real (12 x ~40 s), não a do mockup
    assert "8 min 12 s" not in page_text(r.text)
    assert "script_v1" in r.text and "atual" in r.text
    assert H1[:6] in r.text  # hash real exibido encurtado
    assert "<details" in r.text
    assert "fact-check aprovado" in page_text(r.text)
    assert "Aguardando sua aprovação" in r.text


def test_roteiro_approval_binds_to_version_and_editing_supersedes(env):
    video = seed_video(env)
    env["snaps"].add(video.id, "https://example.com/x", SOURCE)
    env["scripts"].save_planned_version(video.id, "texto", drafts(), [CID], PLAN, H1,
                                        VideoStatus.IDEA, VideoStatus.SCRIPTED)
    env["checks"].save(video.id, FactCheckReport(passed=True), advance=True, script_version=1)

    ok = env["client"].post(f"/studio/videos/{video.id}/script/approve",
                            json={"version": 1, "content_hash": H1}, headers=POST_HEADER)
    assert ok.status_code == 200 and ok.json()["decision"] == "approved"
    approved_page = env["client"].get(f"/studio/videos/{video.id}/roteiro", headers=AUTH_HEADER)
    assert "Versão aprovada" in approved_page.text

    # simula o rewind da produção: nova versão substitui a anterior
    env["conn"].execute("UPDATE studio.videos SET status='SCRIPTED' WHERE id=%s", (video.id,))
    env["conn"].commit()
    env["scripts"].save_planned_version(video.id, "texto 2", drafts(title="novo"), ["c1"], PLAN, H2,
                                        VideoStatus.SCRIPTED, VideoStatus.SCRIPTED)
    updated = env["client"].get(f"/studio/videos/{video.id}/roteiro", headers=AUTH_HEADER)
    assert updated.status_code == 200 and "Versão 2" in updated.text
    assert "Aguardando sua aprovação" in updated.text
    assert "aprovada (superada)" in updated.text

    stale_version = env["client"].post(f"/studio/videos/{video.id}/script/approve",
                                       json={"version": 1, "content_hash": H1}, headers=POST_HEADER)
    assert stale_version.status_code == 409
    stale_hash = env["client"].post(f"/studio/videos/{video.id}/script/approve",
                                    json={"version": 2, "content_hash": H1}, headers=POST_HEADER)
    assert stale_hash.status_code == 409


def test_roteiro_approval_without_fact_check_is_refused(env):
    video = seed_video(env)
    env["snaps"].add(video.id, "https://example.com/x", SOURCE)
    env["scripts"].save_planned_version(video.id, "texto", drafts(), [CID], PLAN, H1,
                                        VideoStatus.IDEA, VideoStatus.SCRIPTED)
    r = env["client"].post(f"/studio/videos/{video.id}/script/approve",
                           json={"version": 1, "content_hash": H1}, headers=POST_HEADER)
    assert r.status_code == 422


def test_roteiro_escapes_xss_in_chapter_title(env):
    video = seed_video(env)
    env["snaps"].add(video.id, "https://example.com/x", SOURCE)
    evil = ScriptPlan(words_per_minute=150, target_seconds=480, chapters=(
        Chapter(title="<script>alert(1)</script>", block=Block.HOOK, scene_count=2, target_seconds=80),
        Chapter(title="Contexto", block=Block.CONTEXT, scene_count=3, target_seconds=120),
        Chapter(title="Desenvolvimento", block=Block.DEVELOPMENT, scene_count=5, target_seconds=200),
        Chapter(title="Fecho", block=Block.CTA, scene_count=2, target_seconds=80),
    ))
    env["scripts"].save_planned_version(video.id, "texto", drafts(), [CID], evil, H1,
                                        VideoStatus.IDEA, VideoStatus.SCRIPTED)
    r = env["client"].get(f"/studio/videos/{video.id}/roteiro", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    assert "innerHTML" not in r.text


def test_roteiro_page_uses_the_shared_shell(env):
    """A tela de Roteiro entra pela casca aprovada, não por uma <aside> própria.

    Antes ela hardcodava a barra lateral (marca + nav reduzida). Agora usa
    `api.panel.render_sidebar`, a mesma casca de todas as telas.
    """
    video = seed_video(env)
    r = env["client"].get(f"/studio/videos/{video.id}/roteiro", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert '<aside class="sidebar" aria-label="Barra lateral">' in r.text
    assert "Faceless Studio V2" in r.text and "YouTube Automation" in r.text

    nav = re.search(r'<nav class="nav" aria-label="Principal">(.*?)</nav>', r.text, re.S)
    assert nav is not None, "roteiro sem a navegação principal da casca"
    labels = " ".join(re.sub(r"<[^>]+>", " ", nav.group(1)).split())
    for expected in ("Início", "Produção", "Tendências", "Vídeos", "Analytics", "Canais", "Equipe"):
        assert expected in labels, f"roteiro: '{expected}' fora da casca"

    assert r.text.count('aria-current="page"') == 1
    videos_item = next(li for li in re.findall(r"<li>(.*?)</li>", nav.group(1), re.S) if "Vídeos" in li)
    assert 'aria-current="page"' in videos_item


def test_roteiro_page_preserves_csp(env):
    video = seed_video(env)
    r = env["client"].get(f"/studio/videos/{video.id}/roteiro", headers=AUTH_HEADER)
    assert r.status_code == 200
    csp = r.headers["Content-Security-Policy"]
    assert "nonce-" in csp and "no-store" in r.headers.get("Cache-Control", "")
