"""Miniatura 1280x720 em JPEG (até 2 MB) a partir da imagem da primeira cena."""
import io
from pathlib import Path

from PIL import Image, ImageOps

SIZE = (1280, 720)
MAX_BYTES = 2 * 1024 * 1024


class PillowThumbnail:
    def make(self, image: Path) -> bytes:
        with Image.open(image) as img:
            fitted = ImageOps.fit(ImageOps.exif_transpose(img).convert("RGB"), SIZE, Image.LANCZOS, centering=(0.5, 0.35))
        for quality in (88, 80, 70, 60, 50):
            buf = io.BytesIO()
            fitted.save(buf, "JPEG", quality=quality, optimize=True)
            if buf.tell() <= MAX_BYTES:
                return buf.getvalue()
        raise ValueError("thumbnail does not fit in 2 MB")
