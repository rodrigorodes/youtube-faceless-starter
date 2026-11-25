import json
import logging
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.text_demo import DemoText  # noqa: E402
from app.studio.adapters.text_opencode import OpenCodeText  # noqa: E402
from app.studio.application.budget import PreEffectFailure  # noqa: E402
from app.studio.application.editorial import build_prompt, parse_drafts  # noqa: E402
from app.studio.application.ports import ModelUnavailable  # noqa: E402
from app.studio.domain.claims import extract_claims  # noqa: E402

SOURCE = ("Amsterdam Dance Event celebrates 30 years with more than 3,600 artists, 1,300 events and 300 venues across the city.\n"
          "Jean-Michel Jarre opens the festival with a concert at AFAS Live on 21 October to mark 50 years of Oxygène.\n")


def opencode(handler, token="tok", model="openai/gpt-6-luna", bridge_model=None):
    """`bridge_model` é o que o `/health` do bridge declara (padrão: o mesmo modelo configurado)."""
    declared = model if bridge_model is None else bridge_model

    def routed(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "model": declared})
        return handler(request)

    return OpenCodeText(model, token=token, base_url="http://bridge:8787/", transport=httpx.MockTransport(routed))


def test_opencode_posts_prompt_with_bearer_and_returns_text_and_free_usage():
    seen = {}

    def handler(request):
        seen["auth"], seen["body"], seen["url"] = request.headers["authorization"], json.loads(request.content), str(request.url)
        return httpx.Response(200, json={"text": "resposta"})

    result = opencode(handler).complete("olá")
    assert seen == {"auth": "Bearer tok", "body": {"prompt": "olá"}, "url": "http://bridge:8787/generate"}
    assert result.text == "resposta" and result.usage.provider == "opencode" and result.usage.cost_usd == 0
    assert opencode(handler).cost_estimate("x") == 0.0


def test_opencode_accepts_a_bridge_that_declares_the_same_text_model():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"text": "ok"})

    result = opencode(handler, model="openai/gpt-6-luna", bridge_model="openai/gpt-6-luna").complete("p")
    assert result.text == "ok" and result.usage.model == "openai/gpt-6-luna"
    assert calls == ["/generate"]  # o /health foi consultado, mas nada foi gerado a mais


def test_opencode_refuses_a_bridge_that_declares_another_text_model_before_generating():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"text": "nunca"})

    model = opencode(handler, model="openai/gpt-6-luna", bridge_model="openai/gpt-5")
    with pytest.raises(PreEffectFailure) as err:
        model.complete("p")
    assert "openai/gpt-5" in str(err.value) and "openai/gpt-6-luna" in str(err.value)
    assert calls == []  # divergência declarada: nenhum efeito externo aconteceu


def test_opencode_accepts_a_bridge_without_the_declared_text_model_but_warns(caplog):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"text": "ok"})

    def no_model(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})  # bridge antigo: sem o campo
        return handler(request)

    model = OpenCodeText("openai/gpt-6-luna", token="tok", base_url="http://bridge:8787/",
                         transport=httpx.MockTransport(no_model))
    with caplog.at_level(logging.WARNING, logger="studio.alerts"):
        assert model.complete("p").text == "ok"
    assert calls == ["/generate"]
    assert "bridge_text_model_undeclared" in caplog.text
    assert "openai/gpt-6-luna" not in caplog.text  # o aviso é um evento, não um eco do modelo


@pytest.mark.parametrize("response", [httpx.Response(502, json={"detail": "x"}), httpx.Response(200, json={"nada": 1}), httpx.Response(200, content=b"nao json")])
def test_opencode_failures_become_model_unavailable(response):
    with pytest.raises(ModelUnavailable):
        opencode(lambda r: response).complete("p")


def test_opencode_upstream_rejection_424_is_pre_effect_and_carries_the_reason():
    response = httpx.Response(424, json={"detail": "upstream rejected: subscription_sharing_usage_limit_exceeded"})
    with pytest.raises(PreEffectFailure) as err:
        opencode(lambda r: response).complete("p")
    assert "subscription_sharing_usage_limit_exceeded" in str(err.value)


def test_opencode_network_error_and_missing_token():
    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(ModelUnavailable):
        opencode(boom).complete("p")
    with pytest.raises(ValueError, match="OPENCODE_BRIDGE_TOKEN"):
        opencode(lambda r: httpx.Response(200), token="")


def test_error_message_never_contains_token():
    with pytest.raises(ModelUnavailable) as err:
        opencode(lambda r: httpx.Response(401, json={"detail": "unauthorized"}), token="SECRET-TOKEN").complete("p")
    assert "SECRET-TOKEN" not in str(err.value)


def test_demo_text_output_is_a_valid_script_built_from_the_claims():
    claims = extract_claims("s" * 32, SOURCE)
    result = DemoText("x").complete(build_prompt("ADE 2026", claims, 4))
    drafts = parse_drafts(result.text, {c.id for c in claims})
    assert len(drafts) == 4 and DemoText("x").cost_estimate("p") == 0.0 and result.usage.cost_usd == 0
    assert all(set(d.claim_ids) <= {c.id for c in claims} for d in drafts)
    assert drafts[0].narration in {c.text for c in claims}
