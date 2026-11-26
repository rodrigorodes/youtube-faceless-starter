"""Contratos e regras de domínio para Asset Management (V4-11).

Implementa:
- Verificação estrita de proveniência de licença (verify_license_provenance, assert_known_license).
- Bloqueio de publicação com licença desconhecida ou ausente (LicenseVerificationError).
- Metadados completos de asset com integridade por hash e tags (AssetMetadataRecord).
- Algoritmo puro de detecção de assets órfãos (detect_orphan_assets).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "LicenseVerificationError",
    "KNOWN_PERMITTED_LICENSES",
    "PROVENANCE_REQUIRED_LICENSES",
    "verify_license_provenance",
    "requires_attribution",
    "assert_known_license",
    "AssetMetadataRecord",
    "detect_orphan_assets",
]


class LicenseVerificationError(ValueError):
    """Lançada quando um asset apresenta licença desconhecida, ausente ou inválida."""


# Licenças abertas e comerciais homologadas para distribuição no canal
KNOWN_PERMITTED_LICENSES: frozenset[str] = frozenset({
    "cc0",
    "cc0-1.0",
    "cc-by",
    "cc-by-4.0",
    "cc-by-sa",
    "cc-by-sa-4.0",
    "public domain",
    "free stock",
    "commercial stock",
    "studio generated",
    "own_original",
    "own original",
    "commercial_licensed",
    "commercial licensed",
    "proprietary commercial",
    "gerado pelo estúdio a partir de assets licenciados",
})

PROVENANCE_REQUIRED_LICENSES: frozenset[str] = frozenset({
    "cc-by-4.0",
    "cc-by-sa-4.0",
    "commercial_licensed",
    "commercial licensed",
})


def requires_attribution(license_name: str | None) -> bool:
    """Indica se a licença exige declaração de atribuição ou URL de origem."""
    if not license_name or not license_name.strip():
        return False
    return license_name.strip().casefold() in PROVENANCE_REQUIRED_LICENSES


def verify_license_provenance(license_name: str | None) -> bool:
    """Verifica se a licença do asset é formalmente reconhecida e segura para publicação."""
    if not license_name or not license_name.strip():
        return False
    normalized = license_name.strip().casefold()
    if normalized in ("unknown", "desconhecida", "sem licença", "none", "n/a"):
        return False
    return normalized in KNOWN_PERMITTED_LICENSES


def assert_known_license(license_name: str | None) -> None:
    """Exige licença conhecida; bloqueia incondicionalmente publicação caso contrário."""
    if not verify_license_provenance(license_name):
        raise LicenseVerificationError(
            f"Asset carries an unknown, missing or unverified license ({license_name!r}); publication is blocked."
        )


class AssetMetadataRecord(BaseModel):
    """Registro descritor de metadados, integridade e licença de um asset no acervo."""

    model_config = ConfigDict(frozen=True)

    asset_id: str = Field(min_length=1)
    asset_version: int = Field(default=1, ge=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    media_type: str = Field(pattern=r"^(image|video|audio|graphic|text)$")
    license: str = Field(min_length=1)
    author: str = ""
    origin_url: str = ""
    tags: tuple[str, ...] = ()
    file_size_bytes: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context) -> None:
        # Garante que a licença informada no registro seja válida
        assert_known_license(self.license)


def detect_orphan_assets(
    storage_asset_ids: Sequence[str],
    referenced_asset_ids: Sequence[str] | set[str],
) -> tuple[str, ...]:
    """Identifica assets físicos presentes no acervo que não possuem nenhuma referência ativa em projetos."""
    referenced_set = set(referenced_asset_ids)
    orphans = [aid for aid in storage_asset_ids if aid not in referenced_set]
    return tuple(sorted(set(orphans)))
