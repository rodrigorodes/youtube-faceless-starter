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
    from decimal import Decimal

    from app.studio.composition import _ChannelBudgetFloor
    from app.studio.domain.channel_budget import BudgetLimits

    class Usage:
        def spent_month(self):
            return 4.0

    limits = BudgetLimits(project_id="a" * 32, hard_monthly_usd=Decimal("9"), soft_monthly_usd=Decimal("5"),
                          hard_video_usd=Decimal("2"), soft_video_usd=Decimal("1"))
    floor = _ChannelBudgetFloor(Usage(), _Videos({"b" * 32: _Video("a" * 32)}), _Budgets([limits]),
                                Decimal("15"))
    projection = floor.project(type("R", (), {"video_id": "b" * 32}), None)
    assert projection.ceiling_usd == Decimal("5")  # soft do canal, não o padrão
    assert projection.projected_usd == Decimal("4.0")
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
