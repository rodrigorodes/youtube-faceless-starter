"""Política pura da publicação resiliente (F8-02..F8-06).

Concentra as decisões que **não** podem depender de infraestrutura: identidade imutável do render
que autoriza a publicação, classificação de falhas, backoff/DLQ, janela de agendamento e a regra
de confirmação extra para visibilidade pública. A aplicação e os adaptadores só executam isto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

_ID32 = re.compile(r"^[0-9a-f]{32}$")
_CHECKSUM64 = re.compile(r"^[0-9a-f]{64}$")
_VISIBILITIES = ("private", "unlisted", "public")
MIN_PROCESSING_LEAD = timedelta(minutes=15)


class PublicationPolicyError(ValueError):
    """Entrada inválida para a política de publicação."""


class PublicConfirmationRequired(PublicationPolicyError):
    """Visibilidade pública exige uma confirmação humana separada da escolha."""


class PublicationGateError(PublicationPolicyError):
    """O render/QA aprovado não é exatamente o que se pretende publicar."""


class FailureClass(str, Enum):
    TRANSIENT = "TRANSIENT"      # rede/5xx/429: repetir com backoff
    PERMANENT = "PERMANENT"      # metadado inválido, quota, token inválido: DLQ + humano
    AMBIGUOUS = "AMBIGUOUS"      # timeout/404/410/409: reconciliar antes de qualquer novo efeito


def _id32(value: object, what: str) -> str:
    if not isinstance(value, str) or not _ID32.fullmatch(value):
        raise PublicationPolicyError(f"{what} must be a 32-character lowercase hex id")
    return value


def _checksum(value: object) -> str:
    if not isinstance(value, str) or not _CHECKSUM64.fullmatch(value):
        raise PublicationPolicyError("media checksum must be 64 lowercase hex characters")
    return value


def validate_visibility(value: object) -> str:
    if not isinstance(value, str) or value not in _VISIBILITIES:
        raise PublicationPolicyError("visibility must be private, unlisted or public")
    return value


def requires_public_confirmation(visibility: str) -> bool:
    return validate_visibility(visibility) == "public"


def resolve_visibility(visibility: object, confirmed: bool | None) -> str:
    """Privado é o padrão. Público só passa com uma confirmação explícita (`True`)."""
    value = validate_visibility(visibility)
    if value == "public" and confirmed is not True:
        raise PublicConfirmationRequired("publishing publicly requires explicit confirmation")
    return value


def idempotency_key(video_id: str, render_id: str, checksum: str) -> str:
    """Chave estável pela identidade exata do vídeo+render+checksum; muda se qualquer um mudar."""
    return f"pub-{_id32(video_id, 'video_id')}-{_id32(render_id, 'render_id')}-{_checksum(checksum)}"


@dataclass(frozen=True)
class PublicationIntentEvidence:
    """Intenção de publicação gravada atomicamente com a aprovação (F8-02).

    `render_id` e `checksum` são imutáveis: um render novo depois da aprovação nunca passa no gate.
    """

    video_id: str
    render_id: str
    checksum: str
    output_asset_id: str
    qa_passed: bool
    qa_override: bool
    visibility: str
    public_confirmed: bool
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "video_id", _id32(self.video_id, "video_id"))
        object.__setattr__(self, "render_id", _id32(self.render_id, "render_id"))
        object.__setattr__(self, "checksum", _checksum(self.checksum))
        object.__setattr__(self, "output_asset_id", _id32(self.output_asset_id, "output_asset_id"))
        visibility = validate_visibility(self.visibility)
        object.__setattr__(self, "visibility", visibility)
        if visibility == "public" and self.public_confirmed is not True:
            raise PublicConfirmationRequired("a public publication intent needs explicit confirmation")
        if not isinstance(self.qa_passed, bool) or not isinstance(self.qa_override, bool):
            raise PublicationPolicyError("qa_passed and qa_override must be booleans")
        if self.idempotency_key != idempotency_key(self.video_id, self.render_id, self.checksum):
            raise PublicationPolicyError("the idempotency key does not match the media identity")


def verify_publication_gate(intent: PublicationIntentEvidence, *, render_id: str, checksum: str,
                            output_asset_id: str, qa_report_passed: bool,
                            approval_output_asset_id: str | None) -> None:
    """Só publica a versão exata aprovada: render, checksum, output e QA precisam coincidir.

    Override humano de QA só vale quando foi registrado na aprovação (`qa_override=True`).
    """
    if intent.render_id != _id32(render_id, "render_id"):
        raise PublicationGateError("the render revision changed since approval; review it again")
    if intent.checksum != _checksum(checksum):
        raise PublicationGateError("the media checksum changed since approval; review it again")
    if intent.output_asset_id != _id32(output_asset_id, "output_asset_id"):
        raise PublicationGateError("the approved output is not the current render output")
    if approval_output_asset_id != intent.output_asset_id:
        raise PublicationGateError("the approved output no longer matches the publication intent")
    if not qa_report_passed and not intent.qa_override:
        raise PublicationGateError("QA did not pass; publication needs an approved QA report or a recorded override")


def classify_http(status: int | None, *, error_code: str | None = None) -> FailureClass:
    """Classifica sem presumir sucesso. `None` é rede/timeout — nunca "deu certo"."""
    code = (error_code or "").lower()
    if status is None or status == 408 or status == 429 or (isinstance(status, int) and 500 <= status < 600):
        return FailureClass.TRANSIENT
    if status in (404, 410, 409) or code in ("notfound", "sessionexpired"):
        return FailureClass.AMBIGUOUS
    return FailureClass.PERMANENT


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_seconds: int = 30
    cap_seconds: int = 3600

    def __post_init__(self) -> None:
        for value in (self.max_attempts, self.base_seconds, self.cap_seconds):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError("retry policy values must be positive integers")
        if self.cap_seconds < self.base_seconds:
            raise ValueError("cap_seconds must be at least base_seconds")


def retry_delay(policy: RetryPolicy, attempt: int) -> int:
    """Backoff exponencial a partir da tentativa (1 → base), limitado ao teto."""
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ValueError("attempt must be >= 1")
    return min(policy.cap_seconds, policy.base_seconds * 2 ** (attempt - 1))


def next_action(policy: RetryPolicy, attempt: int, failure: FailureClass) -> str:
    """`RETRY` apenas para falha transiente com tentativa restante; todo o resto é DLQ."""
    if failure is FailureClass.TRANSIENT and attempt < policy.max_attempts:
        return "RETRY"
    return "DEAD_LETTER"


def publication_window_state(publish_at: datetime | None, now: datetime) -> str:
    """`OPEN` (sem agenda), `SCHEDULED`, `TOO_LATE` (upload não processa a tempo) ou `EXPIRED`."""
    if now.tzinfo is None:
        raise ValueError("now needs a time zone")
    if publish_at is None:
        return "OPEN"
    if publish_at.tzinfo is None:
        raise ValueError("publish_at needs a time zone")
    if publish_at <= now:
        return "EXPIRED"
    if publish_at - now < MIN_PROCESSING_LEAD:
        return "TOO_LATE"
    return "SCHEDULED"


def body_privacy_status(visibility: str, publish_at: datetime | None) -> str:
    """Privacidade enviada ao `videos.insert`; a visibilidade desejada fica na intenção.

    O YouTube agenda com `private` + `publishAt` (o vídeo vira público no horário). `unlisted`
    agendado não existe na API, então recusamos em vez de prometer um comportamento falso.
    """
    value = validate_visibility(visibility)
    if publish_at is None:
        return value
    if value == "unlisted":
        raise PublicationPolicyError("a scheduled publication cannot be unlisted; schedule private or public")
    return "private"