"""Regras e tipos do painel do Studio (camada de domínio puro, sem I/O)."""
import re
import string
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum

from .contracts import JobStatus, PublicationStatus, VideoStatus

_PUNCT_EDGES = string.punctuation + " \t\n\r"


class Stage(str, Enum):
    PENDING = "PENDING"
    IN_PRODUCTION = "IN_PRODUCTION"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


def topic_key(topic: str) -> str:
    """Normaliza o tema para agrupar variações de pontuação/espaço/caixa."""
    normalized = unicodedata.normalize("NFKC", topic or "").casefold()
    collapsed = re.sub(r"\s+", " ", normalized).strip(_PUNCT_EDGES)
    return collapsed


def classify(status: VideoStatus, *, job: JobStatus | None = None, step_running: bool = False,
             publication: PublicationStatus | None = None) -> Stage:
    """Classifica a etapa observável do vídeo para o operador segundo precedência estrita."""
    if status == VideoStatus.REJECTED:
        return Stage.REJECTED
    if status == VideoStatus.PUBLISHED or publication == PublicationStatus.UPLOADED:
        return Stage.COMPLETED
    if status == VideoStatus.FAILED or publication == PublicationStatus.FAILED:
        return Stage.FAILED
    if (job in (JobStatus.RUNNING, JobStatus.QUEUED)) or step_running or (publication == PublicationStatus.UPLOADING):
        return Stage.IN_PRODUCTION
    if job == JobStatus.FAILED and status != VideoStatus.APPROVED:
        return Stage.FAILED
    if status in (VideoStatus.AWAITING_APPROVAL, VideoStatus.RENDERED):
        return Stage.AWAITING_APPROVAL
    if status == VideoStatus.APPROVED:
        return Stage.APPROVED
    return Stage.PENDING


def is_known_cost(provider: str, model: str, cost_usd: float,
                  free_providers: Collection[str]) -> bool:
    """Determina se o custo de uma chamada é confiavelmente conhecido.

    `free_providers` é a política de gratuidade declarada pela raiz de composição: o domínio
    não conhece nome concreto de fornecedor, só a regra que recebe.
    """
    if cost_usd > 0.0:
        return True
    if (model or "").lower().endswith(":free"):
        return True
    if (provider or "").lower() in {str(name).lower() for name in free_providers}:
        return True
    return False


@dataclass(frozen=True)
class CostSummary:
    known_usd: float
    calls: int
    unknown_calls: int


def cost_text(c: CostSummary) -> str:
    """Apresenta o custo com honestidade: nunca mostra 'US$ 0,00' se houver chamadas desconhecidas."""
    if c.calls == 0:
        return "sem registro de uso"
    formatted = f"US$ {c.known_usd:.2f}".replace(".", ",")
    if c.unknown_calls == 0:
        if c.known_usd == 0.0:
            return "US$ 0,00 (gratuito)"
        return formatted
    noun = "chamada" if c.unknown_calls == 1 else "chamadas"
    return f"{formatted} + {c.unknown_calls} {noun} sem custo informado"
