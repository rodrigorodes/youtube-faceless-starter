"""Montagem do modo "rich": imagens (Ken Burns), narração (Piper), trilha original sintetizada e legendas.

Sem dependência do restante do app. Funções bloqueantes: chame com asyncio.to_thread.
"""
import io
import math
import os
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1080, 1920
FPS = 25
LEAD, TAIL = 0.30, 0.50  # silêncio antes/depois de cada fala (s)
FADE = 0.25
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MUSIC_SR = 44100
_voice = None


# ---------- áudio ----------

def synthesize_speech(text, path):
    """Narração pt-BR com Piper (voz definida em PIPER_VOICE). Devolve a duração em segundos."""
    global _voice
    from piper import PiperVoice
    if _voice is None:
        _voice = PiperVoice.load(os.getenv("PIPER_VOICE", "/opt/voices/pt_BR-faber-medium.onnx"))
    with wave.open(str(path), "wb") as wav:
        _voice.synthesize_wav(text, wav)
    return wav_duration(path)


def wav_duration(path):
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def scene_length(speech_seconds):
    """Duração da cena em quadros inteiros, para áudio e vídeo ficarem alinhados."""
    return math.ceil((LEAD + speech_seconds + TAIL) * FPS) / FPS


def build_narration_track(speech_wavs, out_path):
    """Junta as falas com silêncio de lead/tail. Devolve as durações (s) de cada cena."""
    lengths, rate, chunks = [], None, []
    for wav_path in speech_wavs:
        with wave.open(str(wav_path), "rb") as wav:
            rate = rate or wav.getframerate()
            width, channels = wav.getsampwidth(), wav.getnchannels()
            frames = wav.readframes(wav.getnframes())
            seconds = wav.getnframes() / wav.getframerate()
        total = scene_length(seconds)
        lengths.append(total)
        pad_front = int(LEAD * rate) * width * channels
        pad_back = int(round(total * rate)) * width * channels - pad_front - len(frames)
        chunks.append(b"\x00" * pad_front + frames + b"\x00" * max(0, pad_back))
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(b"".join(chunks))
    return lengths


def synth_music(seconds, path, bpm=122):
    """Loop eletrônico original (house/minimal) gerado por síntese. Sem samples nem músicas de terceiros."""
    sr = MUSIC_SR
    n = int(seconds * sr)
    out = np.zeros(n)
    rng = np.random.default_rng(7)
    beat = 60.0 / bpm

    def put(sig, start):
        i = int(start * sr)
        if 0 <= i < n:
            j = min(n, i + len(sig))
            out[i:j] += sig[: j - i]

    kt = np.arange(int(0.30 * sr)) / sr
    kick = np.sin(2 * np.pi * (45 * kt + 90 * (1 - np.exp(-25 * kt)) / 25)) * np.exp(-kt * 11)
    ht = np.arange(int(0.06 * sr)) / sr
    hat = np.diff(rng.standard_normal(len(ht) + 1)) * np.exp(-ht * 70) * 0.35
    ct = np.arange(int(0.16 * sr)) / sr
    clap = np.diff(rng.standard_normal(len(ct) + 1)) * np.exp(-ct * 28) * 0.4
    bass_notes = [55.0, 55.0, 65.41, 49.0]  # A1 A1 C2 G1
    bar = 4 * beat
    bars = int(seconds / bar) + 1
    for b in range(bars):
        t0 = b * bar
        drums = b >= 2
        for k in range(4):
            tb = t0 + k * beat
            if drums:
                put(kick * 0.95, tb)
                if k in (1, 3):
                    put(clap, tb)
            put(hat, tb + beat / 2)  # contratempo
            if b >= 4:
                put(hat * 0.5, tb + beat / 4)
        if drums:
            f = bass_notes[b % 4]
            for k in range(4):
                bt = np.arange(int(0.26 * sr)) / sr
                note = (np.sin(2 * np.pi * f * bt) + 0.35 * np.sin(2 * np.pi * 2 * f * bt)) * np.exp(-bt * 9) * 0.55
                put(note, t0 + k * beat + beat / 2)  # baixo no contratempo
    t = np.arange(n) / sr
    pad = sum(np.sin(2 * np.pi * f * t + i) for i, f in enumerate((220.0, 261.63, 329.63, 392.0)))
    pad *= (0.5 + 0.5 * np.sin(2 * np.pi * t / (bar * 2))) * 0.035
    mix = out + pad
    fade_in, fade_out = min(2.0, seconds / 4), min(3.0, seconds / 4)
    env = np.ones(n)
    env[: int(fade_in * sr)] = np.linspace(0, 1, int(fade_in * sr))
    env[n - int(fade_out * sr):] = np.linspace(1, 0, int(fade_out * sr))
    mix = np.tanh(mix * 1.2) * env
    mix = mix / max(1e-9, np.max(np.abs(mix))) * 0.8
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes((mix * 32767).astype("<i2").tobytes())


