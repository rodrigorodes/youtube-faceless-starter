"""Porta agnóstica para reserva preventiva de orçamento em USD."""
from decimal import Decimal
from enum import Enum
from typing import Protocol


class IdempotencyConflict(ValueError):
    """Uma chave já foi usada para uma solicitação diferente."""


class ReservationResult(str, Enum):
    CREATED = "CREATED"
    EXISTING = "EXISTING"
    DENIED = "DENIED"

    def __bool__(self) -> bool:
        raise TypeError("compare the reservation result explicitly")


class BudgetReservationRepository(Protocol):
    def reserve(
        self, key: str, video_id: str, amount: Decimal,
        monthly_limit: Decimal, video_limit: Decimal,
    ) -> ReservationResult:
        """Reserva atomicamente; DENIED indica limite ou custo desconhecido.

        Uma repetição idêntica retorna EXISTING; reutilização divergente falha.
        CREATED não garante exclusividade nem estado da operação externa:
        execução, retry e reconciliação exigem um protocolo independente.
        A reserva continua ativa até reconciliação, ainda não implementada.
        """
        ...
