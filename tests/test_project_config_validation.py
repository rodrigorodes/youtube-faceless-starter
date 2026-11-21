"""PUT /studio/projects/{id}/config: prova HTTP sem banco (fakes) de que a escrita recusa cedo.

Complementa os testes com Postgres de `test_channel_api.py`: aqui o foco é a regra de aceitação e
a higiene da mensagem — provedor inexistente é 422 e o valor ofensor nunca aparece na resposta.
"""
import base64
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.routes import make_router  # noqa: E402
from app.studio.application.secrets import GetPublicProjectConfig, SetPublicProjectConfig  # noqa: E402
from app.studio.application.use_cases import UseCases  # noqa: E402
from app.studio.domain.contracts import Project  # noqa: E402
from app.studio.domain.provider import CostEstimate, ProviderImplementation, ProviderKind  # noqa: E402

WORKER_HEADER = {"Authorization": "Bearer test-worker-token"}
PID = "c" * 32


class _FakeVideos:
    """Repositório mínimo em memória: guarda o config por projeto como o Postgres faria."""

    def __init__(self, config):
        self._project = Project(id=PID, name="fake", config=dict(config))

    def get_project(self, project_id):
        return self._project if project_id == PID else None

    def set_project_config(self, project_id, config):
        if project_id != PID:
            return None
        self._project = self._project.model_copy(update={"config": dict(config)})
        return self._project


def _implementations():
    return [
        ProviderImplementation(ProviderKind.TEXT, "demo", cost=CostEstimate.free(), validated=True),
        ProviderImplementation(ProviderKind.TEXT, "opencode", validated=False, reason="token ausente"),
        ProviderImplementation(ProviderKind.IMAGE, "placeholder", cost=CostEstimate.free(), validated=True),
        ProviderImplementation(ProviderKind.IMAGE, "veo", cost=CostEstimate.estimate("0.4"),
                               validated=False, reason="experimental"),
        ProviderImplementation(ProviderKind.VOICE, "piper", cost=CostEstimate.free(), validated=True),
        ProviderImplementation(ProviderKind.RENDERER, "ffmpeg", cost=CostEstimate.free(), validated=True),
    ]


def _client():
    videos = _FakeVideos({})
    use_cases = UseCases(None, None, None, None,
                         get_project_config=GetPublicProjectConfig(videos),
                         set_project_config=SetPublicProjectConfig(videos, _implementations()))
    app = FastAPI()
    app.include_router(make_router(lambda: use_cases, lambda: True))
    client = TestClient(app)
    auth = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
    return client, auth


VALID = {"text": "demo", "image": "placeholder", "voice": "piper", "renderer": "ffmpeg"}


def test_unknown_provider_is_422_and_the_offending_value_does_not_leak():
    client, auth = _client()
    r = client.put(f"/studio/projects/{PID}/config",
                   json={**VALID, "text": "nope-do-not-echo"}, headers={**auth, **WORKER_HEADER})
    assert r.status_code == 422, r.text
    assert "nope-do-not-echo" not in r.text
    assert "demo" in r.text and "opencode" in r.text  # a mensagem diz o que existe na porta


def test_registered_valid_and_unvalidated_providers_are_accepted_and_get_round_trips():
    client, auth = _client()
    body = {**VALID, "image": "veo:veo-3.1"}  # registrado porém não validado: aceito
    r = client.put(f"/studio/projects/{PID}/config", json=body, headers={**auth, **WORKER_HEADER})
    assert r.status_code == 200, r.text
    assert client.get(f"/studio/projects/{PID}/config", headers={**auth, **WORKER_HEADER}).json()["config"] == body


def test_missing_port_is_422_listing_the_ports_and_never_persists():
    client, auth = _client()
    r = client.put(f"/studio/projects/{PID}/config", json={"text": "demo"},
                   headers={**auth, **WORKER_HEADER})
    assert r.status_code == 422 and "image" in r.text and "renderer" in r.text
    assert client.get(f"/studio/projects/{PID}/config", headers={**auth, **WORKER_HEADER}).json()["config"] == {}
