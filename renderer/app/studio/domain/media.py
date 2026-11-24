"""Regras de mídia (domínio puro): estilo do prompt de imagem, aspecto por formato e tamanhos finais."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .contracts import VideoFormat

_COMMON = ", cinematic photography, {orientation} {aspect} composition, rich colors, no text, no logos, no recognizable real people"
IMAGE_STYLE = {
    "9:16": _COMMON.format(orientation="vertical", aspect="9:16"),
    "16:9": _COMMON.format(orientation="horizontal", aspect="16:9"),
}
ASPECT_FOR = {VideoFormat.short: "9:16", VideoFormat.long: "16:9"}
SIZE_FOR = {"9:16": (1080, 1920), "16:9": (1920, 1080)}


def build_image_prompt(prompt: str, aspect: str) -> str:
    return prompt.strip() + IMAGE_STYLE[aspect]


def strip_style(prompt: str) -> str:
    """Prompt original, sem o sufixo de estilo (provedores de busca, como o stock, usam só o tema)."""
    for suffix in IMAGE_STYLE.values():
        if prompt.endswith(suffix):
            return prompt[: -len(suffix)]
    return prompt


@dataclass(frozen=True)
class MediaCandidate:
    """Candidato de mídia de uma busca agnóstica de fornecedor.

    Licença, proveniência (``source_url``), URL do arquivo e atribuição são obrigatórias: um
    candidato sem esses dados nunca é aceito — o core não inventa licença nem crédito. Custo e
    dimensões são opcionais porque nem todo provedor os informa. O fornecedor concreto não
    aparece neste contrato; o adaptador é quem o conhece.
    """

    license: str
    source_url: str
    url: str
    attribution: str
    author: str = ""
    media_id: str = ""
    media_type: str = "image"
    width: int | None = None
    height: int | None = None
    cost_usd: Decimal | None = None
    duration_s: float | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("license", "source_url", "url", "attribution", "media_type"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if self.cost_usd is not None:
            amount = Decimal(str(self.cost_usd))
            if not amount.is_finite() or amount < 0:
                raise ValueError("cost_usd must be a finite non-negative Decimal")
            object.__setattr__(self, "cost_usd", amount)
        for name in ("width", "height"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
                raise ValueError(f"{name} must be a positive integer when provided")
        if self.duration_s is not None:
            if isinstance(self.duration_s, bool) or not isinstance(self.duration_s, (int, float)) or self.duration_s <= 0:
                raise ValueError("duration_s must be a positive number when provided")
            object.__setattr__(self, "duration_s", float(self.duration_s))
        if self.tags:
            if isinstance(self.tags, (list, tuple, set)):
                object.__setattr__(self, "tags", tuple(str(t) for t in self.tags))
            else:
                object.__setattr__(self, "tags", (str(self.tags),))
        else:
            object.__setattr__(self, "tags", ())

