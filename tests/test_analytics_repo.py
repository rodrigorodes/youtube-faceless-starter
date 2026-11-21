"""Integração F9 no PostgreSQL descartável: atribuição, experimento e decisão.

Roda só com `STUDIO_TEST_DSN`/`STUDIO_BUDGET_DISPOSABLE_DSN` + prova. As sondas de banco
provam que a versão inventada, o valor ausente sem motivo e o "A/B suportado" são recusados
pelo schema, não só pelo domínio.
"""
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from app.studio.adapters.postgres.analytics_learning_repo import (
    PostgresAnalyticsLearningRepository,
)
from app.studio.adapters.postgres.db import migrate
from app.studio.domain.analytics_learning import (
    ExperimentConclusion,
    ExperimentRecord,
    ExperimentVariant,
    MetricMeasurement,
    MissingVersionLink,
    RecommendationDecision,
    VersionAttribution,
)
from app.studio.domain.ids import check_id
from app.studio.domain.insight import (
    ConfidenceDeclaration,
    MetricObservation,
    MetricWindow,
)
from conftest import verified_test_connect

PROJECT, VIDEO, OTHER = "a" * 32, "b" * 32, "c" * 32
CATEGORY, OTHER_CATEGORY = "d" * 32, "e" * 32
PUBLICATION = "f" * 32
CHANNEL = "UC1234567890abcdefghij"
YOUTUBE = "AbCdEf12345"


def at(day=2, hour=12):
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


def window():
    return MetricWindow(start_at=at(2), end_at=at(9))


@pytest.fixture()
def repo(dsn, conn):
    proof = __import__("os").environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'Canal Real')", (PROJECT,))
    for video in (VIDEO, OTHER):
        conn.execute("INSERT INTO studio.videos(id, project_id, topic, format, status) "
                     "VALUES (%s, %s, 'Tema real', 'long', 'PUBLISHED')", (video, PROJECT))
    conn.execute("INSERT INTO studio.scripts(id, video_id, version, text) "
                 "VALUES (%s, %s, 1, 'roteiro')", ("1" * 32, VIDEO))
    conn.execute("INSERT INTO studio.publications(id, video_id, youtube_video_id, status) "
                 "VALUES (%s, %s, %s, 'UPLOADED')", (PUBLICATION, VIDEO, YOUTUBE))
    for category, name in ((CATEGORY, "Finanças"), (OTHER_CATEGORY, "IA")):
        conn.execute("INSERT INTO studio.project_categories(id, project_id, name) "
                     "VALUES (%s, %s, %s)", (category, PROJECT, name))
    conn.commit()
    return PostgresAnalyticsLearningRepository(
        lambda: verified_test_connect(dsn, proof))


def attribution(video=VIDEO, script_version=1, publication=None, youtube=None):
    missing = [MissingVersionLink(kind="brief", reason="briefing não persistido"),
               MissingVersionLink(kind="packaging", reason="embalagem não persistida")]
    if script_version is None:
        missing.append(MissingVersionLink(kind="script", reason="sem roteiro"))
    if publication is None:
        missing.append(MissingVersionLink(kind="publication", reason="sem publicação"))
    if youtube is None:
        missing.append(MissingVersionLink(kind="youtube_video", reason="sem id remoto"))
    return VersionAttribution(video_id=video, script_version=script_version,
                              publication_id=publication, youtube_video_id=youtube,
                              missing=tuple(missing))


def measurement(metric="views", value=10.0, *, observation_id=None, video=VIDEO,
                pillar=CATEGORY, origin="youtube_analytics_api", reason=None,
                collected=at(9), publication=PUBLICATION, youtube=YOUTUBE,
                script_version=1):
    unit = {"ctr": "percent", "average_view_percentage": "percent"}.get(metric, "count")
    observation = MetricObservation(
        observation_id=observation_id or uuid.uuid4().hex, metric=metric, unit=unit,
        window=window(), source="API YouTube Analytics", collected_at=collected,
        state="measured" if value is not None else "not_yet_available",
        value=value, unavailable_reason=reason,
    )
    return MetricMeasurement(observation=observation, origin=origin,
                             attribution=attribution(video, script_version=script_version,
                                                      publication=publication, youtube=youtube),
                             pillar_id=pillar)


def read(repo, **kwargs):
    return repo.observations(project_id=PROJECT, start=at(2), end=at(9), **kwargs)


def test_measurements_round_trip_with_versions_and_pillar(repo):
    rows = [measurement("views", 1200.0), measurement("ctr", 4.8, pillar=OTHER_CATEGORY)]
    assert repo.save_measurements(PROJECT, rows) == 2
    stored = read(repo)
    assert len(stored) == 2
    by_metric = {row.measurement.metric: row for row in stored}
    views = by_metric["views"].measurement
    assert views.observation.value == 1200.0
    assert views.origin == "youtube_analytics_api"
    assert views.attribution.script_version == 1
    assert views.attribution.publication_id == PUBLICATION
    assert views.attribution.youtube_video_id == YOUTUBE
    assert {link.kind for link in views.attribution.missing} == {"brief", "packaging"}
    assert by_metric["views"].pillar_name == "Finanças"
    assert by_metric["ctr"].pillar_name == "IA"


