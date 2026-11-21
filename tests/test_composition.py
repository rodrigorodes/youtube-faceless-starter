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


# -- VS-03: o estilo do canal é resolvido de verdade (fakes, sem banco) --


class _Profile:
    def __init__(self, project_id, style_id):
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
    def __init__(self, style=None):
        self.style = style

    def get(self, style_id):
        return self.style if style_id == (self.style.id if self.style else None) else None


def test_style_for_project_resolves_the_channel_visual_style():
    from app.studio.composition import _style_for_project
    from app.studio.domain.visual_style import VisualStyle

    style_id = "a" * 32
    visual = VisualStyle(id=style_id, name="Cinemático",
                         params={"motion": ["zoom_in", "pan_right"], "music": {"bpm": 90}})
    resolved = _style_for_project("b" * 32, _Channels(_Profile("b" * 32, style_id)), _Styles(visual))
    assert resolved is not None
    assert resolved.snapshot.style_id == style_id and resolved.snapshot.version == 1
    assert resolved.motion == ("zoom_in", "pan_right") and resolved.music == {"bpm": 90}


def test_style_for_project_is_none_without_channel_or_style():
    from app.studio.composition import _style_for_project
    from app.studio.domain.visual_style import VisualStyle

    style_id = "a" * 32
    visual = VisualStyle(id=style_id, name="Cinemático")
    # sem canal
    assert _style_for_project("b" * 32, _Channels(None), _Styles(visual)) is None
    # canal sem style_id
    assert _style_for_project("b" * 32, _Channels(_Profile("b" * 32, None)), _Styles(visual)) is None
    # style_id aponta para um estilo inexistente
    assert _style_for_project("b" * 32, _Channels(_Profile("b" * 32, style_id)), _Styles(None)) is None
    # id inválido não derruba a composição (mesma tolerância do channel_guard_limits)
    assert _style_for_project("not-a-hex-id", _Channels(raises=True), _Styles(visual)) is None
