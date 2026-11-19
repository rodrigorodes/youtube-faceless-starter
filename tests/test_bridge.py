import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("bridge", Path(__file__).resolve().parents[1] / "scripts" / "opencode-bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

TOKEN = "x" * 24


@pytest.fixture()
def server():
    seen = []

    def fake_generate(prompt, model_ref, binary):
        seen.append((prompt, model_ref))
        if prompt == "boom":
            raise RuntimeError("secret internals")
        return "resposta"

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), bridge.make_handler(TOKEN, "openai/gpt-6-luna", "opencode", fake_generate))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def call(url, path, body=None, token=TOKEN, method="POST"):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health_open(server):
    assert call(server[0], "/health", method="GET", token=None)[0] == 200


def test_requires_token(server):
    assert call(server[0], "/generate", {"prompt": "oi"}, token=None)[0] == 401
    assert call(server[0], "/generate", {"prompt": "oi"}, token="errado")[0] == 401
    assert not server[1]


def test_generate_ok(server):
    assert call(server[0], "/generate", {"prompt": "oi"}) == (200, {"text": "resposta"})
    assert server[1] == [("oi", "openai/gpt-6-luna")]


@pytest.mark.parametrize("body", [{}, {"prompt": ""}, {"prompt": 5}, {"prompt": "a" * 4001}])
def test_invalid_body(server, body):
    assert call(server[0], "/generate", body)[0] == 400


def test_failure_does_not_leak(server):
    status, payload = call(server[0], "/generate", {"prompt": "boom"})
    assert status == 502 and "secret" not in json.dumps(payload)


def test_unknown_path(server):
    assert call(server[0], "/outra", {"prompt": "oi"})[0] == 404


def test_parse_model():
    assert bridge.parse_model("openai/gpt-6-luna") == {"providerID": "openai", "id": "gpt-6-luna"}
    assert bridge.parse_model("openai/gpt-6-luna#low")["variant"] == "low"
    with pytest.raises(ValueError):
        bridge.parse_model("semprovider")


# ---------- imagens ----------

@pytest.fixture()
def image_server():
    seen = []

    def fake_image(prompt, model, binary):
        seen.append((prompt, model))
        return {"mime": "image/webp", "data": "QUJD"}

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), bridge.make_handler(TOKEN, "openai/gpt-6-luna", "opencode", image_model="openrouter/x/y:free", image_fn=fake_image))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def test_image_endpoint_ok_and_auth(image_server):
    assert call(image_server[0], "/image", {"prompt": "stage"}, token=None)[0] == 401
    assert call(image_server[0], "/image", {"prompt": "stage"}) == (200, {"mime": "image/webp", "data": "QUJD"})
    assert image_server[1] == [("stage", "openrouter/x/y:free")]


def test_image_prompt_limit(image_server):
    assert call(image_server[0], "/image", {"prompt": "a" * 801})[0] == 400


def test_only_free_image_models(monkeypatch):
    monkeypatch.delenv("OPENCODE_ALLOW_PAID_IMAGES", raising=False)
    bridge.check_image_model("openrouter/recraft/recraft-v4.1-flash-v2:free")
    with pytest.raises(ValueError):
        bridge.check_image_model("openrouter/google/gemini-3-pro-image")
    monkeypatch.setenv("OPENCODE_ALLOW_PAID_IMAGES", "1")
    bridge.check_image_model("openrouter/google/gemini-3-pro-image")


def test_health_declares_the_image_model(image_server):
    import json as _json
    import urllib.request
    body = _json.loads(urllib.request.urlopen(f"{image_server[0]}/health").read())
    assert body["image_model"] == "openrouter/x/y:free" and "token" not in str(body).lower()
