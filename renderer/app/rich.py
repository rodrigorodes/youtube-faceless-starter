"""Modo "rich": áudio (narração Piper, trilha sintetizada e faixa de narração) e utilidades de texto.

O alinhamento áudio↔vídeo e os parâmetros determinísticos da trilha **não** são recriados
aqui: vêm do domínio puro (``studio.domain.render`` para ``FPS``/``LEAD``/``TAIL``/
``scene_length`` e ``studio.domain.render_plan_builder`` para ``DEFAULT_MUSIC_PARAMS``). A
direção adapter→domínio é a correta e é o que impede que os dois lados divirjam em
silêncio. Funções bloqueantes: chame com asyncio.to_thread.

O vídeo (Ken Burns), a legenda queimada e a montagem final saíram daqui com o renderer
legado: agora são produzidos pelo executor do Render Plan
(``studio/adapters/render_plan_ffmpeg.py``), que consome deste módulo o áudio (narração e
trilha) e as fontes/``_wrap`` para compor os overlays de texto.
"""
import os
import wave
from contextlib import contextmanager

import numpy as np

# Fonte canônica do tempo de cena (reexportados para os consumidores deste módulo).
from .studio.domain.render import FPS, LEAD, TAIL, scene_length  # noqa: F401
from .studio.domain.render_plan_builder import DEFAULT_MUSIC_PARAMS

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MUSIC_SR = 44100
DEFAULT_VOICE = "/opt/voices/pt_BR-faber-medium.onnx"  # a voz baixada e conferida no Dockerfile
_voice = None
_voice_loaded = None  # caminho do modelo carregado em `_voice`
_requested_voice = None  # voz pedida pelo chamador (a voz efetiva do render, via porta Voice)


# ---------- áudio ----------

@contextmanager
def use_voice(voice_path):
    """Aponta a voz pedida para o próximo ``synthesize_speech`` e restaura o valor ao sair.

    A porta Voice (``PiperVoice``) usa isto para passar o arquivo derivado do modelo **efetivo**
    (estilo do canal/vídeo > ``STUDIO_VOICE``/``Project.config.voice``). Precedência final:
    voz pedida aqui > ``PIPER_VOICE`` > ``DEFAULT_VOICE``. ``PIPER_VOICE`` é só o **fallback de
    deployment/teste**: quem manda é quem pede (a mesma voz que o ledger/cache registra).
    """
    global _requested_voice
    previous = _requested_voice
    _requested_voice = voice_path
    try:
        yield
    finally:
        _requested_voice = previous


def synthesize_speech(text, path):
    """Narração pt-BR com Piper. Voz: voz pedida > PIPER_VOICE > default. Devolve a duração (s).

    A voz pedida (via ``use_voice``) vence porque é a mesma que o estilo/projeto resolveram e que
    o ledger/cache registram — síntese e registro não podem divergir. ``PIPER_VOICE`` é apenas o
    fallback de deployment/teste, usado quando ninguém pediu uma voz; ``DEFAULT_VOICE`` é o último
    recurso.
    """
    global _voice, _voice_loaded
    wanted = _requested_voice or os.getenv("PIPER_VOICE") or DEFAULT_VOICE
    if _voice is None or _voice_loaded != wanted:
        if not os.path.isfile(wanted):
            # Nunca cair para outra voz em silêncio: falha dizendo qual modelo foi pedido.
            raise FileNotFoundError(f"voz do Piper não encontrada para o modelo pedido: {wanted}")
        from piper import PiperVoice
        _voice = PiperVoice.load(wanted)
        _voice_loaded = wanted
    with wave.open(str(path), "wb") as wav:
        _voice.synthesize_wav(text, wav)
    return wav_duration(path)


def wav_duration(path):
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


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


def synth_music(seconds, path, bpm=DEFAULT_MUSIC_PARAMS["bpm"], seed=DEFAULT_MUSIC_PARAMS["seed"]):
    """Loop eletrônico original (house/minimal) gerado por síntese. Sem samples nem músicas de terceiros.

    ``bpm``/``seed`` são os mesmos parâmetros determinísticos que o Render Plan carrega em
    ``GeneratedAudioSource.params`` (``DEFAULT_MUSIC_PARAMS``): quem executa tem de honrar o
    que o plano documenta, senão o áudio diverge do fingerprint que o cache usa.
    """
    sr = MUSIC_SR
    n = int(seconds * sr)
    out = np.zeros(n)
    rng = np.random.default_rng(seed)
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


# ---------- layout de texto ----------

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
