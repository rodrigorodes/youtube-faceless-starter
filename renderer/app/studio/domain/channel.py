"""Domínio do perfil de canal (multi-canal). Puro: sem I/O, sem banco.

Um canal é um projeto; o perfil guarda a configuração editorial/visual/áudio desse canal
(estratégia, idioma, público, pilares, narrativa, duração, identidade, voz, áudio, thumbnail e CTA).
O perfil é imutável e versionado: cada leitura/atualização carrega a `version`, e o repositório
incrementa a versão de forma otimista, gravando um snapshot auditável por versão.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .ids import check_id

MAX_NAME_LENGTH = 120
MAX_STRATEGY_LENGTH = 500
MAX_AUDIENCE_LENGTH = 500
MAX_NARRATIVE_LENGTH = 4000
MAX_VISUAL_IDENTITY_LENGTH = 2000
MAX_THUMBNAIL_LENGTH = 2000
MAX_PROVIDER_SPEC_LENGTH = 200
MAX_CTA_LENGTH = 500
MAX_PILLARS = 20
MAX_DURATION_S = 36000

# Campos que um `update` pode alterar (id, project_id, version e timestamps são do repositório).
UPDATABLE_FIELDS = (
    "name",
    "strategy",
    "language",
    "audience",
    "pillars",
    "narrative",
    "target_duration_s",
    "visual_identity",
    "voice",
    "audio",
    "thumbnail",
    "cta",
    "archived",
)


class ChannelError(Exception):
    """Erro base do perfil de canal."""


class ChannelNameInvalid(ChannelError, ValueError):
    """Nome do canal vazio, longo demais ou de tipo inválido."""


class ChannelFieldInvalid(ChannelError, ValueError):
    """Campo textual/estrutural do perfil com tipo ou tamanho inválido."""


class ChannelDurationInvalid(ChannelError, ValueError):
    """Duração-alvo inválida (precisa ser inteiro entre 1 e 36000 segundos)."""


class ChannelVersionInvalid(ChannelError, ValueError):
    """Versão do perfil inválida (precisa ser inteiro >= 1)."""


class DuplicateChannelProfile(ChannelError, ValueError):
    """Já existe um perfil para este canal (projeto)."""


class ChannelVersionConflict(ChannelError, ValueError):
    """A versão informada não é a versão atual: outra atualização venceu a corrida."""


def validate_channel_name(name: object) -> str:
    if not isinstance(name, str):
        raise ChannelNameInvalid("channel name must be a string")
    cleaned = name.strip()
    if not (1 <= len(cleaned) <= MAX_NAME_LENGTH):
        raise ChannelNameInvalid(f"channel name must be between 1 and {MAX_NAME_LENGTH} characters")
    return cleaned


def _text(value: object, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ChannelFieldInvalid(f"{field_name} must be a string")
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise ChannelFieldInvalid(f"{field_name} must be at most {max_length} characters")
    return cleaned


def validate_language(language: object) -> str:
    cleaned = _text(language, "language", 20)
    if len(cleaned) < 2:
        raise ChannelFieldInvalid("language must be at least 2 characters")
    return cleaned


def validate_duration(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ChannelDurationInvalid("target_duration_s must be an integer")
    if not (1 <= value <= MAX_DURATION_S):
        raise ChannelDurationInvalid(f"target_duration_s must be between 1 and {MAX_DURATION_S}")
    return value


def validate_version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ChannelVersionInvalid("version must be an integer >= 1")
    return value


def clean_pillars(pillars: object) -> list[str]:
    """Pilares de conteúdo: tira espaços, descarta vazios, remove repetidos e limita a MAX_PILLARS."""
    if not pillars:
        return []
    if not isinstance(pillars, (list, tuple)):
        raise ChannelFieldInvalid("pillars must be a list of strings")
    cleaned: list[str] = []
    for item in pillars:
        if not isinstance(item, str):
            raise ChannelFieldInvalid("every pillar must be a string")
        text = item.strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned[:MAX_PILLARS]


@dataclass(frozen=True)
class ChannelProfile:
    id: str
    project_id: str
    name: str
    strategy: str = ""
    language: str = "pt-BR"
    audience: str = ""
    pillars: list[str] = field(default_factory=list)
    narrative: str = ""
    target_duration_s: int = 60
    visual_identity: str = ""
    voice: str = ""
    audio: str = ""
    thumbnail: str = ""
    cta: str = ""
    version: int = 1
    archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        check_id(self.id)
        check_id(self.project_id)
        object.__setattr__(self, "name", validate_channel_name(self.name))
        object.__setattr__(self, "strategy", _text(self.strategy, "strategy", MAX_STRATEGY_LENGTH))
        object.__setattr__(self, "language", validate_language(self.language))
        object.__setattr__(self, "audience", _text(self.audience, "audience", MAX_AUDIENCE_LENGTH))
        object.__setattr__(self, "pillars", clean_pillars(self.pillars))
        object.__setattr__(self, "narrative", _text(self.narrative, "narrative", MAX_NARRATIVE_LENGTH))
        object.__setattr__(self, "target_duration_s", validate_duration(self.target_duration_s))
        object.__setattr__(self, "visual_identity", _text(self.visual_identity, "visual_identity", MAX_VISUAL_IDENTITY_LENGTH))
        object.__setattr__(self, "voice", _text(self.voice, "voice", MAX_PROVIDER_SPEC_LENGTH))
        object.__setattr__(self, "audio", _text(self.audio, "audio", MAX_PROVIDER_SPEC_LENGTH))
        object.__setattr__(self, "thumbnail", _text(self.thumbnail, "thumbnail", MAX_THUMBNAIL_LENGTH))
        object.__setattr__(self, "cta", _text(self.cta, "cta", MAX_CTA_LENGTH))
        object.__setattr__(self, "version", validate_version(self.version))
        if not isinstance(self.archived, bool):
            raise ChannelFieldInvalid("archived must be a boolean")
