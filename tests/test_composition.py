import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

pytest.importorskip("psycopg")
from app.studio.composition import Settings, Studio  # noqa: E402

DEAD = "postgresql://x:y@127.0.0.1:1/z"


def counting(studio, monkeypatch):
    calls, original = [], studio._connect
    monkeypatch.setattr(studio, "_connect", lambda: (calls.append(1), original())[1])
    return calls


def test_connection_has_lock_and_statement_timeouts(dsn, tmp_path):
    with Studio(Settings(database_url=dsn, storage_root=tmp_path))._connect() as c:
        assert c.execute("SHOW statement_timeout").fetchone()[0] == "15s"
        assert c.execute("SHOW lock_timeout").fetchone()[0] == "5s"


def test_failed_init_backs_off_instead_of_retrying_every_call(tmp_path, monkeypatch):
    studio = Studio(Settings(database_url=DEAD, storage_root=tmp_path))
    calls = counting(studio, monkeypatch)
    assert studio.use_cases() is None and studio.use_cases() is None and studio.ping() is False
    assert len(calls) == 1


def test_recover_in_flight_is_a_noop_without_a_database(tmp_path):
    """PROD-03: sem banco a recuperação de boot degrada em silêncio, nunca derruba a subida."""
    studio = Studio(Settings(database_url=DEAD, storage_root=tmp_path))
    assert studio.recover_in_flight() == ()


def test_recover_orphans_is_a_noop_without_a_database(tmp_path):
    studio = Studio(Settings(database_url=DEAD, storage_root=tmp_path))
    assert studio.recover_orphans() == ()


def test_tracked_submit_registers_and_releases_active_runs(tmp_path):
    from concurrent.futures import Future

    from app.studio.application.production import ActiveRuns
    from app.studio.composition.wiring import tracked_submit

    class Executor:
        def __init__(self):
            self.futures = []
            self.fail = False

        def submit(self, fn, *args):
            if self.fail:
                raise RuntimeError("pool shut down")
            future = Future()
            self.futures.append(future)
            return future

    executor, active = Executor(), ActiveRuns()
    submit = tracked_submit(executor, lambda run_id: None, active)
    submit("a" * 32)
    assert active.snapshot() == frozenset({"a" * 32})
    executor.futures[0].set_result(None)
    assert active.snapshot() == frozenset()
    executor.fail = True
    with pytest.raises(RuntimeError):
        submit("b" * 32)
    assert active.snapshot() == frozenset()


def test_ping_is_cached_for_a_few_seconds(conn, dsn, tmp_path, monkeypatch):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    calls = counting(studio, monkeypatch)
    assert studio.ping() is True
    after_first = len(calls)
    assert studio.ping() is True and len(calls) == after_first


# -- F10-05: limites por canal ligados ao guard e à pausa humana (fakes, sem banco) --


class _Video:
    def __init__(self, project_id):
        self.project_id = project_id


class _Videos:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_video(self, video_id):
        return self.mapping.get(video_id)


class _Budgets:
    def __init__(self, limits):
        self.limits = limits

    def get(self, project_id):
        return next((lim for lim in self.limits if lim.project_id == project_id), None)


def test_channel_guard_limits_resolve_from_the_channel_budget():
    from decimal import Decimal

    from app.studio.composition import channel_guard_limits
    from app.studio.domain.channel_budget import BudgetLimits

    limits = BudgetLimits(project_id="a" * 32, hard_monthly_usd=Decimal("7"), soft_monthly_usd=Decimal("3"),
                          hard_video_usd=Decimal("2"), soft_video_usd=Decimal("1"))
    resolve = channel_guard_limits(_Videos({"b" * 32: _Video("a" * 32)}), _Budgets([limits]))
    assert resolve("b" * 32) == (Decimal("7"), Decimal("2"))
    assert resolve(None) is None
    assert resolve("9" * 32) is None  # vídeo inexistente usa o padrão das settings
    assert resolve("not-a-hex-id") is None  # id inválido não bloqueia por si: cai no padrão


