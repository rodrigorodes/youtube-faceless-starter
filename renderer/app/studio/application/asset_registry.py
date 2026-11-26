"""Serviços de aplicação para Asset Management (V4-11).

Orquestra:
- Deduplicação de acervo baseada em content_sha256 (AssetCatalogManager).
- Indexação e busca por tags.
- Verificação de integridade e auditoria de órfãos.
"""
from __future__ import annotations

from typing import Sequence

from ..domain.asset_registry import (
    AssetMetadataRecord,
    assert_known_license,
    detect_orphan_assets,
)

__all__ = [
    "AssetCatalogManager",
]


class AssetCatalogManager:
    """Catálogo centralizado de acervo com deduplicação por hash de conteúdo SHA-256."""

    def __init__(self) -> None:
        self._by_id: dict[str, AssetMetadataRecord] = {}
        self._by_hash: dict[str, AssetMetadataRecord] = {}

    def register(self, record: AssetMetadataRecord) -> tuple[AssetMetadataRecord, bool]:
        """Registra um asset no catálogo. Se o hash já existir, reutiliza o registro canônico (deduplicação)."""
        # Garante validação prévia de licença
        assert_known_license(record.license)

        existing = self._by_hash.get(record.content_sha256)
        if existing is not None:
            # Deduplicação: o asset já existe fisicamente sob o mesmo SHA-256
            return existing, True

        self._by_id[record.asset_id] = record
        self._by_hash[record.content_sha256] = record
        return record, False

    def get_by_id(self, asset_id: str) -> AssetMetadataRecord | None:
        return self._by_id.get(asset_id)

    def get_by_hash(self, content_sha256: str) -> AssetMetadataRecord | None:
        return self._by_hash.get(content_sha256)

    def search_by_tag(self, tag: str) -> list[AssetMetadataRecord]:
        clean_tag = tag.strip().casefold()
        matches: list[AssetMetadataRecord] = []
        for rec in self._by_id.values():
            if any(clean_tag in t.casefold() for t in rec.tags):
                matches.append(rec)
        return matches

    def find_orphans(self, referenced_asset_ids: Sequence[str] | set[str]) -> tuple[str, ...]:
        return detect_orphan_assets(list(self._by_id.keys()), referenced_asset_ids)

    @property
    def total_assets(self) -> int:
        return len(self._by_id)
