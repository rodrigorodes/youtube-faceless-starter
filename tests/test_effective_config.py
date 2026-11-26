"""Contrato da configuração efetiva de produção (F03.T01): tipada, versionada, com proveniência.

Puro, sem banco: só `app.studio.domain.effective_config`. O foco é o contrato — mesma entrada,
mesma configuração canônica; precedência explícita (seleção de estilo inteiro ≠ patch); default
legado quando não há perfil de canal; e recusa de payload inválido ou com segredo.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.channel import ChannelProfile  # noqa: E402
from app.studio.domain.contracts import Video, VideoFormat  # noqa: E402
from app.studio.domain.effective_config import (  # noqa: E402
    SCHEMA_VERSION,
    ConfigSource,
    EffectiveConfig,
    EffectiveConfigError,
    EffectiveConfigInvalid,
    UnsupportedConfigSchema,
    resolve_effective_config,
)
from app.studio.domain.ids import check_id  # noqa: E402
from app.studio.domain.provider import EconomicProfile  # noqa: E402
from app.studio.domain.visual_style import StylePatch, VisualStyle  # noqa: E402

PID = "f" * 32
VID = "e" * 32
CID = "d" * 32
SID = "a" * 32
OTHER = "b" * 32


def video(style_id=None):
    return Video(id=VID, project_id=PID, topic="Um tema sobre história", format=VideoFormat.short,
                 style_id=style_id)


def channel(style_id=None, **kwargs):
    return ChannelProfile(id=CID, project_id=PID, name="Canal", style_id=style_id, **kwargs)


def style(style_id=SID, version=1, archived=False, **params):
    return VisualStyle(id=style_id, name="Estilo", version=version, archived=archived, params=params)


def resolve(*, vid=None, chan=None, styles=(), **kwargs):
    catalog = {item.id: item for item in styles}
    return resolve_effective_config(video=vid or video(), channel=chan, lookup_style=catalog.get,
                                    **kwargs)


def _keys(node):
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            found.update(_keys(value))
    elif isinstance(node, list):
        for value in node:
            found.update(_keys(value))
    return found


def leaves(section, prefix):
    """Caminhos folha de um documento (por chave declarada), o que a proveniência cobre."""
    found = {}
    for key, value in section.items():
        path = f"{prefix}.{key}"
        if isinstance(value, dict) and value:
            found.update({f"{path}.{nested}": item for nested, item in value.items()})
        else:
            found[path] = value
    return found


# ---------- contrato do documento ----------


def test_document_shape_is_the_versioned_contract():
    config = resolve(vid=video(SID), chan=channel(), styles=[style(version=4, motion=["zoom_in"])])
    document = config.to_document()
    assert list(document) == ["schema_version", "project_id", "video_id", "channel_profile", "style",
                              "editorial", "audiovisual", "provider_policy", "provenance"]
    assert document["schema_version"] == SCHEMA_VERSION == 1
    assert document["project_id"] == PID and document["video_id"] == VID
    assert document["channel_profile"] == {"id": CID, "version": 1}
    assert document["style"] == {"id": SID, "version": 4}
    assert list(document["editorial"]) == ["language", "audience", "pillars", "narrative",
                                            "duration_s", "cta"]
    assert list(document["audiovisual"]) == ["voice", "motion", "music", "transition", "caption",
                                             "palette", "extra"]
    assert document["provider_policy"] == {"profile": "BALANCED", "version": 2}
    assert config.content_hash == config.content_hash and len(config.content_hash) == 64


def test_same_inputs_produce_the_same_canonical_configuration():
    args = dict(vid=video(SID), chan=channel(), video_patch={"music": {"bpm": 130}},
                channel_patch={"caption": {"bottom": 1400}})
    one = resolve(styles=[style(music={"bpm": 90}, caption={"font_size": 40})], **args)
    two = resolve(styles=[style(caption={"font_size": 40}, music={"bpm": 90})], **args)
    assert one == two
    assert one.to_document() == two.to_document()
    assert one.canonical_json() == two.canonical_json()
    assert one.content_hash == two.content_hash
    # mudou um valor criativo → outro hash (o hash é a identidade da configuração)
    assert resolve(vid=video(SID), styles=[style(music={"bpm": 91})]).content_hash != \
        resolve(vid=video(SID), styles=[style(music={"bpm": 90})]).content_hash


def test_canonical_document_sorts_keys_and_normalizes_numbers():
    config = resolve(video_patch={"extra": {"zeta": 1.0, "alpha": -0.0, "half": 0.5}})
    canonical = config.canonical_document()
    assert canonical["audiovisual"]["extra"] == {"alpha": 0, "half": 0.5, "zeta": 1}
    for node in (canonical, canonical["editorial"], canonical["audiovisual"],
                 canonical["audiovisual"]["extra"]):
        assert list(node) == sorted(node)
    assert '"alpha":0' in config.canonical_json()
    assert json.loads(config.canonical_json())["schema_version"] == 1


def test_non_json_or_non_finite_values_are_refused_at_resolution():
    with pytest.raises(EffectiveConfigInvalid, match="finite"):
        resolve(video_patch={"extra": {"gain": float("nan")}})
    with pytest.raises(EffectiveConfigInvalid, match="JSON"):
        resolve(video_patch={"extra": {"when": object()}})


# ---------- defaults legados e editorial ----------


def test_without_a_channel_profile_the_legacy_defaults_are_explicit():
    config = resolve()
    assert config.channel_profile is None and config.style is None
    assert (config.language, config.audience, config.pillars, config.narrative, config.duration_s,
            config.cta) == ("pt-BR", "", (), "", 60, "")
    assert config.motion == ()
    assert dict(config.music) == {"bpm": 122, "seed": 7}
    assert dict(config.transition) == {"kind": "none", "duration_ticks": 0}
    assert dict(config.caption) == {} and dict(config.palette) == {}
    assert dict(config.voice) == {} and dict(config.extra) == {}
    assert config.provider_profile is EconomicProfile.BALANCED
    assert set(config.provenance.values()) == {"engine_default"}
    assert config.to_document()["editorial"] == {
        "language": "pt-BR", "audience": "", "pillars": [], "narrative": "", "duration_s": 60,
        "cta": ""}


def test_the_channel_supplies_the_editorial_values_with_provenance():
    chan = channel(language="en-US", audience="curiosos", pillars=["história"],
                   narrative="linear", target_duration_s=480, cta="inscreva-se")
    config = resolve(chan=chan)
    assert (config.language, config.audience, config.pillars, config.narrative,
            config.duration_s, config.cta) == ("en-US", "curiosos", ("história",), "linear", 480,
                                               "inscreva-se")
    assert {key: value for key, value in config.provenance.items()
            if key.startswith("editorial.")} == {f"editorial.{field}": "channel" for field in
                                                 ("language", "audience", "pillars", "narrative",
                                                  "duration_s", "cta")}
    assert config.to_document()["editorial"]["pillars"] == ["história"]


# ---------- seleção de estilo inteiro (≠ patch) ----------


def test_whole_style_selection_prefers_the_video_then_the_channel():
    channel_style = style(SID, version=3, music={"bpm": 100})
    video_style = style(OTHER, version=7, music={"bpm": 150})
    chosen = resolve(vid=video(OTHER), chan=channel(SID), styles=[channel_style, video_style])
    assert (chosen.style.id, chosen.style.version) == (OTHER, 7)
    assert dict(chosen.music) == {"bpm": 150, "seed": 7}
    assert chosen.provenance["style"] == "video"
    inherited = resolve(vid=video(), chan=channel(SID), styles=[channel_style, video_style])
    assert (inherited.style.id, inherited.style.version) == (SID, 3)
    assert inherited.provenance["style"] == "channel"


def test_an_archived_or_missing_style_counts_as_absent():
    archived_video_style = style(OTHER, archived=True, music={"bpm": 150})
    channel_style = style(SID, music={"bpm": 100})
    falls_back = resolve(vid=video(OTHER), chan=channel(SID),
                         styles=[archived_video_style, channel_style])
    assert falls_back.style.id == SID and falls_back.provenance["style"] == "channel"
    missing = resolve(vid=video("d" * 32), chan=channel(SID), styles=[channel_style])
    assert missing.style.id == SID
    # id legado fora da forma canônica não derruba a resolução: conta como ausente
    weird = resolve(vid=video("not-an-id"), chan=channel(SID), styles=[channel_style])
    assert weird.style.id == SID
    none = resolve(vid=video(OTHER), chan=channel(SID),
                   styles=[style(SID, archived=True), archived_video_style])
    assert none.style is None and none.provenance["style"] == "engine_default"


# ---------- precedência de patch ----------


def test_patch_precedence_is_video_then_channel_then_style_then_engine_default():
    base = style(music={"bpm": 100, "seed": 3}, motion=["zoom_in"], caption={"font_size": 40},
                 palette={"accent": "#FF008C"})
    config = resolve(vid=video(SID), chan=channel(), styles=[base],
                     channel_patch={"music": {"bpm": 110}, "motion": ["pan_left"]},
                     video_patch={"music": {"bpm": 130}})
    assert dict(config.music) == {"bpm": 130, "seed": 3}
    assert config.motion == ("pan_left",)
    assert dict(config.caption) == {"font_size": 40}
    assert dict(config.palette) == {"accent": "#FF008C"}
    assert config.provenance["audiovisual.music.bpm"] == "video"
    assert config.provenance["audiovisual.music.seed"] == "style"
    assert config.provenance["audiovisual.motion"] == "channel"
    assert config.provenance["audiovisual.caption.font_size"] == "style"
    assert config.provenance["audiovisual.transition.kind"] == "engine_default"


def test_lists_replace_and_a_none_in_a_patch_resets_to_the_lower_layer():
    base = style(music={"bpm": 100}, motion=["zoom_in"],
                 caption={"font_size": 40, "bottom": 1500})
    config = resolve(vid=video(SID), chan=channel(), styles=[base],
                     channel_patch={"music": {"bpm": 110}, "motion": ["pan_left"]},
                     video_patch={"motion": ["pan_right"], "music": {"bpm": None},
                                  "caption": {"font_size": None}})
    assert config.motion == ("pan_right",)  # lista substitui, não concatena
    assert dict(config.music) == {"bpm": 110, "seed": 7}  # reset: bpm volta ao canal, seed ao engine
    assert config.provenance["audiovisual.music.bpm"] == "channel"
    assert config.provenance["audiovisual.music.seed"] == "engine_default"
    # o reset removeu só o override do vídeo: o valor volta ao estilo selecionado
    assert dict(config.caption) == {"font_size": 40, "bottom": 1500}
    assert config.provenance["audiovisual.caption.font_size"] == "style"


def test_a_whole_group_reset_falls_back_to_the_lower_layer():
    base = style(music={"bpm": 100}, motion=["zoom_in"])
    inherited = resolve(vid=video(SID), styles=[base],
                        video_patch={"music": None, "motion": None})
    assert dict(inherited.music) == {"bpm": 100, "seed": 7}
    assert inherited.motion == ("zoom_in",)
    assert inherited.provenance["audiovisual.music.bpm"] == "style"
    empty = resolve(vid=video(SID), video_patch={"music": None, "motion": None})
    assert dict(empty.music) == {"bpm": 122, "seed": 7}
    assert empty.motion == ()
    assert empty.provenance["audiovisual.music.bpm"] == "engine_default"
    assert empty.provenance["audiovisual.motion"] == "engine_default"


# ---------- proveniência ----------


def test_provenance_covers_every_materialized_creative_value():
    config = resolve(vid=video(SID), chan=channel(),
                     styles=[style(music={"bpm": 90}, caption={"font_size": 40},
                                   extra={"lut": "warm"})],
                     video_patch={"palette": {"accent": "#000000"}})
    document = config.to_document()
    expected = ({"style", "provider_policy"}
                | set(leaves(document["editorial"], "editorial"))
                | set(leaves(document["audiovisual"], "audiovisual")))
    assert set(config.provenance) == expected
    assert set(config.provenance.values()) <= {source.value for source in ConfigSource}
    assert config.provenance["audiovisual.music.bpm"] == "style"
    assert config.provenance["audiovisual.palette.accent"] == "video"
    assert config.provenance["audiovisual.voice"] == "engine_default"
    assert config.provenance["style"] == "video"


def test_a_nested_extension_is_one_declared_value_in_the_provenance():
    # `extra` é extensão livre: um valor aninhado é o valor daquela chave, não um caminho novo.
    config = resolve(vid=video(SID), styles=[style(extra={"nested": {"x": 1}, "lut": "warm"})])
    assert config.to_document()["audiovisual"]["extra"] == {"nested": {"x": 1}, "lut": "warm"}
    assert config.provenance["audiovisual.extra.nested"] == "style"
    assert config.provenance["audiovisual.extra.lut"] == "style"


# ---------- política de providers ----------


def test_the_provider_policy_is_only_a_frozen_reference():
    config = resolve(provider_profile=EconomicProfile.PREMIUM)
    assert config.provider_profile is EconomicProfile.PREMIUM
    assert config.to_document()["provider_policy"] == {"profile": "PREMIUM", "version": 2}
    assert config.provenance["provider_policy"] == "declared"
    assert set(config.to_document()["provider_policy"]) == {"profile", "version"}
    with pytest.raises(EffectiveConfigInvalid, match="profile"):
        resolve(provider_profile="TURBO")


def test_the_provider_selection_is_frozen_as_an_optional_reference():
    selection = {"text": "opencode:gpt-4", "image": "pexels:landscape",
                 "voice": "piper:pt_BR-faber-medium", "renderer": "ffmpeg:rich"}
    config = resolve(provider_selection=selection)
    document = config.to_document()
    assert document["provider_policy"]["selection"] == selection
    assert set(document["provider_policy"]) == {"profile", "version", "selection"}
    restored = EffectiveConfig.from_document(document)
    assert restored == config
    assert dict(restored.provider_selection) == selection


def test_a_legacy_document_without_a_selection_keeps_working():
    config = resolve(provider_profile="PREMIUM")
    document = config.to_document()
    assert "selection" not in document["provider_policy"]
    restored = EffectiveConfig.from_document(document)
    assert restored == config
    assert restored.provider_selection is None


def test_the_provider_selection_refuses_unknown_capability_or_invalid_spec():
    for selection in ({"unknown_kind": "x:y"}, {"text": ""}, {"text": ":"}, {"text": 123}):
        with pytest.raises(EffectiveConfigInvalid):
            resolve(provider_selection=selection)


def test_the_provider_selection_never_carries_a_secret():
    with pytest.raises(EffectiveConfigInvalid) as exc:
        resolve(provider_selection={"text": "opencode:sk-live-123"})
    assert "sk-live-123" not in str(exc.value)
    # o modelo pode conter `:`; um segredo em qualquer segmento também é recusado
    with pytest.raises(EffectiveConfigInvalid):
        resolve(provider_selection={"text": "opencode:vendor:sk-live-123"})
    config = resolve(provider_selection={"text": "opencode:gpt-4",
                                         "voice": "piper:pt_BR-faber-medium"})
    assert "sk-live-123" not in config.canonical_json()
    assert "token" not in config.canonical_json().lower()


# ---------- recusa de inválido e de segredo ----------


def test_invalid_payloads_are_refused_with_a_domain_error():
    for kwargs in ({"video_patch": {"colour": "#fff"}},
                   {"video_patch": {"motion": ["nope"]}},
                   {"video_patch": {"palette": {"accent": "red"}}},
                   {"video_patch": {"music": "loud"}},
                   {"video_patch": ["not-a-mapping"]},
                   {"video_patch": {"music": {"bpm": 10}}},
                   {"channel_patch": {"music": {"bpm": 110}}}):  # patch de canal sem canal
        with pytest.raises(EffectiveConfigInvalid):
            resolve(**kwargs)
    eager = style(transition={"kind": "fade", "duration_ticks": 8})
    with pytest.raises(EffectiveConfigInvalid, match="transition"):
        resolve(vid=video(SID), styles=[eager], video_patch={"transition": {"kind": "none"}})
    assert issubclass(EffectiveConfigInvalid, EffectiveConfigError)
    assert issubclass(EffectiveConfigError, ValueError)


def test_a_channel_profile_from_another_project_is_refused():
    other = ChannelProfile(id=CID, project_id="9" * 32, name="Outro")
    with pytest.raises(EffectiveConfigInvalid, match="project"):
        resolve(chan=other)


def test_a_declared_style_requires_a_lookup_but_a_legacy_id_counts_as_absent():
    with pytest.raises(EffectiveConfigInvalid, match="lookup"):
        resolve_effective_config(video=video(SID))
    # o lookup pode recusar um id legado (InvalidId): a resolução cai no default, não quebra
    config = resolve_effective_config(video=video("not-an-id"), lookup_style=check_id)
    assert config.style is None and config.provenance["style"] == "engine_default"


def test_secrets_are_refused_and_never_part_of_the_document():
    with pytest.raises(EffectiveConfigInvalid) as exc:
        resolve(video_patch={"extra": {"api_key": "sk-live-123"}})
    assert "api_key" in str(exc.value) and "sk-live-123" not in str(exc.value)
    with pytest.raises(EffectiveConfigInvalid):
        resolve(vid=video(SID), styles=[style(extra={"access_token": "t0ken-do-not-echo"})])
    config = resolve(vid=video(SID), styles=[style(voice={"model": "pt_BR-faber-medium"})])
    assert not any(part in key.lower() for key in _keys(config.to_document())
                   for part in ("token", "secret", "password", "authorization", "balance", "saldo",
                                "grant", "api_key", "credential"))
    assert "access_token" not in config.canonical_json()


# ---------- documento canônico como contrato (round-trip) ----------


def test_the_document_round_trips_through_the_same_canonical_configuration():
    config = resolve(vid=video(SID), chan=channel(language="en-US"),
                     styles=[style(music={"bpm": 90}, motion=["zoom_in"])],
                     channel_patch={"caption": {"bottom": 1400}},
                     video_patch={"music": {"seed": 5}}, provider_profile="PREMIUM")
    restored = EffectiveConfig.from_document(config.to_document())
    assert restored == config
    assert restored.content_hash == config.content_hash

    broken = config.to_document()
    broken["style"] = {"id": SID, "version": 0}
    with pytest.raises(EffectiveConfigInvalid):
        EffectiveConfig.from_document(broken)
    unsupported = config.to_document()
    unsupported["schema_version"] = 2
    with pytest.raises(UnsupportedConfigSchema):
        EffectiveConfig.from_document(unsupported)
    unknown = config.to_document()
    unknown["extra_root"] = 1
    with pytest.raises(EffectiveConfigInvalid):
        EffectiveConfig.from_document(unknown)
    bogus_provenance = config.to_document()
    bogus_provenance["provenance"]["style"] = "somewhere"
    with pytest.raises(EffectiveConfigInvalid):
        EffectiveConfig.from_document(bogus_provenance)
    gap = config.to_document()
    gap["provenance"].pop("editorial.cta")  # todo valor criativo tem origem declarada
    with pytest.raises(EffectiveConfigInvalid, match="provenance"):
        EffectiveConfig.from_document(gap)


def test_the_configuration_is_immutable_and_isolated_from_the_caller():
    shared = {"lut": "warm"}
    config = resolve(video_patch={"extra": shared})
    shared["lut"] = "cold"
    assert dict(config.extra) == {"lut": "warm"}
    with pytest.raises(TypeError):
        config.extra["lut"] = "cold"
    document = config.to_document()
    document["audiovisual"]["extra"]["lut"] = "cold"
    assert config.to_document()["audiovisual"]["extra"] == {"lut": "warm"}

# ---------- F05.T01: o patch tipado é a entrada canônica da resolução ----------

BASE_STYLE = dict(music={"bpm": 100, "seed": 3}, motion=["zoom_in"],
                  caption={"font_size": 40, "bottom": 1500})

TYPED_PATCH_CASES = [
    # (caso, patch do vídeo, esperado (music, motion, caption), proveniência esperada)
    ("ausência herda o estilo", {},
     ({"bpm": 100, "seed": 3}, ("zoom_in",), {"font_size": 40, "bottom": 1500}),
     {"audiovisual.music.bpm": "style", "audiovisual.motion": "style"}),
    ("campo presente sobrescreve só ele", {"music": {"bpm": 130}},
     ({"bpm": 130, "seed": 3}, ("zoom_in",), {"font_size": 40, "bottom": 1500}),
     {"audiovisual.music.bpm": "video", "audiovisual.music.seed": "style"}),
    ("nulo na chave devolve a chave à camada de baixo", {"music": {"bpm": None}},
     ({"bpm": 100, "seed": 3}, ("zoom_in",), {"font_size": 40, "bottom": 1500}),
     {"audiovisual.music.bpm": "style"}),
    ("nulo no grupo devolve o grupo à camada de baixo", {"music": None},
     ({"bpm": 100, "seed": 3}, ("zoom_in",), {"font_size": 40, "bottom": 1500}),
     {"audiovisual.music.bpm": "style"}),
    ("lista substitui, nunca concatena", {"motion": ["pan_left"]},
     ({"bpm": 100, "seed": 3}, ("pan_left",), {"font_size": 40, "bottom": 1500}),
     {"audiovisual.motion": "video"}),
    ("nulo na lista volta ao estilo", {"motion": None},
     ({"bpm": 100, "seed": 3}, ("zoom_in",), {"font_size": 40, "bottom": 1500}),
     {"audiovisual.motion": "style"}),
    ("mapa mescla chave a chave", {"caption": {"font_size": 50}},
     ({"bpm": 100, "seed": 3}, ("zoom_in",), {"font_size": 50, "bottom": 1500}),
     {"audiovisual.caption.font_size": "video", "audiovisual.caption.bottom": "style"}),
]


@pytest.mark.parametrize("patch,expected,provenance",
                         [case[1:] for case in TYPED_PATCH_CASES],
                         ids=[case[0] for case in TYPED_PATCH_CASES])
def test_typed_patch_semantics_are_tabulated_end_to_end(patch, expected, provenance):
    music, motion, caption = expected
    # o mapping cru é aceito e normalizado pelo mesmo modelo tipado...
    raw = resolve(vid=video(SID), styles=[style(**BASE_STYLE)], video_patch=patch)
    assert dict(raw.music) == music
    assert raw.motion == motion
    assert dict(raw.caption) == caption
    for path, source in provenance.items():
        assert raw.provenance[path] == source
    # ...e o patch já tipado é a entrada canônica: mesmo resultado, mesmo hash.
    typed = resolve(vid=video(SID), styles=[style(**BASE_STYLE)],
                    video_patch=StylePatch.from_mapping(patch))
    assert typed == raw and typed.content_hash == raw.content_hash


def test_the_typed_patch_follows_the_video_then_channel_precedence():
    typed_channel = StylePatch.from_mapping({"music": {"bpm": 110}, "motion": ["pan_left"]})
    typed_video = StylePatch.from_mapping({"music": {"bpm": 130}})
    config = resolve(vid=video(SID), chan=channel(), styles=[style(**BASE_STYLE)],
                     channel_patch=typed_channel, video_patch=typed_video)
    assert dict(config.music) == {"bpm": 130, "seed": 3}
    assert config.motion == ("pan_left",)
    assert config.provenance["audiovisual.music.bpm"] == "video"
    assert config.provenance["audiovisual.motion"] == "channel"


def test_an_invalid_typed_patch_is_refused_as_a_domain_error():
    cases = [
        ("campo fora da allowlist", {"music": {"tempo": 130}}, "tempo"),
        ("grupo fora da allowlist", {"colour": "#fff"}, "colour"),
        ("seleção de estilo não é patch", {"style_id": SID}, "style_id"),
        ("nulo em campo não resetável", {"extra": {"lut": None}}, "reset"),
        ("grupo de mapa vazio", {"music": {}}, "at least one key"),
        ("lista vazia", {"motion": []}, "motion"),
    ]
    for _, patch, message in cases:
        with pytest.raises(EffectiveConfigInvalid, match=message):
            resolve(vid=video(SID), styles=[style(**BASE_STYLE)], video_patch=patch)
