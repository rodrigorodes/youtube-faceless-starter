"""Adaptador de fallback resiliente para síntese de voz (V4-02).

Permite orquestrar um provedor primário (ex: neural ou experimental)
com fallback transparente para um secundário comprovado (ex: Piper local),
evitando que falhas temporárias, falta de credencial ou silêncio anômalo
interrompam a produção audiovisual.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from ..application.ports import Voice

logger = logging.getLogger(__name__)


class FallbackVoice:
    """Adaptador de voz resiliente com fallback automático."""

    def __init__(
        self,
        primary: Voice,
        fallback: Voice,
        on_fallback: Callable[[str, Exception], None] | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.on_fallback = on_fallback
        self.name = f"{getattr(primary, 'name', 'primary')}_with_fallback_{getattr(fallback, 'name', 'fallback')}"
        self.last_used: str = getattr(primary, "name", "primary")

    def speak(self, text: str, out_path: Path) -> float:
        try:
            duration = self.primary.speak(text, out_path)
            self.last_used = getattr(self.primary, "name", "primary")
            return duration
        except Exception as err:
            primary_name = getattr(self.primary, "name", "primary")
            fallback_name = getattr(self.fallback, "name", "fallback")
            logger.warning(
                "Primary voice %s failed (%s); engaging fallback %s",
                primary_name,
                err,
                fallback_name,
            )
            if self.on_fallback:
                self.on_fallback(primary_name, err)
            duration = self.fallback.speak(text, out_path)
            self.last_used = fallback_name
            return duration