def test_channel_budget_floor_uses_soft_limit_and_falls_back():
    """F01.T03: o piso do modo guardado vive na aplicação (`ChannelBudgetFloor`), medindo o canal.

    O teste original cobria a classe que morava na composição; a composição agora só injeta a
    dependência, e as mesmas duas garantias seguem verificadas aqui (soft do canal; fallback das
    settings). O escopo global x canal tem cobertura própria em `test_channel_budget_service`.
    """
    from decimal import Decimal

    from app.studio.application.channel_budget import ChannelBudgetFloor
    from app.studio.domain.channel_budget import BudgetLimits

    class Usage:
        def month_summary(self, project_id):
            return type("S", (), {"spent_usd": Decimal("4.0")})()

        def global_month_summary(self):
            return type("S", (), {"spent_usd": Decimal("44.0")})()

    limits = BudgetLimits(project_id="a" * 32, hard_monthly_usd=Decimal("9"), soft_monthly_usd=Decimal("5"),
                          hard_video_usd=Decimal("2"), soft_video_usd=Decimal("1"))
    floor = ChannelBudgetFloor(Usage(), _Videos({"b" * 32: _Video("a" * 32)}), _Budgets([limits]),
                               Decimal("15"))
    projection = floor.project(type("R", (), {"video_id": "b" * 32}), None)
    assert projection.ceiling_usd == Decimal("5")  # soft do canal, não o padrão
    assert projection.projected_usd == Decimal("4.0")  # gasto do canal, não o global
    default = floor.project(type("R", (), {"video_id": "c" * 32}), None)
    assert default.ceiling_usd == Decimal("15")  # sem budget de canal: teto das settings


# -- F8-05: OAuth configurado pelo arquivo original, nunca copiado --


def test_google_oauth_is_built_from_the_client_secret_file_without_copying_it(tmp_path):
    import json

    from app.studio.composition import build_google_oauth
    secret = tmp_path / "client-secret-synthetic.json"
    secret.write_text(json.dumps({"web": {
        "client_id": "client-id.apps.googleusercontent.com",
        "client_secret": "your_client_secret",
        "redirect_uris": ["http://localhost:8000/studio/oauth/callback"]}}), encoding="utf-8")
    settings = Settings(google_client_secret_file=secret, google_oauth_redirect_uri="http://localhost:8000/studio/oauth/callback")
    client = build_google_oauth(settings)
    assert client is not None and "your_client_secret" not in repr(client)
    assert "your_client_secret" not in client.authorization_url(
        "http://localhost:8000/studio/oauth/callback", ("https://www.googleapis.com/auth/youtube.upload",),
        "state-abcdefghijklmnop", "challenge")


def test_google_oauth_is_none_when_the_file_is_missing_or_the_redirect_is_not_registered(tmp_path):
    import json

    from app.studio.composition import build_google_oauth
    assert build_google_oauth(Settings()) is None
    assert build_google_oauth(Settings(google_client_secret_file=tmp_path / "missing.json")) is None
    secret = tmp_path / "client-secret-synthetic.json"
    secret.write_text(json.dumps({"web": {"client_id": "id", "client_secret": "your_client_secret", 
                                          "redirect_uris": ["http://localhost:9000/other"]}}), encoding="utf-8")
    assert build_google_oauth(Settings(google_client_secret_file=secret,
                                       google_oauth_redirect_uri="http://localhost:8000/studio/oauth/callback")) is None


def test_settings_read_the_oauth_file_path_from_env():
    settings = Settings.from_env({"STUDIO_GOOGLE_CLIENT_SECRET_FILE": "/tmp/synthetic-oauth.json",
                                  "STUDIO_GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/cb"})
    assert settings.google_client_secret_file == Path("/tmp/synthetic-oauth.json")
    assert settings.google_oauth_redirect_uri == "http://localhost:8000/cb"


def test_provider_production_is_off_by_default_and_only_enabled_explicitly():
    """F06.T02: produção é sinal explícito; o padrão dev preserva stand-ins no roteamento."""
    assert Settings().provider_production is False
    assert Settings.from_env({}).provider_production is False
    assert Settings.from_env({"STUDIO_PROVIDER_PRODUCTION": "1"}).provider_production is True


# -- VS-03/VS-05c: o estilo do render é resolvido de verdade (fakes, sem banco) --


class _Profile:
    def __init__(self, project_id, style_id):
        self.project_id, self.style_id = project_id, style_id


class _Video:
    def __init__(self, project_id, style_id=None):
        self.project_id, self.style_id = project_id, style_id


class _Channels:
    def __init__(self, profile=None, raises=False):
        self.profile, self.raises = profile, raises

    def get_by_project(self, project_id):
        if self.raises:
            from app.studio.domain.ids import InvalidId
            raise InvalidId("bad id")
        return self.profile


