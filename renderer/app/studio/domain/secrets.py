"""Higiene de segredos (F10-07). Puro: só regras de nomes e valores.

O `Project.config` que vai ao browser é uma lista branca das portas de provider. Qualquer chave
desconhecida — e qualquer coisa com cara de segredo — é descartada antes da resposta.
"""
from __future__ import annotations

from collections.abc import Mapping

# Portas de provider que podem aparecer no config público (espelham `application.config.KINDS`).
PUBLIC_CONFIG_KEYS: tuple[str, ...] = ("text", "image", "voice", "renderer")

# Sufixos/segmentos que denunciam material sensível, independentemente da porta.
_SECRET_MARKERS = ("SECRET", "TOKEN", "PASSWORD", "PASSWD", "CREDENTIAL", "APIKEY", "PRIVATE", "ACCESS_KEY")


def is_secret_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    upper = key.upper()
    if upper in {name.upper() for name in PUBLIC_CONFIG_KEYS}:
        return False
    if "KEY" in upper or upper.endswith("_SECRET"):
        return True
    return any(marker in upper for marker in _SECRET_MARKERS)


def sanitize_project_config(config: object) -> dict[str, str]:
    """Devolve só as portas conhecidas com valores string não vazios. Nunca inclui segredos."""
    if not isinstance(config, Mapping):
        return {}
    cleaned: dict[str, str] = {}
    for key in PUBLIC_CONFIG_KEYS:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            cleaned[key] = value.strip()
    return cleaned


def redact(mapping: Mapping[str, object]) -> dict[str, object]:
    """Cópia com os valores sensíveis mascarados; as chaves permanecem (para diagnóstico)."""
    return {key: ("***" if is_secret_key(key) else value) for key, value in mapping.items()}
