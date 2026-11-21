"""Segredos (F10-07): sanitização do Project.config e redação — nada vaza para o browser.

O `Project.config` só devolve as portas de provider conhecidas; qualquer chave que pareça segredo
(ou desconhecida) é descartada. Testes puros, sem banco.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.secrets import (  # noqa: E402
    PUBLIC_CONFIG_KEYS,
    is_secret_key,
    redact,
    sanitize_project_config,
)


def test_provider_specs_are_returned():
    config = {"text": "demo", "image": "placeholder", "voice": "piper:pt_BR-faber-medium",
              "renderer": "ffmpeg:rich"}
    assert sanitize_project_config(config) == config


def test_secret_looking_keys_are_dropped():
    config = {
        "text": "demo",
        "OPENAI_API_KEY": "sk-live-should-never-leak",
        "YOUTUBE_CLIENT_SECRET": "s3cr3t",
        "GOOGLE_REFRESH_TOKEN": "1//token",
        "DB_PASSWORD": "hunter2",
    }
    cleaned = sanitize_project_config(config)
    assert cleaned == {"text": "demo"}
    assert "sk-live-should-never-leak" not in cleaned.values()


def test_unknown_keys_are_dropped_even_without_secret_name():
    assert sanitize_project_config({"text": "demo", "experimental_flag": "on"}) == {"text": "demo"}


def test_non_string_values_are_dropped():
    assert sanitize_project_config({"text": 123, "image": None, "voice": "piper:x"}) == {"voice": "piper:x"}


def test_blank_values_are_dropped():
    assert sanitize_project_config({"text": "  ", "image": "placeholder"}) == {"image": "placeholder"}


def test_sanitize_does_not_mutate_the_source():
    source = {"text": "demo", "OPENAI_API_KEY": "x"}
    sanitize_project_config(source)
    assert source == {"text": "demo", "OPENAI_API_KEY": "x"}


def test_is_secret_key_matches_common_names():
    for key in ("OPENAI_API_KEY", "youtube_refresh_token", "client_secret", "db_password", "GOOGLE_CREDENTIALS"):
        assert is_secret_key(key), key
    for key in PUBLIC_CONFIG_KEYS:
        assert not is_secret_key(key), key


def test_redact_masks_values_without_dropping_keys():
    redacted = redact({"API_KEY": "secret-value", "name": "canal"})
    assert redacted["API_KEY"] == "***"
    assert redacted["name"] == "canal"
    assert "secret-value" not in str(redacted)
