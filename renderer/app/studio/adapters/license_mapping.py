"""Mapeamento de rótulos de licença de fornecedores de mídia para classes canônicas de domínio.

Os nomes de fornecedores concretos (Pexels, Pixabay, Unsplash) ficam restritos à camada
de adaptadores, mantendo ``domain`` e ``application`` agnósticos a fornecedor.
"""
from __future__ import annotations

VENDOR_LICENSE_TO_CANONICAL: dict[str, str] = {
    "pexels license": "free stock",
    "pixabay content license": "free stock",
    "pixabay license": "free stock",
    "unsplash license": "free stock",
}


def normalize_vendor_license(license_name: str | None) -> str | None:
    """Normaliza rótulos exatos de licença de fornecedores homologados para classe canônica.

    Não faz match por substring: strings desconhecidas ou adulteradas retornam intactas
    para serem recusadas fail-closed pelo domínio.
    """
    if not license_name or not license_name.strip():
        return license_name
    return VENDOR_LICENSE_TO_CANONICAL.get(license_name.strip().casefold(), license_name)
