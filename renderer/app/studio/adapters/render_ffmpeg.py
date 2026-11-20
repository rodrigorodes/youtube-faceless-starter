"""Renderer FFmpeg: cenas com Ken Burns, selo, aviso de imagem sintética e legenda queimada por trecho (Pillow),
narração + trilha original sintetizada com ducking e loudnorm. Short 1080x1920 e long 1920x1080.
Reaproveita a mixagem do modo rich (app/rich.py), que continua intacto para o /videos."""
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ... import rich
from ..application.ports import RenderSpec
from ..domain.contracts import VideoFormat
from ..domain.render import FADE_S, FPS, NARRATION_FILE, SIZE, Cue

FONT, FONT_BOLD = rich.FONT, rich.FONT_BOLD
_LAYOUT = {  # margens que respeitam a interface dos Shorts (vertical) e a área segura do vídeo horizontal
    VideoFormat.short: {"caption_bottom": 1560, "caption_font": 58, "caption_side": 100, "box_side": 50, "line_h": 78},
    VideoFormat.long: {"caption_bottom": 960, "caption_font": 50, "caption_side": 300, "box_side": 250, "line_h": 68},
}


def _wrap(draw, text, font, max_width):
    return rich._wrap(draw, text, font, max_width)


def static_overlay(fmt: VideoFormat, label: str, disclosure: str, dst: Path) -> None:
    w, h = SIZE[fmt]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((60, 96), disclosure, font=ImageFont.truetype(FONT, 30), fill=(255, 255, 255, 190))
    if label:
        badge = ImageFont.truetype(FONT_BOLD, 46)
        box = draw.textbbox((0, 0), label, font=badge)
        bw, bh = box[2] - box[0], box[3] - box[1]
        draw.rounded_rectangle((60, 160, 60 + bw + 56, 160 + bh + 40), radius=26, fill=(255, 0, 140, 235))
        draw.text((60 + 28, 160 + 14), label, font=badge, fill="white")
    img.save(dst)


def caption_overlay(fmt: VideoFormat, text: str, dst: Path) -> None:
    w, h = SIZE[fmt]
    lay = _LAYOUT[fmt]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_BOLD, lay["caption_font"])
    lines = _wrap(draw, text, font, w - 2 * lay["caption_side"])[:4]
    height = len(lines) * lay["line_h"] + 64
    bottom = lay["caption_bottom"]
    top = bottom - height
    draw.rounded_rectangle((lay["box_side"], top, w - lay["box_side"], bottom), radius=36, fill=(0, 0, 0, 165))
    y = top + 32
    for line in lines:
        draw.text((lay["caption_side"] + 2, y + 2), line, font=font, fill=(0, 0, 0, 200))
        draw.text((lay["caption_side"], y), line, font=font, fill="white")
        y += lay["line_h"]
    img.save(dst)


def _run(cmd: list[str], timeout: int = 600) -> None:
    try:
        subprocess.run(cmd, check=True, timeout=timeout, capture_output=True)
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or b"").decode("utf-8", "replace").strip()[-300:]
        raise RuntimeError(f"ffmpeg failed: {tail}") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg timed out") from None


def _scene_enable(start: float, end: float) -> str:
    """Intervalo semiaberto [a, b): dois trechos contíguos nunca aparecem juntos no mesmo quadro."""
    return f"gte(t,{start:.3f})*lt(t,{end:.3f})"


