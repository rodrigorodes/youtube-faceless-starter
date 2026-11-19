import base64
import io
import json
import sys
from pathlib import Path

import httpx
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.image_opencode import OpenCodeImage  # noqa: E402
from app.studio.adapters.image_placeholder import PlaceholderImage  # noqa: E402
from app.studio.adapters.image_stock import PexelsImage  # noqa: E402
from app.studio.adapters.image_veo import VeoImage  # noqa: E402
from app.studio.adapters.storage import FileAssetStore  # noqa: E402
from app.studio.adapters.voice_piper import PiperVoice  # noqa: E402
from app.studio.application.config import ProviderNotFound  # noqa: E402
from app.studio.application.media import AssetRefused  # noqa: E402
from app.studio.application.ports import ModelUnavailable  # noqa: E402
from app.studio.domain.ids import InvalidId  # noqa: E402
from app.studio.domain.media import IMAGE_STYLE  # noqa: E402

KEY = "ab" + "c" * 62


def png(size=(300, 200), color=(200, 30, 30), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


# ---------- store ----------
def test_store_normalizes_to_the_target_size_and_returns_a_relative_path(tmp_path):
    store = FileAssetStore(tmp_path)
    rel = store.put(KEY, png(), "9:16")
    assert rel == f"cache/ab/{KEY}.png" and not rel.startswith("/") and ".." not in rel
    assert Image.open(tmp_path / rel).size == (1080, 1920)
    rel2 = FileAssetStore(tmp_path).put("cd" + "e" * 62, png(fmt="JPEG"), "16:9")
    assert Image.open(tmp_path / rel2).size == (1920, 1080)
    assert [p.name for p in (tmp_path / "cache" / "ab").iterdir()] == [f"{KEY}.png"]  # sem temporários


def test_store_is_idempotent_for_the_same_key(tmp_path):
    store = FileAssetStore(tmp_path)
    assert store.put(KEY, png(), "9:16") == store.put(KEY, png(color=(1, 2, 3)), "9:16")


@pytest.mark.parametrize("data", [b"", b"nao e imagem", b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"GIF89a" + b"\0" * 10])
def test_store_refuses_non_images(tmp_path, data):
    with pytest.raises(AssetRefused):
        FileAssetStore(tmp_path).put(KEY, data, "9:16")
    assert not (tmp_path / "cache").exists() or not list((tmp_path / "cache").rglob("*.png"))


def test_store_refuses_decompression_bombs_and_huge_inputs(tmp_path):
    buf = io.BytesIO()
    Image.new("1", (9000, 9000)).save(buf, "PNG")  # 81 milhões de pixels, poucos KB
    with pytest.raises(AssetRefused):
        FileAssetStore(tmp_path).put(KEY, buf.getvalue(), "9:16")
    with pytest.raises(AssetRefused):
        FileAssetStore(tmp_path).put(KEY, b"x" * (20 * 1024 * 1024 + 1), "9:16")


def test_store_rejects_bad_keys_and_aspects(tmp_path):
    for bad in ("../../etc/passwd", "ab", "A" * 64):
        with pytest.raises(InvalidId):
            FileAssetStore(tmp_path).put(bad, png(), "9:16")
    with pytest.raises(AssetRefused):
        FileAssetStore(tmp_path).put(KEY, png(), "4:3")


# ---------- placeholder ----------
def test_placeholder_is_deterministic_sized_free_and_licensed():
    model = PlaceholderImage("gradient")
    a, b = model.generate("palco", aspect="9:16"), model.generate("palco", aspect="9:16")
    assert a.data == b.data and a.mime == "image/png" and Image.open(io.BytesIO(a.data)).size == (1080, 1920)
    assert model.generate("outro", aspect="9:16").data != a.data
    assert Image.open(io.BytesIO(model.generate("palco", aspect="16:9").data)).size == (1920, 1080)
    assert a.license.startswith("CC0") and a.usage.cost_usd == 0 and model.cost_estimate("x") == 0.0 and model.name == "placeholder"


# ---------- opencode ----------
def opencode(handler, model="openrouter/recraft/recraft-v4.1-flash-v2:free", token="tok", **kw):
    return OpenCodeImage(model, token=token, base_url="http://bridge:8787/", transport=httpx.MockTransport(handler), **kw)


def test_opencode_posts_prompt_decodes_image_and_records_license():
    seen = {}

    def handler(request):
        seen.update(auth=request.headers["authorization"], body=json.loads(request.content), url=str(request.url))
        return httpx.Response(200, json={"mime": "image/png", "data": base64.b64encode(b"PNGDATA").decode()})

    result = opencode(handler).generate("stage" + IMAGE_STYLE["9:16"])
    assert seen["auth"] == "Bearer tok" and seen["url"] == "http://bridge:8787/image" and seen["body"] == {"prompt": "stage" + IMAGE_STYLE["9:16"]}
    assert result.data == b"PNGDATA" and result.mime == "image/png" and result.license == "ai-generated:openrouter/recraft/recraft-v4.1-flash-v2:free"
    assert result.usage.cost_usd == 0 and result.usage.provider == "opencode"


def test_opencode_paid_model_has_a_nonzero_estimate_so_the_guard_can_refuse():
    free = opencode(lambda r: httpx.Response(200), model="a/b:free")
    paid = opencode(lambda r: httpx.Response(200), model="a/b")
    assert free.cost_estimate("p") == 0.0 and paid.cost_estimate("p") == pytest.approx(0.05)
    assert opencode(lambda r: httpx.Response(200), model="a/b", paid_estimate_usd=0.2).cost_estimate("p") == pytest.approx(0.2)


def test_opencode_retries_transient_failures_once_but_not_client_errors():
    calls = []

    def flaky(request):
        calls.append(1)
        return httpx.Response(502, json={"detail": "x"}) if len(calls) == 1 else httpx.Response(200, json={"mime": "image/png", "data": base64.b64encode(b"x").decode()})

    assert opencode(flaky).generate("p").data == b"x" and len(calls) == 2
    calls.clear()
    with pytest.raises(ModelUnavailable):
        opencode(lambda r: (calls.append(1), httpx.Response(502))[1]).generate("p")
    assert len(calls) == 2
    calls.clear()
    with pytest.raises(ModelUnavailable):
        opencode(lambda r: (calls.append(1), httpx.Response(401, json={"detail": "unauthorized"}))[1], token="SECRET-TOKEN").generate("p")
    assert len(calls) == 1


@pytest.mark.parametrize("response", [httpx.Response(200, json={"nada": 1}), httpx.Response(200, json={"mime": "image/png", "data": "!!!não-base64"}), httpx.Response(200, content=b"x")])
def test_opencode_bad_payloads_are_model_unavailable(response):
    with pytest.raises(ModelUnavailable) as err:
        opencode(lambda r: response, token="SECRET-TOKEN").generate("p")
    assert "SECRET-TOKEN" not in str(err.value)


def test_opencode_requires_token():
    with pytest.raises(ProviderNotFound, match="OPENCODE_BRIDGE_TOKEN"):
        opencode(lambda r: httpx.Response(200), token="")


# ---------- stock (Pexels) ----------
PHOTO = {"url": "https://www.pexels.com/photo/1/", "photographer": "Fulano de Tal", "photographer_url": "https://www.pexels.com/@fulano",
         "src": {"portrait": "https://images.pexels.com/photos/1/p.jpg", "landscape": "https://images.pexels.com/photos/1/l.jpg"}}


def pexels(photos=None, api_key="KEY", image_url=None, **kw):
    seen = {"search": [], "download": []}

    def handler(request):
        if request.url.host == "api.pexels.com":
            seen["search"].append((dict(request.url.params), request.headers.get("authorization")))
            return httpx.Response(200, json={"photos": [PHOTO] if photos is None else photos})
        seen["download"].append(str(request.url))
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=png(fmt="JPEG"))

    model = PexelsImage("pexels", api_key=api_key, transport=httpx.MockTransport(handler), **kw)
    return model, seen


