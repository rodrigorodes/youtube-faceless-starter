import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.text_demo import DemoText  # noqa: E402
from app.studio.adapters.text_opencode import OpenCodeText  # noqa: E402
from app.studio.application.editorial import build_prompt, parse_drafts  # noqa: E402
from app.studio.application.ports import ModelUnavailable  # noqa: E402
from app.studio.domain.claims import extract_claims  # noqa: E402

SOURCE = ("Amsterdam Dance Event celebrates 30 years with more than 3,600 artists, 1,300 events and 300 venues across the city.\n"
          "Jean-Michel Jarre opens the festival with a concert at AFAS Live on 21 October to mark 50 years of Oxygène.\n")


def opencode(handler, token="tok"):
    return OpenCodeText("openai/gpt-6-luna", token=token, base_url="http://bridge:8787/", transport=httpx.MockTransport(handler))


def test_opencode_posts_prompt_with_bearer_and_returns_text_and_free_usage():
    seen = {}

    def handler(request):
        seen["auth"], seen["body"], seen["url"] = request.headers["authorization"], json.loads(request.content), str(request.url)
        return httpx.Response(200, json={"text": "resposta"})

    result = opencode(handler).complete("olá")
    assert seen == {"auth": "Bearer tok", "body": {"prompt": "olá"}, "url": "http://bridge:8787/generate"}
    assert result.text == "resposta" and result.usage.provider == "opencode" and result.usage.cost_usd == 0
    assert opencode(handler).cost_estimate("x") == 0.0


@pytest.mark.parametrize("response", [httpx.Response(502, json={"detail": "x"}), httpx.Response(200, json={"nada": 1}), httpx.Response(200, content=b"nao json")])
def test_opencode_failures_become_model_unavailable(response):
    with pytest.raises(ModelUnavailable):
        opencode(lambda r: response).complete("p")


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