def _scene(fmt: VideoFormat, image: Path, static: Path, cues: list[tuple[Cue, Path]], seconds: float, index: int, out: Path) -> None:
    """Ken Burns + selo + legendas com `enable` por trecho + fades; os tempos das legendas são relativos à cena."""
    w, h = SIZE[fmt]
    frames = int(round(seconds * FPS))
    mode = index % 4
    if mode == 0:
        zoom, x = f"1+0.10*on/{frames}", "iw/2-(iw/zoom/2)"
    elif mode == 1:
        zoom, x = f"1.10-0.10*on/{frames}", "iw/2-(iw/zoom/2)"
    elif mode == 2:
        zoom, x = "1.12", f"(iw-iw/zoom)*on/{frames}"
    else:
        zoom, x = "1.12", f"(iw-iw/zoom)*(1-on/{frames})"
    parts = [f"[0:v]scale={int(w * 1.5)}:{int(h * 1.5)}:flags=lanczos,zoompan=z='{zoom}':x='{x}':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={FPS},format=yuv420p[b0]",
             "[b0][1:v]overlay=0:0:format=auto[o1]"]
    last = "o1"
    for n, (cue, _) in enumerate(cues, start=2):
        parts.append(f"[{last}][{n}:v]overlay=0:0:format=auto:enable='{_scene_enable(cue.start, cue.end)}'[o{n}]")
        last = f"o{n}"
    parts.append(f"[{last}]fade=t=in:st=0:d={FADE_S},fade=t=out:st={max(0.0, seconds - FADE_S):.3f}:d={FADE_S}[v]")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(image), "-i", str(static)]
    for _, png in cues:
        cmd += ["-i", str(png)]
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-frames:v", str(frames), "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", str(out)]
    _run(cmd)


class FfmpegRenderer:
    name = "ffmpeg"

    def __init__(self, model: str = "rich"):
        self.model = model

    def render(self, spec: RenderSpec, out_path: Path) -> Path:
        work = Path(spec.work_dir or Path(out_path).parent)
        work.mkdir(parents=True, exist_ok=True)
        fmt = spec.format
        narration = work / NARRATION_FILE
        lengths = rich.build_narration_track(spec.speech_wavs, narration)
        if any(abs(a - b) > 0.05 for a, b in zip(lengths, spec.scene_seconds)):
            raise RuntimeError("narration track does not match the planned scene lengths")
        total = sum(lengths)
        music = work / "music.wav"
        rich.synth_music(total + 1.0, music)
        if not spec.music:  # mantém o mesmo grafo de mixagem, com a trilha silenciada
            with wave.open(str(music), "wb") as w:
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(rich.MUSIC_SR)
                w.writeframes(b"\x00\x00" * int((total + 1.0) * rich.MUSIC_SR))
        mp4s, offset = [], 0.0
        for i, (scene, image, seconds) in enumerate(zip(spec.scenes, spec.images, lengths)):
            static = work / f"static_{i:03d}.png"
            static_overlay(fmt, scene.label, spec.disclosure, static)
            pngs = []
            for n, cue in enumerate(c for c in spec.cues if offset - 1e-6 <= c.start < offset + seconds):
                png = work / f"cue_{i:03d}_{n:02d}.png"
                caption_overlay(fmt, cue.text, png)
                pngs.append((Cue(max(0.0, cue.start - offset), min(seconds, cue.end - offset), cue.text), png))
            mp4 = work / f"scene_{i:03d}.mp4"
            _scene(fmt, image, static, pngs, seconds, i, mp4)
            mp4s.append(mp4)
            offset += seconds
        self._assemble(mp4s, narration, music, work, out_path, total)
        return Path(out_path)

    @staticmethod
    def _assemble(mp4s, narration: Path, music: Path, work: Path, out_path: Path, total: float) -> None:
        """Mesma mixagem do modo rich (ducking + loudnorm), com timeout proporcional à duração do vídeo."""
        timeout = int(300 + 3 * total)
        concat, silent = work / "concat.txt", work / "video_only.mp4"
        concat.write_text("".join(f"file '{Path(p).as_posix()}'\n" for p in mp4s), encoding="utf-8")
        _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent)], timeout)
        mix = ("[1:a]aresample=44100,pan=stereo|c0=c0|c1=c0,asplit=2[nar][nsc];"
               "[2:a]volume=0.40,pan=stereo|c0=c0|c1=c0[mus];"
               "[mus][nsc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck];"
               "[duck][nar]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
        _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(narration), "-i", str(music),
              "-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
              "-shortest", "-movflags", "+faststart", str(out_path)], timeout)
