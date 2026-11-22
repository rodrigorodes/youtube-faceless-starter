"""Domínio do perfil de canal (multi-canal). Puro: sem I/O, sem banco.

Um canal é um projeto; o perfil guarda a configuração editorial/visual/áudio desse canal
(estratégia, idioma, público, pilares, narrativa, duração, identidade, voz, áudio, thumbnail e CTA).
O perfil é imutável e versionado: cada leitura/atualização carrega a `version`, e o repositório
incrementa a versão de forma otimista, gravando um snapshot auditável por versão.

YT-02: o canal também **referencia** o canal do YouTube em que publica (`youtube_channel_id`) e o
domínio sabe **resolver** qual autorização (`ChannelAuthorization`) o valida — sem religar a
publicação (essa é a YT-03).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from .ids import check_id
from .youtube_channel import OAuthStatus
from .youtube_identity import ChannelAuthorization, validate_youtube_channel_id

if TYPE_CHECKING:  # `visual_style` importa este módulo no topo; o import real é local (F05.T02)
    from .visual_style import StylePatch

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

# Campos que um `create` aceita (id, project_id e timestamps são do repositório).
CREATABLE_FIELDS = (
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
    "style_id",
    "youtube_channel_id",
    "archived",
)

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
    "style_id",
    "youtube_channel_id",
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


class ChannelProjectNotFound(ChannelError, LookupError):
    """O projeto (canal) informado não existe: o perfil não pode ser criado."""


class ChannelStyleNotFound(ChannelError, LookupError):
    """O estilo visual informado não existe: o canal não pode apontar para ele (VS-02)."""


class ChannelYouTubeTargetNotFound(ChannelError, LookupError):
    """O canal do YouTube informado não existe: o canal do estúdio não pode publicar nele (YT-02).

    A referência é para `studio.youtube_channels(youtube_channel_id)` — a identidade oficial do
    canal (`UC...`), não a conta nem a autorização.
    """


class ChannelLockTimeout(ChannelError, RuntimeError):
    """A linha do perfil ficou bloqueada além do `lock_timeout` do banco (contenção)."""


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


def clean_pillars(pillars: object) -> tuple[str, ...]:
    """Pilares de conteúdo: tira espaços, descarta vazios, remove repetidos e limita a MAX_PILLARS.

    Devolve uma tupla: o agregado imutável não compartilha uma lista mutável com o chamador.
    """
    if not pillars:
        return ()
    if not isinstance(pillars, (list, tuple)):
        raise ChannelFieldInvalid("pillars must be a list or tuple of strings")
    cleaned: list[str] = []
    for item in pillars:
        if not isinstance(item, str):
            raise ChannelFieldInvalid("every pillar must be a string")
        text = item.strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return tuple(cleaned[:MAX_PILLARS])


@dataclass(frozen=True)
class ChannelProfile:
    id: str
    project_id: str
    name: str
    strategy: str = ""
    language: str = "pt-BR"
    audience: str = ""
    pillars: tuple[str, ...] = ()
    narrative: str = ""
    target_duration_s: int = 60
    visual_identity: str = ""
    voice: str = ""
    audio: str = ""
    thumbnail: str = ""
    cta: str = ""
    # VS-02: o estilo visual que este canal segue (biblioteca compartilhada). None = sem estilo;
    # o render cai no bundle neutro. A referência é por chave — o plano grava (style_id, version).
    style_id: str | None = None
    # F05.T02: override tipado deste canal sobre o estilo selecionado (ADR fs31-004). None =
    # herda o estilo inteiro. Só overrides: personalizar o canal **não** copia nem edita `params`
    # do estilo. A escrita é dedicada (`set_style_patch`), com revisão própria — fora de
    # `UPDATABLE_FIELDS` de propósito.
    style_patch: "StylePatch | None" = None
    # Revisão do patch (0 = nunca personalizado). É o token do controle otimista da escrita do
    # patch: um cliente com revisão velha recebe `ChannelVersionConflict` e não grava.
    style_patch_revision: int = 0
    # YT-02: o canal do YouTube **em que** este canal publica (identidade oficial, `UC...`).
    # None = destino não escolhido; a publicação segue pelo caminho antigo até a YT-03.
    youtube_channel_id: str | None = None
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
        if self.style_id is not None:
            if not isinstance(self.style_id, str):
                raise ChannelFieldInvalid("style_id must be a string or null")
            check_id(self.style_id)
        if self.style_patch is not None:
            from .visual_style import StylePatch  # import local: `visual_style` importa este módulo
            patch = (self.style_patch if isinstance(self.style_patch, StylePatch)
                     else StylePatch.from_mapping(self.style_patch, where="channel style patch"))
            # Patch vazio é ausência de override: o agregado nunca carrega `{}` sem semântica.
            object.__setattr__(self, "style_patch", None if patch.is_empty else patch)
        if isinstance(self.style_patch_revision, bool) or not isinstance(self.style_patch_revision, int) \
                or self.style_patch_revision < 0:
            raise ChannelFieldInvalid("style_patch_revision must be an integer >= 0")
        if self.youtube_channel_id is not None:
            if not isinstance(self.youtube_channel_id, str):
                raise ChannelFieldInvalid("youtube_channel_id must be a string or null")
            object.__setattr__(self, "youtube_channel_id",
                               validate_youtube_channel_id(self.youtube_channel_id))
        object.__setattr__(self, "version", validate_version(self.version))
        if not isinstance(self.archived, bool):
            raise ChannelFieldInvalid("archived must be a boolean")


def resolve_publication_authorization(
    channel: ChannelProfile,
    authorizations: Iterable[ChannelAuthorization],
) -> ChannelAuthorization | None:
    """Qual autorização valida o canal do YouTube deste canal do estúdio (YT-02). Puro, sem I/O.

    Devolve a primeira autorização **vigente** (status CONECTADO) cujo `youtube_channel_id` casa
    com o destino do canal; `None` se o canal não escolheu destino, se não há autorização para
    ele, ou se todas estão revogadas/expiradas. Nunca presume vínculo: só o que está CONECTADO
    resolve — a mesma postura de `ChannelAuthorization`/`effective_status`.
    """
    target = channel.youtube_channel_id
    if target is None:
        return None
    for authorization in authorizations:
        if authorization.youtube_channel_id != target:
            continue
        if authorization.status is OAuthStatus.CONNECTED:
            return authorization
    return None


class PublicationAuthorizationDecision(str, Enum):
    """Decisão do gate de identidade antes de publicar (YT-03)."""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class PublicationAuthorizationVerdict:
    """Veredito do gate de identidade: a publicação pode prosseguir e, se sim, por qual autorização."""

    decision: PublicationAuthorizationDecision
    reason: str = ""
    authorization: ChannelAuthorization | None = None

    @property
    def allowed(self) -> bool:
        return self.decision is PublicationAuthorizationDecision.ALLOW


def verify_publication_authorization(
    channel: ChannelProfile,
    authorizations: Iterable[ChannelAuthorization],
    *,
    token_channel_id: str | None,
) -> PublicationAuthorizationVerdict:
    """O upload pode acontecer? Puro, sem I/O (YT-03).

    Regra obrigatória (§3 do desenho): **antes de publicar**, a autorização tem de resolver para o
    ``youtubeChannelId`` esperado. A verificação é sobre a **identidade do canal** — nunca sobre os
    valores dos tokens (dois tokens isolados não provam restrição a um canal).

    - Canal **sem destino** (``youtube_channel_id is None``): ``BLOCK`` com motivo acionável. O gate
      **falha fechado** (W0B.2/R8): sem destino configurado não há como provar a identidade do
      canal, então a publicação é recusada — nunca se presume o caminho antigo por omissão.
    - Canal **com destino**: exige uma autorização ``CONNECTED`` que case com o destino
      (``resolve_publication_authorization``) **e** que o token usado pertença ao mesmo canal. Sem
      autorização vigente, com token de outro canal ou com canal do token **desconhecido**, bloqueia:
      na dúvida sobre a identidade, não se publica (falha fechada).

    Nota: o caso "repositórios de canal não injetados" (``channels``/``authorizations`` ausentes) é
    tratado em ``RunPublication._authorization_gate``, não aqui.
    """
    target = channel.youtube_channel_id
    if target is None:
        return PublicationAuthorizationVerdict(
            PublicationAuthorizationDecision.BLOCK,
            "no YouTube destination is configured for this channel; connect the channel in Canais → Conexão")
    authorization = resolve_publication_authorization(channel, authorizations)
    if authorization is None:
        return PublicationAuthorizationVerdict(
            PublicationAuthorizationDecision.BLOCK,
            f"no connected authorization for the expected YouTube channel {target}")
    if token_channel_id != target:
        arrived = token_channel_id or "an unknown channel"
        return PublicationAuthorizationVerdict(
            PublicationAuthorizationDecision.BLOCK,
            f"the access token belongs to {arrived}, not the expected YouTube channel {target}",
            authorization)
    return PublicationAuthorizationVerdict(
        PublicationAuthorizationDecision.ALLOW,
        f"the authorization resolves to the expected YouTube channel {target}",
        authorization)
