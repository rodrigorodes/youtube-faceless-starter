"""F9-02: coleta autorizada atrás de porta, com escopo yt-analytics.readonly.

Nada aqui fala com o YouTube de verdade: a porta e o cliente HTTP são falsos. O que se prova é
que sem autorização não há coleta nem número inventado, que a resposta é validada, e que a
medição sai ligada à versão do vídeo.
"""
from datetime import datetime, timezone

import pytest

from app.studio.adapters.youtube_analytics import (
    ANALYTICS_METRICS,
    API_METRIC_NAMES,
    YoutubeAnalyticsAdapter,
)
from app.studio.application.analytics_collection import (
    AnalyticsPoint,
    AnalyticsQuery,
    AnalyticsUnavailable,
    AnalyticsNotAuthorized,
    CollectMetrics,
    CollectionRequest,
)
from app.studio.application.analytics_ports import AnalyticsVideoInfo, ChannelAnalyticsState
from app.studio.domain.analytics_learning import AnalyticsPeriod, ANALYTICS_READONLY_SCOPE

VIDEO = "a" * 32
PROJECT = "b" * 32
PUBLICATION = "c" * 32
CHANNEL = "UC1234567890abcdefghij"
YOUTUBE = "AbCdEf12345"


def at(day=9):
    return datetime(2026, 11, day, 12, tzinfo=timezone.utc)


def video_info(**overrides):
    values = {
        "id": VIDEO,
        "project_id": PROJECT,
        "topic": "Como funciona o dinheiro",
        "format": "long",
        "status": "PUBLISHED",
        "created_at": at(1),
        "updated_at": at(2),
        "script_version": 3,
        "publication_id": PUBLICATION,
        "youtube_video_id": YOUTUBE,
        "publication_status": "UPLOADED",
    }
    values.update(overrides)
    return AnalyticsVideoInfo(**values)


class FakeRepo:
    def __init__(self, video=None, channel=None, pillars=(("d" * 32, "Finanças"),)):
        self._video = video or video_info()
        self.channel = channel or ChannelAnalyticsState(
            connected=True, channel_id=CHANNEL, scopes=(ANALYTICS_READONLY_SCOPE,),
            token_expires_at=None)
        self._pillars = list(pillars)
        self.saved = []

    def pillars(self, project_id):
        return list(self._pillars)

    def video(self, video_id):
        return self._video if self._video and self._video.id == video_id else None

    def channel_state(self, project_id):
        return self.channel

    def save_measurements(self, project_id, rows):
        self.saved.extend(rows)
        return len(rows)


class FakePort:
    scope = ANALYTICS_READONLY_SCOPE

    def __init__(self, points=(), error=None):
        self.points = list(points)
        self.error = error
        self.calls = []

    def collect(self, query):
        self.calls.append(query)
        if self.error:
            raise self.error
        return tuple(self.points)


def service(port=None, repo=None):
    repo = repo or FakeRepo()
    return CollectMetrics(port or FakePort(), repo, clock=lambda: at()), repo


def request(**overrides):
    values = {"video_id": VIDEO, "period": AnalyticsPeriod(days=7, end_at=at())}
    values.update(overrides)
    return CollectionRequest(**values)


def points(views=1000.0):
    return [AnalyticsPoint("views", views), AnalyticsPoint("impressions", 20000.0),
            AnalyticsPoint("ctr", 5.0), AnalyticsPoint("average_view_percentage", 42.0),
            AnalyticsPoint("estimated_minutes_watched", 300.0)]


def test_without_authorized_scope_the_port_is_never_called_and_nothing_is_faked():
    repo = FakeRepo(channel=ChannelAnalyticsState(
        connected=True, channel_id=CHANNEL, scopes=(), token_expires_at=None))
    port = FakePort(points())
    outcome = CollectMetrics(port, repo, clock=lambda: at()).execute(request())
    assert outcome.collected is False
    assert outcome.measurements == ()
    assert port.calls == []
    assert any("yt-analytics.readonly" in reason for reason in outcome.readiness.reasons)


def test_without_publication_there_is_no_remote_id_so_collection_waits_for_f8():
    repo = FakeRepo(video=video_info(publication_id=None, youtube_video_id=None,
                                     publication_status=None))
    port = FakePort(points())
    outcome = CollectMetrics(port, repo, clock=lambda: at()).execute(request())
    assert outcome.collected is False
    assert outcome.measurements == ()
    assert port.calls == []
    assert any("publica" in reason for reason in outcome.readiness.reasons)


