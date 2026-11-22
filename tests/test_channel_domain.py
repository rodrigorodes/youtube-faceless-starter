"""Testes do contrato de domínio do perfil de canal (puro, sem banco)."""
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.channel import (  # noqa: E402
    ChannelDurationInvalid,
    ChannelFieldInvalid,
    ChannelNameInvalid,
    ChannelProfile,
    ChannelVersionInvalid,
    MAX_PILLARS,
    clean_pillars,
    resolve_publication_authorization,
    verify_publication_authorization,
)
from app.studio.domain.ids import InvalidId  # noqa: E402
from app.studio.domain.youtube_channel import OAuthStatus  # noqa: E402
from app.studio.domain.youtube_identity import (  # noqa: E402
    ChannelAuthorization,
    YouTubeChannelIdentityInvalid,
)

PID = "a" * 32
CID = "b" * 32


def profile(**kw) -> ChannelProfile:
    base = {"id": CID, "project_id": PID, "name": "História"}
    base.update(kw)
    return ChannelProfile(**base)


def test_valid_profile_defaults():
    p = profile()
    assert p.name == "História"
    assert p.language == "pt-BR"
    assert p.target_duration_s == 60
    assert p.version == 1
    assert p.archived is False
    assert p.strategy == ""
    assert p.pillars == ()
    assert p.created_at is None and p.updated_at is None


def test_name_is_stripped_and_validated():
    assert profile(name="  História  ").name == "História"
    for bad in ("", "   ", "a" * 121, None, 123):
        with pytest.raises(ChannelNameInvalid):
            profile(name=bad)


def test_ids_must_be_hex32():
    with pytest.raises(InvalidId):
        profile(id="nope")
    with pytest.raises(InvalidId):
        profile(project_id="x" * 31)


def test_pillars_are_cleaned_deduped_and_capped():
    p = profile(pillars=["  IA ", "IA", "", "Robótica", "  ", "Análise"])
    assert p.pillars == ("IA", "Robótica", "Análise")
    assert isinstance(p.pillars, tuple)
    capped = profile(pillars=[f"p{i}" for i in range(30)])
    assert len(capped.pillars) == MAX_PILLARS
    assert capped.pillars == tuple(f"p{i}" for i in range(MAX_PILLARS))


def test_invalid_duration_rejected():
    for bad in (0, -1, 36001, "60", 1.5, True):
        with pytest.raises(ChannelDurationInvalid):
            profile(target_duration_s=bad)
    assert profile(target_duration_s=1).target_duration_s == 1


def test_invalid_version_rejected():
    for bad in (0, -1, "1", 1.0, True):
        with pytest.raises(ChannelVersionInvalid):
            profile(version=bad)


def test_other_fields_trimmed_and_bounded():
    assert profile(strategy="  nicho  ", cta="  compre  ").strategy == "nicho"
    with pytest.raises(ChannelFieldInvalid):
        profile(narrative="x" * 4001)
    with pytest.raises(ChannelFieldInvalid):
        profile(language="x")
    with pytest.raises(ChannelFieldInvalid):
        profile(audience=123)


def test_profile_is_immutable():
    p = profile()
    with pytest.raises(FrozenInstanceError):
        p.name = "novo"  # type: ignore[misc]


def test_pillars_are_deeply_immutable_and_hashable():
    source = ["IA", "Robótica"]
    p = profile(pillars=source)

    # a coleção do agregado é imutável: mutar falha em vez de alterar o perfil
    assert isinstance(p.pillars, tuple)
    with pytest.raises(AttributeError):
        p.pillars.append("INJETADO")  # type: ignore[attr-defined]

    # mutar a lista do chamador não vaza para o agregado
    source.append("INJETADO")
    assert p.pillars == ("IA", "Robótica")

    # e o agregado inteiro é hashable (collections imutáveis + escalares)
    assert hash(p) == hash(profile(pillars=["IA", "Robótica"]))
    assert {p: "ok"}[p] == "ok"


def test_replace_revalidates():
    p = profile()
    p2 = replace(p, version=2, name="Novo")
    assert p2.version == 2 and p2.name == "Novo"
    with pytest.raises(ChannelNameInvalid):
        replace(p, name="")


def test_clean_pillars_helper_returns_tuple():
    assert clean_pillars(None) == ()
    assert clean_pillars(["a", " a ", "b"]) == ("a", "b")
    assert clean_pillars(("a", "b")) == ("a", "b")  # aceita tupla e normaliza para tupla


def test_style_id_is_optional_but_validated_when_present():
    assert profile().style_id is None  # canal sem estilo é válido
    assert profile(style_id="c" * 32).style_id == "c" * 32
    with pytest.raises(InvalidId):
        profile(style_id="not-an-id")
    with pytest.raises(ChannelFieldInvalid):
        profile(style_id=42)


