"""Sandboxed media probe & decode adapter (Pillow for images, ffprobe+ffmpeg for videos)."""
from __future__ import annotations

import io
import json
import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from ..application.media import AssetRefused
from ..application.ports import ProbedMedia

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_DIM = 8192
MAX_VIDEO_DIM = 4096
MAX_VIDEO_DURATION_S = 3600.0
ALLOWED_VIDEO_CODECS_BY_MIME = {
    "video/mp4": frozenset({"h264", "hevc", "av1"}),
    "video/webm": frozenset({"vp8", "vp9", "av1"}),
}

_IMAGE_FORMAT_FOR_MIME = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
}
_VIDEO_CONTAINER_TOKENS = {
    "video/mp4": frozenset({"mp4", "mov"}),
    "video/webm": frozenset({"webm", "matroska"}),
}
_VIDEO_FORBIDDEN_TOKENS = {
    "video/mp4": frozenset({"webm", "matroska"}),
    "video/webm": frozenset({"mp4", "mov"}),
}
_VIDEO_TEMP_EXT = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


class FfmpegMediaProbe:
    """Validates external media via real magic bytes, Pillow decode, and ffprobe + 1-frame ffmpeg decode."""

    def __init__(self, *, probe_timeout_s: float = 10.0, decode_timeout_s: float = 15.0):
        self.probe_timeout_s = probe_timeout_s
        self.decode_timeout_s = decode_timeout_s

    def probe(self, data: bytes, declared_mime: str) -> ProbedMedia:
        mime = (declared_mime or "").strip().lower()
        if not data:
            raise AssetRefused("empty media payload")
        if mime in _IMAGE_FORMAT_FOR_MIME:
            return self._probe_image(data, mime)
        if mime in _VIDEO_CONTAINER_TOKENS:
            return self._probe_video(data, mime)
        raise AssetRefused(f"unsupported media mime {declared_mime!r}")

    def _probe_image(self, data: bytes, mime: str) -> ProbedMedia:
        if len(data) > MAX_IMAGE_BYTES:
            raise AssetRefused("image exceeds 20MB limit")
        if mime == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AssetRefused("corrupted or fake png magic bytes")
        if mime == "image/jpeg" and not data.startswith(b"\xff\xd8\xff"):
            raise AssetRefused("corrupted or fake jpeg magic bytes")
        if mime == "image/webp" and (len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP"):
            raise AssetRefused("corrupted or fake webp magic bytes")

        expected_fmt = _IMAGE_FORMAT_FOR_MIME[mime]
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.format != expected_fmt:
                    raise AssetRefused(f"image format {img.format!r} does not match declared mime {mime!r}")
                w, h = img.size
                if w <= 0 or h <= 0 or w > MAX_IMAGE_DIM or h > MAX_IMAGE_DIM or (w * h) > MAX_IMAGE_PIXELS:
                    raise AssetRefused(f"image dimensions {w}x{h} exceed safety bounds")
                img.verify()
            with Image.open(io.BytesIO(data)) as img_decode:
                img_decode.load()
        except AssetRefused:
            raise
        except (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError):
            raise AssetRefused("corrupted or undecodable image payload") from None

        return ProbedMedia(
            mime=mime,
            kind="image",
            format_name=expected_fmt,
            width=w,
            height=h,
            size_bytes=len(data),
        )

    def _probe_video(self, data: bytes, mime: str) -> ProbedMedia:
        if len(data) < 16:
            raise AssetRefused("video payload is too small")
        if len(data) > MAX_VIDEO_BYTES:
            raise AssetRefused("video exceeds 100MB limit")

        ext = _VIDEO_TEMP_EXT[mime]
        with tempfile.TemporaryDirectory(prefix="media_probe_") as tmp_dir:
            tmp_path = Path(tmp_dir) / f"probe{ext}"
            tmp_path.write_bytes(data)

            info = self._run_ffprobe(tmp_path)
            fmt = info.get("format") or {}
            fmt_name = (fmt.get("format_name") or "").lower()
            tokens = {t.strip() for t in fmt_name.split(",") if t.strip()}
            if not (tokens & _VIDEO_CONTAINER_TOKENS[mime]) or (tokens & _VIDEO_FORBIDDEN_TOKENS[mime]):
                raise AssetRefused(f"video container {fmt_name!r} does not match declared mime {mime!r}")

            vstreams = [s for s in (info.get("streams") or []) if s.get("codec_type") == "video"]
            if not vstreams:
                raise AssetRefused("video has no decodable video stream")

            vstream = vstreams[0]
            codec = (vstream.get("codec_name") or "").strip().lower()
            allowed_codecs = ALLOWED_VIDEO_CODECS_BY_MIME[mime]
            if codec not in allowed_codecs:
                raise AssetRefused(f"disallowed or unknown video codec {codec!r} for {mime}")

            width = int(vstream.get("width") or 0)
            height = int(vstream.get("height") or 0)
            if width <= 0 or height <= 0 or width > MAX_VIDEO_DIM or height > MAX_VIDEO_DIM:
                raise AssetRefused(f"video dimensions {width}x{height} exceed safety bounds")

            raw_duration = vstream.get("duration") or fmt.get("duration")
            try:
                duration_s = float(raw_duration)
            except (TypeError, ValueError):
                duration_s = 0.0
            if not math.isfinite(duration_s) or duration_s <= 0.0 or duration_s > MAX_VIDEO_DURATION_S:
                raise AssetRefused(f"invalid or out-of-bounds video duration {raw_duration!r}")

            self._decode_first_frame(tmp_path)

        return ProbedMedia(
            mime=mime,
            kind="video",
            format_name=fmt_name,
            width=width,
            height=height,
            duration_s=duration_s,
            video_codec=codec,
            size_bytes=len(data),
        )

    def _run_ffprobe(self, path: Path) -> dict:
        cmd = [
            "ffprobe", "-v", "error", "-protocol_whitelist", "file",
            "-print_format", "json", "-show_format", "-show_streams", str(path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.probe_timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise AssetRefused("video probe timed out") from None
        except OSError as exc:
            raise AssetRefused(f"video probe unavailable: {exc}") from None
        if proc.returncode != 0:
            raise AssetRefused("video probe failed: corrupt or invalid container")
        try:
            return json.loads(proc.stdout)
        except ValueError:
            raise AssetRefused("video probe returned invalid metadata") from None

    def _decode_first_frame(self, path: Path) -> None:
        cmd = [
            "ffmpeg", "-v", "error", "-protocol_whitelist", "file",
            "-xerror", "-err_detect", "explode", "-threads", "1",
            "-i", str(path), "-frames:v", "1", "-f", "null", "-",
        ]
        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.decode_timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise AssetRefused("video frame decode timed out") from None
        except OSError as exc:
            raise AssetRefused(f"video decode unavailable: {exc}") from None
        if proc.returncode != 0:
            raise AssetRefused("video frame decode failed: corrupt bitstream")
