"""Identificadores e chave de cache (domínio puro)."""
import hashlib
import json
import re

_ID = re.compile(r"[0-9a-f]{32}")
_KEY = re.compile(r"[0-9a-f]{64}")


class InvalidId(ValueError):
    pass


def check_id(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise InvalidId("invalid id")
    return value


def check_cache_key(value: str) -> str:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise InvalidId("invalid cache key")
    return value


def asset_cache_key(kind: str, provider: str, model: str, prompt: str, params: dict) -> str:
    """sha256 de JSON canônico: mesma entrada, mesma chave; qualquer mudança, outra chave."""
    payload = json.dumps({"kind": kind, "provider": provider, "model": model, "prompt": prompt, "params": params},
                         sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
