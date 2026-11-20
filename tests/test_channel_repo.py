"""Testes de integração do repositório Postgres de perfis de canal (banco descartável)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.channel_repo import PostgresChannelProfileRepository  # noqa: E402
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.domain.channel import (  # noqa: E402
    ChannelNameInvalid,
    ChannelProfile,
    ChannelVersionConflict,
    DuplicateChannelProfile,
)


@pytest.fixture()
def chan_env(conn, dsn):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    repo = PostgresChannelProfileRepository(connect)
    project = videos.create_project("Canal História", niche="História", language="pt-BR")
    return {"repo": repo, "project_id": project.id, "conn": conn, "connect": connect, "videos": videos}


def test_create_and_read_profile(chan_env):
    repo = chan_env["repo"]
    p_id = chan_env["project_id"]

    created = repo.create(
        p_id,
        "História sem Fim",
        strategy="narrativa cronológica",
        language="pt-BR",
        audience="adultos curiosos",
        pillars=["Idade Média", "Roma"],
        narrative="tom documental",
        target_duration_s=480,
        visual_identity="sépia",
        voice="piper:pt_BR-faber-medium",
        audio="música épica",
        thumbnail="rosto em close",
        cta="inscreva-se",
    )

    assert isinstance(created, ChannelProfile)
    assert len(created.id) == 32
    assert created.project_id == p_id
    assert created.name == "História sem Fim"
    assert created.pillars == ["Idade Média", "Roma"]
    assert created.target_duration_s == 480
    assert created.version == 1
    assert created.archived is False
    assert created.created_at is not None
    assert created.updated_at is not None

    by_id = repo.get(created.id)
    by_project = repo.get_by_project(p_id)
    assert by_id is not None and by_project is not None
    assert by_id == by_project == created


def test_get_missing_returns_none(chan_env):
    repo = chan_env["repo"]
    assert repo.get("0" * 32) is None
    assert repo.get_by_project("0" * 32) is None


def test_duplicate_project_profile_raises(chan_env):
    repo = chan_env["repo"]
    p_id = chan_env["project_id"]
    repo.create(p_id, "Canal")
    with pytest.raises(DuplicateChannelProfile):
        repo.create(p_id, "Outro")


def test_same_name_in_different_projects_allowed(chan_env):
    repo = chan_env["repo"]
    videos = chan_env["videos"]
    p1 = chan_env["project_id"]
    p2 = videos.create_project("Canal Finanças", niche="Finanças").id
    a = repo.create(p1, "Geral")
    b = repo.create(p2, "Geral")
    assert a.id != b.id and a.name == b.name == "Geral"


def test_invalid_name_rejected_before_writing(chan_env):
    repo = chan_env["repo"]
    p_id = chan_env["project_id"]
    for bad in ("", "   ", "x" * 121):
        with pytest.raises(ChannelNameInvalid):
            repo.create(p_id, bad)
    assert repo.list(include_archived=True) == []


def test_list_filters_and_orders(chan_env):
    repo = chan_env["repo"]
    videos = chan_env["videos"]

    assert repo.list() == []

    # um perfil por canal (projeto): nomes distintos exigem canais distintos
    repo.create(videos.create_project("Canal Zebra").id, "Zebra")
    repo.create(videos.create_project("Canal Alpha").id, "Alpha")
    other = repo.create(videos.create_project("Canal Meio").id, "Meio")
    archived = repo.create(videos.create_project("Canal Antigo").id, "Antigo", archived=True)

    active = repo.list()
    assert [p.name for p in active] == ["Alpha", "Meio", "Zebra"]
    assert other in active
    assert archived not in active
    assert archived in repo.list(include_archived=True)


def test_update_bumps_version_and_writes_revision(chan_env):
    repo = chan_env["repo"]
    conn = chan_env["conn"]
    p_id = chan_env["project_id"]

    created = repo.create(p_id, "Canal", strategy="antiga")
    updated = repo.update(
        created.id,
        created.version,
        {"name": "Canal Novo", "strategy": "nova", "target_duration_s": 240, "archived": True},
    )

    assert updated is not None
    assert updated.id == created.id
    assert updated.project_id == p_id
    assert updated.name == "Canal Novo"
    assert updated.strategy == "nova"
    assert updated.target_duration_s == 240
    assert updated.archived is True
    assert updated.version == 2
    assert updated.created_at == created.created_at
    assert updated.updated_at is not None

    assert repo.get(created.id) == updated

    rows = conn.execute(
        "SELECT version, snapshot->>'name', snapshot->>'version' "
        "FROM studio.channel_profile_revisions WHERE profile_id = %s ORDER BY version",
        (created.id,),
    ).fetchall()
    assert rows == [(1, "Canal", "1"), (2, "Canal Novo", "2")]


def test_update_with_stale_version_raises(chan_env):
    repo = chan_env["repo"]
    p_id = chan_env["project_id"]
    created = repo.create(p_id, "Canal")
    repo.update(created.id, created.version, {"name": "Canal 2"})
    with pytest.raises(ChannelVersionConflict):
        repo.update(created.id, created.version, {"name": "Canal 3"})
    assert repo.get(created.id).version == 2


def test_update_missing_profile_returns_none(chan_env):
    repo = chan_env["repo"]
    assert repo.update("0" * 32, 1, {"name": "x"}) is None


def test_update_validates_changes(chan_env):
    repo = chan_env["repo"]
    p_id = chan_env["project_id"]
    created = repo.create(p_id, "Canal")
    with pytest.raises(ValueError):
        repo.update(created.id, created.version, {"unknown": 1})
    with pytest.raises(ChannelNameInvalid):
        repo.update(created.id, created.version, {"name": ""})
    assert repo.get(created.id) == created


def test_create_requires_existing_project(chan_env):
    repo = chan_env["repo"]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repo.create("9" * 32, "Fantasma")
