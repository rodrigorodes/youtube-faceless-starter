"""Configuração efetiva de produção (F03.T01): tipada, versionada e com proveniência. Puro.

A configuração efetiva é o retrato **criativo** de um run, resolvido **antes** de qualquer efeito
(ADR fs31-003) e consumido igual pela voz e pelo render. Aqui só entram valores criativos e
referências (``style_id`` + ``version``); autorização, grant, token, chave, saldo, preço e
disponibilidade continuam **dinâmicos** por operação e nunca aparecem neste documento.

## Precedência (duas etapas, explícitas)

1. **Seleção de estilo inteiro** — ``video.style_id > channel.style_id > default``. Estilo
   arquivado ou inexistente conta como ausente (VS-05c): um vínculo que escape nunca dirige o
   render; se o estilo do vídeo não vale, o do canal decide.
2. **Patches** denunciados por camada — ``video override > channel override > estilo selecionado >
   engine default``, resolvidos **por chave**. O patch é tipado (``visual_style.StylePatch``,
   F05.T01): allowlist de grupos/campos com erro na chave ofensora, ``null`` só onde há reset
   documentado (grupo inteiro ou campo tipado) e a entrada canônica é o ``StylePatch`` já
   validado (o mapping cru é normalizado por ele, sem regra duplicada). Um ``None`` no patch é
   *reset*: remove aquele override e a chave volta à camada de baixo (não força o default do
   motor). Listas (``motion``, ``pillars``) **substituem**; mapas (``music``, ``caption``,
   ``palette``, ``voice``, ``extra``, ``transition``) são mesclados chave a chave. O resultado
   final é validado pelo **mesmo** ``clean_params`` do estilo visual — a configuração efetiva
   nunca é mais frouxa que a biblioteca.

## Documento canônico

``to_document()`` devolve o documento na forma documentada (ADR/arquitetura): ``schema_version``
explícito, ``project_id``/``video_id``, referências de canal e estilo, ``editorial``,
``audiovisual``, ``provider_policy`` e ``provenance``. ``canonical_document()`` ordena as chaves em
todos os níveis e normaliza números (float integral vira inteiro; ``-0.0`` vira ``0``; ``NaN``/
``Infinity`` são recusados), então ``canonical_json()``/``content_hash`` são determinísticos: mesma
entrada, mesma configuração, mesmo hash.

A proveniência é um mapa plano, com a mesma linguagem do documento: ``"style"`` diz de onde veio a
seleção de estilo, ``"provider_policy"`` de onde veio a política, ``"editorial.<campo>"`` e
``"audiovisual.<grupo>[.<chave>]"`` dizem de onde veio **cada valor materializado**. Os valores são
``video``/``channel``/``style``/``engine_default`` e ``declared`` (política declarada pela
aplicação, F06 — não é camada criativa).

## Defaults do motor, explícitos

Sem estilo e sem patch, o comportamento legado é preservado e o documento o diz com todas as
letras: editorial ``pt-BR``/``""``/``()``/``""``/``60``/``""`` (os mesmos defaults de
``ChannelProfile``), ``music`` 122/7 (``DEFAULT_MUSIC_BPM``/``DEFAULT_MUSIC_SEED``), ``transition``
``none``/0, e ``motion``/``caption``/``palette``/``voice``/``extra`` vazios — vazio signifca "o
motor decide" (ciclo de Ken Burns, layout e voz do projeto), exatamente como hoje.

Este módulo não persiste nada (F03.T02) nem faz I/O: ele recebe o vídeo, o perfil já carregado e um
``lookup_style`` injetado, e devolve o valor imutável.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from .channel import (MAX_AUDIENCE_LENGTH, MAX_CTA_LENGTH, MAX_DURATION_S, MAX_NARRATIVE_LENGTH,
                      MAX_PILLARS, ChannelProfile)
from .contracts import Video
from .ids import InvalidId, check_id
from .provider import EconomicProfile
from .visual_style import (DEFAULT_MUSIC_BPM, DEFAULT_MUSIC_SEED, MOTIONS, PATCH_LIST_GROUPS,
                           StylePatch, VisualStyle, VisualStyleError, VisualStyleParamsInvalid,
                           clean_params)

SCHEMA_VERSION = 1
PROVIDER_POLICY_VERSION = 1

EDITORIAL_FIELDS = ("language", "audience", "pillars", "narrative", "duration_s", "cta")
AUDIOVISUAL_GROUPS = ("voice", "motion", "music", "transition", "caption", "palette", "extra")
_LIST_GROUPS = PATCH_LIST_GROUPS
_REFERENCE_FIELDS = ("style", "provider_policy")

EDITORIAL_DEFAULTS: Mapping[str, Any] = MappingProxyType({
    "language": "pt-BR",
    "audience": "",
    "pillars": (),
    "narrative": "",
    "duration_s": 60,
    "cta": "",
})

# Defaults do motor para os parâmetros de estilo. Vazio NÃO é "sem valor": é "o motor decide"
# (ciclo de motion, layout de legenda, cores do overlay e voz do projeto) — por isso só music e
# transition, que têm valor explícito hoje, aparecem materializados.
AUDIOVISUAL_DEFAULTS: Mapping[str, Mapping[str, Any]] = MappingProxyType({
    "music": MappingProxyType({"bpm": DEFAULT_MUSIC_BPM, "seed": DEFAULT_MUSIC_SEED}),
    "transition": MappingProxyType({"kind": "none", "duration_ticks": 0}),
})

# Chaves que cheiram a credencial/efeito operacional nunca entram na configuração criativa, nem
# pela biblioteca de estilos nem por patch: a configuração efetiva é congelável e auditável.
_FORBIDDEN_KEY_PARTS = ("token", "secret", "password", "authoriz", "balance", "saldo",
                        "credential", "api_key", "apikey", "grant")
_MAX_CANONICAL_INT = 2 ** 53


class EffectiveConfigError(ValueError):
    """Erro base da configuração efetiva."""


class EffectiveConfigInvalid(EffectiveConfigError):
    """Payload inválido: camada desconhecida, valor fora do contrato ou inconsistência de origem."""


class UnsupportedConfigSchema(EffectiveConfigError):
    """``schema_version`` do documento não é a suportada por este contrato."""


class ConfigSource(str, Enum):
    """De onde veio um valor da configuração (proveniência)."""

    VIDEO = "video"                # vídeo: seleção de estilo ou override do vídeo
    CHANNEL = "channel"            # canal: seleção de estilo, override do canal ou editorial
    STYLE = "style"                # estilo selecionado (parâmetros da biblioteca)
    ENGINE_DEFAULT = "engine_default"
    DECLARED = "declared"          # política declarada pela aplicação (F06), não é camada criativa


@dataclass(frozen=True)
class ConfigReference:
    """Referência imutável por chave + versão (nunca o objeto inteiro)."""

    id: str
    version: int

    def __post_init__(self) -> None:
        _check_id(self.id, "reference id")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise EffectiveConfigInvalid("reference version must be an integer >= 1")

    def to_document(self) -> dict:
        return {"id": self.id, "version": self.version}


# ---------- validação e canonicalização puras ----------


def _check_id(value: object, where: str) -> str:
    try:
        return check_id(value)  # type: ignore[arg-type]
    except InvalidId:
        raise EffectiveConfigInvalid(f"{where} must be a 32-char hexadecimal id") from None


def _looks_secret(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return any(part in normalized for part in _FORBIDDEN_KEY_PARTS)


def _assert_no_secrets(node: object, where: str) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if _looks_secret(key):
                raise EffectiveConfigInvalid(
                    f"{where} cannot carry credentials, keys, balance or authorization ({key!r})")
            _assert_no_secrets(value, f"{where}.{key}")
    elif isinstance(node, (list, tuple)):
        for item in node:
            _assert_no_secrets(item, where)


def _canonical_value(value: object, where: str) -> Any:
    """Forma canônica: chaves ordenadas, números normalizados e só tipos JSON."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EffectiveConfigInvalid(f"{where} must be a finite number")
        if value.is_integer() and abs(value) <= _MAX_CANONICAL_INT:
            return int(value)  # -0.0 → 0; 1.0 → 1: a mesma configuração tem um só hash
        return value
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item, f"{where}.{key}")
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item, f"{where}[{index}]") for index, item in enumerate(value)]
    raise EffectiveConfigInvalid(
        f"{where} must be a JSON value (got {type(value).__name__})")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _text(value: object, where: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise EffectiveConfigInvalid(f"{where} must be a string")
    if len(value) > maximum:
        raise EffectiveConfigInvalid(f"{where} must be at most {maximum} characters")
    return value


def _mapping(value: object, where: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise EffectiveConfigInvalid(f"{where} must be an object")
    return value


def _sequence(value: object, where: str) -> list:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise EffectiveConfigInvalid(f"{where} must be a list")
    return list(value)


def _leaf_paths(section: Mapping, prefix: str) -> set[str]:
    """Caminhos de todo valor criativo materializado, **por chave declarada** (não recursivo).

    Um grupo vazio também é um valor materializado ("o motor decide") e ganha seu caminho; um
    valor aninhado em ``extra`` é um único valor e conta como a chave de topo que o declarou.
    """
    found: set[str] = set()
    for key, value in section.items():
        path = f"{prefix}.{key}"
        if isinstance(value, Mapping) and value:
            found |= {f"{path}.{nested}" for nested in value}
        else:
            found.add(path)
    return found


def _exact_keys(mapping: Mapping, allowed: tuple[str, ...], where: str) -> None:
    unknown = sorted(set(mapping) - set(allowed), key=str)
    if unknown:
        raise EffectiveConfigInvalid(f"unknown {where} key(s): {unknown}")


def _validated_patch(patch: object, where: str) -> dict[str, Any]:
    """Normaliza o patch pela allowlist tipada de `visual_style` (F05.T01), sem duplicar regra."""
    if isinstance(patch, StylePatch):
        return patch.to_mapping()
    try:
        return StylePatch.from_mapping(patch, where=where).to_mapping()
    except VisualStyleError as exc:
        raise EffectiveConfigInvalid(str(exc)) from None


# ---------- o valor ----------


@dataclass(frozen=True)
class EffectiveConfig:
    """Retrato criativo congelado de um run: editorial, audiovisual, referências e proveniência."""

    project_id: str
    video_id: str
    channel_profile: ConfigReference | None = None
    style: ConfigReference | None = None
    language: str = EDITORIAL_DEFAULTS["language"]
    audience: str = EDITORIAL_DEFAULTS["audience"]
    pillars: tuple[str, ...] = ()
    narrative: str = EDITORIAL_DEFAULTS["narrative"]
    duration_s: int = EDITORIAL_DEFAULTS["duration_s"]
    cta: str = EDITORIAL_DEFAULTS["cta"]
    motion: tuple[str, ...] = ()
    music: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    transition: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    caption: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    palette: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    voice: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    extra: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    provider_profile: EconomicProfile = EconomicProfile.BALANCED
    provider_policy_version: int = PROVIDER_POLICY_VERSION
    schema_version: int = SCHEMA_VERSION
    provenance: Mapping[str, str] = field(default_factory=dict)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) \
                or self.schema_version != SCHEMA_VERSION:
            raise UnsupportedConfigSchema(
                f"unsupported effective config schema_version {self.schema_version!r}; "
                f"expected {SCHEMA_VERSION}")
        object.__setattr__(self, "project_id", _check_id(self.project_id, "project_id"))
        object.__setattr__(self, "video_id", _check_id(self.video_id, "video_id"))
        for name in ("channel_profile", "style"):
            reference = getattr(self, name)
            if reference is not None and not isinstance(reference, ConfigReference):
                raise EffectiveConfigInvalid(f"{name} must be a ConfigReference or null")
        self._validate_editorial()
        self._validate_audiovisual()
        self._validate_provider_policy()
        self._validate_provenance()
        # Defesa final: o documento inteiro é JSON canônico, não carrega segredo e a
        # proveniência cobre exatamente os valores criativos materializados.
        document = self._document()
        _canonical_value(document, "effective_config")
        _assert_no_secrets(document, "effective_config")
        expected = {"style", "provider_policy"}
        for section in ("editorial", "audiovisual"):
            expected |= _leaf_paths(document[section], section)
        missing = expected - set(self.provenance)
        orphan = set(self.provenance) - expected
        if missing or orphan:
            raise EffectiveConfigInvalid(
                "provenance does not match the document: missing "
                f"{sorted(missing)}, unknown {sorted(map(str, orphan))}")

    # -- validação ---------------------------------------------------------

    def _validate_editorial(self) -> None:
        object.__setattr__(self, "language", _text(self.language, "language", 20))
        if len(self.language.strip()) < 2:
            raise EffectiveConfigInvalid("language must be at least 2 characters")
        object.__setattr__(self, "audience",
                           _text(self.audience, "audience", MAX_AUDIENCE_LENGTH))
        object.__setattr__(self, "narrative",
                           _text(self.narrative, "narrative", MAX_NARRATIVE_LENGTH))
        object.__setattr__(self, "cta", _text(self.cta, "cta", MAX_CTA_LENGTH))
        if isinstance(self.duration_s, bool) or not isinstance(self.duration_s, int) \
                or not 1 <= self.duration_s <= MAX_DURATION_S:
            raise EffectiveConfigInvalid(
                f"duration_s must be an integer between 1 and {MAX_DURATION_S}")
        pillars = tuple(_text(item, "pillars item", 500) for item in self.pillars) \
            if isinstance(self.pillars, (list, tuple)) else None
        if pillars is None:
            raise EffectiveConfigInvalid("pillars must be a list of strings")
        if len(pillars) > MAX_PILLARS:
            raise EffectiveConfigInvalid(f"pillars accepts at most {MAX_PILLARS} items")
        object.__setattr__(self, "pillars", pillars)

    def _validate_audiovisual(self) -> None:
        raw: dict[str, Any] = {}
        for group in AUDIOVISUAL_GROUPS:
            value = getattr(self, group)
            if group in _LIST_GROUPS:
                items = tuple(value or ())
                for item in items:
                    if item not in MOTIONS:
                        raise EffectiveConfigInvalid(
                            f"{group} item must be one of {sorted(MOTIONS)}")
                if items:
                    raw[group] = list(items)
                object.__setattr__(self, group, items)
                continue
            values = dict(_mapping(value or {}, group))
            if values:
                raw[group] = values
        try:
            cleaned = clean_params(raw)
        except VisualStyleParamsInvalid as exc:
            raise EffectiveConfigInvalid(str(exc)) from None
        for group in AUDIOVISUAL_GROUPS:
            if group in _LIST_GROUPS:
                object.__setattr__(self, group, tuple(cleaned.get(group, ())))
            else:
                object.__setattr__(self, group, _freeze(cleaned.get(group, {})))

    def _validate_provider_policy(self) -> None:
        if not isinstance(self.provider_profile, EconomicProfile):
            try:
                object.__setattr__(self, "provider_profile",
                                   EconomicProfile(self.provider_profile))
            except ValueError:
                raise EffectiveConfigInvalid(
                    f"unknown economic profile {self.provider_profile!r}") from None
        if isinstance(self.provider_policy_version, bool) \
                or not isinstance(self.provider_policy_version, int) \
                or self.provider_policy_version < 1:
            raise EffectiveConfigInvalid("provider policy version must be an integer >= 1")

    def _validate_provenance(self) -> None:
        provenance = _mapping(self.provenance, "provenance")
        known = {source.value for source in ConfigSource}
        unknown = {key: value for key, value in provenance.items()
                   if not isinstance(value, str) or value not in known}
        if unknown:
            raise EffectiveConfigInvalid(
                f"unknown provenance source(s): {sorted(map(str, unknown))}")
        object.__setattr__(self, "provenance",
                           MappingProxyType({str(key): value
                                             for key, value in provenance.items()}))

    # -- documento ---------------------------------------------------------

    def _document(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "video_id": self.video_id,
            "channel_profile": (self.channel_profile.to_document()
                                if self.channel_profile is not None else None),
            "style": self.style.to_document() if self.style is not None else None,
            "editorial": {
                "language": self.language,
                "audience": self.audience,
                "pillars": list(self.pillars),
                "narrative": self.narrative,
                "duration_s": self.duration_s,
                "cta": self.cta,
            },
            "audiovisual": {group: _thaw(getattr(self, group)) for group in AUDIOVISUAL_GROUPS},
            "provider_policy": {
                "profile": self.provider_profile.value,
                "version": self.provider_policy_version,
            },
            "provenance": _thaw(self.provenance),
        }

    def to_document(self) -> dict[str, Any]:
        """Documento do contrato (estruturas novas: o valor imutável não é exposto por referência)."""
        return self._document()

    def canonical_document(self) -> dict[str, Any]:
        """Documento com chaves ordenadas e números normalizados — pronto para hash/comparação."""
        return _canonical_value(self._document(), "effective_config")

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_document(), sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False)

    @property
    def content_hash(self) -> str:
        """sha256 do documento canônico: a identidade determinística da configuração."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def __hash__(self) -> int:
        return int(self.content_hash, 16)

    @classmethod
    def from_document(cls, document: object) -> "EffectiveConfig":
        """Relê o documento do contrato com a mesma validação (base de F03.T02, sem persistência)."""
        doc = _mapping(document, "effective_config")
        _exact_keys(doc, ("schema_version", "project_id", "video_id", "channel_profile", "style",
                          "editorial", "audiovisual", "provider_policy", "provenance"),
                    "effective_config")
        version = doc["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version != SCHEMA_VERSION:
            raise UnsupportedConfigSchema(
                f"unsupported effective config schema_version {version!r}; expected {SCHEMA_VERSION}")
        editorial = _mapping(doc["editorial"], "editorial")
        _exact_keys(editorial, EDITORIAL_FIELDS, "editorial")
        audiovisual = _mapping(doc["audiovisual"], "audiovisual")
        _exact_keys(audiovisual, AUDIOVISUAL_GROUPS, "audiovisual")
        policy = _mapping(doc["provider_policy"], "provider_policy")
        _exact_keys(policy, ("profile", "version"), "provider_policy")
        provenance = _mapping(doc["provenance"], "provenance")
        return cls(
            project_id=doc["project_id"],
            video_id=doc["video_id"],
            channel_profile=_reference(doc["channel_profile"], "channel_profile"),
            style=_reference(doc["style"], "style"),
            language=editorial["language"],
            audience=editorial["audience"],
            pillars=tuple(_sequence(editorial["pillars"], "editorial.pillars")),
            narrative=editorial["narrative"],
            duration_s=editorial["duration_s"],
            cta=editorial["cta"],
            motion=tuple(_sequence(audiovisual["motion"], "audiovisual.motion")),
            music=dict(_mapping(audiovisual["music"], "audiovisual.music")),
            transition=dict(_mapping(audiovisual["transition"], "audiovisual.transition")),
            caption=dict(_mapping(audiovisual["caption"], "audiovisual.caption")),
            palette=dict(_mapping(audiovisual["palette"], "audiovisual.palette")),
            voice=dict(_mapping(audiovisual["voice"], "audiovisual.voice")),
            extra=dict(_mapping(audiovisual["extra"], "audiovisual.extra")),
            provider_profile=policy["profile"],
            provider_policy_version=policy["version"],
            schema_version=version,
            provenance={str(key): value for key, value in provenance.items()},
        )


def _reference(value: object, where: str) -> ConfigReference | None:
    if value is None:
        return None
    ref = _mapping(value, where)
    _exact_keys(ref, ("id", "version"), where)
    return ConfigReference(ref["id"], ref["version"])


# ---------- resolução ----------


def _load_style(lookup_style: Callable[[str], VisualStyle | None] | None,
                style_id: str | None) -> VisualStyle | None:
    """Carrega o estilo de uma seleção; ausente, arquivado ou id legado contam como ausente."""
    if style_id is None:
        return None
    if lookup_style is None:
        raise EffectiveConfigInvalid(
            "a style lookup is required to resolve a declared style selection")
    try:
        style = lookup_style(style_id)
    except InvalidId:
        return None
    if style is None:
        return None
    if not isinstance(style, VisualStyle):
        raise EffectiveConfigInvalid("the style lookup must return a VisualStyle or null")
    return None if style.archived else style


def _select_style(video: Video, channel: ChannelProfile | None,
                  lookup_style: Callable[[str], VisualStyle | None] | None
                  ) -> tuple[VisualStyle | None, ConfigSource]:
    """Etapa 1: estilo inteiro — ``video.style_id > channel.style_id > default``."""
    candidates = ((video.style_id, ConfigSource.VIDEO),
                  (channel.style_id if channel is not None else None, ConfigSource.CHANNEL))
    for style_id, source in candidates:
        style = _load_style(lookup_style, style_id)
        if style is not None:
            return style, source
    return None, ConfigSource.ENGINE_DEFAULT


def _merge_audiovisual(
    style: VisualStyle | None,
    video_patch: Mapping[str, Any],
    channel_patch: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Etapa 2: patches por chave, ascendendo ``engine < estilo < canal < vídeo``.

    Devolve os parâmetros mesclados e a proveniência de cada valor materializado.
    """
    layers: list[tuple[Mapping[str, Any], ConfigSource]] = [
        (AUDIOVISUAL_DEFAULTS, ConfigSource.ENGINE_DEFAULT)]
    if style is not None:
        layers.append((style.params, ConfigSource.STYLE))
    if channel_patch:
        layers.append((channel_patch, ConfigSource.CHANNEL))
    if video_patch:
        layers.append((video_patch, ConfigSource.VIDEO))

    merged: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    highest: dict[str, ConfigSource] = {}
    for group in AUDIOVISUAL_GROUPS:
        if group in _LIST_GROUPS:
            winner: tuple[tuple[str, ...], ConfigSource] | None = None
            for layer, source in layers:
                value = layer.get(group)
                if value is not None:
                    winner = (tuple(value), source)
            if winner is not None:
                merged[group] = list(winner[0])
                provenance[f"audiovisual.{group}"] = winner[1].value
            continue
        values: dict[str, Any] = {}
        for layer, source in layers:
            declared = layer.get(group)
            if declared is None:
                continue  # reset do grupo: não contribui nada
            if not isinstance(declared, Mapping):
                raise EffectiveConfigInvalid(f"{group} override must be an object")
            for key, value in declared.items():
                highest[group] = source
                if value is None:
                    continue  # reset da chave: a camada de baixo decide
                values[key] = value
                provenance[f"audiovisual.{group}.{key}"] = source.value
        if values:
            merged[group] = values

    try:
        cleaned = clean_params(merged)
    except VisualStyleParamsInvalid as exc:
        raise EffectiveConfigInvalid(str(exc)) from None

    for group in AUDIOVISUAL_GROUPS:
        if group in _LIST_GROUPS:
            # `motion` vazio é o ciclo do motor: o documento materializa [] e a proveniência
            # diz que ele veio do default, não de uma camada criativa.
            if f"audiovisual.{group}" not in provenance:
                provenance[f"audiovisual.{group}"] = ConfigSource.ENGINE_DEFAULT.value
            continue
        for key in cleaned.get(group, {}):
            path = f"audiovisual.{group}.{key}"
            if path not in provenance:
                provenance[path] = highest.get(group, ConfigSource.ENGINE_DEFAULT).value
        declared_keys = {f"audiovisual.{group}.{key}" for key in cleaned.get(group, {})}
        for path in [path for path in provenance if path.startswith(f"audiovisual.{group}.")]:
            if path not in declared_keys:
                provenance.pop(path)
        if not declared_keys:
            # grupo vazio = o motor decide (layout/voz/trilha): um valor materializado, com origem.
            provenance[f"audiovisual.{group}"] = \
                highest.get(group, ConfigSource.ENGINE_DEFAULT).value
    return cleaned, provenance


