import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from decimal import Decimal
from app.studio.adapters.postgres.db import migrate
from app.studio.application.channel_creation import (
    CreateChannelTransactional,
    ChannelCreationPayload,
    IdempotencyConflict,
    _payload_hash,
)
from app.studio.domain.channel import ChannelStyleNotFound
from app.studio.domain.channel_budget import BudgetLimitInvalid
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


def test_create_channel_transactional_budget_soft_monthly_exceeds_hard(uc_env):
    payload = ChannelCreationPayload(
        name="Canal Budget Invalido",
        hard_monthly_usd=100.0,
        soft_monthly_usd=150.0,
    )
    with pytest.raises(BudgetLimitInvalid, match="soft_monthly_usd must not exceed hard_monthly_usd"):
        uc_env["uc"].execute(payload)


def test_create_channel_transactional_budget_soft_video_exceeds_hard(uc_env):
    payload = ChannelCreationPayload(
        name="Canal Budget Video Invalido",
        hard_video_usd=10.0,
        soft_video_usd=15.0,
    )
    with pytest.raises(BudgetLimitInvalid, match="soft_video_usd must not exceed hard_video_usd"):
        uc_env["uc"].execute(payload)


def test_create_channel_transactional_invalid_style_id(uc_env):
    payload = ChannelCreationPayload(
        name="Canal Estilo Invalido",
        style_id="deadbeefdeadbeefdeadbeefdeadbeef",
    )
    with pytest.raises(ChannelStyleNotFound, match="visual style 'deadbeefdeadbeefdeadbeefdeadbeef' does not exist"):
        uc_env["uc"].execute(payload)


def test_create_channel_transactional_monetary_normalization_hash(uc_env):
    payload1 = ChannelCreationPayload(
        name="Canal Normalizacao",
        hard_monthly_usd=20,
        soft_monthly_usd=10,
        hard_video_usd=2,
        soft_video_usd=1,
    )
    payload2 = ChannelCreationPayload(
        name="Canal Normalizacao",
        hard_monthly_usd=20.0,
        soft_monthly_usd=10.0,
        hard_video_usd=2.0,
        soft_video_usd=1.0,
    )
    payload3 = ChannelCreationPayload(
        name="Canal Normalizacao",
        hard_monthly_usd=Decimal("20.00"),
        soft_monthly_usd=Decimal("10.00"),
        hard_video_usd=Decimal("2.00"),
        soft_video_usd=Decimal("1.00"),
    )
    h1 = _payload_hash(payload1)
    h2 = _payload_hash(payload2)
    h3 = _payload_hash(payload3)
    assert h1 == h2 == h3

    res1 = uc_env["uc"].execute(payload1, idempotency_key="key-norm-01")
    # Replay usando payload com float 20.0 deve reconhecer mesmo hash e devolver replay
    res2 = uc_env["uc"].execute(payload2, idempotency_key="key-norm-01")
    assert res1.project.id == res2.project.id


def test_create_channel_transactional_concurrent_unique_violation_replays_cleanly(uc_env):
    payload = ChannelCreationPayload(name="Canal Concorrente Replay", niche="Tech")
    key = "concurrent-race-key"

    # Criar primeiro o registro com a chave
    res1 = uc_env["uc"].execute(payload, idempotency_key=key)

    # Simular transação que não viu a chave no SELECT inicial, mas sofre UniqueViolation no INSERT
    real_connect = uc_env["uc"]._connect
    intercept = [True]

    class RaceMockCursor:
        def __init__(self, real_cur):
            self._real_cur = real_cur

        def __enter__(self):
            self._real_cur.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._real_cur.__exit__(exc_type, exc_val, exc_tb)

        def execute(self, query, params=None):
            if intercept[0] and "FROM studio.channel_creation_requests WHERE idempotency_key" in str(query):
                intercept[0] = False
                return self._real_cur.execute(
                    "SELECT project_id, request_hash FROM studio.channel_creation_requests WHERE 1=0"
                )
            return self._real_cur.execute(query, params)

        def __getattr__(self, name):
            return getattr(self._real_cur, name)

    class RaceMockConn:
        def __init__(self, real_conn):
            self._real_conn = real_conn

        def __enter__(self):
            self._real_conn.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._real_conn.__exit__(exc_type, exc_val, exc_tb)

        def cursor(self, *args, **kwargs):
            return RaceMockCursor(self._real_conn.cursor(*args, **kwargs))

        def __getattr__(self, name):
            return getattr(self._real_conn, name)

    uc_env["uc"]._connect = lambda: RaceMockConn(real_connect())
    try:
        replay = uc_env["uc"].execute(payload, idempotency_key=key)
        assert replay.project.id == res1.project.id
        assert replay.profile.id == res1.profile.id
    finally:
        uc_env["uc"]._connect = real_connect


def test_create_channel_transactional_concurrent_unique_violation_conflict_on_divergent_payload(uc_env):
    payload1 = ChannelCreationPayload(name="Canal Concorrente 1", niche="Tech")
    payload2 = ChannelCreationPayload(name="Canal Concorrente 2", niche="Tech Divergente")
    key = "concurrent-conflict-key"

    res1 = uc_env["uc"].execute(payload1, idempotency_key=key)

    real_connect = uc_env["uc"]._connect
    intercept = [True]

    class RaceMockCursor:
        def __init__(self, real_cur):
            self._real_cur = real_cur

        def __enter__(self):
            self._real_cur.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._real_cur.__exit__(exc_type, exc_val, exc_tb)

        def execute(self, query, params=None):
            if intercept[0] and "FROM studio.channel_creation_requests WHERE idempotency_key" in str(query):
                intercept[0] = False
                return self._real_cur.execute(
                    "SELECT project_id, request_hash FROM studio.channel_creation_requests WHERE 1=0"
                )
            return self._real_cur.execute(query, params)

        def __getattr__(self, name):
            return getattr(self._real_cur, name)

    class RaceMockConn:
        def __init__(self, real_conn):
            self._real_conn = real_conn

        def __enter__(self):
            self._real_conn.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._real_conn.__exit__(exc_type, exc_val, exc_tb)

        def cursor(self, *args, **kwargs):
            return RaceMockCursor(self._real_conn.cursor(*args, **kwargs))

        def __getattr__(self, name):
            return getattr(self._real_conn, name)

    uc_env["uc"]._connect = lambda: RaceMockConn(real_connect())
    try:
        with pytest.raises(IdempotencyConflict):
            uc_env["uc"].execute(payload2, idempotency_key=key)
    finally:
        uc_env["uc"]._connect = real_connect


def test_create_channel_transactional_multithreaded_concurrency(uc_env):
    from concurrent.futures import ThreadPoolExecutor

    payload = ChannelCreationPayload(name="Canal Threads", niche="Finanças")
    key = "multithread-key-1"

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(uc_env["uc"].execute, payload, idempotency_key=key)
        f2 = executor.submit(uc_env["uc"].execute, payload, idempotency_key=key)
        res1 = f1.result()
        res2 = f2.result()

    assert res1.project.id == res2.project.id
    assert res1.profile.id == res2.profile.id


