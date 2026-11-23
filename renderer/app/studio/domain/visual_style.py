"""Domínio do estilo visual (biblioteca de estilos compartilhada). Puro: sem I/O, sem banco.

Um **estilo** é a identidade de aparência e som que o produtor configura uma vez e aplica a
vários canais (`ChannelProfile.style_id`). O estilo é imutável e versionado: cada leitura/
atualização carrega a `version`, e o repositório incrementa de forma otimista, gravando um
snapshot auditável por versão — o mesmo padrão de `channel_profile_revisions`.

`params` é o retrato do estilo. Os grupos que o render **de fato** aplica hoje são
motion · music · caption · palette · voice · transition; `extra` é **carregado
sem efeito** — versionado e preservado desde o dia 1, mas nenhum deles muda o vídeo até o
compilador/executor ligar a ponta. É o "conforme o uso vamos melhorando" com contrato, não com
promessa.

A honestidade é explícita (W3.2): ``APPLIED_GROUPS`` são os grupos que o compilador/executor
levam ao vídeo hoje e ``LOADED_ONLY_GROUPS`` o que é carregado sem efeito (``extra``).
``PRESETS``/``preset_params`` oferecem presets por nicho **só** com grupos
aplicáveis — um preset nunca promete o que o render não faz. Note que ``Shot.transition`` (a
transição **do plano**, por shot) é consumida pelo compilador e instanciada pelo builder
a partir de ``style.transition``.

## Patch tipado (F05.T01)

Personalizar um canal/vídeo **não** edita o estilo da biblioteca: é um `StylePatch`, um override
por camada com allowlist e semântica determinística (ADR fs31-004):

- **allowlist**: só os grupos de `params`; dentro de cada grupo, só as chaves que o render
  entende (`PATCH_GROUP_FIELDS`). `extra` é o bag aberto. Campo desconhecido é recusado com a
  chave no erro — nunca ignorado em silêncio.
- **ausência = herdar**: a chave que o patch não menciona continua vindo da camada de baixo.
- **`null` = reset explícito**, só onde é documentado: no grupo inteiro (`"music": null`) ou numa
  chave tipada (`"music": {"bpm": null}`). Numa chave de `extra` (bag sem schema) é recusado —
  reset ali é ambíguo. Reset remove o patch daquela chave, não força o default do motor.
- **lista substitui**: `motion` é um valor inteiro; nunca concatena com a camada de baixo.
- **validação final**: o resultado mesclado passa pelo **mesmo** `clean_params` do estilo. O
  patch valida cada campo isoladamente (para o erro apontar o campo), mas a consistência entre
  campos/camadas (ex.: `fade` precisa de duração) só é conhecida depois da mesclagem.
- **seleção de estilo inteiro** (`video.style_id > channel.style_id > default`) é outra etapa,
  fora do patch: `style_id` não é campo de patch.

`StylePatch` é a **entrada canônica** de `effective_config.resolve_effective_config` (que aceita
o mapping cru e o normaliza por aqui, sem duplicar allowlist). Este módulo não persiste nada
(F05.T02) nem faz I/O.
"""
from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, get_args

from .channel import ChannelProfile
from .ids import check_id
from .render_plan import Motion, StyleSnapshot

MAX_NAME_LENGTH = 120
MAX_VOICE_MODEL_LENGTH = 200
MAX_EXTRA_KEYS = 50
DEFAULT_MUSIC_BPM = 122
DEFAULT_MUSIC_SEED = 7
MIN_BPM, MAX_BPM = 20, 300
_MIN_SEED, _MAX_SEED = 0, 2**31 - 1
# A lista de movimentos válidos é a do contrato do plano — uma fonte só (evita divergir).
MOTIONS = frozenset(get_args(Motion))
TRANSITION_KINDS = frozenset({"none", "fade"})
# Cor hex `#RRGGBB` ou `#RRGGBBAA` (o alfa é o que o adapter usa na legenda/badge).
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
# Chaves de `params` que o contrato conhece. Qualquer outra é recusada — a extensão é `extra`.
KNOWN_PARAMS = ("motion", "music", "transition", "caption", "palette", "voice", "extra")
# W3.2: quais grupos o render **de fato** leva ao vídeo hoje. Só estes podem ganhar controle: o
# compilador/executor consomem `motion` (Ken Burns), `music` (bpm/seed da trilha), `caption`
# (geometria e layout da legenda), `palette` (cores do overlay), `voice` (modelo de fala) e
# `transition` (fade entre cenas vizinhas). Um grupo fora daqui é carregado e versionado sem
# efeito — a UI deve rotulá-lo "declarado e não aplicado", não fingir suporte.
# `LOADED_ONLY_GROUPS` é o complemento **exato** (`APPLIED ∥ LOADED_ONLY` = KNOWN).
APPLIED_GROUPS: frozenset[str] = frozenset({"motion", "music", "caption", "palette", "voice", "transition"})
LOADED_ONLY_GROUPS: frozenset[str] = frozenset(set(KNOWN_PARAMS) - APPLIED_GROUPS)
CREATABLE_FIELDS = ("organization_id", "params", "archived")
UPDATABLE_FIELDS = ("name", "params", "archived")


