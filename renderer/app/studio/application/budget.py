"""Porta agnóstica para reserva preventiva de orçamento em USD."""
from decimal import Decimal
from typing import Protocol


class IdempotencyConflict(ValueError):
    """Uma chave já foi usada para uma solicitação diferente."""


class BudgetReservationRepository(Protocol):
    def reserve(
        self, key: str, video_id: str, amount: Decimal,
        monthly_limit: Decimal, video_limit: Decimal,
    ) -> bool:
        """Reserva atomicamente; False indica limite insuficiente.

        Uma repetição idêntica retorna True; reutilização divergente falha.
        A reserva continua ativa até reconciliação, ainda não implementada.
        """
        ...