def test_save_measurements_is_idempotent_by_observation_id(repo):
    observation_id = uuid.uuid4().hex
    repo.save_measurements(PROJECT, [measurement("views", 10.0, observation_id=observation_id)])
    repo.save_measurements(PROJECT, [measurement("views", 12.0, observation_id=observation_id)])
    stored = read(repo)
    assert len(stored) == 1
    assert stored[0].measurement.observation.value == 12.0


def test_unavailable_value_requires_and_keeps_the_reason(repo):
    repo.save_measurements(PROJECT, [measurement("views", None, reason="a API não devolveu views")])
    stored = read(repo)[0].measurement
    assert stored.observation.value is None
    assert stored.observation.unavailable_reason == "a API não devolveu views"
    assert stored.observation.state == "not_yet_available"


def test_zero_is_stored_as_measured_zero(repo):
    repo.save_measurements(PROJECT, [measurement("views", 0.0)])
    stored = read(repo)[0].measurement.observation
    assert stored.value == 0.0 and stored.is_measured


def test_period_video_and_pillar_filters_are_honest(repo):
    repo.save_measurements(PROJECT, [
        measurement("views", 1.0),
        measurement("views", 2.0, video=OTHER, pillar=OTHER_CATEGORY, script_version=None,
                    publication=None, youtube=None),
    ])
    assert len(read(repo)) == 2
    assert len(read(repo, video_id=VIDEO)) == 1
    assert len(read(repo, pillar_id=OTHER_CATEGORY)) == 1
    later = repo.observations(project_id=PROJECT, start=at(10), end=at(16))
    assert later == []


def test_last_collected_is_the_latest_real_observation(repo):
    assert repo.last_collected_at(PROJECT) is None
    repo.save_measurements(PROJECT, [measurement("views", 1.0, collected=at(8, 10))])
    repo.save_measurements(PROJECT, [measurement("ctr", 2.0, collected=at(9, 9))])
    assert repo.last_collected_at(PROJECT) == at(9, 9)


def test_channel_state_reports_scopes_without_token(repo, conn):
    state = repo.channel_state(PROJECT)
    assert state.connected is False and state.scopes == () and state.channel_id is None
    conn.execute("INSERT INTO studio.channel_youtube_channels "
                 "(project_id, channel_id, scopes, oauth_status) VALUES (%s, %s, %s, 'CONNECTED')",
                 (PROJECT, CHANNEL, '["yt-analytics.readonly"]'))
    conn.commit()
    state = repo.channel_state(PROJECT)
    assert state.connected is True
    assert state.channel_id == CHANNEL
    assert "yt-analytics.readonly" in state.scopes


def test_invented_script_version_is_rejected_by_the_foreign_key(repo):
    # Versão ausente é permitida: vira motivo explícito, não número inventado.
    repo.save_measurements(PROJECT, [MetricMeasurement(
        observation=measurement("views", 1.0).observation, origin="youtube_analytics_api",
        attribution=attribution(script_version=None))])
    assert repo.observations(project_id=PROJECT, start=at(2), end=at(9))[0] \
        .measurement.attribution.script_version is None

    bad = VersionAttribution(video_id=VIDEO, script_version=99,
                             publication_id=PUBLICATION, youtube_video_id=YOUTUBE,
                             missing=(MissingVersionLink(kind="brief", reason="x"),
                                      MissingVersionLink(kind="packaging", reason="y")))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repo.save_measurements(PROJECT, [MetricMeasurement(
            observation=measurement("likes", 1.0).observation, origin="youtube_analytics_api",
            attribution=bad)])


def test_schema_refuses_value_and_reason_together_or_neither(repo, conn):
    base = ("INSERT INTO studio.metric_observations (observation_id, project_id, video_id, "
            "metric, unit, value, unavailable_reason, window_start, window_end, source, origin, "
            "collected_at) VALUES (%s, %s, %s, 'views', 'count', %s, %s, %s, %s, 'API', "
            "'youtube_analytics_api', %s)")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(base, (uuid.uuid4().hex, PROJECT, VIDEO, 1.0, "motivo", at(2), at(9), at(9)))
    conn.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(base, (uuid.uuid4().hex, PROJECT, VIDEO, None, None, at(2), at(9), at(9)))
    conn.rollback()


