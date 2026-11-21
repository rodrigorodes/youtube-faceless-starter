"""Testes de integração do repositório Postgres de perfis de canal (banco descartável)."""
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.channel_repo import PostgresChannelProfileRepository  # noqa: E402
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.domain.channel import (  # noqa: E402
    MAX_PILLARS,
    ChannelFieldInvalid,
    ChannelLockTimeout,
    ChannelNameInvalid,
    ChannelProfile,
    ChannelProjectNotFound,
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
    return {"repo": repo, "project_id": project.id, "conn": conn, "dsn": dsn, "connect": connect, "videos": videos}


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
    assert created.pillars == ("Idade Média", "Roma")
    assert isinstance(created.pillars, tuple)
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
    with pytest.raises(ChannelProjectNotFound):
        repo.create("9" * 32, "Fantasma")
    assert repo.list(include_archived=True) == []


def test_create_rejects_unknown_option_before_writing(chan_env):
    repo = chan_env["repo"]
    p_id = chan_env["project_id"]
    with pytest.raises(ValueError):
        repo.create(p_id, "Canal", bogus=1)
    assert repo.list(include_archived=True) == []


def test_list_rejects_non_boolean_include_archived(chan_env):
    repo = chan_env["repo"]
    for bad in ("yes", 1, None):
        with pytest.raises(ChannelFieldInvalid):
            repo.list(include_archived=bad)  # type: ignore[arg-type]


def test_db_rejects_more_pillars_than_domain_limit(chan_env):
    repo = chan_env["repo"]
    conn = chan_env["conn"]
    p_id = chan_env["project_id"]
    other_project = chan_env["videos"].create_project("Canal Limite").id

    # controle positivo: exatamente o limite é aceito
    conn.execute(
        "INSERT INTO studio.channel_profiles(id, project_id, name, pillars) VALUES (%s, %s, %s, %s)",
        ("c" * 32, p_id, "No limite", [f"p{i}" for i in range(MAX_PILLARS)]),
    )
    conn.commit()
    assert len(repo.get("c" * 32).pillars) == MAX_PILLARS

    # acima do limite o banco recusa, em vez de truncar no round-trip
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO studio.channel_profiles(id, project_id, name, pillars) VALUES (%s, %s, %s, %s)",
            ("d" * 32, other_project, "Acima do limite", [f"p{i}" for i in range(MAX_PILLARS + 1)]),
        )
    conn.rollback()


def test_update_lock_timeout_is_translated(chan_env):
    p_id = chan_env["project_id"]
    dsn = chan_env["dsn"]
    created = chan_env["repo"].create(p_id, "Canal")

    # conexão separada segura o lock da linha; a conexão do repositório espera e estoura o lock_timeout
    holder = psycopg.connect(dsn)
    try:
        holder.execute("SELECT id FROM studio.channel_profiles WHERE id = %s FOR UPDATE", (created.id,))
        short_lock = lambda: psycopg.connect(dsn, options="-c lock_timeout=200")
        with pytest.raises(ChannelLockTimeout):
            PostgresChannelProfileRepository(short_lock).update(created.id, created.version, {"name": "x"})
    finally:
        holder.rollback()
        holder.close()

    assert chan_env["repo"].get(created.id).version == 1


def test_concurrent_update_has_single_winner(chan_env):
    repo = chan_env["repo"]
    conn = chan_env["conn"]
    p_id = chan_env["project_id"]
    created = repo.create(p_id, "Canal")
    barrier = threading.Barrier(2)

    def worker(name):
        barrier.wait()
        try:
            updated = repo.update(created.id, created.version, {"name": name})
            return ("ok", updated.version)
        except ChannelVersionConflict:
            return ("conflict", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in (pool.submit(worker, "A"), pool.submit(worker, "B"))]

    assert sorted(r[0] for r in results) == ["conflict", "ok"]
    assert [r[1] for r in results if r[0] == "ok"] == [2]
    versions = conn.execute(
        "SELECT version FROM studio.channel_profile_revisions WHERE profile_id = %s ORDER BY version",
        (created.id,),
    ).fetchall()
    assert [v[0] for v in versions] == [1, 2]


