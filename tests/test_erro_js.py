"""Fallback de erros na tela: `detail` da API vira português com próximo passo, nunca JSON cru.

O helper `window.StudioErro.texto` roda no navegador; aqui ele é executado em Node, sem rede.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.erro_js import ERRO_JS  # noqa: E402
from app.studio.api import shell_v3  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node indisponível")


def _texto(dados, fallback="tente novamente.", status=None):
    script = ("global.window = {};" + ERRO_JS +
              f"process.stdout.write(JSON.stringify(window.StudioErro.texto({json.dumps(dados)}, "
              f"{json.dumps(fallback)}, {json.dumps(status)})));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_known_oauth_errors_are_translated_with_a_next_step():
    msg = _texto({"detail": "YouTube OAuth is not configured: OAuth scopes must be https URLs"})
    assert msg.startswith("A conexão com o Google não está configurada")
    assert "Detalhe técnico: YouTube OAuth is not configured" in msg  # o motivo real não se perde
    assert "Conecte de novo" in _texto({"detail": "the authorized account did not expose an email; reconnect"})
    assert "refaça o consentimento" in _texto({"detail": "the OAuth state does not match the started consent"})
    assert "Conecte a conta Google de novo" in _texto({"detail": "YouTube channel reconnect required: x"})
    assert "indisponível agora" in _texto({"detail": "YouTube OAuth is temporarily unavailable: HTTP 503"})


def test_validation_list_never_prints_raw_json():
    msg = _texto({"detail": [{"loc": ["body", "name"], "msg": "field required", "type": "missing"},
                             {"loc": ["body", "niche"], "msg": "too short", "type": "x"}]})
    assert msg == "Revise os campos: name, niche."
    assert "{" not in msg and "msg" not in msg


def test_portuguese_detail_is_shown_as_is():
    assert _texto({"detail": "Falhou: o canal não tem perfil."}) == "Falhou: o canal não tem perfil."


def test_unknown_english_detail_keeps_the_screen_fallback_plus_a_short_technical_note():
    msg = _texto({"detail": "something odd happened " + "x" * 400}, "verifique os campos.")
    assert msg.startswith("verifique os campos. (Detalhe técnico: something odd happened")
    assert len(msg) < 240


def test_empty_or_non_json_response_uses_status_then_the_fallback():
    assert _texto({}, "tente novamente.", 503).startswith("Este recurso está indisponível")
    assert _texto({}, "tente novamente.", 422) == "Revise os campos informados."
    assert _texto({}, "tente novamente.") == "tente novamente."
    assert _texto(None, "tente novamente.") == "tente novamente."


def test_helper_ships_with_every_v3_page_and_no_page_prints_detail_raw():
    assert "window.StudioErro" in shell_v3.SHELL_JS
    api = Path(__file__).resolve().parents[1] / "renderer/app/studio/api"
    offenders = [p.name for p in api.glob("*.py")
                 if p.name != "erro_js.py" and "JSON.stringify(" in p.read_text() and
                 ".detail || " in p.read_text()]
    assert offenders == []
