"""Testes de conformidade para V4-11 — Asset Management.

Valida as atividades V4-11.01 a V4-11.14:
- V4-11.02 / V4-11.03: Deduplicação de acervo por hash SHA-256 (AssetCatalogManager).
- V4-11.05 / V4-11.06 / V4-11.07: Bloqueio estrito de licença desconhecida (assert_known_license, LicenseVerificationError).
- V4-11.08 / V4-11.09: Metadados, versionamento e busca por tags.
- V4-11.12: Identificação de assets órfãos (find_orphans).
"""
from __future__ import annotations

import pytest

from app.studio.application.asset_registry import AssetCatalogManager
from app.studio.domain.asset_registry import (
    AssetMetadataRecord,
    LicenseVerificationError,
    assert_known_license,
    detect_orphan_assets,
    verify_license_provenance,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


class TestLicenseProvenanceAndBlocking:
    """V4-11.05, V4-11.06 e V4-11.07: Validação e bloqueio estrito de licença desconhecida."""

    @pytest.mark.parametrize("lic", [
        "CC0",
        "CC-BY",
        "Public Domain",
        "Free Stock",
        "Commercial Stock",
        "Studio Generated",
        "gerado pelo estúdio a partir de assets licenciados",
    ])
    def test_permitted_licenses_pass(self, lic: str):
        assert verify_license_provenance(lic) is True
        assert_known_license(lic)

    @pytest.mark.parametrize("bad_lic", [
        "",
        "   ",
        "unknown",
        "desconhecida",
        "sem licença",
        "pirate_copy",
        "unlicensed_web_scrape",
    ])
    def test_unknown_or_missing_license_blocked(self, bad_lic: str):
        assert verify_license_provenance(bad_lic) is False
        with pytest.raises(LicenseVerificationError, match="unknown, missing or unverified license"):
            assert_known_license(bad_lic)

    def test_asset_metadata_record_enforces_known_license(self):
        with pytest.raises((LicenseVerificationError, ValueError), match="unknown, missing or unverified license"):
            AssetMetadataRecord(
                asset_id="asset_unverified",
                asset_version=1,
                content_sha256=SHA_A,
                media_type="image",
                license="unknown_custom_license",
            )


class TestAssetCatalogAndDeduplication:
    """V4-11.02 e V4-11.03: Deduplicação por hash de conteúdo e gestão de acervo."""

    def test_deduplication_of_identical_content(self):
        catalog = AssetCatalogManager()

        rec1 = AssetMetadataRecord(
            asset_id="asset_orig_01",
            asset_version=1,
            content_sha256=SHA_A,
            media_type="image",
            license="CC0",
            author="Author Alpha",
            tags=("nature", "mountains"),
        )
        saved1, is_dup1 = catalog.register(rec1)
        assert is_dup1 is False
        assert saved1.asset_id == "asset_orig_01"
        assert catalog.total_assets == 1

        # Segundo registro com ID diferente, mas mesmo content_sha256
        rec2 = AssetMetadataRecord(
            asset_id="asset_copy_02",
            asset_version=1,
            content_sha256=SHA_A,  # Mesmo SHA-256!
            media_type="image",
            license="CC0",
            author="Author Beta",
        )
        saved2, is_dup2 = catalog.register(rec2)
        assert is_dup2 is True
        # Reutilizou a referência canônica do primeiro
        assert saved2.asset_id == "asset_orig_01"
        assert catalog.total_assets == 1

        # Terceiro registro com SHA-256 diferente
        rec3 = AssetMetadataRecord(
            asset_id="asset_distinct_03",
            asset_version=1,
            content_sha256=SHA_B,
            media_type="video",
            license="Free Stock",
            tags=("ocean", "waves"),
        )
        saved3, is_dup3 = catalog.register(rec3)
        assert is_dup3 is False
        assert catalog.total_assets == 2

    def test_search_by_tag(self):
        catalog = AssetCatalogManager()
        rec1 = AssetMetadataRecord(
            asset_id="a1",
            content_sha256=SHA_A,
            media_type="image",
            license="CC0",
            tags=("cinematic", "scifi", "space"),
        )
        rec2 = AssetMetadataRecord(
            asset_id="a2",
            content_sha256=SHA_B,
            media_type="image",
            license="Free Stock",
            tags=("nature", "forest"),
        )
        catalog.register(rec1)
        catalog.register(rec2)

        matches = catalog.search_by_tag("scifi")
        assert len(matches) == 1
        assert matches[0].asset_id == "a1"

        empty = catalog.search_by_tag("urban")
        assert len(empty) == 0


class TestOrphanAssetDetection:
    """V4-11.12: Detecção de assets órfãos para limpeza de storage."""

    def test_detect_orphan_assets(self):
        catalog = AssetCatalogManager()
        rec1 = AssetMetadataRecord(asset_id="used_01", content_sha256=SHA_A, media_type="image", license="CC0")
        rec2 = AssetMetadataRecord(asset_id="orphan_02", content_sha256=SHA_B, media_type="image", license="CC0")
        catalog.register(rec1)
        catalog.register(rec2)

        # O projeto ativo referencia apenas used_01
        orphans = catalog.find_orphans(referenced_asset_ids=["used_01"])
        assert orphans == ("orphan_02",)

        # Se ambos forem referenciados, nenhum órfão
        assert catalog.find_orphans(referenced_asset_ids=["used_01", "orphan_02"]) == ()