def resolve_effective_config(
    *,
    video: Video,
    channel: ChannelProfile | None = None,
    lookup_style: Callable[[str], VisualStyle | None] | None = None,
    video_patch: StylePatch | Mapping[str, Any] | None = None,
    channel_patch: StylePatch | Mapping[str, Any] | None = None,
    provider_profile: EconomicProfile | str | None = None,
) -> EffectiveConfig:
    """Resolve a configuração efetiva **antes** de qualquer efeito. Puro, sem I/O.

    ``video``/``channel`` são os agregados já carregados; ``lookup_style`` é a leitura injetada
    (a composição passa a biblioteca) e pode devolver ``None`` para id ausente. ``video_patch`` e
    ``channel_patch`` são os overrides tipados de estilo (``StylePatch``, F05.T01/ADR-004); o
    mapping cru também é aceito e normalizado pela mesma allowlist. ``provider_profile`` é a
    política econômica **declarada** (F06) — aqui só a referência é congelada.
    """
    if not isinstance(video, Video):
        raise EffectiveConfigInvalid("video must be a Video")
    if channel is not None and not isinstance(channel, ChannelProfile):
        raise EffectiveConfigInvalid("channel must be a ChannelProfile or null")
    if channel is not None and channel.project_id != video.project_id:
        raise EffectiveConfigInvalid("the channel profile belongs to another project")
    if channel_patch is not None and channel is None:
        raise EffectiveConfigInvalid("a channel override requires a channel profile to own it")
    video_patch = _validated_patch(video_patch, "video override")
    channel_patch = _validated_patch(channel_patch, "channel override")

    style, style_source = _select_style(video, channel, lookup_style)
    if channel is None:
        editorial = dict(EDITORIAL_DEFAULTS)
        editorial_source = ConfigSource.ENGINE_DEFAULT
    else:
        editorial = {
            "language": channel.language,
            "audience": channel.audience,
            "pillars": channel.pillars,
            "narrative": channel.narrative,
            "duration_s": channel.target_duration_s,
            "cta": channel.cta,
        }
        editorial_source = ConfigSource.CHANNEL
    audiovisual, provenance = _merge_audiovisual(style, video_patch, channel_patch)

    if provider_profile is None:
        profile = EconomicProfile.BALANCED
        policy_source = ConfigSource.ENGINE_DEFAULT
    else:
        try:
            profile = EconomicProfile(provider_profile)
        except ValueError:
            raise EffectiveConfigInvalid(
                f"unknown economic profile {provider_profile!r}") from None
        policy_source = ConfigSource.DECLARED

    return EffectiveConfig(
        project_id=video.project_id,
        video_id=video.id,
        channel_profile=(ConfigReference(channel.id, channel.version)
                         if channel is not None else None),
        style=ConfigReference(style.id, style.version) if style is not None else None,
        language=editorial["language"],
        audience=editorial["audience"],
        pillars=tuple(editorial["pillars"]),
        narrative=editorial["narrative"],
        duration_s=editorial["duration_s"],
        cta=editorial["cta"],
        motion=tuple(audiovisual.get("motion", ())),
        music=audiovisual.get("music", {}),
        transition=audiovisual.get("transition", {}),
        caption=audiovisual.get("caption", {}),
        palette=audiovisual.get("palette", {}),
        voice=audiovisual.get("voice", {}),
        extra=audiovisual.get("extra", {}),
        provider_profile=profile,
        provider_policy_version=PROVIDER_POLICY_VERSION,
        provenance={
            **{"style": style_source.value, "provider_policy": policy_source.value},
            **{f"editorial.{field}": editorial_source.value for field in EDITORIAL_FIELDS},
            **provenance,
        },
    )