class VisualStyleError(Exception):
    """Erro base do estilo visual."""


class VisualStyleNameInvalid(VisualStyleError, ValueError):
    """Nome vazio, longo demais ou de tipo inválido."""


class VisualStyleParamsInvalid(VisualStyleError, ValueError):
    """Parâmetro com chave desconhecida, tipo ou valor inválido."""


class VisualStyleFieldInvalid(VisualStyleError, ValueError):
    """Campo de atualização desconhecido (fora de `UPDATABLE_FIELDS`)."""


class VisualStyleArchived(VisualStyleError, ValueError):
    """Estilo arquivado não pode ser escolhido para uso novo (F02.T02/G15).

    O arquivado continua legível para o histórico (runs e vídeos que já o referenciavam), mas
    não entra como opção de criação nem como override novo.
    """


class VisualStyleVersionInvalid(VisualStyleError, ValueError):
    """Versão inválida (precisa ser inteiro >= 1)."""


class VisualStyleVersionConflict(VisualStyleError, ValueError):
    """A versão informada não é a atual: outra atualização venceu a corrida."""


class DuplicateVisualStyle(VisualStyleError, ValueError):
    """Já existe um estilo ativo com este nome."""


class StylePatchInvalid(VisualStyleParamsInvalid):
    """Patch de estilo fora da allowlist, `null` sem reset documentado ou valor inválido (F05.T01).

    Subclasse de ``VisualStyleParamsInvalid`` de propósito: quem já traduz parâmetro inválido para
    o erro do seu contrato continua funcionando; quem trata patch pode ser mais específico.
    """


def validate_name(name: object) -> str:
    if not isinstance(name, str):
        raise VisualStyleNameInvalid("style name must be a string")
    cleaned = name.strip()
    if not (1 <= len(cleaned) <= MAX_NAME_LENGTH):
        raise VisualStyleNameInvalid(f"style name must be between 1 and {MAX_NAME_LENGTH} characters")
    return cleaned


def validate_version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise VisualStyleVersionInvalid("version must be an integer >= 1")
    return value


