"""Layout de pastas em disco. Todo ID é validado antes de virar caminho."""
import io
import os
import shutil
import uuid
from pathlib import Path

from PIL import Image, ImageOps

from ..application.media import AssetRefused
from ..domain.ids import check_cache_key, check_id
from ..domain.media import SIZE_FOR

import re

_FINAL = re.compile(r"final-[0-9a-f]{32}\.mp4")
_FINAL_ANY = re.compile(r"final-[0-9a-f]{32}\.(mp4|srt)")

MAX_INPUT_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 25_000_000  # ~0,5 GB de RAM ao decodificar; checagem explícita (não altera o limite global do PIL)


def video_dir(root: Path, project_id: str, video_id: str) -> Path:
    return Path(root) / "projects" / check_id(project_id) / "videos" / check_id(video_id)


def cache_path(root: Path, cache_key: str) -> Path:
    return Path(root) / "cache" / check_cache_key(cache_key)[:2] / cache_key


class FileAssetStore:
    """Grava imagens no cache por conteúdo (PNG normalizado no tamanho do aspecto). Escrita atômica: arquivo
    temporário + os.replace; cache hit não reescreve. Devolve caminho relativo (portável entre macOS e Windows)."""

    def __init__(self, root: Path):
        self.root = Path(root)

    @staticmethod
    def _valid(path: Path, size: tuple[int, int]) -> bool:
        try:
            with Image.open(path) as img:
                img.load()
                return img.format == "PNG" and img.size == size
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            return False

    def put(self, cache_key: str, data: bytes, aspect: str) -> str:
        key = check_cache_key(cache_key)
        size = SIZE_FOR.get(aspect)
        if size is None:
            raise AssetRefused(f"unsupported aspect {aspect!r}")
        dest = cache_path(self.root, key).with_name(key + ".png")
        relative = dest.relative_to(self.root).as_posix()
        if dest.exists() and self._valid(dest, size):
            return relative  # cache hit só vale se o arquivo ainda abre e tem o tamanho do aspecto
        if not data or len(data) > MAX_INPUT_BYTES:
            raise AssetRefused("image is empty or larger than 20 MB")
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.format not in ("PNG", "JPEG", "WEBP") or img.width * img.height > MAX_PIXELS:
                    raise AssetRefused("unsupported image format or too many pixels")
                fitted = ImageOps.fit(ImageOps.exif_transpose(img).convert("RGB"), size, method=Image.LANCZOS, centering=(0.5, 0.5))
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

    _VIDEO_EXT = {"video/mp4": ".mp4", "video/webm": ".webm"}

    def put_video(self, cache_key: str, data: bytes, mime: str = "video/mp4") -> str:
        """Armazena um vídeo (MP4/WebM) de forma atômica no cache de assets por conteúdo."""
        key = check_cache_key(cache_key)
        ext = self._VIDEO_EXT.get((mime or "").strip().lower())
        if ext is None:
            raise AssetRefused(f"unsupported video mime {mime!r}")
        if not data or len(data) > 100 * 1024 * 1024:
            raise AssetRefused("video is empty or larger than 100 MB")
        dest = cache_path(self.root, key).with_name(key + ext)
        relative = dest.relative_to(self.root).as_posix()
        if dest.exists() and dest.stat().st_size == len(data):
            return relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f"{key}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        return relative

    def delete(self, relative_path: str) -> bool:
        """Remove um arquivo dentro da raiz de storage (compensação segura; sem traversal)."""
        if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            return False
        root = self.root.resolve()
        try:
            target = (root / relative_path).resolve()
            target.relative_to(root)
        except (ValueError, OSError):
            return False
        if target.is_file():
            target.unlink(missing_ok=True)
            return True
        return False


class FileRenderStorage:
    """Arquivos do render: intermediários em `work/<job>` (descartáveis) e saída em `final.mp4`/`final.srt`, publicada de forma atômica."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def image_path(self, relative: str) -> Path:
        path = (self.root / relative)
        if Path(relative).is_absolute() or ".." in Path(relative).parts or self.root.resolve() not in path.resolve().parents:
            raise ValueError("asset path escapes the storage root")
        return path

    def work_dir(self, project_id: str, video_id: str, job_id: str) -> Path:
        path = video_dir(self.root, project_id, video_id) / "work" / check_id(job_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def narration_path(self, project_id: str, video_id: str, scene_id: str) -> Path:
        """W4.3: WAV de narração de uma cena, fora do `work/` descartável do render."""
        path = video_dir(self.root, project_id, video_id) / "narration" / f"{check_id(scene_id)}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def publish(self, project_id: str, video_id: str, job_id: str, mp4: Path, srt: str) -> str:
        """Arquivo próprio do job (`final-<job>.mp4/.srt`): render novo nunca sobrescreve o que está sendo servido.
        O .srt vai primeiro; o .mp4 (que o asset aponta) só aparece quando o par está completo."""
        folder = video_dir(self.root, project_id, video_id)
        folder.mkdir(parents=True, exist_ok=True)
        job = check_id(job_id)
        token = uuid.uuid4().hex
        tmp_mp4, tmp_srt = folder / f"{token}.mp4.tmp", folder / f"{token}.srt.tmp"
        try:
            shutil.copyfile(mp4, tmp_mp4)
            tmp_srt.write_text(srt, encoding="utf-8")
            os.replace(tmp_srt, folder / f"final-{job}.srt")
            os.replace(tmp_mp4, folder / f"final-{job}.mp4")
        finally:
            tmp_mp4.unlink(missing_ok=True)
            tmp_srt.unlink(missing_ok=True)
        return (folder / f"final-{job}.mp4").relative_to(self.root).as_posix()

    def resolve(self, relative: str, kind: str) -> Path | None:
        if kind not in ("mp4", "srt") or Path(relative).is_absolute() or ".." in Path(relative).parts:
            return None
        mp4 = self.root / relative
        try:
            inside = (self.root / "projects").resolve() in mp4.resolve().parents
        except OSError:
            return None
        if not inside or not _FINAL.fullmatch(mp4.name) or mp4.parent.parent.name != "videos":
            return None
        path = mp4 if kind == "mp4" else mp4.with_suffix(".srt")
        return path if path.is_file() else None

    def prune(self, project_id: str, video_id: str, keep: str) -> None:
        folder = video_dir(self.root, project_id, video_id)
        keep_name = Path(keep).name
        if not folder.is_dir():
            return
        for f in folder.iterdir():
            if _FINAL_ANY.fullmatch(f.name) and f.stem != Path(keep_name).stem:
                f.unlink(missing_ok=True)

    def sweep_work(self) -> int:
        """Na subida: apaga `work/<job>` que um processo anterior deixou (render interrompido). Devolve quantos."""
        removed = 0
        for work in (self.root / "projects").glob("*/videos/*/work/*"):
            if work.is_dir():
                shutil.rmtree(work, ignore_errors=True)
                removed += 1
        for folder in (self.root / "projects").glob("*/videos/*/work"):
            try:
                folder.rmdir()
            except OSError:
                pass
        return removed

    def cleanup(self, work_dir: Path) -> None:
        """Só apaga `projects/<p>/videos/<v>/work/<job>`; qualquer outro caminho é ignorado."""
        path = Path(work_dir)
        try:
            ok = path.parent.name == "work" and path.parent.parent.parent.name == "videos" and (self.root / "projects").resolve() in path.resolve().parents
        except OSError:
            ok = False
        if ok:
            shutil.rmtree(path, ignore_errors=True)
            try:
                path.parent.rmdir()  # só se ficou vazia
            except OSError:
                pass
