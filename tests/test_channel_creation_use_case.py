import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate
from app.studio.application.channel_creation import (
    CreateChannelTransactional,
    ChannelCreationPayload,
    IdempotencyConflict,
)
from app.studio.domain.contracts import ProductionMode, VideoFormat


@pytest.fixture()
def uc_env(conn, dsn):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    uc = CreateChannelTransactional(connect)
    return {"uc": uc, "conn": conn}


def test_create_channel_transactional_success(uc_env):
    payload = ChannelCreationPayload(
        name="Canal História V3",
        niche="História",
        language="pt-BR",
        strategy="Estratégia clara",
        default_mode=ProductionMode.diretor,
        default_format=VideoFormat.long,
        hard_monthly_usd=20.0,
        soft_monthly_usd=10.0,
        hard_video_usd=2.0,
        soft_video_usd=1.0,
    )
    result = uc_env["uc"].execute(payload, idempotency_key="key-001")
    assert result.project.id
    assert result.project.name == "Canal História V3"
    assert result.profile.default_mode is ProductionMode.diretor
    assert result.profile.default_format is VideoFormat.long
    assert result.budget.hard_monthly_usd == 20.0

    # Replay com a mesma chave e mesmo payload -> idempotente
    replay = uc_env["uc"].execute(payload, idempotency_key="key-001")
    assert replay.project.id == result.project.id
    assert replay.profile.id == result.profile.id
    assert replay.budget.project_id == result.project.id


def test_create_channel_transactional_idempotency_conflict(uc_env):
    payload1 = ChannelCreationPayload(name="Canal 1", niche="Nicho 1")
    payload2 = ChannelCreationPayload(name="Canal 2 (divergente)", niche="Nicho 1")
    uc_env["uc"].execute(payload1, idempotency_key="key-conflict")
    with pytest.raises(IdempotencyConflict):
        uc_env["uc"].execute(payload2, idempotency_key="key-conflict")


def test_create_channel_transactional_rolls_back_on_error(uc_env):
    payload = ChannelCreationPayload(
        name="Canal que vai falhar",
        hard_monthly_usd=-50.0,  # Orçamento negativo viola constraint e causa erro
    )
    with pytest.raises(Exception):
        uc_env["uc"].execute(payload)

    # Verifica que não criou projeto no banco
    rows = uc_env["conn"].execute("SELECT id FROM studio.projects WHERE name='Canal que vai falhar'").fetchall()
    assert len(rows) == 0


def test_create_channel_transactional_with_provider_config(uc_env):
    payload = ChannelCreationPayload(
        name="Canal com Provider Config",
        niche="Tecnologia",
        provider_config={"text": "opencode:gemini-2.5-pro", "image": "veo:veo-2"},
    )
    result = uc_env["uc"].execute(payload)
    assert result.project.id
    assert result.project.config == {"text": "opencode:gemini-2.5-pro", "image": "veo:veo-2"}


def test_create_channel_transactional_creates_profile_revision(uc_env):
    payload = ChannelCreationPayload(
        name="Canal Revision Check",
        pillars=("Ciência", "Física"),
    )
    result = uc_env["uc"].execute(payload)
    rows = uc_env["conn"].execute(
        "SELECT version, snapshot FROM studio.channel_profile_revisions WHERE profile_id = %s",
        (result.profile.id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1


def test_use_cases_wiring_exposes_create_channel_transactional(dsn, tmp_path):
    from app.studio.composition.wiring import Studio
    from app.studio.composition.settings import Settings

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    cases = studio.use_cases()
    assert cases is not None
    assert cases.create_channel_transactional is not None
    assert isinstance(cases.create_channel_transactional, CreateChannelTransactional)