def test_ready_collection_maps_points_to_measurements_linked_to_the_versions():
    repo = FakeRepo()
    port = FakePort(points())
    outcome = CollectMetrics(port, repo, clock=lambda: at()).execute(request())
    assert outcome.collected is True
    assert port.calls and port.calls[0].youtube_video_id == YOUTUBE
    by_metric = {row.metric: row for row in outcome.measurements}
    assert by_metric["views"].observation.value == 1000.0
    assert by_metric["ctr"].observation.unit == "percent"
    assert all(row.origin == "youtube_analytics_api" for row in outcome.measurements)
    assert all(row.attribution.video_id == VIDEO for row in outcome.measurements)
    assert all(row.attribution.script_version == 3 for row in outcome.measurements)
    assert all(row.attribution.publication_id == PUBLICATION for row in outcome.measurements)
    assert all(row.attribution.youtube_video_id == YOUTUBE for row in outcome.measurements)
    # briefing e embalagem ainda não são persistidos: o motivo fica explícito.
    assert {link.kind for link in outcome.measurements[0].attribution.missing} == {"brief", "packaging"}
    assert len(repo.saved) == len(outcome.measurements)


def test_a_core_metric_absent_from_the_api_is_explicitly_unavailable_not_zero():
    repo = FakeRepo()
    partial = [point for point in points() if point.metric != "ctr"]
    outcome = CollectMetrics(FakePort(partial), repo, clock=lambda: at()).execute(request())
    by_metric = {row.metric: row for row in outcome.measurements}
    assert by_metric["views"].is_measured
    assert by_metric["ctr"].is_measured is False
    assert by_metric["ctr"].observation.value is None
    assert by_metric["ctr"].observation.unavailable_reason
    assert by_metric["ctr"].origin == "youtube_analytics_api"


def test_authorization_error_is_reported_without_inventing_numbers():
    repo = FakeRepo()
    port = FakePort(error=AnalyticsNotAuthorized("token ausente"))
    outcome = CollectMetrics(port, repo, clock=lambda: at()).execute(request())
    assert outcome.collected is False
    assert outcome.measurements == ()
    assert "token ausente" in (outcome.reason or "")
    assert repo.saved == []


def test_provider_failure_is_an_explicit_unavailable_state_not_an_exception():
    repo = FakeRepo()
    port = FakePort(error=AnalyticsUnavailable("tempo esgotado"))
    outcome = CollectMetrics(port, repo, clock=lambda: at()).execute(request())
    assert outcome.collected is False
    assert outcome.measurements == ()
    assert "tempo esgotado" in (outcome.reason or "")
    assert repo.saved == []


def test_unknown_video_raises_a_domain_error_before_any_io():
    from app.studio.application.analytics_collection import AnalyticsVideoNotFound

    with pytest.raises(AnalyticsVideoNotFound, match="video"):
        CollectMetrics(FakePort(), FakeRepo(), clock=lambda: at()).execute(
            request(video_id="b" * 32))


def test_pillar_must_belong_to_the_project_before_any_collection():
    from app.studio.application.analytics_collection import AnalyticsPillarNotFound

    port = FakePort(points())
    with pytest.raises(AnalyticsPillarNotFound, match="pillar"):
        CollectMetrics(port, FakeRepo(), clock=lambda: at()).execute(
            request(pillar_id="e" * 32))
    assert port.calls == []
    outcome = CollectMetrics(port, FakeRepo(), clock=lambda: at()).execute(
        request(pillar_id="d" * 32))
    assert all(row.pillar_id == "d" * 32 for row in outcome.measurements)


def test_observation_ids_are_deterministic_so_a_retry_is_idempotent():
    repo = FakeRepo()
    first = CollectMetrics(FakePort(points()), repo, clock=lambda: at()).execute(request())
    second = CollectMetrics(FakePort(points()), repo, clock=lambda: at()).execute(request())
    assert [row.observation.observation_id for row in first.measurements] == \
           [row.observation.observation_id for row in second.measurements]


# -- adapter HTTP (sem rede): contrato de escopo, janela e validação -------------------------


def fake_http(payload, captured=None):
    def get(url, headers):
        if captured is not None:
            captured.append((url, headers))
        return payload
    return get


def adapter(**overrides):
    values = {"channel_id": CHANNEL, "access_token": "token", "scope_granted": True,
              "http_get": fake_http({"columnHeaders": [], "rows": []})}
    values.update(overrides)
    return YoutubeAnalyticsAdapter(**values)


def query(**overrides):
    values = {"channel_id": CHANNEL, "start": at(2), "end": at(9), "youtube_video_id": YOUTUBE}
    values.update(overrides)
    return AnalyticsQuery(**values)


def test_adapter_refuses_to_call_without_the_readonly_scope():
    called = []
    port = adapter(scope_granted=False, http_get=fake_http({}, captured=called))
    with pytest.raises(AnalyticsNotAuthorized, match="yt-analytics.readonly"):
        port.collect(query())
    assert called == []


def test_adapter_refuses_to_call_without_a_token():
    called = []
    port = adapter(access_token="", http_get=fake_http({}, captured=called))
    with pytest.raises(AnalyticsNotAuthorized, match="token"):
        port.collect(query())
    assert called == []