class _Styles:
    def __init__(self, *styles):
        self.by_id = {style.id: style for style in styles if style is not None}

    def get(self, style_id):
        return self.by_id.get(style_id)


P, CHANNEL_STYLE, VIDEO_STYLE = "b" * 32, "a" * 32, "c" * 32


def test_style_for_video_resolves_the_channel_style_when_the_video_has_no_override():
    from app.studio.composition import _style_for_video
    from app.studio.domain.visual_style import VisualStyle

    channel_style = VisualStyle(id=CHANNEL_STYLE, name="Cinemático",
                                params={"motion": ["zoom_in", "pan_right"], "music": {"bpm": 90}})
    resolved = _style_for_video(_Video(P), _Channels(_Profile(P, CHANNEL_STYLE)), _Styles(channel_style))
    assert resolved is not None
    assert resolved.snapshot.style_id == CHANNEL_STYLE and resolved.snapshot.version == 1
    assert resolved.motion == ("zoom_in", "pan_right") and resolved.music == {"bpm": 90}


def test_style_for_video_lets_the_override_win_over_the_channel():
    from app.studio.composition import _style_for_video
    from app.studio.domain.visual_style import VisualStyle

    channel_style = VisualStyle(id=CHANNEL_STYLE, name="Canal", params={"motion": ["zoom_in"]})
    video_style = VisualStyle(id=VIDEO_STYLE, name="Do vídeo", params={"motion": ["pan_left"], "music": {"bpm": 60}})
    video = _Video(P, style_id=VIDEO_STYLE)  # override do vídeo (VS-05b)
    resolved = _style_for_video(video, _Channels(_Profile(P, CHANNEL_STYLE)), _Styles(channel_style, video_style))
    assert resolved is not None
    assert resolved.snapshot.style_id == VIDEO_STYLE  # o vídeo sobrepõe o canal
    assert resolved.motion == ("pan_left",) and resolved.music == {"bpm": 60}


def test_style_for_video_is_none_without_channel_and_video_style():
    from app.studio.composition import _style_for_video
    from app.studio.domain.visual_style import VisualStyle

    styles = _Styles(VisualStyle(id=CHANNEL_STYLE, name="Canal"), VisualStyle(id=VIDEO_STYLE, name="Do vídeo"))
    # sem canal e sem estilo de vídeo (o caso comum hoje) → bundle neutro
    assert _style_for_video(_Video(P), _Channels(None), styles) is None
    # canal sem style_id e vídeo sem override
    assert _style_for_video(_Video(P), _Channels(_Profile(P, None)), styles) is None


def test_style_for_video_tolerates_a_broken_link_without_breaking_the_render():
    from app.studio.composition import _style_for_video
    from app.studio.domain.visual_style import VisualStyle

    channel_style = VisualStyle(id=CHANNEL_STYLE, name="Canal")
    # id inválido no canal não derruba (mesma tolerância do channel_guard_limits)
    assert _style_for_video(_Video(P), _Channels(raises=True), _Styles(channel_style)) is None
    # canal apontando para um estilo inexistente e vídeo sem override → None
    assert _style_for_video(_Video(P), _Channels(_Profile(P, "f" * 32)), _Styles(channel_style)) is None
    # override do vídeo inexistente cai no estilo do canal (nunca derruba)
    fallback = _style_for_video(_Video(P, style_id="f" * 32), _Channels(_Profile(P, CHANNEL_STYLE)), _Styles(channel_style))
    assert fallback is not None and fallback.snapshot.style_id == CHANNEL_STYLE


def test_style_for_video_treats_an_archived_style_as_absent():
    from app.studio.composition import _style_for_video
    from app.studio.domain.visual_style import VisualStyle

    channel_style = VisualStyle(id=CHANNEL_STYLE, name="Canal")
    archived = VisualStyle(id=VIDEO_STYLE, name="Arquivado", archived=True)
    styles = _Styles(channel_style, archived)
    # canal apontando para um estilo arquivado → neutro (defesa em profundidade do VS-05c)
    assert _style_for_video(_Video(P), _Channels(_Profile(P, VIDEO_STYLE)), styles) is None
    # override arquivado cai no estilo do canal, não dirige o render
    resolved = _style_for_video(_Video(P, style_id=VIDEO_STYLE), _Channels(_Profile(P, CHANNEL_STYLE)), styles)
    assert resolved is not None and resolved.snapshot.style_id == CHANNEL_STYLE


# -- VS-06: a voz é resolvida UMA vez (estilo > projeto > default) --


