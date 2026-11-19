"""Veo (clipes de vídeo): desligado por padrão. A estimativa de custo é conservadora, então o CostGuard recusa com
teto 0 antes de qualquer chamada. Preço conferido em out/2026: Veo 3.1 de US$ 0,05/s (Lite 720p) a US$ 0,60/s (4K);
clipes de 4 a 8 s. A geração em si ainda não está implementada."""
from ..application.ports import ImageResult, ModelUnavailable


class VeoImage:
    name = "veo"

    def __init__(self, model: str, usd_per_second: float = 0.40, seconds: int = 8):
        self.model, self._rate, self._seconds = model, usd_per_second, seconds

    def cost_estimate(self, prompt: str) -> float:
        return self._rate * self._seconds

    def generate(self, prompt: str, *, aspect: str = "9:16") -> ImageResult:
        raise ModelUnavailable("Veo clip generation is not implemented in this version")