def test_pexels_searches_by_theme_with_orientation_and_records_credits():
    model, seen = pexels()
    r = model.generate("wide stage with lights" + IMAGE_STYLE["9:16"], aspect="9:16")
    params, auth = seen["search"][0]
    assert auth == "KEY" and params["query"] == "wide stage with lights" and params["orientation"] == "portrait" and params["per_page"] == "1"
    assert seen["download"] == ["https://images.pexels.com/photos/1/p.jpg"]
    assert r.license == "Pexels License" and "Fulano de Tal" in r.attribution and r.source_url == "https://www.pexels.com/photo/1/"
    assert r.mime == "image/jpeg" and r.usage.cost_usd == 0 and model.cost_estimate("x") == 0.0
    model2, seen2 = pexels()
    model2.generate("tema", aspect="16:9")
    assert seen2["search"][0][0]["orientation"] == "landscape" and seen2["download"] == ["https://images.pexels.com/photos/1/l.jpg"]


def test_pexels_no_result_and_untrusted_image_hosts_are_refused():
    with pytest.raises(ModelUnavailable, match="no stock"):
        pexels(photos=[])[0].generate("tema")
    for bad in ("https://evil.example/p.jpg", "http://images.pexels.com/p.jpg", "https://images.pexels.com.evil.example/p.jpg", "file:///etc/passwd"):
        photo = {**PHOTO, "src": {"portrait": bad, "landscape": bad}}
        model, seen = pexels(photos=[photo])
        with pytest.raises(ModelUnavailable):
            model.generate("tema")
        assert seen["download"] == []


def test_pexels_requires_key_and_never_leaks_it():
    with pytest.raises(ProviderNotFound, match="PEXELS_API_KEY"):
        PexelsImage("pexels", api_key="")
    model = PexelsImage("pexels", api_key="SECRET-KEY", transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    with pytest.raises(ModelUnavailable) as err:
        model.generate("tema")
    assert "SECRET-KEY" not in str(err.value)


# ---------- veo ----------
def test_veo_is_expensive_by_estimate_and_refuses_to_generate():
    veo = VeoImage("veo-3.1")
    assert veo.cost_estimate("x") == pytest.approx(3.2) and VeoImage("v", usd_per_second=0.05).cost_estimate("x") == pytest.approx(0.4)
    with pytest.raises(ModelUnavailable, match="not implemented"):
        veo.generate("x")


# ---------- voz ----------
def test_piper_voice_wraps_the_legacy_synthesis(tmp_path, monkeypatch):
    import wave

    from app import rich

    def fake(text, path):
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050)
            w.writeframes(b"\0\0" * 22050)

    monkeypatch.setattr(rich, "synthesize_speech", fake)
    assert PiperVoice("pt_BR-faber-medium").speak("Olá, mundo.", tmp_path / "a.wav") == pytest.approx(1.0, abs=0.01)
    with pytest.raises(ValueError):
        PiperVoice("x").speak("   ", tmp_path / "b.wav")
