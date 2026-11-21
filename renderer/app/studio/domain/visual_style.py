"""Domínio do estilo visual (biblioteca de estilos compartilhada). Puro: sem I/O, sem banco.

Um **estilo** é a identidade de aparência e som que o produtor configura uma vez e aplica a
vários canais (`ChannelProfile.style_id`). O estilo é imutável e versionado: cada leitura/
atualização carrega a `version`, e o repositório incrementa de forma otimista, gravando um
snapshot auditável por versão — o mesmo padrão de `channel_profile_revisions`.

`params` é o retrato aplicável pelo render. Só entram os parâmetros que o render **de fato**
entende (motion · music · transition · caption · palette · voice). O que o render ainda não
aplica vai em `extra` — versionado e carregado desde o dia 1, ignorado pelo renderer até o
knob existir. É o "conforme o uso vamos melhorando" com contrato, não com promessa.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime
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
CREATABLE_FIELDS = ("organization_id", "params", "archived")
UPDATABLE_FIELDS = ("name", "params", "archived")


class VisualStyleError(Exception):
    """Erro base do estilo visual."""


class VisualStyleNameInvalid(VisualStyleError, ValueError):
    """Nome vazio, longo demais ou de tipo inválido."""


class VisualStyleParamsInvalid(VisualStyleError, ValueError):
    """Parâmetro com chave desconhecida, tipo ou valor inválido."""


class VisualStyleVersionInvalid(VisualStyleError, ValueError):
    """Versão inválida (precisa ser inteiro >= 1)."""


class VisualStyleVersionConflict(VisualStyleError, ValueError):
    """A versão informada não é a atual: outra atualização venceu a corrida."""


class DuplicateVisualStyle(VisualStyleError, ValueError):
    """Já existe um estilo ativo com este nome."""


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


def _clean_caption(value: object) -> dict:
    caption = _object(value, "caption")
    _unknown("params.caption", caption, ("font_size", "bottom"))
    out: dict[str, int] = {}
    if "font_size" in caption:
        out["font_size"] = _int(caption["font_size"], "params.caption.font_size", minimum=8, maximum=400)
    if "bottom" in caption:
        out["bottom"] = _int(caption["bottom"], "params.caption.bottom", minimum=0)
    if not out:
        raise VisualStyleParamsInvalid("params.caption needs at least one of font_size/bottom")
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
class ResolvedStyle:
    """Estilo **resolvido** para o render: a referência versionada **e** os parâmetros aplicáveis.

    É a ponte pura entre o agregado ``VisualStyle`` e o executor: o ``snapshot`` (chave +
    versão) é o que o ``RenderPlan`` grava (R4/RP-016) e ``motion``/``music`` são o que o
    render **de fato** honra hoje. O tipo não carrega o objeto inteiro (nem nome/`extra`),
    só o que o render consome — o plano referencia, não copia.

    ``transition`` é **carregada** desde já, por fidelidade ao estilo, mas **ainda não é
    aplicada**: o builder/compilador/executor não leem transição hoje (o plano a representa
    como ``Transition`` em ``Shot.transition``, que ninguém preenche). Ligá-la é fatia
    futura; aqui ela fica só carregada, sem fingir suporte.

    ``motion`` vazio significa "sem ciclo declarado": o executor cai no seu próprio ciclo
    de Ken Burns. ``music`` vazio (ou parcial) significa "usar o default do plano" para as
    chaves ausentes (bpm 122 / seed 7).
    """

    snapshot: StyleSnapshot
    motion: tuple[Motion, ...] = ()
    music: dict[str, int] = field(default_factory=dict)
    transition: dict[str, Any] = field(default_factory=dict)


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
    """
    chosen = override if override is not None else style
    if chosen is None:
        return None
    params = chosen.params
    return ResolvedStyle(
        snapshot=StyleSnapshot(source="channel", style_id=chosen.id, version=chosen.version),
        motion=tuple(params.get("motion", ())),
        music=dict(params.get("music", {})),
        transition=dict(params.get("transition", {})),
    )
