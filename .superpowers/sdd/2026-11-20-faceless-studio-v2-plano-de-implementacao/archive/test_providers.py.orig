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


# ---------- modo rich ----------

def test_storyboard_parse_valid_and_clamped():
    scenes = [{"narration": f"Narração número {i} da cena", "caption": "c" * 200, "label": "QUA • 21/10", "image_prompt": "a stage"} for i in range(5)]
    out = main.parse_storyboard_text('```json\n' + __import__("json").dumps({"title": " T ", "description": "d", "tags": ["a", 3], "scenes": scenes}) + '\n```', 5)
    assert len(out["scenes"]) == 5 and len(out["scenes"][0]["caption"]) == 110 and out["title"] == "T" and out["tags"] == ["a"]


@pytest.mark.parametrize("raw", ['{"scenes": []}', '{"scenes": [{"narration": "x"}]}', '[1,2,3]', '{"scenes": "no"}'])
def test_storyboard_parse_rejects_invalid(raw):
    with pytest.raises((ValueError, TypeError, AttributeError)):
        main.parse_storyboard_text(raw, 5)


def test_storyboard_requires_ai_provider(monkeypatch):
    with pytest.raises(HTTPException) as e:
        run(main.generate_storyboard("t", "s", "", 6))
    assert e.value.status_code == 422


def test_storyboard_prompt_forbids_real_people_and_requires_context():
    prompt = main.build_storyboard_prompt("tema", "doc", "FATO X", 8)
    assert "EXATAMENTE 8" in prompt and "PROIBIDO" in prompt and "SOMENTE" in prompt and "FATO X" in prompt


def test_scene_model_limits():
    main.Scene(narration="Uma fala válida", image_prompt="a nice stage with lights")
    with pytest.raises(Exception):
        main.Scene(narration="x", image_prompt="a nice stage with lights")
    with pytest.raises(Exception):
        main.VideoRequest(topic="abc", scenes=[{"narration": "Uma fala válida", "image_prompt": "a stage with lights"}] * 17)


def test_fetch_image_placeholder(monkeypatch, tmp_path):
    monkeypatch.setenv("IMAGE_PROVIDER", "placeholder")
    dst = tmp_path / "i.png"
    run(main.fetch_image("prompt", 2, dst))
    from PIL import Image
    assert Image.open(dst).size == (1080, 1920)


def test_fetch_image_via_bridge_and_retry(monkeypatch, tmp_path):
    import base64, io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (768, 1344), (200, 10, 90)).save(buf, "WEBP")
    monkeypatch.setenv("OPENCODE_BRIDGE_TOKEN", "t" * 20)
    attempts = []

    async def flaky(url, headers, payload, **kw):
        attempts.append((url, payload["prompt"]))
        if len(attempts) == 1:
            raise httpx.ConnectError("boom")
        return {"mime": "image/webp", "data": base64.b64encode(buf.getvalue()).decode()}

    monkeypatch.setattr(main, "post_json", flaky)
    dst = tmp_path / "i.png"
    run(main.fetch_image("stage lights", 0, dst))
    assert len(attempts) == 2 and attempts[0][0].endswith("/image") and "no text" in attempts[0][1]
    assert Image.open(dst).size == (1080, 1920)


def test_fetch_image_failure_is_502(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCODE_BRIDGE_TOKEN", "t" * 20)
    capture(monkeypatch, error=httpx.ConnectError("down"))
    with pytest.raises(HTTPException) as e:
        run(main.fetch_image("p", 3, tmp_path / "i.png"))
    assert e.value.status_code == 502 and "scene 4" in e.value.detail