def test_concurrent_create_has_single_winner(chan_env):
    repo = chan_env["repo"]
    conn = chan_env["conn"]
    p_id = chan_env["project_id"]
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        try:
            return ("ok", repo.create(p_id, "Canal").id)
        except DuplicateChannelProfile:
            return ("duplicate", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in (pool.submit(worker), pool.submit(worker))]

    assert sorted(r[0] for r in results) == ["duplicate", "ok"]
    assert conn.execute(
        "SELECT count(*) FROM studio.channel_profiles WHERE project_id = %s", (p_id,)
    ).fetchone()[0] == 1


def test_channel_can_point_to_a_visual_style_and_clear_it(chan_env):
    from app.studio.adapters.postgres.visual_style_repo import PostgresVisualStyleRepository
    styles = PostgresVisualStyleRepository(chan_env["connect"])
    style = styles.create("Cinemático", params={"music": {"bpm": 90}})
    created = chan_env["repo"].create(chan_env["project_id"], "História", style_id=style.id)
    assert created.style_id == style.id
    assert chan_env["repo"].get(created.id).style_id == style.id  # persistiu
    cleared = chan_env["repo"].update(created.id, 1, {"style_id": None})
    assert cleared.style_id is None and cleared.version == 2


def test_channel_pointing_to_an_unknown_style_is_refused(chan_env):
    from app.studio.domain.channel import ChannelStyleNotFound
    with pytest.raises(ChannelStyleNotFound):
        chan_env["repo"].create(chan_env["project_id"], "História", style_id="f" * 32)
    profile = chan_env["repo"].create(chan_env["project_id"], "Outro")
    with pytest.raises(ChannelStyleNotFound):
        chan_env["repo"].update(profile.id, 1, {"style_id": "f" * 32})


def test_channel_can_point_to_a_youtube_channel_and_clear_it(chan_env):
    from app.studio.adapters.postgres.youtube_identity_repo import PostgresYouTubeChannelIdentityRepository
    from app.studio.domain.youtube_identity import YouTubeChannelIdentity
    channels = PostgresYouTubeChannelIdentityRepository(chan_env["connect"])
    channels.upsert(YouTubeChannelIdentity(youtube_channel_id="UCabc123", title="História"))

    created = chan_env["repo"].create(chan_env["project_id"], "História", youtube_channel_id="UCabc123")
    assert created.youtube_channel_id == "UCabc123"
    assert chan_env["repo"].get(created.id).youtube_channel_id == "UCabc123"  # persistiu

    cleared = chan_env["repo"].update(created.id, 1, {"youtube_channel_id": None})
    assert cleared.youtube_channel_id is None and cleared.version == 2


def test_channel_pointing_to_an_unknown_youtube_channel_is_refused(chan_env):
    from app.studio.domain.channel import ChannelYouTubeTargetNotFound
    with pytest.raises(ChannelYouTubeTargetNotFound):
        chan_env["repo"].create(chan_env["project_id"], "História", youtube_channel_id="UCinexistente")
    profile = chan_env["repo"].create(chan_env["project_id"], "Outro")
    with pytest.raises(ChannelYouTubeTargetNotFound):
        chan_env["repo"].update(profile.id, 1, {"youtube_channel_id": "UCinexistente"})
    assert chan_env["repo"].get(profile.id).youtube_channel_id is None


def test_deleting_the_youtube_channel_detaches_the_studio_channel(chan_env):
    from app.studio.adapters.postgres.youtube_identity_repo import PostgresYouTubeChannelIdentityRepository
    from app.studio.domain.youtube_identity import YouTubeChannelIdentity
    channels = PostgresYouTubeChannelIdentityRepository(chan_env["connect"])
    channels.upsert(YouTubeChannelIdentity(youtube_channel_id="UCabc123", title="História"))
    created = chan_env["repo"].create(chan_env["project_id"], "História", youtube_channel_id="UCabc123")

    chan_env["conn"].execute("DELETE FROM studio.youtube_channels WHERE youtube_channel_id = %s", ("UCabc123",))
    chan_env["conn"].commit()

    # ON DELETE SET NULL: apagar a identidade do YouTube destaca o canal, não o apaga nem bloqueia
    detached = chan_env["repo"].get(created.id)
    assert detached is not None and detached.youtube_channel_id is None and detached.version == 1