def test_voice_for_video_prefers_the_style_voice_over_the_project():
    from app.studio.composition import _voice_for_video
    from app.studio.domain.visual_style import VisualStyle

    style = VisualStyle(id=CHANNEL_STYLE, name="Com voz", params={"voice": {"model": "pt_BR-jeff-medium"}})
    built = []
    voice = _voice_for_video(_Video(P), _Channels(_Profile(P, CHANNEL_STYLE)), _Styles(style),
                             fallback=lambda project_id: built.append(("fallback", project_id)) or "VOZ DO PROJETO",
                             build_provider=lambda kind, spec: built.append((kind, spec)) or "VOZ DO ESTILO")
    assert voice == "VOZ DO ESTILO"
    assert built == [("voice", "piper:pt_BR-jeff-medium")]  # construído pelo registro, com o prefixo


def test_voice_for_video_accepts_the_piper_prefix_and_the_video_override():
    from app.studio.composition import _voice_for_video
    from app.studio.domain.visual_style import VisualStyle

    channel_style = VisualStyle(id=CHANNEL_STYLE, name="Canal", params={"voice": {"model": "pt_BR-faber-medium"}})
    video_style = VisualStyle(id=VIDEO_STYLE, name="Do vídeo", params={"voice": {"model": "piper:pt_BR-jeff-medium"}})
    specs = []
    _voice_for_video(_Video(P, style_id=VIDEO_STYLE), _Channels(_Profile(P, CHANNEL_STYLE)),
                     _Styles(channel_style, video_style),
                     fallback=lambda project_id: "VOZ DO PROJETO",
                     build_provider=lambda kind, spec: specs.append(spec) or "VOZ")
    # o override do vídeo vence o canal; o prefixo piper: é aceito sem duplicar
    assert specs == ["piper:pt_BR-jeff-medium"]


def test_voice_for_video_falls_back_to_the_project_without_a_style_voice():
    from app.studio.composition import _voice_for_video
    from app.studio.domain.visual_style import VisualStyle

    def never(kind, spec):
        raise AssertionError("não deveria construir voz de estilo")

    # sem canal/estilo nenhum → voz do projeto
    assert _voice_for_video(_Video(P), _Channels(None), _Styles(), lambda pid: f"projeto:{pid}", never) == f"projeto:{P}"
    # canal com estilo, mas sem params.voice → voz do projeto
    no_voice = VisualStyle(id=CHANNEL_STYLE, name="Sem voz", params={"motion": ["zoom_in"]})
    assert _voice_for_video(_Video(P), _Channels(_Profile(P, CHANNEL_STYLE)), _Styles(no_voice),
                            lambda pid: f"projeto:{pid}", never) == f"projeto:{P}"


def test_the_resolved_voice_synthesizes_and_registers_the_same_model():
    """VS-06 fecha a "duas verdades": com voz de estilo, o que sintetiza (arquivo do Piper) e o
    que o cache/ledger registram (``_voice_identity``) derivam do **mesmo** modelo efetivo."""
    from app.studio.adapters.voice_piper import PiperVoice
    from app.studio.application.config import build, register
    from app.studio.application.render import _voice_identity
    from app.studio.composition import _voice_for_video
    from app.studio.domain.render_cache import narration_fingerprint
    from app.studio.domain.visual_style import VisualStyle

    register("voice", "piper", PiperVoice)
    style = VisualStyle(id=CHANNEL_STYLE, name="Voz do canal", params={"voice": {"model": "pt_BR-jeff-medium"}})
    voice = _voice_for_video(_Video(P), _Channels(_Profile(P, CHANNEL_STYLE)), _Styles(style),
                             fallback=lambda project_id: build("voice", "piper:pt_BR-faber-medium"),
                             build_provider=build)
    assert isinstance(voice, PiperVoice) and voice.model == "pt_BR-jeff-medium"
    assert voice.voice_path == "/opt/voices/pt_BR-jeff-medium.onnx"  # o que sintetiza
    identity = _voice_identity(voice)
    assert identity == "piper:pt_BR-jeff-medium"                    # o que registra
    project_identity = _voice_identity(build("voice", "piper:pt_BR-faber-medium"))
    assert narration_fingerprint("texto da cena", "voice:cena", {"voice": identity}) != \
        narration_fingerprint("texto da cena", "voice:cena", {"voice": project_identity})


# -- F01.T01: o token da publicação vem do grant do canal de destino ----------


