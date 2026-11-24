"""VE-03 (W3.1): porta de busca de mídia e candidatos.

O contrato é agnóstico de fornecedor: ``MediaCandidate`` exige licença, proveniência e
atribuição; o adaptador Pexels é o único que conhece o fornecedor. Nenhum teste aqui usa
rede real — o HTTP é falso via ``httpx.MockTransport``.
"""
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.media_pexels import PexelsMediaFetcher, PexelsMediaSearch  # noqa: E402
from app.studio.application.config import ProviderNotFound  # noqa: E402
from app.studio.application.ports import (  # noqa: E402
    MediaCandidate,
    MediaSearch,
    ModelUnavailable,
)
from app.studio.composition import Settings, _provider_implementations  # noqa: E402
from app.studio.domain.provider import (  # noqa: E402
    Availability,
    Capability,
    CostKind,
    ProviderKind,
    card_for,
)


# -- contrato do candidato ----------------------------------------------------


def test_media_candidate_requires_license():
    with pytest.raises(ValueError):
        MediaCandidate(
            license="",
            source_url="https://example.test/photo/1",
            url="https://cdn.example.test/1.jpg",
            attribution="Foto de alguém",
        )


def test_media_candidate_requires_provenance():
    with pytest.raises(ValueError):
        MediaCandidate(
            license="CC0",
            source_url="",
            url="https://cdn.example.test/1.jpg",
            attribution="Foto de alguém",
        )


def test_media_candidate_requires_media_url_and_attribution():
    with pytest.raises(ValueError):
        MediaCandidate(license="CC0", source_url="https://example.test/photo/1", url="", attribution="x")
    with pytest.raises(ValueError):
        MediaCandidate(license="CC0", source_url="https://example.test/photo/1", url="https://cdn.example.test/1.jpg", attribution="")


def test_media_candidate_accepts_optional_cost_and_dimensions():
    candidate = MediaCandidate(
        license="CC0",
        source_url="https://example.test/photo/1",
        url="https://cdn.example.test/1.jpg",
        attribution="Foto de alguém",
        author="Alguém",
        width=1080,
        height=1920,
        cost_usd=Decimal("0"),
    )
    assert candidate.width == 1080 and candidate.height == 1920
    assert candidate.cost_usd == Decimal("0")
    assert candidate.license == "CC0"


def test_media_candidate_rejects_invalid_dimensions():
    with pytest.raises(ValueError):
        MediaCandidate(
            license="CC0",
            source_url="https://example.test/photo/1",
            url="https://cdn.example.test/1.jpg",
            attribution="Foto de alguém",
            width=0,
        )


# -- adaptador Pexels (HTTP falso) -------------------------------------------

# A API de fotos do Pexels não devolve ``license`` por foto (só a licença do provedor).
PHOTO = {
    "id": 42,
    "width": 1080,
    "height": 1920,
    "url": "https://www.pexels.com/photo/42/",
    "photographer": "Fotógrafa Teste",
    "photographer_url": "https://www.pexels.com/@fotografa",
    "src": {
        "portrait": "https://images.pexels.com/photos/42/p.jpg",
        "landscape": "https://images.pexels.com/photos/42/l.jpg",
        "original": "https://images.pexels.com/photos/42/o.jpg",
    },
}


