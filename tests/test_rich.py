import math
import os
import struct
import sys
import types
import wave
from pathlib import Path

import pytest

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app import rich  # noqa: E402
from app.studio.domain import render as domain_render  # noqa: E402
from app.studio.domain.render_plan_builder import DEFAULT_MUSIC_PARAMS  # noqa: E402


def write_tone(path, seconds, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(b"\x10\x00" * int(seconds * rate))


def test_scene_length_is_whole_frames():
    for speech in (1.0, 3.37, 5.123):
        total = domain_render.scene_length(speech)  # a função canônica, não uma cópia do rich
        assert math.isclose(total * domain_render.FPS, round(total * domain_render.FPS), abs_tol=1e-9)
        assert total >= speech + domain_render.LEAD + domain_render.TAIL


def test_rich_reexports_the_canonical_timing_and_music_constants():
    """Fonte única: o que `rich` expõe é o MESMO objeto do domínio, não uma recópia.

    Se alguém reintroduzir `FPS`/`LEAD`/`TAIL`/`scene_length` no `rich`, a identidade falha;
    se mudar `DEFAULT_MUSIC_PARAMS`, os defaults do `synth_music` acompanham.
    """
    assert rich.scene_length is domain_render.scene_length
    assert (rich.FPS, rich.LEAD, rich.TAIL) == (domain_render.FPS, domain_render.LEAD, domain_render.TAIL)
    assert rich.synth_music.__defaults__ == (DEFAULT_MUSIC_PARAMS["bpm"], DEFAULT_MUSIC_PARAMS["seed"])


def test_narration_track_matches_scene_lengths(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    write_tone(a, 2.0), write_tone(b, 3.3)
    lengths = rich.build_narration_track([a, b], tmp_path / "n.wav")
    assert len(lengths) == 2
    assert math.isclose(rich.wav_duration(tmp_path / "n.wav"), sum(lengths), abs_tol=0.01)  # áudio e vídeo alinhados


def test_music_is_original_bounded_and_nonsilent(tmp_path):
    rich.synth_music(6.0, tmp_path / "m.wav")
    with wave.open(str(tmp_path / "m.wav"), "rb") as w:
        assert w.getframerate() == rich.MUSIC_SR and math.isclose(w.getnframes() / w.getframerate(), 6.0, abs_tol=0.01)
        import numpy as np
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    assert 0.3 < np.abs(data).max() / 32767 <= 0.81 and data.std() > 500


# ---------- VS-06: precedência da voz (voz pedida > PIPER_VOICE > default) ----------

class _FakePiperVoice:
    """Síntese falsa: escreve 1 s de tom — nenhum modelo do Piper é carregado."""

    def synthesize_wav(self, text, wav):
        wav.setnchannels(1), wav.setsampwidth(2), wav.setframerate(22050)
        wav.writeframes(struct.pack("<h", 8000) * 22050)


def _fake_piper(monkeypatch, loaded):
    """Troca o `piper` por um carregador que registra o caminho pedido, e isola o estado global."""
    class FakePiper:
        @staticmethod
        def load(path):
            loaded.append(path)
            return _FakePiperVoice()

    monkeypatch.setitem(sys.modules, "piper", types.SimpleNamespace(PiperVoice=FakePiper))
    monkeypatch.setattr(rich.os.path, "isfile", lambda path: True)  # os arquivos não existem no teste
    monkeypatch.setattr(rich, "_voice", None)
    monkeypatch.setattr(rich, "_voice_loaded", None)
    monkeypatch.setattr(rich, "_requested_voice", None)


def test_synthesize_speech_prefers_the_requested_voice_over_the_env(monkeypatch, tmp_path):
    """Uma voz**pedida** vence o `PIPER_VOICE`: é a mesma que o ledger/cache registram."""
    loaded = []
    _fake_piper(monkeypatch, loaded)
    monkeypatch.setenv("PIPER_VOICE", "/opt/voices/from-env.onnx")
    with rich.use_voice("/opt/voices/requested.onnx"):
        assert rich.synthesize_speech("Olá, mundo.", tmp_path / "a.wav") == pytest.approx(1.0, abs=0.01)
    assert loaded == ["/opt/voices/requested.onnx"]


def test_synthesize_speech_uses_the_env_only_when_nothing_was_requested(monkeypatch, tmp_path):
    """`PIPER_VOICE` é fallback de deployment/teste: só decide quando ninguém pediu voz."""
    loaded = []
    _fake_piper(monkeypatch, loaded)
    monkeypatch.setenv("PIPER_VOICE", "/opt/voices/from-env.onnx")
    rich.synthesize_speech("Olá, mundo.", tmp_path / "b.wav")
    assert loaded == ["/opt/voices/from-env.onnx"]


def test_synthesize_speech_falls_back_to_the_deployment_default(monkeypatch, tmp_path):
    loaded = []
    _fake_piper(monkeypatch, loaded)
    monkeypatch.delenv("PIPER_VOICE", raising=False)
    rich.synthesize_speech("Olá, mundo.", tmp_path / "c.wav")
    assert loaded == [rich.DEFAULT_VOICE]


def test_synthesize_speech_names_the_missing_model_instead_of_falling_silent(monkeypatch, tmp_path):
    """Voz pedida sem arquivo em /opt/voices: falha dizendo **qual** modelo faltou (nunca silêncio)."""
    monkeypatch.setitem(sys.modules, "piper", types.SimpleNamespace(PiperVoice=object))
    monkeypatch.setattr(rich.os.path, "isfile", lambda path: False)
    monkeypatch.setattr(rich, "_voice", None)
    monkeypatch.setattr(rich, "_voice_loaded", None)
    with rich.use_voice("/opt/voices/pt_BR-inexistente.onnx"):
        with pytest.raises(FileNotFoundError, match="pt_BR-inexistente"):
            rich.synthesize_speech("Olá, mundo.", tmp_path / "d.wav")