def test_schema_refuses_nan_and_duplicate_window(repo, conn):
    base = ("INSERT INTO studio.metric_observations (observation_id, project_id, video_id, "
            "metric, unit, value, window_start, window_end, source, origin, collected_at) "
            "VALUES (%s, %s, %s, 'views', 'count', %s, %s, %s, 'API', "
            "'youtube_analytics_api', %s)")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(base, (uuid.uuid4().hex, PROJECT, VIDEO, float("nan"), at(2), at(9), at(9)))
    conn.rollback()
    conn.execute(base, (uuid.uuid4().hex, PROJECT, VIDEO, 1.0, at(2), at(9), at(9)))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(base, (uuid.uuid4().hex, PROJECT, VIDEO, 1.0, at(2), at(9), at(9)))
    conn.rollback()


def experiment(**overrides):
    values = {
        "experiment_id": "9" * 32, "project_id": PROJECT, "video_id": VIDEO,
        "kind": "thumbnail", "status": "running", "approved_by": "operador",
        "platform_note": "A API do YouTube não expõe A/B; rotação manual.",
        "variants": (ExperimentVariant(variant_id="controle", label="Atual", is_control=True),
                     ExperimentVariant(variant_id="b", label="Nova", is_control=False)),
        "window": window(),
    }
    values.update(overrides)
    return ExperimentRecord(**values)


def test_experiment_round_trip_with_variants_and_conclusion(repo):
    conclusion = ExperimentConclusion(
        statement="Sem diferença mensurável.", confidence=ConfidenceDeclaration(
            level="low", basis="1 rotação", declared_by="operador"),
        observation_ids=(uuid.uuid4().hex,), concluded_at=at(9))
    repo.save_experiment(experiment(status="finished", conclusion=conclusion))
    stored = repo.experiments(PROJECT)
    assert len(stored) == 1
    assert stored[0].status == "finished"
    assert [v.label for v in stored[0].variants] == ["Atual", "Nova"]
    assert stored[0].control.label == "Atual"
    assert stored[0].conclusion.statement == "Sem diferença mensurável."
    assert stored[0].conclusion.confidence.level == "low"
    assert stored[0].platform_ab_supported is False


def test_experiment_save_replaces_variants_instead_of_duplicating(repo):
    repo.save_experiment(experiment())
    repo.save_experiment(experiment(variants=(
        ExperimentVariant(variant_id="controle", label="Atual", is_control=True),
        ExperimentVariant(variant_id="c", label="Terceira", is_control=False))))
    stored = repo.experiments(PROJECT)[0]
    assert [v.variant_id for v in stored.variants] == ["controle", "c"]


def test_schema_refuses_platform_ab_claim_and_finished_without_conclusion(repo, conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(experiment_columns(), experiment_values(platform_ab_supported=True))
    conn.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(experiment_columns(), experiment_values(status="finished"))
    conn.rollback()


def test_schema_refuses_two_controls_and_missing_control(repo, conn):
    repo.save_experiment(experiment())
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO studio.analytics_experiment_variants "
                     "(experiment_id, variant_id, label, is_control) "
                     "VALUES (%s, 'segundo-controle', 'B', true)", (experiment().experiment_id,))
    conn.rollback()
    # Sem controle, o domínio recusa antes do banco.
    with pytest.raises(Exception):
        experiment(experiment_id="7" * 32, variants=(
            ExperimentVariant(variant_id="a", label="A"),
            ExperimentVariant(variant_id="b", label="B")))


def experiment_columns():
    return ("INSERT INTO studio.analytics_experiments (experiment_id, project_id, video_id, kind, "
            "status, platform_ab_supported, platform_note, approved_by, window_start, window_end) "
            "VALUES (%s, %s, %s, 'thumbnail', %s, %s, 'nota', 'operador', %s, %s)")


def experiment_values(**overrides):
    values = {"experiment_id": "6" * 32, "project_id": PROJECT, "video_id": VIDEO,
              "status": "running", "platform_ab_supported": False,
              "window_start": at(2), "window_end": at(9)}
    values.update(overrides)
    return (values["experiment_id"], values["project_id"], values["video_id"],
            values["status"], values["platform_ab_supported"], values["window_start"],
            values["window_end"])


def test_decisions_are_stored_per_recommendation_and_upserted(repo):
    recommendation_id = "5" * 32
    decision = RecommendationDecision(recommendation_id=recommendation_id,
                                      decision="rejected", decided_by="operador",
                                      decided_at=at(10))
    repo.save_decision(PROJECT, decision)
    stored = repo.decisions(PROJECT)
    assert len(stored) == 1 and stored[0].decision == "rejected"
    repo.save_decision(PROJECT, RecommendationDecision(
        recommendation_id=recommendation_id, decision="accepted_for_review",
        decided_by="outro", decided_at=at(11)))
    stored = repo.decisions(PROJECT)
    assert len(stored) == 1 and stored[0].decision == "accepted_for_review"


def test_unknown_project_returns_none_instead_of_inventing_a_name(repo):
    assert repo.project_name("0" * 32) is None