def _adapter(handler, key="KEY", **kwargs):
    return PexelsMediaSearch(
        "pexels-model",
        key,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _response(photos):
    return httpx.Response(200, json={"photos": photos})


def test_adapter_returns_candidate_with_license_provenance_and_attribution():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["auth"] = request.headers.get("authorization")
        return _response([PHOTO])

    adapter = _adapter(handler)
    candidates = adapter.search("Roma antiga", orientation="portrait")

    assert len(candidates) == 1
    candidate = candidates[0]
    # A licença vem do provedor (documentada), não de um campo por foto que a API não envia.
    assert candidate.license == "Pexels License"
    assert candidate.source_url == "https://www.pexels.com/photo/42/"
    assert candidate.url == "https://images.pexels.com/photos/42/p.jpg"
    assert candidate.author == "Fotógrafa Teste"
    assert "Fotógrafa Teste" in candidate.attribution
    assert candidate.width == 1080 and candidate.height == 1920
    assert candidate.cost_usd == Decimal("0")
    assert seen["path"] == "/v1/search"
    assert seen["params"]["query"] == "Roma antiga"
    assert seen["params"]["orientation"] == "portrait"
    assert seen["auth"] == "KEY"


def test_adapter_rejects_candidate_without_provenance():
    broken = {**PHOTO, "url": ""}

    def handler(request):
        return _response([broken])

    assert _adapter(handler).search("Roma antiga") == []


def test_adapter_rejects_candidate_with_untrusted_media_url():
    broken = {**PHOTO, "src": {**PHOTO["src"], "portrait": "https://evil.example/1.jpg"}}

    def handler(request):
        return _response([broken])

    assert _adapter(handler).search("Roma antiga", orientation="portrait") == []


def test_adapter_requires_api_key():
    with pytest.raises(ProviderNotFound):
        PexelsMediaSearch("pexels-model", "  ")


def test_adapter_refuses_when_license_is_unknown():
    # Sem licença conhecida o adapter não é construído: nada de candidato com licença inventada.
    with pytest.raises(ProviderNotFound):
        PexelsMediaSearch("pexels-model", "KEY", license_text="  ")


def test_adapter_uses_informed_license_when_provider_exposes_one():
    def handler(request):
        return _response([PHOTO])

    candidates = _adapter(handler, license_text="CC0").search("Roma antiga")
    assert candidates[0].license == "CC0"


def test_adapter_does_not_leak_key_on_http_error():
    def handler(request):
        return httpx.Response(429, json={"error": "rate limit"})

    with pytest.raises(ModelUnavailable) as excinfo:
        _adapter(handler, key="SECRET-KEY").search("Roma antiga")
    assert "SECRET-KEY" not in str(excinfo.value)


def test_adapter_returns_empty_list_when_no_photo_is_found():
    def handler(request):
        return _response([])

    assert _adapter(handler).search("Roma antiga") == []


def test_adapter_rejects_unsupported_media_type():
    def handler(request):  # pragma: no cover - não deve ser chamado
        raise AssertionError("HTTP não deveria ser chamado")

    with pytest.raises(ModelUnavailable):
        _adapter(handler).search("Roma antiga", media_type="audio")


# -- porta e catálogo ---------------------------------------------------------


def test_media_search_port_is_runtime_checkable():
    def handler(request):
        return _response([])

    assert isinstance(_adapter(handler), MediaSearch)


def test_catalog_registers_media_search_capability():
    implementations = _provider_implementations(Settings(pexels_key="key"))
    search = {impl.name: impl for impl in implementations if impl.kind is ProviderKind.SEARCH}
    assert "pexels" in search
    impl = search["pexels"]
    assert impl.name == "pexels"
    assert "search.media" in impl.capabilities
    assert impl.cost.kind is CostKind.FREE
    assert impl.validated is True


def test_catalog_marks_media_search_unavailable_without_key():
    implementations = _provider_implementations(Settings(pexels_key=""))
    card = card_for(ProviderKind.SEARCH, "pexels:", implementations)
    assert card.availability is Availability.UNAVAILABLE
    assert "PEXELS_API_KEY" in (card.reason or "")


def test_catalog_card_is_available_with_key():
    implementations = _provider_implementations(Settings(pexels_key="key"))
    card = card_for(ProviderKind.SEARCH, "pexels:", implementations)
    assert card.availability is Availability.AVAILABLE
    assert card.kind is ProviderKind.SEARCH


def test_required_capability_declares_search():
    from app.studio.domain.provider import REQUIRED_CAPABILITY

    assert REQUIRED_CAPABILITY[ProviderKind.SEARCH] is Capability.SEARCH_MEDIA


# -- materialização do candidato (W4.4) --------------------------------------


def _candidate(url="https://images.pexels.com/photos/42/p.jpg", license="Pexels License"):
    return MediaCandidate(license=license, source_url="https://www.pexels.com/photo/42/", url=url,
                          attribution="Foto de Fotógrafa Teste no Pexels", author="Fotógrafa Teste", media_id="42")


def test_fetcher_returns_bytes_and_keeps_the_candidate_license():
    def handler(request):
        assert str(request.url) == "https://images.pexels.com/photos/42/p.jpg"
        return httpx.Response(200, content=b"png-bytes", headers={"content-type": "image/png"})

    result = PexelsMediaFetcher("pexels-model", transport=httpx.MockTransport(handler)).fetch(_candidate())
    assert result.data == b"png-bytes" and result.mime == "image/png"
    assert result.license == "Pexels License" and result.source_url == "https://www.pexels.com/photo/42/"
    assert result.usage.cost_usd == 0


def test_fetcher_allows_trusted_video_url():
    def handler(request):
        assert str(request.url) == "https://videos.pexels.com/video-files/42/video.mp4"
        return httpx.Response(200, content=b"mp4-bytes", headers={"content-type": "video/mp4"})

    result = PexelsMediaFetcher("pexels-video", transport=httpx.MockTransport(handler)).fetch(
        _candidate(url="https://videos.pexels.com/video-files/42/video.mp4")
    )
    assert result.data == b"mp4-bytes" and result.mime == "video/mp4"


def test_fetcher_refuses_an_untrusted_host():
    with pytest.raises(ModelUnavailable):
        PexelsMediaFetcher("m", transport=httpx.MockTransport(lambda request: httpx.Response(200))).fetch(
            _candidate(url="https://evil.example/photo.jpg"))


def test_fetcher_reports_an_http_failure_as_model_unavailable():
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(ModelUnavailable):
        PexelsMediaFetcher("m", transport=httpx.MockTransport(handler)).fetch(_candidate())

