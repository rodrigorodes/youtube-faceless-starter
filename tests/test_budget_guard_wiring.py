"""Prova de que o **teto do canal** barra a operação paga ANTES do efeito externo (R1/P-07, W0B.1).

O que a D-C exige é prova por teste: o limite por canal tem de impedir a chamada paga antes do efeito
externo, inclusive com duas reservas concorrentes. Aqui o "efeito externo" é um contador de chamadas
fake; a reserva é o repositório PostgreSQL real, contra um banco **exclusivamente descartável**
(`STUDIO_BUDGET_DISPOSABLE_DSN` + prova privada). Sem essas variáveis, os testes são pulados.

Os tetos das settings são zero de propósito (`video_limit_usd=0`): assim só o teto do CANAL pode
autorizar a chamada, e o teste não passa por acidente.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
from threading import Barrier

import pytest

from app.studio.adapters.postgres.db import migrate
from conftest import verified_test_connect, verify_disposable_connection

PROJECT, VIDEO, OTHER_VIDEO = "a" * 32, "b" * 32, "c" * 32


@pytest.fixture
def dsn():
    value = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not value or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável de orçamento não configurado")
    return value


@pytest.fixture
def conn(dsn):
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    connection = verified_test_connect(dsn, proof)
    try:
        verify_disposable_connection(connection, proof)
        connection.execute("DROP SCHEMA IF EXISTS studio CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.close()


@pytest.fixture
def connect(conn, dsn):
    """Fábrica de conexões do banco descartável (uma por operação, como na composição)."""
    return lambda: verified_test_connect(dsn, os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"])


@pytest.fixture
def paid_channel(conn, connect):
    """Canal com dois vídeos, sem `channel_budgets` (as settings é que mandariam)."""
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'canal')", (PROJECT,))
    for video in (VIDEO, OTHER_VIDEO):
        conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'tema', 'short')",
                     (video, PROJECT))
    conn.commit()
    return connect


def _guard(connect, *, monthly, video, settings_video=Decimal("0"), settings_monthly=Decimal("15")):
    """Guard como a composição o monta: repositório real + `limits_for=channel_guard_limits(...)`."""
    from app.studio.adapters.postgres.budget_repo import PostgresPaidOperationRepository
    from app.studio.adapters.postgres.channel_budget_repo import PostgresChannelBudgetRepository
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.application.budget import PaidOperationGuard
    from app.studio.composition import channel_guard_limits

    return PaidOperationGuard(PostgresPaidOperationRepository(connect), settings_monthly, settings_video,
                              limits_for=channel_guard_limits(PostgresVideoRepository(connect),
                                                              PostgresChannelBudgetRepository(connect)))


def _limits(connect, *, monthly, video):
    from app.studio.adapters.postgres.channel_budget_repo import PostgresChannelBudgetRepository
    from app.studio.domain.channel_budget import BudgetLimits

    PostgresChannelBudgetRepository(connect).upsert(
        BudgetLimits(project_id=PROJECT, hard_monthly_usd=monthly, soft_monthly_usd=monthly,
                     hard_video_usd=video, soft_video_usd=video))


def _settle(estimate):
    from app.studio.application.budget import CostConfirmation
    from app.studio.domain.contracts import UsageEntry

    entry = UsageEntry(step="image", provider="fake", model="m", cost_usd=float(estimate))
    return entry, CostConfirmation.actual(estimate, reference="provider:fake", confirmed_by="studio")


def _run(guard, key, video_id, estimate, calls):
    def call():
        calls.append((key, video_id))
        return object()

    return guard.run(key, video_id, estimate, call, settle=lambda _result: _settle(estimate))


def test_the_channel_ceiling_blocks_the_paid_call_before_the_external_effect(paid_channel):
    """Estimativa acima do teto do canal: 403-lógico (`BudgetDenied`) e **nenhuma** chamada externa."""
    from app.studio.application.budget import BudgetDenied

    _limits(paid_channel, monthly=Decimal("5"), video=Decimal("0.50"))
    guard = _guard(paid_channel, monthly=Decimal("5"), video=Decimal("0.50"))
    calls = []

    _run(guard, "dentro-do-teto", VIDEO, Decimal("0.40"), calls)
    assert calls == [("dentro-do-teto", VIDEO)]  # dentro do teto do canal: executou uma vez

    with pytest.raises(BudgetDenied):
        _run(guard, "acima-do-teto", VIDEO, Decimal("0.60"), calls)
    with pytest.raises(BudgetDenied):
        _run(guard, "acima-do-teto-mensal", OTHER_VIDEO, Decimal("4.80"), calls)

    assert len(calls) == 1, "o teto do canal bloqueia ANTES do efeito externo"
    assert guard.repo.state("acima-do-teto") is None, "recusa não deixa operação paga registrada"


def test_a_denied_reservation_says_which_ceiling_was_hit(paid_channel):
    """Achado 3: a recusa de orçamento diz **qual** teto estourou, com os números do escopo."""
    from app.studio.application.budget import BudgetDenied

    _limits(paid_channel, monthly=Decimal("5"), video=Decimal("0.50"))
    # Settings mensal 15 > canal 5: isola o escopo do CANAL; settings por vídeo 0,50 isola o VÍDEO.
    guard = _guard(paid_channel, monthly=Decimal("15"), video=Decimal("0.50"))
    calls = []

    # Escopo VÍDEO: 0,60 > 0,50 (o mensal do canal tem folga).
    with pytest.raises(BudgetDenied) as video_denied:
        _run(guard, "acima-do-video", VIDEO, Decimal("0.60"), calls)
    detail = video_denied.value.detail
    assert detail is not None, "a recusa precisa dizer qual teto barrou"
    assert detail.scope == "VÍDEO"
    assert detail.ceiling_usd == Decimal("0.50")
    assert detail.estimate_usd == Decimal("0.60")
    assert "VÍDEO" in detail.describe() and "0.50" in detail.describe()

    # Escopo CANAL (mês): 0,40 confirmado + 4,80 estoura o teto mensal do canal (5,00).
    _run(guard, "dentro", VIDEO, Decimal("0.40"), calls)
    with pytest.raises(BudgetDenied) as canal_denied:
        _run(guard, "acima-do-canal", OTHER_VIDEO, Decimal("4.80"), calls)
    assert canal_denied.value.detail.scope == "CANAL (mês)"
    assert canal_denied.value.detail.ceiling_usd == Decimal("5")
    assert canal_denied.value.detail.committed_usd == Decimal("0.40")
    assert calls == [("dentro", VIDEO)]


def test_without_a_channel_budget_the_settings_ceiling_applies(paid_channel):
    """Sem limite de canal valem as settings: com teto por vídeo 0, a primeira chamada paga é recusada.

    É a consequência documentada de ligar o guard sem definir `MAX_COST_USD_PER_VIDEO` (ou o teto do
    canal): fail-safe, porém bloqueante — nada pago executa.
    """
    from app.studio.application.budget import BudgetDenied

    guard = _guard(paid_channel, monthly=Decimal("15"), video=Decimal("0"))
    calls = []

    with pytest.raises(BudgetDenied):
        _run(guard, "sem-teto", VIDEO, Decimal("0.05"), calls)
    assert calls == []


def test_two_concurrent_reservations_for_the_same_channel_cannot_both_pass(paid_channel):
    """Duas reservas concorrentes no MESMO canal, 0,60 cada contra teto mensal de 1,00: só uma passa.

    O teto por vídeo (1,00) não bloqueia nenhuma das duas isoladamente; quem bloqueia é o escopo do
    canal. O efeito externo acontece exatamente uma vez.
    """
    from app.studio.application.budget import BudgetDenied

    _limits(paid_channel, monthly=Decimal("1"), video=Decimal("1"))
    guard = _guard(paid_channel, monthly=Decimal("1"), video=Decimal("1"))
    calls, barrier = [], Barrier(2)

    def worker(key, video_id):
        barrier.wait()
        try:
            _run(guard, key, video_id, Decimal("0.60"), calls)
        except BudgetDenied:
            return "DENIED"
        return "EXECUTED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: worker(*pair), [("k1", VIDEO), ("k2", OTHER_VIDEO)]))

    assert sorted(results) == ["DENIED", "EXECUTED"]
    assert len(calls) == 1, "a reserva do canal tem de serializar as duas tentativas"
    with paid_channel() as connection:
        # A operação que passou foi confirmada (a reserva sai; o custo entra no ledger). O que prova a
        # serialização é existir **um só** gasto confirmado e nenhuma reserva ativa sobrando.
        assert connection.execute(
            "SELECT count(*) FROM studio.usage_ledger WHERE cost_confirmation_kind = 'ACTUAL'").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM studio.budget_reservations").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM studio.paid_operations").fetchone()[0] == 1
