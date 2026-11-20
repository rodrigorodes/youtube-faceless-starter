"""QaAnalyzer com ffprobe + ffmpeg (ebur128, silencedetect, blackdetect). Só mede; quem decide é o domínio."""
import json
import re
import subprocess
from pathlib import Path

_LUFS = re.compile(r"Integrated loudness:\s*\n\s*I:\s+(-?[\d.]+|-inf)\s+LUFS")
_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)")
_BLACK = re.compile(r"black_duration:\s*([\d.]+)")


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
    except subprocess.TimeoutExpired:
        raise RuntimeError("media analysis timed out") from None


class FfmpegQa:
    def __init__(self, timeout: int = 900):
        self.timeout = timeout

    def _audio_stats(self, path: Path, duration: float) -> tuple[float | None, float]:
        """(LUFS integrado, fração de silêncio) do áudio do arquivo."""
        run = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=framelog=quiet,silencedetect=n=-45dB:d=0.5",
                    "-f", "null", "-"], self.timeout)
        if run.returncode != 0:
            raise RuntimeError("media analysis failed")
        log = run.stderr
        lufs = None
        if m := list(_LUFS.finditer(log)):
            lufs = None if m[-1].group(1) == "-inf" else float(m[-1].group(1))
        silent = sum(float(m.group(2)) for m in _SILENCE_END.finditer(log))
        starts, ends = _SILENCE_START.findall(log), _SILENCE_END.findall(log)
        if len(starts) > len(ends):  # silêncio que vai até o fim do arquivo
            silent += max(0.0, duration - float(starts[-1]))
        return lufs, (round(min(1.0, silent / duration), 4) if duration else 1.0)

    def analyze(self, path: Path, narration: Path | None = None) -> dict:
        probe = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)], 60)
        try:
            info = json.loads(probe.stdout)
            video = next(s for s in info["streams"] if s["codec_type"] == "video")
            duration = float(info["format"]["duration"])
            width, height = int(video["width"]), int(video["height"])
            has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
        except (ValueError, KeyError, StopIteration, TypeError):
            raise RuntimeError("could not read the rendered media file") from None
        black_run = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf", "blackdetect=d=0.5:pix_th=0.10", "-f", "null", "-"], self.timeout)
        if black_run.returncode != 0:
            raise RuntimeError("media analysis failed")
        black = sum(float(m.group(1)) for m in _BLACK.finditer(black_run.stderr))
        lufs, silence = self._audio_stats(path, duration) if has_audio else (None, 1.0)
        out = {"duration_s": round(duration, 3), "width": width, "height": height, "has_audio": has_audio,
               "integrated_lufs": lufs, "silence_ratio": silence,
               "black_ratio": round(min(1.0, black / duration), 4) if duration else 1.0}
        if narration is not None:  # a trilha musical enche a mistura final: a fala só se prova na voz isolada
            n = Path(narration)
            if n.is_file():
                n_lufs, n_silence = self._audio_stats(n, _duration(n))
                out.update(narration_lufs=n_lufs, narration_silence_ratio=n_silence)
            # sem a faixa de voz as métricas ficam ausentes e o domínio reprova (falha fechada)
        return out


def _duration(path: Path) -> float:
    run = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], 60)
    try:
        return float(run.stdout.strip())
    except ValueError:
        raise RuntimeError("could not read the narration track") from None
