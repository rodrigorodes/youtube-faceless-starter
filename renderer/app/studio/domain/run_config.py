"""Referência imutável da configuração efetiva de um run (F03.T02). Puro, sem I/O.

O run nasce com **uma** configuração efetiva: o snapshot canônico (``domain.effective_config``)
congelado na mesma transação do INSERT do run, antes de qualquer efeito. Este módulo só declara a
forma como essa referência é lida de volta — ``StoredRunConfig`` — e os erros de conflito/integridade
que a aplicação e os adaptadores compartilham, para que nenhum caminho resolva a configuração de
novo depois do fato.

Dois estados são explícitos e não se confundem:

* ``resolved``: há snapshot canônico, hash e schema; a retomada, o retry e o replay leem **este**
  documento e nunca recalculam.
* ``legacy``: o run foi criado sem resolvedor (comportamento anterior preservado). Não há snapshot
  e o run **nunca** ganha um depois do fato: replay com configuração é conflito, não upgrade
  silencioso.

``RunConfigConflict`` é subclasse de ``ProductionIdempotencyConflict``: a mesma chave com outro
snapshot é o mesmo caso de "chave já usada para outra solicitação" (HTTP 409), sem inventar um
caminho novo de erro na API.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .effective_config import EffectiveConfig
from .production_run import ProductionError, ProductionIdempotencyConflict


class RunConfigStatus(str, Enum):
    """Se o run nasceu com snapshot canônico ou como legado explícito."""

    RESOLVED = "resolved"
    LEGACY = "legacy"


class RunConfigConflict(ProductionIdempotencyConflict):
    """A mesma identidade de run foi pedida com uma configuração efetiva diferente.

    Nunca sobrescreve o snapshot: o run existente devolve o que já tinha e a chamada divergente
    falha explicitamente.
    """


class RunConfigIntegrityError(ProductionError):
    """O snapshot persistido não reconstrói a configuração com o hash gravado (dado corrompido)."""


@dataclass(frozen=True)
class StoredRunConfig:
    """Leitura da referência persistida: ``resolved`` sempre traz a configuração; ``legacy``, nunca."""

    status: RunConfigStatus
    config: EffectiveConfig | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RunConfigStatus):
            raise TypeError("status must be a RunConfigStatus")
        if self.status is RunConfigStatus.RESOLVED:
            if not isinstance(self.config, EffectiveConfig):
                raise ValueError("a resolved run config requires the effective config snapshot")
        elif self.config is not None:
            raise ValueError("a legacy run config cannot carry a snapshot")

    @property
    def content_hash(self) -> str | None:
        return self.config.content_hash if self.config is not None else None