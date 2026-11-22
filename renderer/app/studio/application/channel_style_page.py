"""Personalizar o estilo do canal (F05.T04) — projeção de origem, valor efetivo e reset.

Editar a **biblioteca** e personalizar o **canal** são coisas diferentes: a biblioteca é o estilo
compartilhado (``styles_page``), o canal é um ``StylePatch`` por cima dela. Esta projeção mostra,
para cada campo, **de onde vem** o valor efetivo (canal · estilo · padrão do motor), **qual é** o
valor e **o que o reset devolveria** — sem que a tela recalcule precedência.

A resolução é a do Core: ``domain.effective_config.resolve_effective_config`` com
``channel_patch=profile.style_patch`` e sem override de vídeo. O Core resolve por vídeo; para o
canal, um vídeo-âncora (mesmo projeto, sem ``style_id`` e sem patch) só preenche as referências
obrigatórias — nenhum valor de vídeo entra no resultado. A "herança" de cada campo vem de uma
segunda resolução **sem** o patch do canal, então o texto “herda do estilo X” e o alvo do reset
são medidos pela mesma função, nunca copiados da camada de cima.

Só entram como **editáveis** parâmetros que o render aplica (motion · music · caption · palette ·
voice). ``transition`` (carregada no plano, ainda não aplicada) e ``extra`` (bag de extensão sem
leitura pelo renderer) aparecem **rotulados e sem controle de valor**: um controle que não muda o
render seria promessa falsa. O reset deles, quando há override no canal, apenas remove a camada e
é oferecido porque remover é seguro.

Esta camada é só projeção: não faz I/O além das portas recebidas e não grava nada. A escrita é
``application.video_style.SetChannelStylePatch``.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ..domain.contracts import Video, VideoFormat
from ..domain.effective_config import ConfigSource, EffectiveConfig, resolve_effective_config
from ..domain.ids import check_id
from .ports import ChannelProfileRepository, VisualStyleRepository

__all__ = ["ChannelStyleField", "ChannelStylePageView", "BuildChannelStylePage",
           "TRANSITION_NOT_APPLIED", "EXTRA_NOT_APPLIED"]

TRANSITION_NOT_APPLIED = ("O render carrega a transição no plano, mas ainda não a aplica.")
EXTRA_NOT_APPLIED = ("Bag livre de extensão do estilo; o render não lê estas chaves.")


@dataclass(frozen=True)
class _FieldSpec:
    """Um campo do patch (``key=None`` = valor inteiro, como ``motion``)."""

    group: str
    key: str | None
    label: str
    control: str  # motion | int | color | text
    minimum: int | None = None
    maximum: int | None = None
    applied: bool = True
    reason: str = ""

    @property
    def path(self) -> str:
        return self.group if self.key is None else f"{self.group}.{self.key}"


# Ordem de exibição: primeiro o que o render aplica, na ordem em que aparece no vídeo.
_APPLIED_SPECS: tuple[_FieldSpec, ...] = (
    _FieldSpec("motion", None, "Ritmo de câmera", "motion"),
    _FieldSpec("music", "bpm", "Música (bpm)", "int", minimum=20, maximum=300),
    _FieldSpec("music", "seed", "Semente da música", "int", minimum=0, maximum=2 ** 31 - 1),
    _FieldSpec("caption", "font_size", "Tamanho da legenda (px)", "int", minimum=8, maximum=400),
    _FieldSpec("caption", "bottom", "Distância do rodapé (px)", "int", minimum=0),
    _FieldSpec("palette", "caption_text", "Cor do texto da legenda", "color"),
    _FieldSpec("palette", "caption_box", "Cor da caixa da legenda", "color"),
    _FieldSpec("palette", "accent", "Cor de destaque", "color"),
    _FieldSpec("voice", "model", "Voz (modelo)", "text"),
)

# Carregado pelo contrato, **não** aplicado pelo render: aparece informativo e sem edição.
_LOADED_ONLY_SPECS: tuple[_FieldSpec, ...] = (
    _FieldSpec("transition", "kind", "Transição", "text", applied=False,
               reason=TRANSITION_NOT_APPLIED),
    _FieldSpec("transition", "duration_ticks", "Duração da transição (ticks)", "int", minimum=0,
               applied=False, reason=TRANSITION_NOT_APPLIED),
)


@dataclass(frozen=True)
class ChannelStyleField:
    """Um campo do patch com a origem e o valor que o Core resolve.

    ``origin``/``effective`` são o estado **atual** (com o patch do canal). ``inherited_origin``/
    ``inherited`` são o que vale **sem** o patch do canal — o destino do reset. ``overridden`` é
    medido pela proveniência (origem ``channel``), não presumido pelo patch.
    """

    group: str
    key: str | None
    label: str
    control: str
    applied: bool = True
    origin: str = ConfigSource.ENGINE_DEFAULT.value
    effective: Any = None
    inherited_origin: str = ConfigSource.ENGINE_DEFAULT.value
    inherited: Any = None
    overridden: bool = False
    minimum: int | None = None
    maximum: int | None = None
    reason: str = ""

    @property
    def path(self) -> str:
        return self.group if self.key is None else f"{self.group}.{self.key}"


@dataclass(frozen=True)
class ChannelStylePageView:
    """O canal, seu estilo e cada campo do patch com origem/efetivo/reset."""

    channel_id: str
    channel_name: str
    project_id: str
    style_id: str | None = None
    style_name: str | None = None
    style_version: int | None = None
    style_archived: bool = False
    revision: int = 0
    patch: Mapping[str, Any] = field(default_factory=dict)
    fields: tuple[ChannelStyleField, ...] = ()

    @property
    def has_patch(self) -> bool:
        return bool(self.patch)

    @property
    def applied_fields(self) -> tuple[ChannelStyleField, ...]:
        return tuple(item for item in self.fields if item.applied)

    @property
    def not_applied_fields(self) -> tuple[ChannelStyleField, ...]:
        return tuple(item for item in self.fields if not item.applied)

    def patch_document(self) -> dict[str, Any]:
        """Forma de transporte (JSON), em cópia: a tela nunca compartilha estrutura com o Core."""
        return {group: _thaw(value) for group, value in self.patch.items()}


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _anchor_video(profile) -> Video:
    """Vídeo-âncora **sem** seleção/override: o Core resolve por vídeo, aqui o canal é a camada.

    ``resolve_effective_config`` exige o agregado ``Video`` para ancorar ``project_id``/`video_id`;
    o âncora usa o próprio canal como id e não declara estilo nem patch, então nada de vídeo
    participa da resolução — o resultado é o do canal sobre o estilo selecionado.
    """
    return Video(id=profile.id, project_id=profile.project_id, topic="canal",
                 format=VideoFormat.short)


def _origin(provenance: Mapping[str, str], spec: _FieldSpec) -> str:
    path = f"audiovisual.{spec.group}" + (f".{spec.key}" if spec.key is not None else "")
    group_path = f"audiovisual.{spec.group}"
    # Ausência de chave é "o motor decide"; o grupo só aparece quando ele é o vencedor inteiro.
    return provenance.get(path) or provenance.get(group_path) or ConfigSource.ENGINE_DEFAULT.value


def _value(config: EffectiveConfig, spec: _FieldSpec) -> Any:
    group = getattr(config, spec.group, None)
    if spec.key is None:
        return group
    if not isinstance(group, Mapping):
        return None
    return group.get(spec.key)


class BuildChannelStylePage:
    """Monta a projeção de personalização a partir do perfil e da biblioteca (sem SQL na tela)."""

    def __init__(self, channels: ChannelProfileRepository, styles: VisualStyleRepository):
        self.channels = channels
        self.styles = styles

    def execute(self, channel_id: str) -> ChannelStylePageView | None:
        profile = self.channels.get(check_id(channel_id))
        if profile is None:
            return None
        style = self.styles.get(profile.style_id) if profile.style_id is not None else None
        anchor = _anchor_video(profile)
        effective = resolve_effective_config(
            video=anchor, channel=profile, lookup_style=self.styles.get,
            channel_patch=profile.style_patch)
        inherited = resolve_effective_config(
            video=anchor, channel=profile, lookup_style=self.styles.get)

        specs = list(_APPLIED_SPECS) + list(_LOADED_ONLY_SPECS)
        # `extra` é bag aberto: mostra as chaves que existem, uma a uma (nunca um JSON editável).
        extra_keys = sorted({str(key) for key in (*effective.extra, *inherited.extra)})
        specs.extend(
            _FieldSpec("extra", key, f"Extra · {key}", "text", applied=False,
                       reason=EXTRA_NOT_APPLIED)
            for key in extra_keys
        )
        fields = tuple(self._field(effective, inherited, spec) for spec in specs)
        return ChannelStylePageView(
            channel_id=profile.id,
            channel_name=profile.name,
            project_id=profile.project_id,
            style_id=profile.style_id,
            style_name=style.name if style is not None else None,
            style_version=style.version if style is not None else None,
            style_archived=bool(style is not None and style.archived),
            revision=profile.style_patch_revision,
            patch=MappingProxyType(profile.style_patch.to_mapping()
                                   if profile.style_patch is not None else {}),
            fields=fields,
        )

    @staticmethod
    def _field(effective: EffectiveConfig, inherited: EffectiveConfig,
               spec: _FieldSpec) -> ChannelStyleField:
        origin = _origin(effective.provenance, spec)
        return ChannelStyleField(
            group=spec.group,
            key=spec.key,
            label=spec.label,
            control=spec.control,
            applied=spec.applied,
            origin=origin,
            effective=_value(effective, spec),
            inherited_origin=_origin(inherited.provenance, spec),
            inherited=_value(inherited, spec),
            overridden=origin == ConfigSource.CHANNEL.value,
            minimum=spec.minimum,
            maximum=spec.maximum,
            reason=spec.reason,
        )