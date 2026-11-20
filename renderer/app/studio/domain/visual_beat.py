"""Contrato de um intervalo visual; não executa renderização nem acessa mídia."""

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