# ---------- imagem ----------

def cover_image(data, dst):
    """Recorta/escala a imagem recebida para 1080x1920 (cobrindo o quadro)."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    ImageOps.fit(img, (W, H), method=Image.LANCZOS, centering=(0.5, 0.5)).save(dst)


def placeholder_image(index, dst):
    """Fundo em degradê (sem rede), usado só com IMAGE_PROVIDER=placeholder."""
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        ratio = y / H
        px.line([(0, y), (W, y)], fill=(int(20 + 60 * ratio), int(10 + 20 * ratio + index * 6), int(60 + 90 * (1 - ratio))))
    img.save(dst)


def _wrap(draw, text, font, max_width):
    lines, current = [], ""
    for word in text.split():
        candidate = (current + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def make_overlay(label, caption, dst, disclosure="Ilustração gerada por IA"):
    """PNG transparente com selo do dia, legenda e aviso de imagem sintética (respeita as margens da UI dos Shorts)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    small = ImageFont.truetype(FONT, 30)
    draw.text((60, 96), disclosure, font=small, fill=(255, 255, 255, 190))
    if label:
        badge = ImageFont.truetype(FONT_BOLD, 46)
        box = draw.textbbox((0, 0), label, font=badge)
        bw, bh = box[2] - box[0], box[3] - box[1]
        draw.rounded_rectangle((60, 160, 60 + bw + 56, 160 + bh + 40), radius=26, fill=(255, 0, 140, 235))
        draw.text((60 + 28, 160 + 14), label, font=badge, fill="white")
    if caption:
        font = ImageFont.truetype(FONT_BOLD, 58)
        lines = _wrap(draw, caption, font, W - 200)[:5]
        line_h = 78
        height = len(lines) * line_h + 64
        bottom = 1560
        top = bottom - height
        draw.rounded_rectangle((50, top, W - 50, bottom), radius=36, fill=(0, 0, 0, 165))
        y = top + 32
        for line in lines:
            draw.text((102, y + 2), line, font=font, fill=(0, 0, 0, 200))
            draw.text((100, y), line, font=font, fill="white")
            y += line_h
    img.save(dst)


# ---------- vídeo ----------

def _run(cmd, timeout=300):
    subprocess.run(cmd, check=True, timeout=timeout, capture_output=True)


def render_scene(bg_png, overlay_png, seconds, index, out_mp4):
    """Cena com Ken Burns (zoom in/out e pan alternados), legenda e fades."""
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
    fade_out = max(0.0, seconds - FADE)
    graph = (f"[0:v]scale=1620:2880:flags=lanczos,zoompan=z='{zoom}':x='{x}':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p[bg];"
             f"[bg][1:v]overlay=0:0:format=auto,fade=t=in:st=0:d={FADE},fade=t=out:st={fade_out:.3f}:d={FADE}[v]")
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(bg_png), "-i", str(overlay_png),
          "-filter_complex", graph, "-map", "[v]", "-frames:v", str(frames), "-r", str(FPS),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", str(out_mp4)])


def assemble(scene_mp4s, narration_wav, music_wav, concat_txt, output):
    """Concatena as cenas e mixa narração + trilha (ducking sob a voz) com normalização de volume."""
    Path(concat_txt).write_text("".join(f"file '{Path(p).as_posix()}'\n" for p in scene_mp4s), encoding="utf-8")
    silent = Path(concat_txt).with_name("video_only.mp4")
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", str(silent)])
    mix = ("[1:a]aresample=44100,pan=stereo|c0=c0|c1=c0,asplit=2[nar][nsc];"
           "[2:a]volume=0.40,pan=stereo|c0=c0|c1=c0[mus];"
           "[mus][nsc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck];"
           "[duck][nar]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(narration_wav), "-i", str(music_wav),
          "-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
          "-shortest", "-movflags", "+faststart", str(output)])
