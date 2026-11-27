"""Contratos e regras de validação para tags de assets (PC-05.02 / V4-11.09)."""
from __future__ import annotations

import re

TAG_REGEX = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")
MAX_TAGS_PER_ASSET = 20


class AssetTagInvalid(ValueError):
    """Tag de asset inválida ou que viola limites de tamanho/formato."""


class AssetNotFound(LookupError):
    """Asset não encontrado no repositório."""


class AssetAccessDenied(PermissionError):
    """Acesso ao asset negado fora do escopo autorizado do projeto ou canal."""


def normalize_tag(tag: str) -> str:
    """Normaliza e valida uma tag de asset.

    Regras:
    - Converte para minúsculas e remove espaços das pontas (strip + lower)
    - Não pode ser vazia
    - Tamanho entre 1 e 64 caracteres
    - Allowlist estrita: ^[a-z0-9][a-z0-9._:-]{0,63}$ (sem espaços, sem caracteres de controle, sem curingas de SQL)
    """
    if not isinstance(tag, str):
        raise AssetTagInvalid("tag must be a string")
    cleaned = tag.strip().lower()
    if not cleaned:
        raise AssetTagInvalid("tag cannot be empty")
    if len(cleaned) > 64:
        raise AssetTagInvalid(f"tag exceeds maximum length of 64 characters: {cleaned[:20]}...")
    if not TAG_REGEX.fullmatch(cleaned):
        raise AssetTagInvalid(f"tag contains invalid characters: {cleaned}")
    return cleaned


def escape_like(term: str) -> str:
    """Escapa caracteres especiais (% e _) e a própria barra invertida para consultas ILIKE seguras."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