def test_youtube_target_is_optional_but_validated_when_present():
    assert profile().youtube_channel_id is None  # canal sem destino do YouTube é válido
    assert profile(youtube_channel_id="  UCabc123  ").youtube_channel_id == "UCabc123"
    # é o id do YouTube ([A-Za-z0-9._-]{1,128}), não o check_id hex32 dos ids internos
    assert profile(youtube_channel_id="UC" + "x" * 126).youtube_channel_id == "UC" + "x" * 126
    for bad in ("", "   ", "com espaço", "x" * 129):
        with pytest.raises(YouTubeChannelIdentityInvalid):
            profile(youtube_channel_id=bad)
    with pytest.raises(ChannelFieldInvalid):
        profile(youtube_channel_id=42)


# --------------------------------------------------- resolvedor de autorização


def _authorization(channel_id: str, status: OAuthStatus = OAuthStatus.CONNECTED, grant_id: str = "b" * 32):
    return ChannelAuthorization(grant_id=grant_id, youtube_channel_id=channel_id, status=status)


def test_resolver_finds_the_connected_authorization():
    chan = profile(youtube_channel_id="UCabc123")
    ok = _authorization("UCabc123")
    assert resolve_publication_authorization(chan, [ok]) is ok


def test_resolver_returns_none_when_channel_has_no_target():
    assert resolve_publication_authorization(profile(), [_authorization("UCabc123")]) is None


def test_resolver_returns_none_without_authorizations():
    assert resolve_publication_authorization(profile(youtube_channel_id="UCabc123"), []) is None


def test_resolver_ignores_revoked_and_expired_authorizations():
    chan = profile(youtube_channel_id="UCabc123")
    revoked = _authorization("UCabc123", OAuthStatus.REVOKED)
    expired = _authorization("UCabc123", OAuthStatus.EXPIRED, grant_id="d" * 32)
    assert resolve_publication_authorization(chan, [revoked, expired]) is None
    # a vigente vence, mesmo vindo depois de revogadas na lista
    ok = _authorization("UCabc123", OAuthStatus.CONNECTED, grant_id="e" * 32)
    assert resolve_publication_authorization(chan, [revoked, ok, expired]) is ok


def test_resolver_ignores_authorizations_for_other_channels():
    chan = profile(youtube_channel_id="UCabc123")
    other = _authorization("UCoutro")
    assert resolve_publication_authorization(chan, [other]) is None


# --------------------------------- verificação de identidade antes de publicar (YT-03)


def test_verification_allows_when_the_channel_has_no_youtube_target():
    # Estado de hoje (0 canais com destino): a publicação segue pelo caminho antigo, sem bloqueio.
    assert verify_publication_authorization(profile(), [], token_channel_id="UCqualquer").allowed
    assert verify_publication_authorization(profile(), [], token_channel_id=None).allowed


def test_verification_allows_when_the_token_belongs_to_the_resolved_channel():
    chan = profile(youtube_channel_id="UCabc123")
    ok = _authorization("UCabc123")
    verdict = verify_publication_authorization(chan, [ok], token_channel_id="UCabc123")
    assert verdict.allowed and verdict.authorization is ok


def test_verification_blocks_a_token_from_another_channel():
    chan = profile(youtube_channel_id="UCabc123")
    verdict = verify_publication_authorization(chan, [_authorization("UCabc123")], token_channel_id="UCoutro")
    assert not verdict.allowed
    assert "UCoutro" in verdict.reason and "UCabc123" in verdict.reason  # motivo nomeia os dois canais


def test_verification_fails_closed_when_the_token_channel_is_unknown():
    chan = profile(youtube_channel_id="UCabc123")
    verdict = verify_publication_authorization(chan, [_authorization("UCabc123")], token_channel_id=None)
    assert not verdict.allowed and "unknown" in verdict.reason


def test_verification_blocks_a_target_without_a_connected_authorization():
    chan = profile(youtube_channel_id="UCabc123")
    verdict = verify_publication_authorization(chan, [], token_channel_id="UCabc123")
    assert not verdict.allowed and "UCabc123" in verdict.reason
    revoked = _authorization("UCabc123", OAuthStatus.REVOKED)
    assert not verify_publication_authorization(chan, [revoked], token_channel_id="UCabc123").allowed


def test_channel_defaults_match_the_effective_config_editorial_defaults():
    """O default do perfil e o default do motor são o mesmo retrato legado (sem duas verdades)."""
    from app.studio.domain.effective_config import EDITORIAL_DEFAULTS

    p = profile()
    assert p.language == EDITORIAL_DEFAULTS["language"]
    assert p.audience == EDITORIAL_DEFAULTS["audience"]
    assert p.pillars == EDITORIAL_DEFAULTS["pillars"]
    assert p.narrative == EDITORIAL_DEFAULTS["narrative"]
    assert p.target_duration_s == EDITORIAL_DEFAULTS["duration_s"]
    assert p.cta == EDITORIAL_DEFAULTS["cta"]
