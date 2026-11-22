"""Persistência do roteiro longo: plano/hash atômicos, aprovação por versão e propagação (F4-06/F4-08)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.editorial_repo import (  # noqa: E402
    PostgresFactCheckRepository, PostgresScriptRepository, PostgresSnapshotRepository,
)
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.application.errors import ScriptEditIdempotencyConflict  # noqa: E402
from app.studio.application.ports import SceneDraft  # noqa: E402
from app.studio.domain.contracts import FactCheckReport, VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.longform import Block, Chapter, ScriptPlan, approval_is_current  # noqa: E402

H1, H2 = "a" * 64, "b" * 64
PLAN = ScriptPlan(words_per_minute=150, target_seconds=480, chapters=(
    Chapter(title="Abertura", block=Block.HOOK, scene_count=2, target_seconds=80),
    Chapter(title="Contexto", block=Block.CONTEXT, scene_count=3, target_seconds=120),
    Chapter(title="Desenvolvimento", block=Block.DEVELOPMENT, scene_count=5, target_seconds=200),
    Chapter(title="Fecho", block=Block.CTA, scene_count=2, target_seconds=80),
))
DRAFTS = [SceneDraft(f"Narracao valida numero {i}.", "Legenda", "CEN", "wide empty stage with colored lights", ["c1"])
          for i in range(12)]


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("canal").id, "Tema longo", VideoFormat.long)
    return {"connect": connect, "conn": conn, "video": video, "videos": videos,
            "scripts": PostgresScriptRepository(connect), "snaps": PostgresSnapshotRepository(connect),
            "checks": PostgresFactCheckRepository(connect)}


def status(env):
    env["conn"].commit()
    return env["conn"].execute("SELECT status FROM studio.videos WHERE id=%s", (env["video"].id,)).fetchone()[0]


def test_plan_and_hash_are_saved_with_the_version(env):
    scripts, v = env["scripts"], env["video"].id
    script = scripts.save_planned_version(v, "t1", DRAFTS, ["c1"], PLAN, H1, VideoStatus.IDEA, VideoStatus.SCRIPTED)
    assert script.version == 1 and status(env) == "SCRIPTED"
    records = scripts.list_script_records(v)
    assert len(records) == 1
    assert records[0].content_hash == H1
    assert records[0].plan is not None and len(records[0].plan.chapters) == 4
    assert records[0].plan.chapters[0].block.value == "hook"
    assert records[0].approval is None
    assert len(scripts.scenes(v)) == 12


def test_approval_is_bound_to_version_and_hash(env):
    scripts, v = env["scripts"], env["video"].id
    scripts.save_planned_version(v, "t1", DRAFTS, ["c1"], PLAN, H1, VideoStatus.IDEA, VideoStatus.SCRIPTED)
    assert scripts.approve(v, 1, H1, "approved", "", "operador") is True
    records = scripts.list_script_records(v)
    assert records[0].approval is not None and records[0].approval.decision == "approved"
    assert approval_is_current(records[0].approval, version=1, content_hash=H1)

    scripts.save_planned_version(v, "t2", DRAFTS, ["c1"], PLAN, H2, VideoStatus.SCRIPTED, VideoStatus.SCRIPTED)
    # a v2 substitui a v1: aprovar a v1 ou com hash antigo deixa de ser possível
    assert scripts.approve(v, 1, H1, "approved", "", "operador") is False
    assert scripts.approve(v, 2, H1, "approved", "", "operador") is False
    assert scripts.approve(v, 2, H2, "approved", "", "operador") is True
    records = scripts.list_script_records(v)
    assert [r.script.version for r in records] == [1, 2]
    assert records[0].approval is not None  # histórico preservado (auditoria)
    assert records[1].approval is not None and records[1].approval.script_version == 2
    assert not approval_is_current(records[0].approval, version=2, content_hash=H2)


def test_new_version_keeps_scene_ids_and_sources(env):
    scripts, v = env["scripts"], env["video"].id
    env["snaps"].add(v, "https://example.com/x", "A fonte original com 42 por cento de crescimento.")
    scripts.save_planned_version(v, "t1", DRAFTS, ["c1"], PLAN, H1, VideoStatus.IDEA, VideoStatus.SCRIPTED)
    first_scene_ids = [s.id for s in scripts.scenes(v)]
    scripts.save_planned_version(v, "t2", DRAFTS, ["c1"], PLAN, H2, VideoStatus.SCRIPTED, VideoStatus.SCRIPTED)
    second_scene_ids = [s.id for s in scripts.scenes(v)]
    assert len(second_scene_ids) == 12 and second_scene_ids == first_scene_ids  # cenas não recriadas
    assert len(env["snaps"].list(v)) == 1  # fonte não é reescrita nem apagada


def test_fact_check_latest_returns_the_checked_version(env):
    scripts, checks, v = env["scripts"], env["checks"], env["video"].id
    scripts.save_planned_version(v, "t1", DRAFTS, ["c1"], PLAN, H1, VideoStatus.IDEA, VideoStatus.SCRIPTED)
    assert checks.latest(v) is None
    checks.save(v, FactCheckReport(passed=True), advance=True, script_version=1)
    record = checks.latest(v)
    assert record is not None and record.script_version == 1 and record.report.passed


def test_rejected_approval_keeps_the_reason(env):
    scripts, v = env["scripts"], env["video"].id
    scripts.save_planned_version(v, "t1", DRAFTS, ["c1"], PLAN, H1, VideoStatus.IDEA, VideoStatus.SCRIPTED)
    assert scripts.approve(v, 1, H1, "rejected", "faltou fechar o payoff", "operador") is True
    approval = scripts.list_script_records(v)[0].approval
    assert approval.decision == "rejected" and approval.reason == "faltou fechar o payoff"


# ---------------------------------------------------------------------------
# W4.1 (EDIT-01): CAS + idempotência por chave + hash de payload
# ---------------------------------------------------------------------------


def _seed(env):
    v = env["video"].id
    env["scripts"].save_planned_version(v, "t1", DRAFTS, ["c1"], PLAN, H1,
                                        VideoStatus.IDEA, VideoStatus.SCRIPTED)
    return v


def _save_edit(env, v, key, digest, drafts, *, expected_version=1, plan=PLAN, content_hash=H2):
    return env["scripts"].save_edit(v, key, digest, expected_version, "t2", drafts, ["c1"], plan,
                                    content_hash, VideoStatus.SCRIPTED, VideoStatus.SCRIPTED)


def test_save_edit_replays_same_key_and_rejects_other_payload(env):
    v = _seed(env)
    digest = "a" * 64
    first = _save_edit(env, v, "edit-1", digest, DRAFTS)
    assert first is not None and first.script.version == 2
    assert len(first.scenes) == 12

    record = env["scripts"].find_edit(v, "edit-1")
    assert record is not None and record.payload_sha256 == digest

    replay = _save_edit(env, v, "edit-1", digest, DRAFTS)
    assert replay is not None and replay.script.id == first.script.id
    assert replay.script.version == 2
    assert [s.id for s in replay.scenes] == [s.id for s in first.scenes]
    assert len(env["scripts"].list_script_records(v)) == 2

    with pytest.raises(ScriptEditIdempotencyConflict):
        _save_edit(env, v, "edit-1", "b" * 64, DRAFTS)
    assert len(env["scripts"].list_script_records(v)) == 2


def test_save_edit_is_cas_and_writes_nothing_when_stale(env):
    v = _seed(env)
    assert _save_edit(env, v, "edit-1", "a" * 64, DRAFTS) is not None

    assert _save_edit(env, v, "edit-2", "b" * 64, DRAFTS) is None
    assert env["scripts"].find_edit(v, "edit-2") is None
    assert len(env["scripts"].list_script_records(v)) == 2
    assert len(env["scripts"].scenes(v)) == 12


def test_save_edit_returns_none_when_status_is_not_expected(env):
    v = _seed(env)
    assert env["scripts"].save_edit(v, "edit-x", "a" * 64, 1, "t", DRAFTS, ["c1"], PLAN, H2,
                                    VideoStatus.IDEA, VideoStatus.SCRIPTED) is None
    assert env["scripts"].find_edit(v, "edit-x") is None
    assert len(env["scripts"].list_script_records(v)) == 1


def test_save_edit_keeps_scene_identity_for_add_remove_and_reorder(env):
    v = _seed(env)
    original = [s.id for s in env["scripts"].scenes(v)]

    added = list(DRAFTS)
    added.insert(2, SceneDraft("Nova cena com 42 por cento de crescimento.", "Legenda", "CEN",
                               "wide empty stage with colored lights", ["c1"]))
    assert _save_edit(env, v, "add-1", "a" * 64, added) is not None
    after_add = [s.id for s in env["scripts"].scenes(v)]
    assert len(after_add) == 13 and after_add[2] not in original
    assert [sid for sid in after_add if sid in original] == original

    assert _save_edit(env, v, "remove-1", "b" * 64, DRAFTS, expected_version=2) is not None
    assert [s.id for s in env["scripts"].scenes(v)] == original

    order = [1, 0] + list(range(2, 12))
    reordered = [DRAFTS[i] for i in order]
    assert _save_edit(env, v, "reorder-1", "c" * 64, reordered, expected_version=3) is not None
    assert [s.id for s in env["scripts"].scenes(v)] == [original[1], original[0]] + original[2:]
