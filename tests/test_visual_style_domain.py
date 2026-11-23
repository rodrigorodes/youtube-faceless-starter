"""Domínio do estilo visual (VS-01): parâmetros, extensão (`extra`) e versionamento. Puro."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.render_plan import Motion, StyleSnapshot  # noqa: E402
from app.studio.domain.visual_style import (  # noqa: E402
    APPLIED_GROUPS,
    KNOWN_PARAMS,
    LOADED_ONLY_GROUPS,
    MOTIONS,
    PATCH_GROUP_FIELDS,
    PRESETS,
    ResolvedStyle,
    StylePatch,
    StylePatchInvalid,
    VisualStyle,
    VisualStyleNameInvalid,
    VisualStyleParamsInvalid,
    VisualStyleVersionInvalid,
    apply_style_patch,
    clean_params,
    preset_params,
    resolve_style,
)

SID = "a" * 32


def style(**kwargs):
    return VisualStyle(id=SID, name="Documentário Cinemático", **kwargs)


def test_minimal_style_has_no_params_and_version_one():
    s = style()
    assert s.params == {} and s.version == 1 and s.archived is False and s.organization_id is None


def test_motions_mirror_the_plan_contract_not_a_copy():
    # A lista válida de movimento é a do contrato do plano: se o plano ganhar um movimento,
    # o estilo acompanha sem edição (uma fonte só).
    from typing import get_args

    assert MOTIONS == frozenset(get_args(Motion))


def test_valid_params_round_trip():
    params = {
        "motion": ["zoom_in", "zoom_out", "pan_right", "pan_left"],
        "music": {"bpm": 122, "seed": 7},
        "transition": {"kind": "fade", "duration_ticks": 8},
        "caption": {"font_size": 58, "bottom": 1560},
        "palette": {"caption_text": "#FFFFFF", "caption_box": "#000000A5", "accent": "#FF008C"},
        "voice": {"model": "pt_BR-faber-medium"},
        "extra": {"lut": "warm"},
    }
    assert style(params=params).params == params


def test_motion_deduplicates_and_rejects_unknown():
    assert clean_params({"motion": ["zoom_in", "zoom_in"]})["motion"] == ["zoom_in"]
    with pytest.raises(VisualStyleParamsInvalid, match="motion"):
        clean_params({"motion": ["nope"]})
    with pytest.raises(VisualStyleParamsInvalid, match="motion"):
        clean_params({"motion": []})
    with pytest.raises(VisualStyleParamsInvalid, match="motion"):
        clean_params({"motion": "zoom_in"})


def test_music_bounds_and_requires_a_field():
    assert clean_params({"music": {"bpm": 120}})["music"] == {"bpm": 120}
    assert clean_params({"music": {"seed": 3}})["music"] == {"seed": 3}
    for bad in ({"bpm": 10}, {"bpm": 400}, {}):
        with pytest.raises(VisualStyleParamsInvalid, match="music"):
            clean_params({"music": bad})


def test_transition_none_has_no_duration_and_fade_needs_one():
    assert clean_params({"transition": {"kind": "none"}})["transition"] == {"kind": "none", "duration_ticks": 0}
    assert clean_params({"transition": {"kind": "fade", "duration_ticks": 8}})["transition"]["kind"] == "fade"
    with pytest.raises(VisualStyleParamsInvalid, match="transition"):
        clean_params({"transition": {"kind": "none", "duration_ticks": 5}})
    with pytest.raises(VisualStyleParamsInvalid, match="transition"):
        clean_params({"transition": {"kind": "fade"}})
    with pytest.raises(VisualStyleParamsInvalid, match="transition"):
        clean_params({"transition": {"kind": "wipe", "duration_ticks": 3}})


def test_palette_needs_hex_colors():
    assert clean_params({"palette": {"accent": "#FF008C"}})["palette"] == {"accent": "#FF008C"}
    assert clean_params({"palette": {"accent": "#FF008CAA"}})["palette"] == {"accent": "#FF008CAA"}
    with pytest.raises(VisualStyleParamsInvalid, match="palette"):
        clean_params({"palette": {"accent": "red"}})
    with pytest.raises(VisualStyleParamsInvalid, match="palette"):
        clean_params({"palette": {}})


def test_voice_requires_a_non_empty_model():
    assert clean_params({"voice": {"model": " pt_BR-faber-medium "}})["voice"] == {"model": "pt_BR-faber-medium"}
    with pytest.raises(VisualStyleParamsInvalid, match="voice"):
        clean_params({"voice": {"model": "  "}})


def test_extra_is_the_extension_escape_hatch():
    assert clean_params({"extra": {"lut": "warm", "beat_grid": [0, 1, 2]}})["extra"]["lut"] == "warm"


def test_unknown_top_level_key_is_rejected_not_silently_dropped():
    with pytest.raises(VisualStyleParamsInvalid, match="unknown params key"):
        clean_params({"colour": "#fff"})  # a extensão é `extra`, não chute


def test_params_are_a_deep_copy_isolated_from_the_caller():
    shared = {"extra": {"nested": {"x": 1}}}
    s = style(params=shared)
    s.params["extra"]["nested"]["x"] = 999
    assert shared["extra"]["nested"]["x"] == 1  # o agregado não compartilha estrutura mutável


def test_blank_or_long_name_is_refused():
    for bad in ("", "   ", "x" * 121, 42):
        with pytest.raises(VisualStyleNameInvalid):
            VisualStyle(id=SID, name=bad)


def test_version_must_be_a_positive_integer():
    for bad in (0, -1, "1", 1.5, True):
        with pytest.raises(VisualStyleVersionInvalid):
            style(version=bad)


# ---------- VS-03: resolução do estilo para o render (puro, sem banco) ----------


def test_resolve_style_without_a_style_is_none():
    assert resolve_style(None, None) is None


def test_resolve_style_projects_the_snapshot_and_the_applicable_params():
    s = style(params={"motion": ["zoom_in", "pan_right"], "music": {"bpm": 90, "seed": 4},
                      "transition": {"kind": "fade", "duration_ticks": 8}})
    resolved = resolve_style(None, s)
    assert resolved is not None
    assert resolved.snapshot == StyleSnapshot(style_id=SID, version=1)
    assert resolved.motion == ("zoom_in", "pan_right")
    assert resolved.music == {"bpm": 90, "seed": 4}
    # a transição é carregada por fidelidade, mas ainda NÃO é aplicada pelo render (fatia futura)
    assert resolved.transition == {"kind": "fade", "duration_ticks": 8}


def test_resolve_style_defaults_are_empty_when_params_are_absent():
    resolved = resolve_style(None, style())
    assert isinstance(resolved, ResolvedStyle)
    assert resolved.motion == () and resolved.music == {} and resolved.transition == {}
    assert resolved.caption == {} and resolved.palette == {} and resolved.voice == {}


def test_resolve_style_carries_caption_palette_and_voice():
    # VS-04: caption/palette são aplicados pelo render; voice é carregado (precedência intacta).
    s = style(params={"caption": {"font_size": 40, "bottom": 1400},
                      "palette": {"caption_box": "#00FF00", "accent": "#FF008C"},
                      "voice": {"model": "pt_BR-jeff-medium"}})
    resolved = resolve_style(None, s)
    assert resolved.caption == {"font_size": 40, "bottom": 1400}
    assert resolved.palette == {"caption_box": "#00FF00", "accent": "#FF008C"}
    assert resolved.voice == {"model": "pt_BR-jeff-medium"}


def test_resolve_style_override_wins_over_the_channel_style():
    channel = style(params={"motion": ["zoom_in"]})
    override = VisualStyle(id="b" * 32, name="Override do vídeo", version=5,
                           params={"motion": ["pan_left"], "music": {"bpm": 60}})
    resolved = resolve_style(None, channel, override=override)
    assert resolved.snapshot == StyleSnapshot(style_id=override.id, version=5)
    assert resolved.motion == ("pan_left",) and resolved.music == {"bpm": 60}


def test_resolve_style_treats_an_archived_style_as_absent():
    # VS-05c: um estilo arquivado nunca dirige um render. O override arquivado cai no canal; o
    # estilo de canal arquivado cai no neutro (None). Ambos arquivados → None.
    channel = style(params={"motion": ["zoom_in"]})
    archived_override = VisualStyle(id="b" * 32, name="Arquivado", archived=True,
                                    params={"motion": ["pan_left"]})
    falls_back = resolve_style(None, channel, override=archived_override)
    assert falls_back is not None and falls_back.snapshot.style_id == channel.id
    assert falls_back.motion == ("zoom_in",)

    archived_channel = VisualStyle(id="c" * 32, name="Canal arquivado", archived=True,
                                   params={"motion": ["pan_left"]})
    assert resolve_style(None, archived_channel) is None
    assert resolve_style(None, archived_channel, override=archived_override) is None


# ---------- F05.T01: patch de estilo tipado (allowlist, herdar, reset, lista substitui) ----------


def test_the_patch_allowlist_is_the_same_contract_as_the_style_params():
    # A allowlist do patch não inventa grupos: é a mesma lista de `params` (uma fonte só).
    assert set(PATCH_GROUP_FIELDS) == set(KNOWN_PARAMS)
    assert PATCH_GROUP_FIELDS["motion"] == ()  # grupo de lista: sem chaves internas
    assert PATCH_GROUP_FIELDS["music"] == ("bpm", "seed")
    assert PATCH_GROUP_FIELDS["transition"] == ("kind", "duration_ticks")
    assert PATCH_GROUP_FIELDS["caption"] == ("font_size", "bottom", "position", "font_family", "style_kind")
    assert PATCH_GROUP_FIELDS["palette"] == ("caption_text", "caption_box", "accent")
    assert PATCH_GROUP_FIELDS["voice"] == ("model",)
    assert PATCH_GROUP_FIELDS["extra"] is None  # bag aberto: qualquer chave de extensão


PATCH_CASES = [
    # (caso, camada de baixo, patch, resultado esperado)
    ("patch vazio herda tudo", {}, {}, {}),
    ("campo ausente herda", {"music": {"bpm": 100, "seed": 3}}, {},
     {"music": {"bpm": 100, "seed": 3}}),
    ("campo presente sobrescreve só ele",
     {"music": {"bpm": 100, "seed": 3}}, {"music": {"bpm": 130}},
     {"music": {"bpm": 130, "seed": 3}}),
    ("nulo na chave remove o patch daquela chave",
     {"music": {"bpm": 100, "seed": 3}}, {"music": {"bpm": None}},
     {"music": {"seed": 3}}),
    ("nulo no grupo remove a camada inteira",
     {"music": {"bpm": 100}, "motion": ["zoom_in"]}, {"music": None},
     {"motion": ["zoom_in"]}),
    ("lista substitui, nunca concatena",
     {"motion": ["zoom_in"]}, {"motion": ["pan_left"]}, {"motion": ["pan_left"]}),
    ("mapa mescla chave a chave",
     {"caption": {"font_size": 40, "bottom": 1500}}, {"caption": {"bottom": 1400}},
     {"caption": {"font_size": 40, "bottom": 1400}}),
    ("transição declarada por partes",
     {"transition": {"kind": "fade", "duration_ticks": 8}}, {"transition": {"duration_ticks": 12}},
     {"transition": {"kind": "fade", "duration_ticks": 12}}),
]


@pytest.mark.parametrize("base,patch,expected", [case[1:] for case in PATCH_CASES],
                         ids=[case[0] for case in PATCH_CASES])
def test_style_patch_semantics_are_tabulated(base, patch, expected):
    assert apply_style_patch(base, patch) == expected
    # o patch tipado é a entrada canônica; o mesmo patch, já tipado, dá o mesmo resultado
    assert apply_style_patch(base, StylePatch.from_mapping(patch)) == expected


PATTERN_CASES = [
    # (caso, payload, trecho do erro)
    ("grupo fora da allowlist", {"colour": "#fff"}, "unknown style patch key"),
    ("seleção de estilo inteiro não é patch", {"style_id": "a" * 32}, "unknown style patch key"),
    ("campo fora da allowlist do grupo", {"music": {"tempo": 130}}, "unknown style patch.music key"),
    ("campo aninhado em motion não existe", {"motion": {"zoom_in": 1}}, "motion must be a list"),
    ("nulo em campo não resetável", {"extra": {"lut": None}}, "cannot be reset"),
    ("grupo de mapa vazio é ambíguo", {"music": {}}, "at least one key"),
    ("lista vazia de motion", {"motion": []}, "motion"),
    ("lista com movimento desconhecido", {"motion": ["nope"]}, "motion item"),
    ("mapa declarado como escalar", {"music": "loud"}, "must be an object"),
    ("bpm fora da faixa", {"music": {"bpm": 10}}, "music.bpm"),
    ("cor que não é hex", {"palette": {"accent": "red"}}, "palette.accent"),
    ("voz vazia", {"voice": {"model": "  "}}, "voice.model"),
    ("transição desconhecida", {"transition": {"kind": "wipe"}}, "transition.kind"),
    ("patch que não é objeto", ["not-a-mapping"], "must be an object"),
]


@pytest.mark.parametrize("payload,message", [case[1:] for case in PATTERN_CASES],
                         ids=[case[0] for case in PATTERN_CASES])
def test_style_patch_refuses_invalid_input_with_a_clear_error(payload, message):
    with pytest.raises(StylePatchInvalid, match=message):
        StylePatch.from_mapping(payload)


def test_a_null_is_accepted_only_where_reset_is_documented():
    patch = StylePatch.from_mapping({"music": None, "motion": None, "voice": {"model": None}})
    assert patch.groups["music"] is None and patch.groups["motion"] is None
    assert patch.groups["voice"] == {"model": None}  # reset de campo tipado: documentado
    with pytest.raises(StylePatchInvalid, match="reset"):
        StylePatch.from_mapping({"extra": {"lut": None}})  # bag aberto: sem reset por chave
    with pytest.raises(StylePatchInvalid, match="unknown style patch"):
        StylePatch.from_mapping({"unknown": None})  # nulo não inventa grupo


def test_the_final_result_is_validated_by_the_same_clean_params():
    # Cada campo isolado é válido para o patch, mas o resultado não é: a mesma validação do
    # estilo recusa (não existe merge "mais frouxo" que o da biblioteca).
    with pytest.raises(VisualStyleParamsInvalid, match="transition"):
        apply_style_patch({"transition": {"kind": "fade", "duration_ticks": 8}},
                          {"transition": {"kind": "none"}})


def test_reset_of_every_key_of_a_group_leaves_the_engine_to_decide():
    # resetar todas as chaves declaradas remove o grupo; o default do motor decide depois.
    assert apply_style_patch({"music": {"bpm": 100, "seed": 3}},
                             {"music": {"bpm": None, "seed": None}}) == {}


def test_the_typed_patch_is_immutable_and_isolated_from_the_caller():
    raw = {"motion": ["zoom_in"], "music": {"bpm": 130}, "extra": {"nested": {"x": 1}}}
    patch = StylePatch.from_mapping(raw)
    raw["motion"].append("pan_left")
    raw["music"]["bpm"] = 999
    raw["extra"]["nested"]["x"] = 999
    assert patch.to_mapping() == {"motion": ["zoom_in"], "music": {"bpm": 130},
                                  "extra": {"nested": {"x": 1}}}
    exported = patch.to_mapping()
    exported["motion"].append("pan_left")
    exported["extra"]["nested"]["x"] = 2
    assert patch.to_mapping()["motion"] == ["zoom_in"]
    assert patch.to_mapping()["extra"] == {"nested": {"x": 1}}


def test_an_absent_patch_is_an_empty_patch_that_changes_nothing():
    assert StylePatch.from_mapping(None) == StylePatch()
    assert StylePatch().groups == {}
    assert apply_style_patch({"music": {"bpm": 100}}, None) == {"music": {"bpm": 100}}


# ---------- W3.2: honestidade dos grupos aplicáveis e presets por nicho ----------


def test_applied_and_loaded_only_groups_partition_the_known_params():
    # A honestidade é exata: todo grupo é ou aplicado pelo render ou carregado-sem-efeito.
    assert APPLIED_GROUPS | LOADED_ONLY_GROUPS == set(KNOWN_PARAMS)
    assert APPLIED_GROUPS.isdisjoint(LOADED_ONLY_GROUPS)
    assert APPLIED_GROUPS == {"motion", "music", "caption", "palette", "voice", "transition"}
    # `extra` é carregado mas não aplicado (não promete efeito).
    assert LOADED_ONLY_GROUPS == {"extra"}


def test_presets_only_carry_groups_the_render_applies():
    # Um preset nunca promete o que o render não faz: só grupos aplicáveis, e passa pelo mesmo
    # `clean_params` (é params de estilo válido, não um dialeto paralelo).
    assert set(PRESETS) == {"documentario", "noticia", "curiosidades"}
    for preset_id in PRESETS:
        params = preset_params(preset_id)
        assert set(params) <= APPLIED_GROUPS
        assert VisualStyle(id=SID, name=f"Preset {preset_id}", params=params).params == params


def test_an_unknown_preset_is_refused_instead_of_invented():
    with pytest.raises(VisualStyleParamsInvalid, match="unknown preset"):
        preset_params("nao-existe")


def test_preset_params_are_isolated_copies_of_the_catalogue():
    first = preset_params("curiosidades")
    first["motion"].append("pan_left")
    first["music"]["bpm"] = 999
    first["caption"]["font_size"] = 1
    again = preset_params("curiosidades")
    assert again["motion"] == ["zoom_in", "zoom_out"]
    assert again["music"] == {"bpm": 122, "seed": 7}
    assert again["caption"] == {"font_size": 58, "bottom": 1560}
