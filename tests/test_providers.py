import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app import main  # noqa: E402

SLIDES = '["a","b","c","d"]'
OK = {"candidates": [{"content": {"parts": [{"text": SLIDES}]}}]}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("AI_PROVIDER", "GEMINI_API_KEY", "VERTEX_PROJECT", "VERTEX_LOCATION", "VERTEX_MODEL", "OPENCODE_BRIDGE_TOKEN", "OPENCODE_BRIDGE_URL"):
        monkeypatch.delenv(name, raising=False)


def run(coro):
    import asyncio
    return asyncio.run(coro)


def capture(monkeypatch, response=OK, error=None):
    calls = []

    async def fake(url, headers, payload, **kwargs):
        calls.append((url, headers, payload))
        if error:
            raise error
        return response

    monkeypatch.setattr(main, "post_json", fake)
    return calls


def test_auto_without_key_is_demo(monkeypatch):
    calls = capture(monkeypatch)
    slides = run(main.generate_script("Tema X", "doc"))
    assert slides[0] == "Tema X" and len(slides) == 4 and not calls


def test_auto_with_gemini_key_uses_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    calls = capture(monkeypatch)
    assert run(main.generate_script("t", "s")) == ["a", "b", "c", "d"]
    assert calls[0][0].startswith("https://generativelanguage.googleapis.com/") and calls[0][1] == {"x-goog-api-key": "k"}


def test_vertex_global_endpoint_and_bearer(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "vertex")
    monkeypatch.setenv("VERTEX_PROJECT", "meu-projeto")
    monkeypatch.setattr(main, "vertex_access_token", lambda: "tok")
    calls = capture(monkeypatch)
    assert run(main.generate_script("t", "s")) == ["a", "b", "c", "d"]
    url, headers, payload = calls[0]
    assert url == "https://aiplatform.googleapis.com/v1/projects/meu-projeto/locations/global/publishers/google/models/gemini-2.5-flash:generateContent"
    assert headers == {"Authorization": "Bearer tok"}
    assert payload["contents"][0]["role"] == "user"


def test_vertex_regional_endpoint():
    assert main.vertex_endpoint("p", "us-central1", "m") == "https://us-central1-aiplatform.googleapis.com/v1/projects/p/locations/us-central1/publishers/google/models/m:generateContent"


def test_vertex_requires_project(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "vertex")
    with pytest.raises(HTTPException) as e:
        run(main.generate_script("t", "s"))
    assert e.value.status_code == 500 and "VERTEX_PROJECT" in e.value.detail


def test_vertex_auth_failure_is_502_without_leak(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "vertex")
    monkeypatch.setenv("VERTEX_PROJECT", "p")

    def boom():
        raise RuntimeError("secret-detail")

    monkeypatch.setattr(main, "vertex_access_token", boom)
    with pytest.raises(HTTPException) as e:
        run(main.generate_script("t", "s"))
    assert e.value.status_code == 502 and "secret-detail" not in e.value.detail


def test_vertex_http_error_reports_status(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "vertex")
    monkeypatch.setenv("VERTEX_PROJECT", "p")
    monkeypatch.setattr(main, "vertex_access_token", lambda: "tok")
    req = httpx.Request("POST", "https://x")
    capture(monkeypatch, error=httpx.HTTPStatusError("e", request=req, response=httpx.Response(403, request=req)))
    with pytest.raises(HTTPException) as e:
        run(main.generate_script("t", "s"))
    assert e.value.status_code == 502 and "HTTP 403" in e.value.detail and "Vertex" in e.value.detail


def test_invalid_model_output_is_502(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    capture(monkeypatch, response={"candidates": [{"content": {"parts": [{"text": '["só um"]'}]}}]})
    with pytest.raises(HTTPException) as e:
        run(main.generate_script("t", "s"))
    assert e.value.status_code == 502


def test_gemini_explicit_requires_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    with pytest.raises(HTTPException) as e:
        run(main.generate_script("t", "s"))
    assert e.value.status_code == 500


def test_invalid_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "foo")
    with pytest.raises(HTTPException) as e:
        run(main.generate_script("t", "s"))
    assert e.value.status_code == 500