def test_publish_wiring_takes_the_token_from_the_target_channel_grant(conn, dsn, tmp_path):
    """A fiação real (sem rede): projeto com destino → token do grant daquele canal no cofre."""
    import json
    from datetime import datetime, timedelta, timezone

    import psycopg

    from app.studio.adapters.postgres.channel_repo import PostgresChannelProfileRepository
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.adapters.postgres.youtube_identity_repo import (
        PostgresChannelAuthorizationRepository, PostgresGoogleAccountRepository,
        PostgresOAuthGrantRepository, PostgresYouTubeChannelIdentityRepository,
    )
    from app.studio.adapters.secret_store import FileSecretStore
    from app.studio.application.channel_grant import EnsureGrantAccessToken
    from app.studio.application.connections import grant_scope
    from app.studio.application.publication_execution import (
        FallbackTokenProvider, TargetChannelTokenProvider,
    )
    from app.studio.domain.youtube_channel import OAuthStatus
    from app.studio.domain.youtube_identity import (
        ChannelAuthorization, GoogleAccount, OAuthGrant, YouTubeChannelIdentity,
    )
    from app.studio.domain.youtube_oauth import DEFAULT_SCOPES

    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    project = PostgresVideoRepository(connect).create_project("Canal", niche="Geral", language="pt-BR")
    PostgresYouTubeChannelIdentityRepository(connect).upsert(
        YouTubeChannelIdentity(youtube_channel_id="UCtargetA", title="Canal A"))
    PostgresChannelProfileRepository(connect).create(project.id, "Canal", youtube_channel_id="UCtargetA")
    aid, gid = "a" * 32, "b" * 32
    PostgresGoogleAccountRepository(connect).upsert(GoogleAccount(id=aid, email="EU@gmail.com"))
    now = datetime.now(timezone.utc)
    PostgresOAuthGrantRepository(connect).create(OAuthGrant(
        id=gid, account_id=aid, scopes=DEFAULT_SCOPES, status=OAuthStatus.CONNECTED,
        token_expires_at=now + timedelta(hours=1)))
    PostgresChannelAuthorizationRepository(connect).link(ChannelAuthorization(
        grant_id=gid, youtube_channel_id="UCtargetA", status=OAuthStatus.CONNECTED, validated_at=now))
    vault = FileSecretStore(tmp_path / "secrets")
    vault.set(grant_scope(gid), "access_token", "ya29.SYNTHETIC_grant_access")
    vault.set(grant_scope(gid), "refresh_token", "1//SYNTHETIC_grant_refresh")
    vault.set(grant_scope(gid), "token_expires_at", (now + timedelta(hours=1)).isoformat())

    secret = tmp_path / "client-secret-synthetic.json"
    secret.write_text(json.dumps({"web": {
        "client_id": "client-id.apps.googleusercontent.com",
        "client_secret": "your_client_secret",
        "redirect_uris": ["http://localhost:8000/studio/oauth/callback"]}}), encoding="utf-8")
    settings = Settings(database_url=dsn, storage_root=tmp_path, secrets_root=tmp_path / "secrets",
                        google_client_secret_file=secret,
                        google_oauth_redirect_uri="http://localhost:8000/studio/oauth/callback")
    tokens = Studio(settings).use_cases().publishing.publish.tokens

    assert isinstance(tokens, TargetChannelTokenProvider)
    assert isinstance(tokens.targeted, EnsureGrantAccessToken)
    assert isinstance(tokens.legacy, FallbackTokenProvider)
    access = tokens.execute(project.id)
    assert access.token == "ya29.SYNTHETIC_grant_access" and access.youtube_channel_id == "UCtargetA"
    assert "SYNTHETIC_grant_access" not in repr(access)


