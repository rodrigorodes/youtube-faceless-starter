"""Contrato canônico de um intervalo visual (beat) dentro de uma cena.

Reconciliação com o esqueleto do plano de implementação (F5):

- Canônico é este módulo, ``app.studio.domain.visual_beat``, alinhado ao card
  F5-01. O esqueleto do plano importava ``VisualBeat`` de ``contracts`` com
  ``beat_id``/``duration``/``effect``; tratava-se de rascunho anterior ao card e
  não há consumidor real usando esses nomes (só ``tests/test_visual_beat.py``).
- ``duration`` do plano -> ``end_s - start_s`` (exposto como ``duration_s``).
- ``effect`` do plano (movimento de câmera: zoom/pan) NÃO é ``transition``
  (crossfade entre beats) e ainda não tem campo canônico: pertence ao render
  (F5-06), não a este contrato.
- ``beat_id`` do plano não existe; a identidade do beat é (``scene_id``, ordem)
  ou ``reference``. Granularidade e cache por beat são decisão de F5-07.

Este contrato NÃO verifica a veracidade da proveniência ou da licença, nem se o
asset é recuperável: exige apenas strings não vazias para mídia externa
(``text_animation`` local é isenta). Auditoria de direitos é F5-08 e está fora
deste escopo; a presença dos metadados não é prova de licença válida.
"""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from .contracts import _Model

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Seconds = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
VisualAssetKind = Literal[
    "stock", "ai_image", "ai_clip", "diagram", "screen_capture", "text_animation"
]


class VisualBeat(_Model):
    """Intervalo em segundos relativos à cena e referência à mídia ou texto local."""

    model_config = ConfigDict(frozen=True)

    scene_id: NonBlank
    start_s: Seconds
    end_s: Seconds
    asset_kind: VisualAssetKind
    reference: NonBlank
    transition: NonBlank | None = None
    provenance: NonBlank | None = None
    license: NonBlank | None = None

    @model_validator(mode="after")
    def _validate_interval_and_rights(self):
        if self.start_s >= self.end_s:
            raise ValueError("start_s must be less than end_s")
        if self.asset_kind != "text_animation" and (
            self.provenance is None or self.license is None
        ):
            raise ValueError("media requires provenance and license")
        return self

    @property
    def duration_s(self) -> float:
        """Duração derivada do intervalo; ponte com o ``duration`` do plano.

        Não é campo persistido nem revalidado: decorre de ``start_s``/``end_s``.
        """
        return self.end_s - self.start_s