def test_vertex_access_token_refreshes_and_caches(monkeypatch):
    import google.auth

    class Creds:
        valid = False
        token = None
        refreshes = 0

        def refresh(self, _request):
            Creds.refreshes += 1
            self.valid, self.token = True, "fresh-token"

    seen = {}

    def fake_default(scopes=None):
        seen["scopes"] = scopes
        return Creds(), "proj"

    monkeypatch.setattr(google.auth, "default", fake_default)
    monkeypatch.setattr(main, "_vertex_credentials", None)
    assert main.vertex_access_token() == "fresh-token"
    assert main.vertex_access_token() == "fresh-token"
    assert Creds.refreshes == 1
    assert seen["scopes"] == ["https://www.googleapis.com/auth/cloud-platform"]


def test_opencode_calls_bridge_with_bearer(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "opencode")
    monkeypatch.setenv("OPENCODE_BRIDGE_TOKEN", "t" * 20)
    calls = capture(monkeypatch, response={"text": SLIDES})
    assert run(main.generate_script("t", "s")) == ["a", "b", "c", "d"]
    url, headers, payload = calls[0]
    assert url == "http://host.docker.internal:8787/generate"
    assert headers == {"Authorization": "Bearer " + "t" * 20}
    assert "Tema: t" in payload["prompt"]


def test_opencode_accepts_markdown_fenced_json(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "opencode")
    monkeypatch.setenv("OPENCODE_BRIDGE_TOKEN", "t" * 20)
    capture(monkeypatch, response={"text": "```json\n" + SLIDES + "\n```"})
    assert run(main.generate_script("t", "s")) == ["a", "b", "c", "d"]


def test_opencode_requires_token(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "opencode")
    with pytest.raises(HTTPException) as e:
        run(main.generate_script("t", "s"))
    assert e.value.status_code == 500 and "OPENCODE_BRIDGE_TOKEN" in e.value.detail


def test_opencode_bridge_down_is_502(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "opencode")
    monkeypatch.setenv("OPENCODE_BRIDGE_TOKEN", "t" * 20)
    capture(monkeypatch, error=httpx.ConnectError("refused"))
    with pytest.raises(HTTPException) as e:
        run(main.generate_script("t", "s"))
    assert e.value.status_code == 502 and "bridge" in e.value.detail


def test_content_object_with_metadata(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "opencode")
    monkeypatch.setenv("OPENCODE_BRIDGE_TOKEN", "t" * 20)
    obj = '{"slides":["a","b","c","d"],"title":"  Meu título  ","description":"desc","tags":["x"," ",5,"y"]}'
    calls = capture(monkeypatch, response={"text": obj})
    out = run(main.generate_content("tema", "doc", "FATO: algo verificado"))
    assert out == {"slides": ["a", "b", "c", "d"], "title": "Meu título", "description": "desc", "tags": ["x", "y"]}
    assert "SOMENTE" in calls[0][2]["prompt"] and "FATO: algo verificado" in calls[0][2]["prompt"]


def test_prompt_without_context_has_no_context_block():
    prompt = main.build_prompt("t", "s")
    assert "CONTEXTO:" not in prompt and "Sem alegações" in prompt


def test_old_list_format_still_valid(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "opencode")
    monkeypatch.setenv("OPENCODE_BRIDGE_TOKEN", "t" * 20)
    capture(monkeypatch, response={"text": SLIDES})
    out = run(main.generate_content("t", "s"))
    assert out["slides"] == ["a", "b", "c", "d"] and out["title"] == "" and out["tags"] == []


def test_video_request_validates_sources():
    ok = main.VideoRequest(topic="abc", sources=["https://www.amsterdam-dance-event.nl/en/news/"])
    assert str(ok.sources[0]).startswith("https://")
    with pytest.raises(Exception):
        main.VideoRequest(topic="abc", sources=["javascript:alert(1)"])
    with pytest.raises(Exception):
        main.VideoRequest(topic="abc", sources=["https://a.com"] * 6)
