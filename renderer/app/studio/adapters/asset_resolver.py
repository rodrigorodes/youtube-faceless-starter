"""``AssetResolver`` no storage local (RP-019..RP-022): toca disco, sem FFmpeg/subprocess.

Resolve ``AssetReference`` → ``AssetDescriptor`` para os quatro tipos de mídia:

- ``image`` / ``graphic``: sonda o arquivo com **Pillow** (formato→codec e dimensões
  reais) e confere o ``content_sha256`` dos bytes;
- ``video``: **não** há ffprobe nesta fatia (é do executor, RP-05). O codec, a
  resolução e a duração vêm **declarados** no ``metadata`` do ``AssetReference`` e são
  validados — se faltarem, a resolução falha claro em vez de inventar;
- ``text``: animação local, isenta de mídia externa: sem arquivo, sem sondagem.

Em todos os casos externos confere existência do arquivo e o hash do conteúdo. O
``content_sha256`` é a identidade **física** do asset (correção C1): nunca o
``assets.cache_key``, que é hash de entrada.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

from ..domain.asset_resolver import (
    IMAGE_CODECS,
    VIDEO_CODECS,
    AssetDescriptor,
    AssetResolutionError,
)
from ..domain.render_plan import AssetReference


class LocalAssetResolver:
    """Resolve assets contra uma raiz de storage. Não importa FFmpeg nem usa subprocess."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def resolve(self, reference: AssetReference) -> AssetDescriptor:
        if reference.media_type == "text":
            return self._local_text(reference)
        if not (reference.license or "").strip():  # RP-020: mídia externa exige licença registrada
            raise AssetResolutionError(f"asset {reference.asset_id!r} has no registered license")
        path = self._path(reference.uri)
        location = self._relative(path)
        if not path.is_file():
            return self._descriptor(reference, available=False, location=location)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != reference.content_sha256:
            raise AssetResolutionError(
                f"asset {reference.asset_id!r} content hash {digest} does not match the manifest "
                f"{reference.content_sha256}"
            )
        byte_size = path.stat().st_size
        if reference.media_type in ("image", "graphic"):
            codec, width, height = self._probe_image(path, reference)
            return self._descriptor(reference, available=True, location=location, byte_size=byte_size,
                                    codec=codec, width=width, height=height)
        codec, width, height, duration_ticks = self._declared_video(reference)
        return self._descriptor(reference, available=True, location=location, byte_size=byte_size,
                                codec=codec, width=width, height=height, duration_ticks=duration_ticks)

    # ------------------------------------------------------------------ #
    # Internos
    # ------------------------------------------------------------------ #

    def _local_text(self, reference: AssetReference) -> AssetDescriptor:
        return self._descriptor(reference, available=True, location="")

    def _descriptor(self, reference: AssetReference, *, available: bool, location: str,
                    byte_size: int | None = None, codec: str | None = None,
                    width: int | None = None, height: int | None = None,
                    duration_ticks: int | None = None) -> AssetDescriptor:
        return AssetDescriptor(
            asset_id=reference.asset_id,
            asset_version=reference.asset_version,
            uri=reference.uri,
            content_sha256=reference.content_sha256,
            media_type=reference.media_type,
            license=reference.license,
            attribution=reference.attribution,
            source_url=reference.source_url,
            location=location,
            available=available,
            codec=codec,
            width=width,
            height=height,
            duration_ticks=duration_ticks,
            byte_size=byte_size,
        )

    def _path(self, uri: str) -> Path:
        relative = Path(uri)
        if relative.is_absolute() or ".." in relative.parts:
            raise AssetResolutionError(f"asset uri {uri!r} escapes the storage root")
        return self.root / relative

    def _relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:  # pragma: no cover - _path já garante que está sob a raiz
            return path.as_posix()

    @staticmethod
    def _probe_image(path: Path, reference: AssetReference) -> tuple[str, int, int]:
        try:
            with Image.open(path) as img:
                codec = (img.format or "").lower()
                width, height = img.size
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            raise AssetResolutionError(f"asset {reference.asset_id!r} is not a readable image") from None
        if codec not in IMAGE_CODECS:
            raise AssetResolutionError(f"unsupported image codec {codec!r} for asset {reference.asset_id!r}")
        if width < 1 or height < 1:
            raise AssetResolutionError(f"asset {reference.asset_id!r} has an empty resolution")
        return codec, width, height

    @staticmethod
    def _declared_video(reference: AssetReference) -> tuple[str, int, int, int]:
        meta = reference.metadata
        try:
            codec = meta["codec"].strip().lower()
            width, height, duration_ticks = int(meta["width"]), int(meta["height"]), int(meta["duration_ticks"])
        except KeyError as exc:
            raise AssetResolutionError(
                f"video asset {reference.asset_id!r} needs the declared metadata {exc.args[0]!r}; "
                f"this slice does not probe video (no FFmpeg)"
            ) from None
        except (AttributeError, TypeError, ValueError):
            raise AssetResolutionError(f"declared video metadata for asset {reference.asset_id!r} is not valid") from None
        if codec not in VIDEO_CODECS:
            raise AssetResolutionError(f"unsupported video codec {codec!r} for asset {reference.asset_id!r}")
        if width < 1 or height < 1 or duration_ticks < 1:
            raise AssetResolutionError(f"declared video metadata for asset {reference.asset_id!r} must be positive")
        return codec, width, height, duration_ticks
