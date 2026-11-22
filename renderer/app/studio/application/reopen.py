"""Reabrir para edição um vídeo APROVADO e não publicado (ADR-002 / P-04).

A transição `APPROVED → SCRIPTED` é declarada no domínio puro; a **guarda de publicação**
mora aqui, na camada de aplicação, porque depende do estado da publicação (lease, upload e
resultado externo) e não de uma regra do grafo de estados. O repositório executa a guarda e
as escritas na mesma transação, com CAS por estado: se outro comando mudou o vídeo antes,
nada é gravado e o conflito é devolvido.

Regras verificáveis do ADR:

1. `APPROVED → SCRIPTED` só sem publicação concluída e sem lease de upload ativo.
2. Reabrir invalida aprovação, intenção pendente, render/QA anteriores na mesma transação.
3. A aprovação anterior não libera a versão nova (o gate de publicação continua fail-closed).
4. `PUBLISHED` não reabre; duplicar é o caminho.
5. Nenhum registro histórico de publicação é apagado ou reescrito.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from ..domain.contracts import PublicationStatus, VideoStatus
from .editorial import StateConflict, VideoNotFound


class PublicationAlreadyCompleted(StateConflict):
    """O vídeo já tem publicação concluída; editar exige duplicar (ADR-002, regra 4)."""


class PublicationInFlight(StateConflict):
    """Há upload/publicação em andamento; o efeito externo não pode ser cancelado por edição."""


class ReopenConflict(StateConflict):
    """O estado do vídeo mudou entre a leitura e a transação (CAS por estado)."""


class ReopenRefusal(str, Enum):
    PUBLISHED = "PUBLISHED"
    IN_FLIGHT = "IN_FLIGHT"


@dataclass(frozen=True)
class PublicationLease:
    """Retrato da publicação ativa do vídeo; lease e estado externo vêm do banco."""

    publication_id: str
    status: PublicationStatus
    lease_until: datetime | None
    upload_uri: str | None
    youtube_video_id: str | None
    invalidated_at: datetime | None = None
    remote_state: str | None = None
    dead_letter: bool = False


def publication_guard(lease: PublicationLease | None, now: datetime) -> ReopenRefusal | None:
    """Guarda pura do ADR-002: devolve o motivo da recusa ou `None` se pode reabrir.

    - Publicação concluída (`UPLOADED`/com id do YouTube) nunca reabre: duplicar.
    - Lease válido (`UPLOADING` ou `PENDING`) ou sessão de upload já aberta: upload em andamento.
    - Resultado externo ambíguo (`UNKNOWN`) ou DLQ com sessão: exige reconciliação, não edição.
    - `PENDING`/`FAILED`/`UPLOADING` sem upload e sem lease ativo: publicação nunca subiu,
      pode ser invalidada na transação.
    """
    if lease is None or lease.invalidated_at is not None:
        return None
    if lease.status is PublicationStatus.UPLOADED or lease.youtube_video_id is not None:
        return ReopenRefusal.PUBLISHED
    if lease.remote_state == "UNKNOWN":
        return ReopenRefusal.IN_FLIGHT
    if lease.lease_until is not None and lease.lease_until > now:
        return ReopenRefusal.IN_FLIGHT
    if lease.upload_uri is not None:
        return ReopenRefusal.IN_FLIGHT
    if lease.dead_letter and lease.status is PublicationStatus.FAILED:
        return ReopenRefusal.IN_FLIGHT
    return None


@dataclass(frozen=True)
class ReopenOutcome:
    """Resultado da transação de reabertura; o caso de uso traduz em erro ou sucesso."""

    video_id: str
    previous_status: VideoStatus
    reopened: bool = False
    approval_archived: bool = False
    intent_invalidated: bool = False
    publication_invalidated: bool = False
    refusal: ReopenRefusal | None = None
    conflict: bool = False
    missing: bool = False


class ReopenRepository(Protocol):
    def reopen(self, video_id: str,
               guard: Callable[[PublicationLease | None, datetime], ReopenRefusal | None]) -> ReopenOutcome:
        """Numa transação: CAS `APPROVED → SCRIPTED`, guarda de publicação, arquivo da
        aprovação/intenção e invalidação da publicação que nunca subiu."""
        ...


class ReopenForEditing:
    """Caso de uso: reabre um vídeo APROVADO e não publicado, invalidando a versão anterior."""

    def __init__(self, repo: ReopenRepository):
        self.repo = repo

    def execute(self, video_id: str) -> ReopenOutcome:
        outcome = self.repo.reopen(video_id, publication_guard)
        if outcome.missing:
            raise VideoNotFound(video_id)
        if outcome.refusal is ReopenRefusal.PUBLISHED:
            raise PublicationAlreadyCompleted(
                "the video already has a completed publication; duplicate it to create an independent revision")
        if outcome.refusal is ReopenRefusal.IN_FLIGHT:
            raise PublicationInFlight(
                "a publication upload is in flight; wait for it to finish or reconcile it before reopening")
        if outcome.conflict:
            raise ReopenConflict("the video state changed; reload and try again")
        return outcome
