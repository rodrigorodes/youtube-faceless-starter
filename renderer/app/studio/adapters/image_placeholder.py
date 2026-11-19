"""ImageModel local: degradê determinístico (sem rede, sem custo). Útil para testar o fluxo e como último recurso."""
import hashlib
import io

from PIL import Image, ImageOps

from ..application.ports import ImageResult
from ..domain.contracts import UsageEntry
from ..domain.media import SIZE_FOR


class PlaceholderImage:
    name = "placeholder"

    def __init__(self, model: str):
        self.model = model

    def cost_estimate(self, prompt: str) -> float:
        return 0.0

    def generate(self, prompt: str, *, aspect: str = "9:16") -> ImageResult:
        digest = hashlib.sha256(prompt.encode("utf-8")).digest()
        dark = (digest[0] // 6, digest[1] // 6, 40 + digest[2] // 5)
        light = (60 + digest[3] // 2, 30 + digest[4] // 3, 90 + digest[5] // 2)
        gradient = Image.linear_gradient("L").resize(SIZE_FOR[aspect])
        buf = io.BytesIO()
        ImageOps.colorize(gradient, dark, light).save(buf, "PNG")
        return ImageResult(data=buf.getvalue(), mime="image/png", license="CC0-1.0 (gerada localmente pelo estúdio)",
                           usage=UsageEntry(step="image", provider=self.name, model=self.model, cost_usd=0.0))