def test_adapter_without_http_client_is_unavailable_instead_of_faking_network():
    with pytest.raises(AnalyticsUnavailable, match="HTTP"):
        adapter(http_get=None).collect(query())


def test_adapter_builds_the_query_with_dates_and_the_video_filter():
    captured = []
    payload = {"columnHeaders": [{"name": name} for name in ANALYTICS_METRICS],
               "rows": [[1000, 20000, 5.0, 42.0, 300.0, 120.0, 10, 2, 1, 4]]}
    port = adapter(http_get=fake_http(payload, captured=captured))
    result = port.collect(query())
    assert {point.metric for point in result} == set(API_METRIC_NAMES.values())
    url, headers = captured[0]
    assert "startDate=2026-11-02" in url and "endDate=2026-11-09" in url
    assert "filters=video%3D%3DAbCdEf12345" in url or "filters=video==AbCdEf12345" in url
    assert headers["Authorization"] == "Bearer token"


def test_adapter_keeps_zero_measured_and_rejects_negative_values():
    headers = [{"name": "views"}, {"name": "impressionClickThroughRate"}]
    zero = adapter(http_get=fake_http({"columnHeaders": headers, "rows": [[0, 0.0]]}))
    result = zero.collect(query())
    assert {point.metric: point.value for point in result} == {"views": 0.0, "ctr": 0.0}

    negative = adapter(http_get=fake_http({"columnHeaders": headers, "rows": [[-1, 1.0]]}))
    with pytest.raises(AnalyticsUnavailable, match="views"):
        negative.collect(query())


def test_adapter_rejects_non_finite_and_malformed_responses():
    headers = [{"name": "views"}]
    infinite = adapter(http_get=fake_http({"columnHeaders": headers, "rows": [[float("inf")]]}))
    with pytest.raises(AnalyticsUnavailable):
        infinite.collect(query())
    malformed = adapter(http_get=fake_http({"rows": [[1]]}))
    with pytest.raises(AnalyticsUnavailable):
        malformed.collect(query())

# -- adaptador por canal: escopo/token vêm do vínculo, nunca do cliente --------------------


class FakeChannels:
    def __init__(self, channel):
        self.channel = channel

    def get(self, project_id):
        return self.channel


class FakeSecrets:
    def __init__(self, values=None, error=None):
        self.values = values or {}
        self.error = error
        self.asked = []

    def get(self, scope, key):
        self.asked.append((scope, key))
        if self.error:
            raise self.error
        return self.values.get(key)


def youtube_channel(scopes=(ANALYTICS_READONLY_SCOPE,)):
    from app.studio.domain.youtube_channel import YouTubeChannel

    return YouTubeChannel(project_id=PROJECT, channel_id=CHANNEL, scopes=scopes)


def channel_adapter(channels=None, secrets=None, **overrides):
    from app.studio.adapters.channel_analytics import ChannelAnalyticsAdapter

    values = {"channels": channels or FakeChannels(youtube_channel()),
              "secrets": secrets or FakeSecrets({"access_token": "segredo"}),
              "http_get": fake_http({"columnHeaders": [{"name": "views"}], "rows": [[7]]})}
    values.update(overrides)
    return ChannelAnalyticsAdapter(**values)


def channel_query(**overrides):
    values = {"channel_id": CHANNEL, "start": at(2), "end": at(9),
              "youtube_video_id": YOUTUBE, "project_id": PROJECT}
    values.update(overrides)
    return AnalyticsQuery(**values)


def test_channel_adapter_refuses_without_a_linked_channel():
    with pytest.raises(AnalyticsNotAuthorized, match="canal"):
        channel_adapter(channels=FakeChannels(None)).collect(channel_query())


def test_channel_adapter_refuses_without_scope_or_token():
    with pytest.raises(AnalyticsNotAuthorized, match="yt-analytics.readonly"):
        channel_adapter(channels=FakeChannels(youtube_channel(scopes=()))).collect(channel_query())
    with pytest.raises(AnalyticsNotAuthorized, match="token"):
        channel_adapter(secrets=FakeSecrets({})).collect(channel_query())


def test_channel_adapter_reads_the_token_from_the_vault_and_returns_points():
    captured = []
    adapter = channel_adapter(http_get=fake_http(
        {"columnHeaders": [{"name": "views"}], "rows": [[7]]}, captured=captured))
    result = adapter.collect(channel_query())
    assert [point.metric for point in result] == ["views"]
    assert captured[0][1]["Authorization"] == "Bearer segredo"


def test_channel_adapter_maps_vault_failure_to_unavailable_not_a_crash():
    with pytest.raises(AnalyticsUnavailable, match="cofre"):
        channel_adapter(secrets=FakeSecrets(error=RuntimeError("vault down"))).collect(
            channel_query())