def test_publish_wiring_keeps_the_legacy_path_restricted_to_projects_without_a_target(conn, dsn, tmp_path):
    """Projeto sem destino não toca o caminho do grant: segue o legado (cofre por projeto)."""
    import psycopg

    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.adapters.secret_store import FileSecretStore

    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    project = PostgresVideoRepository(connect).create_project("Canal Legado", niche="Geral", language="pt-BR")
    vault = FileSecretStore(tmp_path / "secrets")
    vault.set(f"youtube:{project.id}", "access_token", "ya29.SYNTHETIC_legacy_access")
    from datetime import datetime, timedelta, timezone
    vault.set(f"youtube:{project.id}", "token_expires_at",
              (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    import json
    secret = tmp_path / "client-secret-synthetic.json"
    secret.write_text(json.dumps({"web": {
        "client_id": "client-id.apps.googleusercontent.com",
        "client_secret": "your_client_secret",
        "redirect_uris": ["http://localhost:8000/studio/oauth/callback"]}}), encoding="utf-8")

    tokens = Studio(Settings(database_url=dsn, storage_root=tmp_path, secrets_root=tmp_path / "secrets",
                             google_client_secret_file=secret,
                             google_oauth_redirect_uri="http://localhost:8000/studio/oauth/callback")
                    ).use_cases().publishing.publish.tokens

    access = tokens.execute(project.id)
    assert access.token == "ya29.SYNTHETIC_legacy_access"  # caminho legado preservado, sem destino


# -- F03.T02: a composição resolve a configuração efetiva antes de criar o run ----


def test_production_wiring_resolves_the_channel_defaults_into_the_run(conn, dsn, tmp_path):
    import psycopg

    from app.studio.adapters.postgres.channel_repo import PostgresChannelProfileRepository
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.domain.contracts import VideoFormat
    from app.studio.domain.run_config import RunConfigStatus

    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    project = PostgresVideoRepository(connect).create_project("Canal", niche="Geral", language="en-US")
    channel = PostgresChannelProfileRepository(connect).create(project.id, "Canal", language="en-US")
    video = PostgresVideoRepository(connect).create_video(project.id, "Um tema de história", VideoFormat.short)

    production = Studio(Settings(database_url=dsn, storage_root=tmp_path)).use_cases().production
    creation = production.coordinator.start(
        video.id, "cfg-composition-1",
        effective_config_for=production.effective_config_for, config_store=production.config_store)
    stored = production.config_for(creation.run.run_id)
    assert stored is not None and stored.status is RunConfigStatus.RESOLVED
    assert stored.config.language == "en-US"                       # camada do canal, não default
    assert stored.config.channel_profile.id == channel.id
    assert stored.config.provenance["editorial.language"] == "channel"


# -- F03.T03: a voz sai da configuração efetiva congelada (sem segunda leitura de estilo) --


class _Config:
    def __init__(self, voice=None):
        self.voice = voice or {}


def test_voice_for_config_uses_the_frozen_voice_model_without_reading_the_style_again():
    from app.studio.composition import _voice_for_config

    built = []
    voice = _voice_for_config(_Video(P), _Config({"model": "pt_BR-jeff-medium"}),
                              fallback=lambda project_id: built.append(("fallback", project_id)) or "VOZ DO PROJETO",
                              build_provider=lambda kind, spec: built.append((kind, spec)) or "VOZ DO SNAPSHOT")
    assert voice == "VOZ DO SNAPSHOT"
    assert built == [("voice", "piper:pt_BR-jeff-medium")]


def test_voice_for_config_falls_back_to_the_project_when_the_snapshot_has_no_voice():
    from app.studio.composition import _voice_for_config

    def never(kind, spec):
        raise AssertionError("não deveria construir voz de estilo")

    assert _voice_for_config(_Video(P), _Config(), lambda pid: f"projeto:{pid}", never) == f"projeto:{P}"


# -- F06.T02: a execução consome a decisão de roteamento (perfil econômico), com auditoria ----


class _Project:
    def __init__(self, config):
        self.id, self.config = P, config


class _Projects:
    def __init__(self, config=None):
        self.config = config or {}

    def get_project(self, project_id):
        return _Project(self.config) if project_id == P else None


class _BuiltProvider:
    def __init__(self, spec):
        self.name, _, self.model = spec.partition(":")
        self.spec = spec


def _routing(*, config=None, implementations=(), build=None, profile=..., production=False,
             max_cost=None):
    from decimal import Decimal
    from types import SimpleNamespace

    from app.studio.application.providers import ProviderService
    from app.studio.composition import ProviderRouting

    service = ProviderService(_Projects(config), {}, list(implementations))
    built = []

    def default_build(kind, spec):
        built.append(spec)
        return _BuiltProvider(spec)

    limits = None if profile is None else SimpleNamespace(
        economic_profile=profile,
        hard_video_usd=Decimal("1000") if max_cost is None else max_cost)
    routing = ProviderRouting(
        service, build or default_build,
        configured_spec=lambda kind, project_id: (config or {}).get(kind) or {
            "text": "demo:local", "image": "placeholder:", "voice": "piper:pt_BR-faber-medium",
            "renderer": "ffmpeg:rich"}[kind],
        limits_for=lambda project_id: limits,
        production=production)
    return routing, built


def _impl(name, *, cost, quality=3, capabilities=("text.generate",), validated=True):
    from app.studio.domain.provider import ProviderImplementation, ProviderKind

    return ProviderImplementation(ProviderKind.TEXT, name, capabilities=capabilities, cost=cost,
                                  quality=quality, validated=validated,
                                  reason=None if validated else "not validated")


def _decision_events(caplog):
    import json

    return [json.loads(record.message) for record in caplog.records
            if record.name == "studio.providers" and record.message.startswith("{")]


def test_provider_for_executes_the_economy_decision_instead_of_the_configured_spec(caplog):
    """(a) ECONOMY escolhe o candidato mais barato disponível, mesmo com outro configurado."""
    import logging
    from decimal import Decimal

    from app.studio.domain.provider import CostEstimate, EconomicProfile

    caplog.set_level(logging.INFO, logger="studio.providers")
    routing, built = _routing(
        config={"text": "premium:top"},
        implementations=[
            _impl("cheap", cost=CostEstimate.estimate(Decimal("0.01")), quality=2),
            _impl("premium", cost=CostEstimate.estimate(Decimal("0.90")), quality=5),
        ],
        profile=EconomicProfile.ECONOMY)

    provider = routing("text", P)

    assert built == ["cheap"]                      # executou a decisão, não o spec configurado
    assert provider.name == "cheap"
    events = _decision_events(caplog)
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "provider_decision" and event["attempt"] == 1
    assert event["candidate"] == "cheap" and event["effective"] == "cheap"
    assert event["profile"] == "ECONOMY"
    assert "ECONOMY" in event["reason"] and "custo" in event["reason"]


def test_provider_for_reevaluates_explicitly_when_the_decided_provider_is_unavailable(caplog):
    """(b) provider decidido indisponível → nova avaliação auditada, nunca troca silenciosa."""
    import logging
    from decimal import Decimal

    from app.studio.application.config import ProviderNotFound
    from app.studio.domain.provider import CostEstimate, EconomicProfile

    caplog.set_level(logging.INFO, logger="studio.providers")
    service_impls = [
        _impl("cheap", cost=CostEstimate.free(), quality=2),
        _impl("demo", cost=CostEstimate.free(), quality=1),
    ]
    attempts = []

    def build(kind, spec):
        attempts.append(spec)
        if spec == "cheap":
            raise ProviderNotFound("no text provider for 'cheap:'")
        return _BuiltProvider(spec)

    routing, _ = _routing(config={"text": "demo:local"}, implementations=service_impls,
                          build=build, profile=EconomicProfile.ECONOMY)

    provider = routing("text", P)

    assert attempts == ["cheap", "demo:local"]    # reavaliou; não caiu calado no configurado
    assert provider.name == "demo"
    first, second = _decision_events(caplog)
    assert (first["attempt"], first["candidate"], first["effective"]) == (1, "cheap", None)
    assert "unavailable" in first["reason"] and "ProviderNotFound" in first["reason"]
    assert (second["attempt"], second["candidate"], second["effective"]) == (2, "demo:local", "demo")


def test_provider_for_fails_with_the_reason_when_no_acceptable_candidate_exists(caplog):
    """(c) sem candidato aceitável o erro é explícito e nada é construído/executado."""
    import logging

    from app.studio.domain.provider import CostEstimate, EconomicProfile, NoProviderAvailable

    caplog.set_level(logging.INFO, logger="studio.providers")
    routing, built = _routing(
        implementations=[_impl("demo", cost=CostEstimate.free(), quality=1)],
        profile=EconomicProfile.ECONOMY, production=True)

    with pytest.raises(NoProviderAvailable) as excinfo:
        routing("text", P)

    assert "non-production provider" in str(excinfo.value)
    assert built == []
    events = _decision_events(caplog)
    assert len(events) == 1 and events[0]["effective"] is None
    assert "non-production provider" in events[0]["reason"]
    assert events[0]["attempt"] == 1


def test_provider_for_without_a_profile_keeps_the_configured_spec_unchanged():
    """(e) sem perfil econômico a execução continua exatamente como antes (sem rotear)."""
    from app.studio.application.providers import ProviderService
    from app.studio.composition import ProviderRouting

    class _NoRoute(ProviderService):
        def route(self, *args, **kwargs):  # pragma: no cover - falha se chamado
            raise AssertionError("não deveria rotear sem perfil econômico")

    built = []
    routing = ProviderRouting(_NoRoute(_Projects(), {}, []),
                              lambda kind, spec: built.append(spec) or _BuiltProvider(spec),
                              configured_spec=lambda kind, project_id: "premium:top")

    provider = routing("text", P)

    assert built == ["premium:top"] and provider.name == "premium" and provider.model == "top"


def test_provider_routing_uses_the_frozen_run_selection_without_routing():
    """S8: a seleção congelada no run vence a política e não é re-roteada."""
    from app.studio.application.production import use_frozen_provider_selection
    from app.studio.domain.provider import EconomicProfile

    routing, built = _routing(profile=EconomicProfile.PREMIUM)
    routing.service.route = lambda *a, **k: pytest.fail("a seleção congelada não deve ser re-roteada")

    with use_frozen_provider_selection({"text": "frozen:model"}):
        provider = routing("text", P)

    assert built == ["frozen:model"]
    assert provider.name == "frozen"


def test_a_frozen_selection_that_does_not_build_is_not_replaced_by_live_routing():
    """S8: se a seleção congelada não constrói, o erro sobe; nunca há troca silenciosa."""
    from app.studio.application.config import ProviderNotFound
    from app.studio.application.production import use_frozen_provider_selection
    from app.studio.domain.provider import EconomicProfile

    def _build(kind, spec):
        raise ProviderNotFound("gone")

    routing, _ = _routing(profile=EconomicProfile.PREMIUM, build=_build)
    routing.service.route = lambda *a, **k: pytest.fail("a seleção congelada não deve ser re-roteada")

    with use_frozen_provider_selection({"text": "frozen:model"}):
        with pytest.raises(ProviderNotFound):
            routing("text", P)


def test_wiring_consumes_the_channel_profile_and_keeps_the_legacy_path_without_it(conn, dsn, tmp_path, caplog):
    """F06.T02: a fiação real roteia pelo perfil do canal; sem perfil, o spec configurado manda."""
    import logging
    from decimal import Decimal

    import psycopg

    from app.studio.adapters.postgres.channel_budget_repo import PostgresChannelBudgetRepository
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.domain.channel_budget import BudgetLimits
    from app.studio.domain.provider import EconomicProfile

    caplog.set_level(logging.INFO, logger="studio.providers")
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    routed = videos.create_project("Roteado", niche="Geral", language="pt-BR")
    legacy = videos.create_project("Legado", niche="Geral", language="pt-BR")
    PostgresChannelBudgetRepository(connect).upsert(BudgetLimits(
        project_id=routed.id, hard_monthly_usd=Decimal("5"), soft_monthly_usd=Decimal("3"),
        hard_video_usd=Decimal("1"), soft_video_usd=Decimal("1"),
        economic_profile=EconomicProfile.ECONOMY))
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path, bridge_token="fake-token"),
                    environ={"STUDIO_TEXT": "opencode:gpt-legado"})
    model_for = studio.use_cases().editorial.generate.model_for

    assert model_for(routed.id).name == "demo"          # ECONOMY executou a decisão roteada
    assert model_for(legacy.id).name == "opencode"      # sem perfil: comportamento de antes
    assert model_for(legacy.id).model == "gpt-legado"

    events = [record.message for record in caplog.records if record.name == "studio.providers"]
    assert any('"profile": "ECONOMY"' in message and '"effective": "demo"' in message
               for message in events)
    assert any('"profile": null' in message and '"candidate": "opencode:gpt-legado"' in message
               for message in events)


def test_studio_wires_creative_director_on_editorial(tmp_path, dsn):
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path),
                    environ={"STUDIO_TEXT": "demo:mock"})
    editorial = studio.use_cases().editorial
    assert editorial.creative_director is not None
    from app.studio.application.creative_director import CreateCreativeBrief
    assert isinstance(editorial.creative_director, CreateCreativeBrief)


def test_recovery_interval_setting_parsing():
    assert Settings().recovery_interval_seconds == 60.0
    assert Settings.from_env({}).recovery_interval_seconds == 60

    def parse(v):
        return Settings.from_env({"STUDIO_RECOVERY_INTERVAL_SECONDS": v}).recovery_interval_seconds

    assert parse("0") == 0
    assert parse("2") == 5
    assert parse("30") == 30
    for bad in ("abc", "", "-1", "nan", "inf"):
        assert parse(bad) == 60
