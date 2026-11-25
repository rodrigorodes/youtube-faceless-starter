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


def seed_script(env):
    """Vídeo com roteiro longo já persistido (versão 1, SCRIPTED), pronto para edição."""
    video = seed_video(env)
    env["snaps"].add(video.id, "https://example.com/x", SOURCE)
    env["scripts"].save_planned_version(video.id, "texto", drafts(), [CID], PLAN, H1,
                                        VideoStatus.IDEA, VideoStatus.SCRIPTED)
    return video


def edited_narration(marker: str) -> str:
    """Narração com a mesma duração aproximada das cenas do seed, mas texto distinto."""
    return ("ha " * 100).strip() + f" {marker}."


def count(env, sql: str, params: tuple) -> int:
    """Contagem numa transação nova: enxerga o commit feito pela API em outra conexão."""
    env["conn"].rollback()
    return env["conn"].execute(sql, params).fetchone()[0]


def post_edit(env, video, scene_idx: int, key: str, *, expected_version: int = 1,
              narration: str | None = None, **extra):
    body = {"expected_version": expected_version,
            "narration": narration or edited_narration("cena editada"),
            "idempotency_key": key, **extra}
    return env["client"].post(f"/studio/videos/{video.id}/script/scenes/{scene_idx}",
                              json=body, headers=POST_HEADER)


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
    """A tela de Roteiro entra pela casca aprovada (UX V3), não por uma <aside> própria.

    Antes ela hardcodava a barra lateral (marca + nav reduzida). Agora usa
    `api.shell_v3.render_document`, a mesma casca de todas as telas.
    """
    video = seed_video(env)
    r = env["client"].get(f"/studio/videos/{video.id}/roteiro", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert '<aside class="side"' in r.text and '<main class="main">' in r.text
    assert "Faceless Studio" in r.text and "Menu principal" in r.text

    markup = re.sub(r"<(style|script)\b.*?</\1>", "", r.text, flags=re.S)
    nav = re.search(r'<nav aria-label="Principal">(.*?)</nav>', markup, re.S)
    assert nav is not None, "roteiro sem a navegação principal da casca"
    labels = " ".join(re.sub(r"<span aria-hidden.*?</span>|<[^>]+>", " ", nav.group(1)).split())
    for expected in ("Início", "Criar vídeo", "Vídeos", "Tendências e ideias", "Desempenho"):
        assert expected in labels, f"roteiro: '{expected}' fora da casca"

    assert markup.count('aria-current="page"') == 1
    videos_item = next(li for li in re.findall(r"<li>(.*?)</li>", nav.group(1), re.S) if "Vídeos" in li)
    assert 'aria-current="page"' in videos_item


def test_roteiro_page_preserves_csp(env):
    video = seed_video(env)
    r = env["client"].get(f"/studio/videos/{video.id}/roteiro", headers=AUTH_HEADER)
    assert r.status_code == 200
    csp = r.headers["Content-Security-Policy"]
    assert "nonce-" in csp and "no-store" in r.headers.get("Cache-Control", "")


# ---------------------------------------------------------------------------
# W4.1 (EDIT-01): edição de cena com CAS + idempotência
# ---------------------------------------------------------------------------


def test_script_scene_edit_requires_an_idempotency_key(env):
    video = seed_script(env)
    r = env["client"].post(f"/studio/videos/{video.id}/script/scenes/0",
                           json={"expected_version": 1, "narration": edited_narration("sem chave")},
                           headers=POST_HEADER)
    assert r.status_code == 400
    assert "Idempotency-Key" in r.json()["detail"]


def test_script_scene_edit_rejects_a_non_canonical_idempotency_key(env):
    video = seed_script(env)
    r = env["client"].post(f"/studio/videos/{video.id}/script/scenes/0",
                           json={"expected_version": 1, "narration": edited_narration("chave inválida")},
                           headers={**POST_HEADER, "Idempotency-Key": "Not Canonical"})
    assert r.status_code == 422


def test_script_scene_edit_cas_replay_and_key_conflict(env):
    video = seed_script(env)
    key = "edit-zero"
    first = post_edit(env, video, 0, key, narration=edited_narration("cena alfa"))
    assert first.status_code == 200
    payload = first.json()
    assert payload["script"]["version"] == 2
    assert payload["scenes"][0]["narration"] == edited_narration("cena alfa")

    # replay da mesma chave + mesmo payload devolve o resultado gravado, sem criar versão nova
    replay = post_edit(env, video, 0, key, narration=edited_narration("cena alfa"))
    assert replay.status_code == 200 and replay.json() == payload
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 2
    assert count(env, "SELECT count(*) FROM studio.script_edit_requests WHERE video_id=%s", (video.id,)) == 1

    # mesma chave com payload diferente é conflito, não replay
    conflict = post_edit(env, video, 0, key, narration=edited_narration("cena beta"))
    assert conflict.status_code == 409
    assert "different payload" in conflict.json()["detail"]

    # CAS: a versão 1 já não é a mais recente; a segunda aba recebe 409 acionável
    stale = post_edit(env, video, 0, "edit-stale", narration=edited_narration("cena gama"))
    assert stale.status_code == 409
    assert "2" in stale.json()["detail"]
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 2
    assert count(env, "SELECT count(*) FROM studio.script_edit_requests WHERE video_id=%s", (video.id,)) == 1


def test_second_tab_same_version_is_rejected_and_writes_nothing(env):
    video = seed_script(env)
    first = post_edit(env, video, 0, "tab-a", narration=edited_narration("aba a"))
    assert first.status_code == 200

    second = post_edit(env, video, 1, "tab-b", narration=edited_narration("aba b"))
    assert second.status_code == 409
    assert "2" in second.json()["detail"]
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 2
    assert count(env, "SELECT count(*) FROM studio.script_edit_requests WHERE video_id=%s", (video.id,)) == 1
    # o texto da aba perdedora não foi persistido: o servidor recusou antes de escrever
    assert env["scripts"].scenes(video.id)[1].narration == drafts()[1].narration


def test_add_remove_reorder_keep_scene_identity(env):
    video = seed_script(env)
    original = [s.id for s in env["scripts"].scenes(video.id)]
    assert len(original) == 12

    added = env["client"].post(
        f"/studio/videos/{video.id}/script/scenes",
        json={"expected_version": 1, "idempotency_key": "add-1", "position": 2,
              "narration": edited_narration("cena adicionada"), "caption": "Legenda",
              "label": "CEN", "image_prompt": "wide empty stage with colored lights",
              "claim_ids": [CID]}, headers=POST_HEADER)
    assert added.status_code == 200
    after_add = added.json()["scenes"]
    assert len(after_add) == 13
    new_id = after_add[2]["id"]
    assert new_id not in original
    assert [s["id"] for s in after_add if s["id"] in original] == original

    removed = env["client"].request(
        "DELETE", f"/studio/videos/{video.id}/script/scenes/2",
        json={"expected_version": 2, "idempotency_key": "remove-1"}, headers=POST_HEADER)
    assert removed.status_code == 200
    after_remove = removed.json()["scenes"]
    assert [s["id"] for s in after_remove] == original
    assert new_id not in {s["id"] for s in after_remove}

    order = [1, 0] + list(range(2, 12))
    reordered = env["client"].post(
        f"/studio/videos/{video.id}/script/scenes/reorder",
        json={"expected_version": 3, "idempotency_key": "reorder-1", "order": order},
        headers=POST_HEADER)
    assert reordered.status_code == 200
    after_reorder = reordered.json()["scenes"]
    assert [s["id"] for s in after_reorder] == [original[i] for i in order]
    assert [s["idx"] for s in after_reorder] == list(range(12))


def test_invalid_reorder_is_rejected_without_writing(env):
    video = seed_script(env)
    r = env["client"].post(
        f"/studio/videos/{video.id}/script/scenes/reorder",
        json={"expected_version": 1, "idempotency_key": "bad-reorder", "order": [0, 0, 2]},
        headers=POST_HEADER)
    assert r.status_code == 422
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 1
    assert count(env, "SELECT count(*) FROM studio.script_edit_requests WHERE video_id=%s", (video.id,)) == 0


def test_edit_that_fails_review_writes_nothing(env):
    video = seed_script(env)
    bad = ("ha " * 100).strip() + " 987654."
    r = post_edit(env, video, 0, "bad-review", narration=bad)
    assert r.status_code == 502
    assert "review" in r.json()["detail"].lower()
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 1
    assert count(env, "SELECT count(*) FROM studio.script_plans WHERE video_id=%s", (video.id,)) == 1
    assert count(env, "SELECT count(*) FROM studio.script_edit_requests WHERE video_id=%s", (video.id,)) == 0

    # a chave não foi consumida: corrigir o texto com a mesma chave pode gravar
    fixed = post_edit(env, video, 0, "bad-review", narration=edited_narration("texto corrigido"))
    assert fixed.status_code == 200
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 2


def test_editing_is_refused_outside_idea_and_scripted(env):
    video = seed_script(env)
    env["conn"].execute("UPDATE studio.videos SET status='FACT_CHECKED' WHERE id=%s", (video.id,))
    env["conn"].commit()
    r = post_edit(env, video, 0, "state-conflict", narration=edited_narration("estado"))
    assert r.status_code == 409
    assert "IDEA/SCRIPTED" in r.json()["detail"]
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 1


# ---------------------------------------------------------------------------
# W4.5 (EDIT-04): histórico recuperável e "restaurar cria nova revisão"
# ---------------------------------------------------------------------------


def _assign_assets(env, scene_ids):
    asset_ids = []
    for i, scene_id in enumerate(scene_ids):
        asset_id = f"{i + 1:032x}"
        env["conn"].execute(
            "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) "
            "VALUES (%s, 'image', %s, %s, 'p', 'm', 'CC0')",
            (asset_id, f"{i + 1:064x}", f"cache/{i}.png"),
        )
        env["conn"].execute("UPDATE studio.scenes SET asset_id = %s WHERE id = %s", (asset_id, scene_id))
        asset_ids.append(asset_id)
    env["conn"].commit()
    return asset_ids


def test_script_revision_routes_list_read_and_restore(env):
    video = seed_script(env)
    scene_ids = [s.id for s in env["scripts"].scenes(video.id)]
    assets = _assign_assets(env, scene_ids)

    # v2 pela rota de edição: a cena 2 muda e a v1 vira histórico com a mídia congelada.
    edit = post_edit(env, video, 2, "rev-edit", narration=edited_narration("cena reescrita"))
    assert edit.status_code == 200

    listing = env["client"].get(f"/studio/videos/{video.id}/script/revisions", headers=AUTH_HEADER)
    assert listing.status_code == 200
    data = listing.json()
    assert [r["version"] for r in data] == [1, 2]
    assert data[0]["superseded"] is True and data[0]["restorable"] is True
    assert data[1]["current"] is True and data[1]["restorable"] is True

    revision = env["client"].get(f"/studio/videos/{video.id}/script/revisions/1", headers=AUTH_HEADER)
    assert revision.status_code == 200
    scenes = revision.json()["scenes"]
    assert [s["narration"] for s in scenes] == [d.narration for d in drafts()]
    assert [s["asset_id"] for s in scenes] == assets
    assert all(s["media_review_required"] is False for s in scenes)

    restore = env["client"].post(
        f"/studio/videos/{video.id}/script/revisions/1/restore",
        json={"expected_version": 2, "idempotency_key": "restore-api"}, headers=POST_HEADER)
    assert restore.status_code == 200
    payload = restore.json()
    assert payload["script"]["version"] == 3
    assert [s["narration"] for s in payload["scenes"]] == [d.narration for d in drafts()]
    assert [s["idx"] for s in payload["scenes"]] == list(range(12))
    assert [s["asset_id"] for s in payload["scenes"]] == assets
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 3

    # replay da mesma chave não cria versão nova; a mesma chave com outra revisão é conflito.
    replay = env["client"].post(
        f"/studio/videos/{video.id}/script/revisions/1/restore",
        json={"expected_version": 2, "idempotency_key": "restore-api"}, headers=POST_HEADER)
    assert replay.status_code == 200 and replay.json()["script"]["version"] == 3
    conflict = env["client"].post(
        f"/studio/videos/{video.id}/script/revisions/2/restore",
        json={"expected_version": 3, "idempotency_key": "restore-api"}, headers=POST_HEADER)
    assert conflict.status_code == 409
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 3


def test_restore_route_requires_key_and_reports_a_missing_snapshot(env):
    video = seed_script(env)
    no_key = env["client"].post(
        f"/studio/videos/{video.id}/script/revisions/1/restore",
        json={"expected_version": 1}, headers=POST_HEADER)
    assert no_key.status_code == 400

    post_edit(env, video, 0, "mk-v2", narration=edited_narration("cena nova"))
    env["conn"].execute("DELETE FROM studio.scene_revisions WHERE video_id=%s AND version=1", (video.id,))
    env["conn"].commit()
    legacy = env["client"].post(
        f"/studio/videos/{video.id}/script/revisions/1/restore",
        json={"expected_version": 2, "idempotency_key": "legacy-revision"}, headers=POST_HEADER)
    assert legacy.status_code == 409
    assert "snapshot" in legacy.json()["detail"]
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 2


# ---- roteiro curto (sem plano de capítulos): texto, inclusão, exclusão e ordem também são editáveis ----------

SHORT_TEXTS = ["O canal cresceu 42 por cento no ano passado.", "Esse crescimento mudou o mercado inteiro.",
               "O mercado inteiro mudou depois disso."]


def seed_short(env):
    """Short com roteiro gerado pelas fontes (`save_and_advance`): versão 1, SCRIPTED e nenhum plano."""
    video = env["videos"].create_video(env["project"].id, "Tema curto", VideoFormat.short)
    env["snaps"].add(video.id, "https://example.com/x", SOURCE)
    env["scripts"].save_and_advance(
        video.id, "\n".join(SHORT_TEXTS),
        [SceneDraft(t, "Legenda", "CEN", "wide empty stage with colored lights", [CID]) for t in SHORT_TEXTS],
        [CID], VideoStatus.IDEA, VideoStatus.SCRIPTED)
    return video


def test_short_script_scene_text_can_be_edited_without_a_plan(env):
    video = seed_short(env)
    ids = [s.id for s in env["scripts"].scenes(video.id)]
    r = post_edit(env, video, 0, "short-edit-1", narration="O canal cresceu 42 por cento e virou referência.")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["script"]["version"] == 2 and body["scenes"][0]["narration"].endswith("virou referência.")
    assert [s["id"] for s in body["scenes"]] == ids  # a cena editada mantém a identidade
    assert count(env, "SELECT count(*) FROM studio.script_plans WHERE video_id=%s", (video.id,)) == 0
    replay = post_edit(env, video, 0, "short-edit-1", narration="O canal cresceu 42 por cento e virou referência.")
    assert replay.status_code == 200 and replay.json()["script"]["version"] == 2
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 2


def test_short_script_accepts_add_remove_and_reorder(env):
    video = seed_short(env)
    original = [s.id for s in env["scripts"].scenes(video.id)]
    added = env["client"].post(
        f"/studio/videos/{video.id}/script/scenes",
        json={"expected_version": 1, "idempotency_key": "short-add", "position": 1,
              "narration": "O mercado inteiro mudou depois do canal.", "caption": "", "label": "NOVA",
              "image_prompt": "wide empty stage with colored lights", "claim_ids": [CID]}, headers=POST_HEADER)
    assert added.status_code == 200, added.text
    scenes = added.json()["scenes"]
    assert len(scenes) == 4 and scenes[1]["label"] == "NOVA" and scenes[1]["id"] not in original

    reordered = env["client"].post(
        f"/studio/videos/{video.id}/script/scenes/reorder",
        json={"expected_version": 2, "idempotency_key": "short-reorder", "order": [3, 0, 1, 2]}, headers=POST_HEADER)
    assert reordered.status_code == 200, reordered.text
    assert reordered.json()["scenes"][0]["id"] == scenes[3]["id"]

    removed = env["client"].request(
        "DELETE", f"/studio/videos/{video.id}/script/scenes/1",
        json={"expected_version": 3, "idempotency_key": "short-remove"}, headers=POST_HEADER)
    assert removed.status_code == 200 and len(removed.json()["scenes"]) == 3
    assert count(env, "SELECT count(*) FROM studio.script_plans WHERE video_id=%s", (video.id,)) == 0


def test_short_script_edit_with_text_unsupported_by_the_sources_writes_nothing(env):
    video = seed_short(env)
    r = post_edit(env, video, 0, "short-bad", narration="O canal cresceu 987654 por cento no ano passado.")
    assert r.status_code == 502 and "sources" in r.json()["detail"].lower()
    assert count(env, "SELECT count(*) FROM studio.scripts WHERE video_id=%s", (video.id,)) == 1
    assert count(env, "SELECT count(*) FROM studio.script_edit_requests WHERE video_id=%s", (video.id,)) == 0


def test_short_script_edit_cites_the_facts_that_support_the_new_text(env):
    """Bug (E2E real): editar o texto para outro fato das fontes mantinha a citação antiga e o fact-check reprovava."""
    video = env["videos"].create_video(env["project"].id, "Tema curto", VideoFormat.short)
    source = ("Constantinopla caiu em 29 de maio de 1453 depois de um cerco de 53 dias. "
              "O sultão Mehmed II comandava cerca de 80 mil soldados otomanos.")
    env["snaps"].add(video.id, "https://example.com/x", source)
    from app.studio.application.editorial import _claims
    claims = _claims(env["snaps"].list(video.id))
    first, second = claims[0], claims[1]
    texts = [first.text, "A cidade resistiu por semanas ao cerco."]
    env["scripts"].save_and_advance(
        video.id, "\n".join(texts),
        [SceneDraft(t, "Legenda", "CEN", "wide empty stage with colored lights", [first.id]) for t in texts],
        [first.id], VideoStatus.IDEA, VideoStatus.SCRIPTED)

    r = post_edit(env, video, 1, "cite-1", narration="O sultão Mehmed II comandava cerca de 80 mil soldados otomanos.")
    assert r.status_code == 200, r.text
    scenes = env["scripts"].scenes(video.id)
    assert scenes[1].claim_ids == [second.id]  # a citação acompanhou o texto novo
    assert scenes[0].claim_ids == [first.id]  # a outra cena não mudou
    # o texto editado agora passa no mesmo critério do fact-check (conferido só contra o fato citado)
    from app.studio.domain.facts import check_narration
    assert check_narration(scenes[1].narration, [second.text]) == []