def _object(value: object, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise VisualStyleParamsInvalid(f"params.{field_name} must be an object")
    return value


def _unknown(where: str, keys: object, allowed) -> None:
    extra = sorted(set(keys) - set(allowed))
    if extra:
        raise VisualStyleParamsInvalid(f"unknown {where} key(s): {extra}")


def _int(value: object, where: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise VisualStyleParamsInvalid(f"{where} must be an integer")
    if minimum is not None and value < minimum:
        raise VisualStyleParamsInvalid(f"{where} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise VisualStyleParamsInvalid(f"{where} must be <= {maximum}")
    return value


def _clean_motion(value: object) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise VisualStyleParamsInvalid("params.motion must be a list of motions")
    motions: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in MOTIONS:
            raise VisualStyleParamsInvalid(f"params.motion item must be one of {sorted(MOTIONS)}")
        if item not in motions:
            motions.append(item)
    if not motions:
        raise VisualStyleParamsInvalid("params.motion cannot be empty")
    return motions


def _clean_music(value: object) -> dict:
    music = _object(value, "music")
    _unknown("params.music", music, ("bpm", "seed"))
    out: dict[str, int] = {}
    if "bpm" in music:
        out["bpm"] = _int(music["bpm"], "params.music.bpm", minimum=MIN_BPM, maximum=MAX_BPM)
    if "seed" in music:
        out["seed"] = _int(music["seed"], "params.music.seed", minimum=_MIN_SEED, maximum=_MAX_SEED)
    if not out:
        raise VisualStyleParamsInvalid("params.music needs at least one of bpm/seed")
    return out


def _clean_transition(value: object) -> dict:
    transition = _object(value, "transition")
    _unknown("params.transition", transition, ("kind", "duration_ticks"))
    kind = transition.get("kind", "none")
    if kind not in TRANSITION_KINDS:
        raise VisualStyleParamsInvalid(f"params.transition.kind must be one of {sorted(TRANSITION_KINDS)}")
    duration = _int(transition.get("duration_ticks", 0), "params.transition.duration_ticks", minimum=0)
    if kind == "none" and duration != 0:
        raise VisualStyleParamsInvalid("a 'none' transition has no duration")
    if kind == "fade" and duration < 1:
        raise VisualStyleParamsInvalid("a 'fade' transition needs a positive duration")
    return {"kind": kind, "duration_ticks": duration}


CAPTION_POSITIONS: tuple[str, ...] = ("top", "middle", "bottom")
CAPTION_POSITION_ALIASES: Mapping[str, str] = MappingProxyType({
    "top": "top",
    "topo": "top",
    "middle": "middle",
    "meio": "middle",
    "bottom": "bottom",
    "base": "bottom",
})

CAPTION_FONT_FAMILIES: tuple[str, ...] = ("dejavu", "roboto", "georgia", "inter")

CAPTION_STYLE_KINDS: tuple[str, ...] = ("box", "simple", "word_highlight")
CAPTION_STYLE_KIND_ALIASES: Mapping[str, str] = MappingProxyType({
    "box": "box",
    "caixa": "box",
    "simple": "simple",
    "simples": "simple",
    "word_highlight": "word_highlight",
    "destaque": "word_highlight",
})


def _clean_caption(value: object) -> dict:
    caption = _object(value, "caption")
    _unknown("params.caption", caption, ("font_size", "bottom", "position", "font_family", "style_kind"))
    out: dict[str, Any] = {}
    if "font_size" in caption:
        out["font_size"] = _int(caption["font_size"], "params.caption.font_size", minimum=8, maximum=400)
    if "bottom" in caption:
        out["bottom"] = _int(caption["bottom"], "params.caption.bottom", minimum=0)
    if "position" in caption:
        pos = caption["position"]
        if not isinstance(pos, str):
            raise VisualStyleParamsInvalid("params.caption.position must be a string")
        cleaned_pos = pos.strip().lower()
        if cleaned_pos not in CAPTION_POSITION_ALIASES:
            raise VisualStyleParamsInvalid(
                f"params.caption.position must be one of {sorted(CAPTION_POSITION_ALIASES.keys())}"
            )
        out["position"] = CAPTION_POSITION_ALIASES[cleaned_pos]
    if "font_family" in caption:
        fam = caption["font_family"]
        if not isinstance(fam, str):
            raise VisualStyleParamsInvalid("params.caption.font_family must be a string")
        cleaned_fam = fam.strip().lower()
        if cleaned_fam not in CAPTION_FONT_FAMILIES:
            raise VisualStyleParamsInvalid(
                f"params.caption.font_family must be one of {sorted(CAPTION_FONT_FAMILIES)}"
            )
        out["font_family"] = cleaned_fam
    if "style_kind" in caption:
        sk = caption["style_kind"]
        if not isinstance(sk, str):
            raise VisualStyleParamsInvalid("params.caption.style_kind must be a string")
        cleaned_sk = sk.strip().lower()
        if cleaned_sk not in CAPTION_STYLE_KIND_ALIASES:
            raise VisualStyleParamsInvalid(
                f"params.caption.style_kind must be one of {sorted(CAPTION_STYLE_KIND_ALIASES.keys())}"
            )
        out["style_kind"] = CAPTION_STYLE_KIND_ALIASES[cleaned_sk]
    if not out:
        raise VisualStyleParamsInvalid("params.caption needs at least one of font_size/bottom/position/font_family/style_kind")
    return out


def _clean_palette(value: object) -> dict:
    palette = _object(value, "palette")
    allowed = ("caption_text", "caption_box", "accent")
    _unknown("params.palette", palette, allowed)
    out: dict[str, str] = {}
    for key in allowed:
        if key in palette:
            color = palette[key]
            if not isinstance(color, str) or not _HEX_COLOR.match(color):
                raise VisualStyleParamsInvalid(f"params.palette.{key} must be a hex color like #RRGGBB or #RRGGBBAA")
            out[key] = color
    if not out:
        raise VisualStyleParamsInvalid("params.palette needs at least one color")
    return out


def _clean_voice(value: object) -> dict:
    voice = _object(value, "voice")
    _unknown("params.voice", voice, ("model",))
    model = voice.get("model")
    if not isinstance(model, str) or not model.strip() or len(model.strip()) > MAX_VOICE_MODEL_LENGTH:
        raise VisualStyleParamsInvalid(f"params.voice.model must be a non-empty string of at most {MAX_VOICE_MODEL_LENGTH} characters")
    return {"model": model.strip()}


def _clean_extra(value: object) -> dict:
    extra = _object(value, "extra")
    if len(extra) > MAX_EXTRA_KEYS:
        raise VisualStyleParamsInvalid(f"params.extra accepts at most {MAX_EXTRA_KEYS} keys")
    return {str(key): val for key, val in extra.items()}


_CLEANERS = {
    "motion": _clean_motion,
    "music": _clean_music,
    "transition": _clean_transition,
    "caption": _clean_caption,
    "palette": _clean_palette,
    "voice": _clean_voice,
    "extra": _clean_extra,
}


def clean_params(raw: object) -> dict[str, Any]:
    """Valida os parâmetros conhecidos e preserva `extra` como extensão livre.

    Devolve uma cópia profunda: o agregado imutável não compartilha estrutura mutável com o
    chamador. Erro com a chave ofensora; nenhuma chave é silenciosamente ignorada.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise VisualStyleParamsInvalid("params must be an object")
    _unknown("params", raw, KNOWN_PARAMS)
    out: dict[str, Any] = {}
    for key in KNOWN_PARAMS:
        if key in raw:
            out[key] = _CLEANERS[key](raw[key])
    return copy.deepcopy(out)


# ---------- F05.T01: patch tipado (allowlist, herdar, reset, lista substitui) ----------

# Allowlist do patch: os mesmos grupos de `params` e, dentro de cada grupo, só as chaves que o
# render entende. `()` = grupo de valor inteiro (lista); `None` = bag aberto (`extra`).
PATCH_GROUP_FIELDS: Mapping[str, tuple[str, ...] | None] = MappingProxyType({
    "motion": (),
    "music": ("bpm", "seed"),
    "transition": ("kind", "duration_ticks"),
    "caption": ("font_size", "bottom", "position", "font_family", "style_kind"),
    "palette": ("caption_text", "caption_box", "accent"),
    "voice": ("model",),
    "extra": None,
})
# `motion` é um valor inteiro: a lista do patch substitui a de baixo, nunca concatena.
PATCH_LIST_GROUPS = frozenset({"motion"})


def _patch_int(value: object, where: str, *, minimum: int | None = None,
               maximum: int | None = None) -> int:
    try:
        return _int(value, where, minimum=minimum, maximum=maximum)
    except VisualStyleParamsInvalid as exc:  # o erro do patch tem o tipo do patch
        raise StylePatchInvalid(str(exc)) from None


def _patch_motion(value: object, where: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise StylePatchInvalid(f"{where}.motion must be a list of motions")
    motions: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in MOTIONS:
            raise StylePatchInvalid(f"{where}.motion item must be one of {sorted(MOTIONS)}")
        if item not in motions:
            motions.append(item)
    if not motions:
        raise StylePatchInvalid(f"{where}.motion cannot be empty")
    return tuple(motions)


def _patch_field(group: str, key: str, value: object, where: str) -> Any:
    """Valida **um** campo do patch, sem as regras que dependem das outras camadas."""
    path = f"{where}.{group}.{key}"
    if group == "music":
        if key == "bpm":
            return _patch_int(value, path, minimum=MIN_BPM, maximum=MAX_BPM)
        return _patch_int(value, path, minimum=_MIN_SEED, maximum=_MAX_SEED)
    if group == "transition":
        if key == "kind":
            if not isinstance(value, str) or value not in TRANSITION_KINDS:
                raise StylePatchInvalid(
                    f"{path} must be one of {sorted(TRANSITION_KINDS)}")
            return value
        return _patch_int(value, path, minimum=0)
    if group == "caption":
        if key == "font_size":
            return _patch_int(value, path, minimum=8, maximum=400)
        if key == "bottom":
            return _patch_int(value, path, minimum=0)
        if key == "position":
            if not isinstance(value, str):
                raise StylePatchInvalid(f"{path} must be a string")
            cleaned_pos = value.strip().lower()
            if cleaned_pos not in CAPTION_POSITION_ALIASES:
                raise StylePatchInvalid(
                    f"{path} must be one of {sorted(CAPTION_POSITION_ALIASES.keys())}"
                )
            return CAPTION_POSITION_ALIASES[cleaned_pos]
        if key == "font_family":
            if not isinstance(value, str):
                raise StylePatchInvalid(f"{path} must be a string")
            cleaned_fam = value.strip().lower()
            if cleaned_fam not in CAPTION_FONT_FAMILIES:
                raise StylePatchInvalid(
                    f"{path} must be one of {sorted(CAPTION_FONT_FAMILIES)}"
                )
            return cleaned_fam
        if key == "style_kind":
            if not isinstance(value, str):
                raise StylePatchInvalid(f"{path} must be a string")
            cleaned_sk = value.strip().lower()
            if cleaned_sk not in CAPTION_STYLE_KIND_ALIASES:
                raise StylePatchInvalid(
                    f"{path} must be one of {sorted(CAPTION_STYLE_KIND_ALIASES.keys())}"
                )
            return CAPTION_STYLE_KIND_ALIASES[cleaned_sk]
    if group == "palette":
        if not isinstance(value, str) or not _HEX_COLOR.match(value):
            raise StylePatchInvalid(
                f"{path} must be a hex color like #RRGGBB or #RRGGBBAA")
        return value
    if group == "voice" and key == "model":
        if not isinstance(value, str) or not value.strip() \
                or len(value.strip()) > MAX_VOICE_MODEL_LENGTH:
            raise StylePatchInvalid(
                f"{path} must be a non-empty string of at most "
                f"{MAX_VOICE_MODEL_LENGTH} characters")
        return value.strip()
    raise StylePatchInvalid(f"unknown {path} field")  # allowlist desalinhada: falha alto


def _patch_map(group: str, value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StylePatchInvalid(f"{where}.{group} must be an object")
    if not value:
        # `{}` seria idêntico a "herdar"; a intenção se escreve omitindo o grupo ou com null.
        raise StylePatchInvalid(
            f"{where}.{group} must declare at least one key or use null to reset the group")
    allowed = PATCH_GROUP_FIELDS[group]
    cleaned: dict[str, Any] = {}
    if allowed is None:  # `extra`: bag aberto, sem reset por chave
        if len(value) > MAX_EXTRA_KEYS:
            raise StylePatchInvalid(
                f"{where}.{group} accepts at most {MAX_EXTRA_KEYS} keys")
        for key, item in value.items():
            if item is None:
                raise StylePatchInvalid(
                    f"{where}.{group}.{key} cannot be reset with null: it is not a resettable "
                    "field (reset the whole group instead)")
            cleaned[str(key)] = copy.deepcopy(item)
        return MappingProxyType(cleaned)
    unknown = sorted(set(value) - set(allowed), key=str)
    if unknown:
        raise StylePatchInvalid(f"unknown {where}.{group} key(s): {unknown}")
    for key, item in value.items():
        # `null` = reset explícito e documentado de um campo tipado: remove o patch daquela chave.
        cleaned[key] = None if item is None else _patch_field(group, key, item, where)
    return MappingProxyType(cleaned)


def _normalize_style_patch(raw: object, where: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise StylePatchInvalid(f"{where} must be an object of style overrides")
    unknown = sorted(set(raw) - set(KNOWN_PARAMS), key=str)
    if unknown:
        raise StylePatchInvalid(f"unknown {where} key(s): {unknown}")
    normalized: dict[str, Any] = {}
    for group in KNOWN_PARAMS:  # ordem determinística, independente da ordem do JSON
        if group not in raw:
            continue
        value = raw[group]
        if value is None:
            normalized[group] = None  # reset do grupo inteiro
        elif group in PATCH_LIST_GROUPS:
            normalized[group] = _patch_motion(value, where)
        else:
            normalized[group] = _patch_map(group, value, where)
    return normalized


def _thaw_patch(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_patch(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_patch(item) for item in value]
    return copy.deepcopy(value)


@dataclass(frozen=True)
class StylePatch:
    """Override tipado de estilo de uma camada (vídeo ou canal). Imutável, sem I/O.

    ``groups`` guarda, por grupo, ``None`` (reset do grupo), uma tupla (``motion``, valor inteiro)
    ou um mapa chave→valor onde ``None`` significa reset daquela chave. A allowlist e a semântica
    de reset vivem aqui; a mesclagem entre camadas e a validação final continuam em
    ``apply_style_patch``/``effective_config``.
    """

    groups: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "groups",
                           MappingProxyType(_normalize_style_patch(self.groups, "style patch")))

    @classmethod
    def from_mapping(cls, raw: object, *, where: str = "style patch") -> "StylePatch":
        """Entrada canônica: valida a allowlist e normaliza resets. ``None`` é patch ausente."""
        return cls(_normalize_style_patch(raw, where))

    @property
    def is_empty(self) -> bool:
        return not self.groups

    def to_mapping(self) -> dict[str, Any]:
        """Forma de transporte (JSON-ável), em cópia profunda: o patch não vaza estrutura."""
        return {group: (None if value is None else _thaw_patch(value))
                for group, value in self.groups.items()}


def normalize_style_patch(raw: object, *, where: str = "style patch") -> dict[str, Any]:
    """Valida e normaliza um patch pela allowlist do domínio devolvendo dict JSON-ável."""
    if raw is None:
        return {}
    typed = raw if isinstance(raw, StylePatch) else StylePatch.from_mapping(raw, where=where)
    return typed.to_mapping()


def apply_style_patch(base: Mapping[str, Any] | None,
                      patch: StylePatch | Mapping[str, Any] | None) -> dict[str, Any]:
    """Mescla o patch sobre **uma** camada de base e valida o resultado com ``clean_params``.

    A base é o que as camadas de baixo já resolveram (ex.: `effective_config.AUDIOVISUAL_DEFAULTS`
    ou o `params` do estilo). Ausência herda, ``null`` remove o patch (chave ou grupo) e a lista
    substitui. O resultado passa pelo **mesmo** `clean_params` do estilo — a mesclagem nunca é
    mais frouxa que a biblioteca. Puro.
    """
    typed = patch if isinstance(patch, StylePatch) else StylePatch.from_mapping(patch)
    result = clean_params(dict(base) if base else {})
    for group, declared in typed.groups.items():
        if declared is None:
            result.pop(group, None)
            continue
        if group in PATCH_LIST_GROUPS:
            result[group] = list(declared)
            continue
        merged = dict(result.get(group) or {})
        for key, value in declared.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = copy.deepcopy(value)
        if merged:
            result[group] = merged
        else:
            result.pop(group, None)
    return clean_params(result)


@dataclass(frozen=True)
class VisualStyle:
    """Estilo visual versionado. Nunca carrega o objeto do canal: só os parâmetros."""

    id: str
    name: str
    organization_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        check_id(self.id)
        if self.organization_id is not None:
            check_id(self.organization_id)
        object.__setattr__(self, "name", validate_name(self.name))
        object.__setattr__(self, "params", clean_params(self.params))
        object.__setattr__(self, "version", validate_version(self.version))
        if not isinstance(self.archived, bool):
            raise VisualStyleParamsInvalid("archived must be a boolean")


@dataclass(frozen=True)
class VisualStyleArchive:
    """Resultado do arquivamento de um estilo (VS-05c): o estilo e a limpeza **medida** dos vínculos.

    ``cleared_links`` é a soma real (rowcount dos UPDATE) dos canais (``channel_profiles.style_id``)
    e vídeos (``videos.style_id``) que apontavam para o estilo e voltaram a NULL — o canal ao padrão
    do estúdio, o vídeo a herdar do canal. Nunca estimado: é o que o banco de fato limpou.
    """

    style: VisualStyle
    cleared_links: int


@dataclass(frozen=True)
class ResolvedStyle:
    """Estilo **resolvido** para o render: a referência versionada **e** os parâmetros aplicáveis.

    É a ponte pura entre o agregado ``VisualStyle`` e o executor: o ``snapshot`` (chave +
    versão) é o que o ``RenderPlan`` grava (R4/RP-016) e ``motion``/``music`` são o que o
    render **de fato** honra hoje. O tipo não carrega o objeto inteiro (nem nome/`extra`),
    só o que o render consome — o plano referencia, não copia.

    ``transition`` é **aplicada** (Plano 2 / F05.T03): quando o estilo declara transição fade
    com duração positiva, o builder projeta ``Transition(kind="fade", duration_ticks=...)``
    nos shots visuais base que possuem próximo vizinho. ``none`` ou ausente mantém o fade
    legado sem alteração (byte-a-byte).

    ``motion`` vazio significa "sem ciclo declarado": o executor cai no seu próprio ciclo
    de Ken Burns. ``music`` vazio (ou parcial) significa "usar o default do plano" para as
    chaves ausentes (bpm 122 / seed 7).

    ``caption`` (tamanho/posição da legenda) e ``palette`` (cores do overlay) são **aplicados**
    pelo executor (VS-04): o adapter parte do layout/cores atuais como default e sobrepõe só as
    chaves declaradas aqui. Vazio = comportamento default de sempre (byte-a-byte).

    ``voice`` (``params.voice.model``) é **aplicada** (VS-06): quando o estilo declara uma voz,
    ela vence o projeto (``STUDIO_VOICE``/``Project.config.voice``) e o default. A precedência
    final é **estilo > projeto > default**; ``PIPER_VOICE`` é só fallback de deployment/teste.
    Quem resolve o modelo efetivo é a composição (``composition._voice_for_video``), que devolve
    um ``Voice`` com esse modelo — a **mesma** identidade que a síntese usa e o ledger/cache
    registram, fechando a divergência entre a voz que fala e a voz que é cobrada/cacheada.
    """

    snapshot: StyleSnapshot
    motion: tuple[Motion, ...] = ()
    music: dict[str, int] = field(default_factory=dict)
    transition: dict[str, Any] = field(default_factory=dict)
    caption: dict[str, Any] = field(default_factory=dict)
    palette: dict[str, Any] = field(default_factory=dict)
    voice: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        snapshot: StyleSnapshot | None = None,
        motion: tuple[Motion, ...] = (),
        music: dict[str, int] | None = None,
        transition: dict[str, Any] | None = None,
        caption: dict[str, Any] | None = None,
        palette: dict[str, Any] | None = None,
        voice: dict[str, Any] | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        version: int | None = None,
    ) -> None:
        if snapshot is None:
            snapshot = StyleSnapshot(style_id=id or "default", version=version or 1)
        object.__setattr__(self, "snapshot", snapshot)
        object.__setattr__(self, "motion", motion)
        object.__setattr__(self, "music", music or {})
        object.__setattr__(self, "transition", transition or {})
        object.__setattr__(self, "caption", caption or {})
        object.__setattr__(self, "palette", palette or {})
        object.__setattr__(self, "voice", voice or {})


def effective_style_id(channel_style_id: str | None, video_style_id: str | None) -> str | None:
    """Qual estilo vence: **o canal herda, o vídeo pode sobrepor** (VS-02b/VS-05b).

    Puro e sem I/O: o override do vídeo tem precedência sobre o do canal; sem override, vale o
    do canal e, sem nenhum dos dois, ``None`` (o render cai no padrão do estúdio). É a mesma
    precedência do ``resolve_style``, aqui sobre as **chaves** — o suficiente para a tela dizer
    de quem um vídeo herda sem carregar os parâmetros.
    """
    return video_style_id if video_style_id is not None else channel_style_id


def resolve_style(profile: ChannelProfile | None, style: VisualStyle | None,
                  override: VisualStyle | None = None) -> ResolvedStyle | None:
    """Decide o estilo efetivo de um render a partir do estilo do canal (``style``) e do
    ``override`` do vídeo, quando existir.

    Puro (sem I/O, sem banco): a leitura do ``VisualStyle`` e do override do vídeo mora em
    ``adapters/``/``composition.py``; aqui só se projeta o agregado já carregado no que o
    render consome. Sem estilo (``style`` e ``override`` ausentes), devolve ``None`` — o
    renderer cai no bundle neutro (``studio-default@1``).

    O ``override`` (o "pode sobrepor" do vídeo, VS-05) tem precedência sobre o do canal; o
    parâmetro já fica pronto mesmo que a chamada ainda não use override. ``profile`` entra
    para manter a resolução ancorada no canal (o snapshot sai do estilo efetivo, não do
    perfil) e é o ponto natural de precedências futuras por canal.

    Defesa em profundidade (VS-05c): um estilo **arquivado** nunca dirige um render. A resolução
    o trata como ausente — um override arquivado cai no estilo do canal e um estilo de canal
    arquivado cai no neutro. Só assim um vínculo que escape (canal/vídeo apontando para um estilo
    arquivado) não volta a valer no render.
    """
    chosen = override if (override is not None and not override.archived) else style
    if chosen is None or chosen.archived:
        return None
    params = chosen.params
    return ResolvedStyle(
        snapshot=StyleSnapshot(source="channel", style_id=chosen.id, version=chosen.version),
        motion=tuple(params.get("motion", ())),
        music=dict(params.get("music", {})),
        transition=dict(params.get("transition", {})),
        caption=dict(params.get("caption", {})),
        palette=dict(params.get("palette", {})),
        voice=dict(params.get("voice", {})),
    )


# ---------- W3.2: presets por nicho (catálogo puro, só grupos aplicáveis) ----------

# Presets de partida — o "conforme o uso vamos melhorando" com um ponto de partida honesto.
# Cada preset declara **apenas** grupos de `APPLIED_GROUPS`: nada aqui promete efeito que o
# render não faça. Não são estilos persistidos: quem cria um `VisualStyle` copia os `params`
# (via ``preset_params``) e a biblioteca segue sendo a fonte versionada.
PRESETS: Mapping[str, dict[str, Any]] = MappingProxyType({
    # Ritmo lento, âncora dourada, legenda discreta — o tom de documentário.
    "documentario": {
        "motion": ["zoom_in", "pan_right"],
        "music": {"bpm": 96, "seed": 7},
        "caption": {"font_size": 52, "bottom": 1520},
        "palette": {"caption_text": "#F2F2F2", "caption_box": "#000000A5", "accent": "#D4AF37"},
    },
    # Câmera parada e legenda grande, para leitura rápida de manchete.
    "noticia": {
        "motion": ["none"],
        "music": {"bpm": 128, "seed": 11},
        "caption": {"font_size": 62, "bottom": 1580},
        "palette": {"caption_text": "#FFFFFF", "caption_box": "#0B0B11CC", "accent": "#E11D48"},
    },
    # Alterna zoom in/out; sotaque na paleta de marca do estúdio.
    "curiosidades": {
        "motion": ["zoom_in", "zoom_out"],
        "music": {"bpm": 122, "seed": 7},
        "caption": {"font_size": 58, "bottom": 1560},
        "palette": {"caption_text": "#FFFFFF", "caption_box": "#1A0B2ECC", "accent": "#FF008C"},
    },
})


def preset_params(preset_id: str) -> dict[str, Any]:
    """Parâmetros de um preset, validados pelo **mesmo** ``clean_params`` do estilo.

    Devolve uma cópia profunda (o chamador não muta o catálogo do módulo) já na forma canônica do
    estilo — a mesma validação da biblioteca, nunca uma frouxa. Preset desconhecido é recusado
    com ``VisualStyleParamsInvalid``: quem chama decide o fallback (manter o estilo atual), nunca
    um preset inventado.
    """
    try:
        raw = PRESETS[preset_id]
    except (KeyError, TypeError):
        raise VisualStyleParamsInvalid(f"unknown preset {preset_id!r}") from None
    return clean_params(copy.deepcopy(dict(raw)))
