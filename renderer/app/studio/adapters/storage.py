"""Layout de pastas em disco. Todo ID é validado antes de virar caminho."""
import io
import os
import uuid
from pathlib import Path

from PIL import Image, ImageOps

from ..application.media import AssetRefused
from ..domain.ids import check_cache_key, check_id
from ..domain.media import SIZE_FOR

MAX_INPUT_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def video_dir(root: Path, project_id: str, video_id: str) -> Path:
    return Path(root) / "projects" / check_id(project_id) / "videos" / check_id(video_id)


def cache_path(root: Path, cache_key: str) -> Path:
    return Path(root) / "cache" / check_cache_key(cache_key)[:2] / cache_key


class FileAssetStore:
    """Grava imagens no cache por conteúdo (PNG normalizado no tamanho do aspecto). Escrita atômica: arquivo
    temporário + os.replace; cache hit não reescreve. Devolve caminho relativo (portável entre macOS e Windows)."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def put(self, cache_key: str, data: bytes, aspect: str) -> str:
        key = check_cache_key(cache_key)
        size = SIZE_FOR.get(aspect)
        if size is None:
            raise AssetRefused(f"unsupported aspect {aspect!r}")
        dest = cache_path(self.root, key).with_name(key + ".png")
        relative = dest.relative_to(self.root).as_posix()
        if dest.exists():
            return relative
        if not data or len(data) > MAX_INPUT_BYTES:
            raise AssetRefused("image is empty or larger than 20 MB")
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.format not in ("PNG", "JPEG", "WEBP") or img.width * img.height > MAX_PIXELS:
                    raise AssetRefused("unsupported image format or too many pixels")
                fitted = ImageOps.fit(img.convert("RGB"), size, method=Image.LANCZOS, centering=(0.5, 0.5))
        except AssetRefused:
            raise
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            raise AssetRefused("data is not a valid image") from None
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f"{key}.{uuid.uuid4().hex}.tmp")
        try:
            fitted.save(tmp, "PNG")
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        return relative
