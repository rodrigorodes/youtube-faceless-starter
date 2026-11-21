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


def test_new_version_replaces_scenes_and_keeps_sources(env):
    scripts, v = env["scripts"], env["video"].id
    env["snaps"].add(v, "https://example.com/x", "A fonte original com 42 por cento de crescimento.")
    scripts.save_planned_version(v, "t1", DRAFTS, ["c1"], PLAN, H1, VideoStatus.IDEA, VideoStatus.SCRIPTED)
    first_scene_ids = {s.id for s in scripts.scenes(v)}
    scripts.save_planned_version(v, "t2", DRAFTS, ["c1"], PLAN, H2, VideoStatus.SCRIPTED, VideoStatus.SCRIPTED)
    second_scene_ids = {s.id for s in scripts.scenes(v)}
    assert len(second_scene_ids) == 12 and first_scene_ids.isdisjoint(second_scene_ids)  # cenas substituídas
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
