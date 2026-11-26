"""Testes de conformidade para V4-02 — Professional Voice.

Cobre:
- V4-02.01 / V4-02.02: Preservação do contrato Voice e PiperVoice.
- V4-02.03 / V4-02.04: Homologação do Kokoro local e ElevenLabs BYOK.
- V4-02.05 / V4-02.06: Catálogo de vozes tipado e identidade vocal.
- V4-02.07 / V4-02.08: Ritmo, pausas e intenção emocional na narração.
- V4-02.09: Dicionário de pronúncia fonética PT-BR para tecnologia e nomes.
- V4-02.10 / V4-02.12: Inspeção técnica de áudio, detecção de clipping e silêncio.
- V4-02.13 / V4-02.14: Invalidação seletiva de cache por fingerprint e resiliência via FallbackVoice.
- V4-02.15: Roteamento de providers no container de composição.
"""
from __future__ import annotations

import array
import wave
from decimal import Decimal
from pathlib import Path

import pytest

from renderer.app.studio.adapters.voice_elevenlabs import ElevenLabsVoice
from renderer.app.studio.adapters.voice_fallback import FallbackVoice
from renderer.app.studio.adapters.voice_kokoro import KokoroVoice, is_kokoro_installed
from renderer.app.studio.adapters.voice_piper import PiperVoice
from renderer.app.studio.application.config import build
from renderer.app.studio.application.ports import ModelUnavailable, NeuralVoice, Voice
from renderer.app.studio.domain.provider import ProviderMissingCredential
from renderer.app.studio.domain.voice_audio import (
    CLIPPING_THRESHOLD,
    MIN_SPEECH_PEAK,
    AudioSpeechMetrics,
    inspect_speech_audio,
)
from renderer.app.studio.domain.voice_catalog import (
    VoiceGender,
    VoiceProfile,
    VoiceStyle,
)
from renderer.app.studio.composition.voice_catalog import (
    find_voice_profile,
    is_voice_profile_available,
    list_voice_catalog,
)
from renderer.app.studio.domain.voice_preprocessing import (
    DEFAULT_PRONUNCIATION_RULES,
    EmotionalIntention,
    PronunciationDictionary,
    apply_pacing_and_pauses,
    narration_fingerprint,
)


def _create_wav(path: Path, sample_rate: int = 24000, samples_seq: list[int] | None = None) -> Path:
    """Helper para criar arquivo WAV PCM 16-bit com amostras controladas."""
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = samples_seq if samples_seq is not None else [1500] * 2400  # 0.1s de tom seguro
    raw = array.array("h", samples).tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(raw)
    return path


class TestVoiceCatalogAndIdentity:
    """V4-02.05 e V4-02.06: Catálogo de vozes e perfis tipados."""

    def test_catalog_listing_and_filtering(self):
        all_voices = list_voice_catalog()
        assert len(all_voices) >= 4

        pt_voices = list_voice_catalog(language="pt-BR")
        assert len(pt_voices) >= 4
        assert all(v.language == "pt-BR" for v in pt_voices)

        local_voices = list_voice_catalog(is_local=True)
        assert len(local_voices) >= 2
        assert all(v.is_local for v in local_voices)
        assert any(v.provider == "piper" for v in local_voices)
        assert any(v.provider == "kokoro" for v in local_voices)

    def test_find_voice_profile(self):
        faber = find_voice_profile("piper:pt_BR-faber-medium")
        assert faber is not None
        assert faber.name == "Faber (Piper Local)"
        assert faber.gender == VoiceGender.MALE
        assert faber.style == VoiceStyle.DOCUMENTARY
        assert faber.cost_per_1k_chars == Decimal("0.00")
        assert "default" in faber.tags

        bella = find_voice_profile("kokoro:pt_br-af_bella")
        assert bella is not None
        assert bella.is_neural is True
        assert bella.gender == VoiceGender.FEMALE

        assert find_voice_profile("nonexistent:voice") is None

    def test_voice_catalog_available_filtering(self):
        """Valida que available_only filtra vozes sem pesos/dependências instaladas no ambiente."""
        available = list_voice_catalog(available_only=True)
        available_ids = {v.voice_id for v in available}

        # Piper com pt_BR-faber-medium está presente no container
        assert "piper:pt_BR-faber-medium" in available_ids
        assert is_voice_profile_available("piper:pt_BR-faber-medium") is True

        # Kokoro e ElevenLabs devem ser considerados indisponíveis no ambiente padrão
        assert "kokoro:pt_br-af_bella" not in available_ids
        assert is_voice_profile_available("kokoro:pt_br-af_bella") is False
        assert "elevenlabs:adam" not in available_ids
        assert is_voice_profile_available("elevenlabs:adam") is False



class TestVoicePreprocessing:
    """V4-02.07, V4-02.08 e V4-02.09: Ritmo, pausas e fonética."""

    def test_pronunciation_dictionary_substitutions(self):
        dict_pt = PronunciationDictionary()
        text = "A IA revolucionou a CPU e a GPU com modelos LLM desenvolvidos por Alan Turing."
        processed = dict_pt.apply(text)

        assert "I A" in processed
        assert "C P U" in processed
        assert "G P U" in processed
        assert "L L M" in processed
        assert "Álan Tchúring" in processed

    def test_custom_pronunciation_rule(self):
        custom = PronunciationDictionary(rules={r"\bOpenAI\b": "Ôupen Êi Ái"})
        assert custom.apply("Estudo da OpenAI") == "Estudo da Ôupen Êi Ái"

    def test_pacing_and_pauses(self):
        text = "O sistema processou os dados porém encontrou anomalias — algo inesperado."
        pacing_doc = apply_pacing_and_pauses(text, EmotionalIntention.DOCUMENTARY)
        assert ", porém" in pacing_doc
        assert ", algo" in pacing_doc

    def test_narration_fingerprint_stability_and_invalidation(self):
        fp1 = narration_fingerprint("Texto da cena", "piper:pt_BR-faber-medium")
        fp2 = narration_fingerprint("Texto da cena", "piper:pt_BR-faber-medium")
        assert fp1 == fp2  # Determinístico

        # Variação de texto invalida o cache
        fp_diff_text = narration_fingerprint("Texto modificado", "piper:pt_BR-faber-medium")
        assert fp1 != fp_diff_text

        # Variação de voz invalida o cache
        fp_diff_voice = narration_fingerprint("Texto da cena", "kokoro:pt_br-af_bella")
        assert fp1 != fp_diff_voice

        # Variação de intenção invalida o cache
        fp_diff_intent = narration_fingerprint(
            "Texto da cena", "piper:pt_BR-faber-medium", intention=EmotionalIntention.DRAMATIC
        )
        assert fp1 != fp_diff_intent


class TestAudioInspectionAndQuality:
    """V4-02.10 e V4-02.12: Métricas de áudio, clipping e silêncio."""

    def test_inspect_speech_audio_normal(self, tmp_path: Path):
        wav = _create_wav(tmp_path / "normal.wav", sample_rate=24000, samples_seq=[5000] * 24000)
        metrics = inspect_speech_audio(wav)

        assert metrics.duration_s == 1.0
        assert metrics.sample_rate == 24000
        assert metrics.channels == 1
        assert metrics.peak_amplitude == 5000
        assert metrics.is_clipped is False
        assert metrics.is_silent is False
        assert metrics.is_acceptable is True

    def test_detect_clipping(self, tmp_path: Path):
        wav = _create_wav(tmp_path / "clipped.wav", samples_seq=[32765] * 1000)
        metrics = inspect_speech_audio(wav)

        assert metrics.is_clipped is True
        assert metrics.peak_amplitude >= CLIPPING_THRESHOLD
        assert metrics.is_acceptable is False
        assert any("clipping" in issue for issue in metrics.issues)

    def test_detect_silence(self, tmp_path: Path):
        wav = _create_wav(tmp_path / "silent.wav", samples_seq=[100] * 1000)
        metrics = inspect_speech_audio(wav)

        assert metrics.is_silent is True
        assert metrics.peak_amplitude < MIN_SPEECH_PEAK
        assert metrics.is_acceptable is False
        assert any("silent" in issue for issue in metrics.issues)


class TestVoiceAdaptersAndFallback:
    """V4-02.01 a V4-02.04 e V4-02.14: Kokoro, ElevenLabs e FallbackVoice."""

    def test_kokoro_voice_synthesis_and_protocols(self, monkeypatch, tmp_path: Path):
        """Validação determinística de protocolos Voice/NeuralVoice e recusa em modo produção sem pacote."""
        import importlib.util
        orig_find_spec = importlib.util.find_spec
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "kokoro" else orig_find_spec(name))
        nonexistent = tmp_path / "nonexistent_kokoro_opt"
        monkeypatch.setenv("KOKORO_WEIGHTS_DIR", str(nonexistent))
        monkeypatch.setenv("KOKORO_MODEL_PATH", str(nonexistent))
        monkeypatch.setattr("renderer.app.studio.adapters.voice_kokoro.KOKORO_DEFAULT_WEIGHTS_DIR", nonexistent)

        kokoro = KokoroVoice(model="pt_br-af_bella", speed=1.0)
        assert isinstance(kokoro, Voice)
        assert isinstance(kokoro, NeuralVoice)
        assert "pt_br-af_bella" in kokoro.supported_voices()
        assert kokoro.cost_estimate("Qualquer texto") == 0.0

        out_wav = tmp_path / "kokoro_out.wav"
        # Sem pacote nativo instalado, recusa gerar senoide silenciosa
        with pytest.raises(ModelUnavailable, match="pacote kokoro não instalado no ambiente local"):
            kokoro.speak("Introdução sobre computação clássica e algoritmos modernos.", out_wav)

        # Fixture autorizada permite sintetizar tom para testes de pipeline
        kokoro_fixture = KokoroVoice(model="pt_br-af_bella", speed=1.0, allow_synthetic_fixture=True)
        duration = kokoro_fixture.speak("Introdução sobre computação clássica e algoritmos modernos.", out_wav)

        assert duration > 0.5
        assert out_wav.is_file()
        metrics = inspect_speech_audio(out_wav)
        assert metrics.is_acceptable is True

    def test_elevenlabs_voice_requires_credentials(self, tmp_path: Path):
        eleven = ElevenLabsVoice(api_key=None)
        assert isinstance(eleven, NeuralVoice)
        assert eleven.cost_estimate("Teste de cem caracteres " * 4) > 0.0

        out_wav = tmp_path / "eleven_out.wav"
        with pytest.raises(ProviderMissingCredential):
            eleven.speak("Texto para sintetizar", out_wav)

    def test_fallback_voice_engages_on_primary_failure(self, tmp_path: Path):
        class FailingVoice:
            name = "failing_neural"
            def speak(self, text: str, out_path: Path) -> float:
                raise RuntimeError("Neural voice network down")

        class ReliableVoice:
            name = "local_piper"
            def speak(self, text: str, out_path: Path) -> float:
                _create_wav(out_path, samples_seq=[4000] * 4000)
                return 0.5

        fallback_events: list[str] = []
        resilient = FallbackVoice(
            primary=FailingVoice(),
            fallback=ReliableVoice(),
            on_fallback=lambda name, err: fallback_events.append(f"{name}:{type(err).__name__}"),
        )

        out_wav = tmp_path / "fallback_speech.wav"
        duration = resilient.speak("Texto com resiliência", out_wav)

        assert duration == 0.5
        assert resilient.last_used == "local_piper"
        assert len(fallback_events) == 1
        assert "failing_neural:RuntimeError" in fallback_events[0]
        assert out_wav.is_file()

    def test_kokoro_native_multi_chunk_concatenation_offline_double(self, tmp_path: Path):
        """R09: Dublê offline do KPipeline que emite múltiplos chunks deve concatenar TODOS os chunks sem truncamento."""
        import numpy as np

        chunk1 = np.ones(12000, dtype=np.float32) * 0.2  # 0.5s a 24kHz
        chunk2 = np.ones(24000, dtype=np.float32) * 0.3  # 1.0s a 24kHz
        chunk3 = np.ones(18000, dtype=np.float32) * 0.25 # 0.75s a 24kHz
        expected_total_samples = 12000 + 24000 + 18000  # 54000 samples = 2.25s

        class FakePipeline:
            def __call__(self, text, voice, speed):
                return [
                    ("gs1", "ps1", chunk1),
                    ("gs2", "ps2", chunk2),
                    ("gs3", "ps3", chunk3),
                ]

        weights_dir = tmp_path / "mock_weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "kokoro-v0_19.onnx").write_bytes(b"mock_weights")

        kokoro = KokoroVoice(
            model="pt_br-af_bella",
            speed=1.0,
            pipeline_factory=lambda **kw: FakePipeline(),
            weights_dir=weights_dir,
        )

        out_wav = tmp_path / "kokoro_multi_chunk.wav"
        duration = kokoro.speak("Frase um. Frase dois. Frase três.", out_wav)

        assert duration == 2.25, f"Esperado 2.25s (soma de todos os chunks), obtido {duration}s"
        assert out_wav.is_file()

        with wave.open(str(out_wav), "rb") as w:
            n_frames = w.getnframes()
            assert n_frames == expected_total_samples, (
                f"Truncamento detectado! Esperado {expected_total_samples} frames, obtido {n_frames}"
            )
        metrics = inspect_speech_audio(out_wav)
        assert metrics.is_acceptable is True
        assert metrics.is_silent is False

    def test_kokoro_native_empty_generator_fails_closed(self, tmp_path: Path):
        """R09: Generator nativo do Kokoro sem frames de áudio deve falhar fechado com ModelUnavailable."""
        class EmptyPipeline:
            def __call__(self, text, voice, speed):
                return []

        weights_dir = tmp_path / "mock_weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "kokoro-v0_19.onnx").write_bytes(b"mock_weights")

        kokoro = KokoroVoice(
            model="pt_br-af_bella",
            pipeline_factory=lambda **kw: EmptyPipeline(),
            weights_dir=weights_dir,
        )
        out_wav = tmp_path / "empty.wav"
        with pytest.raises(ModelUnavailable, match="Kokoro nativo não retornou frames de áudio"):
            kokoro.speak("Texto de teste", out_wav)
        assert not out_wav.exists()

    def test_kokoro_native_missing_weights_fails_closed(self, tmp_path: Path):
        """R09: Mesmo com pipeline double, ausência de pesos offline locais deve falhar fechado."""
        empty_weights = tmp_path / "empty_dir"
        empty_weights.mkdir(parents=True, exist_ok=True)

        kokoro = KokoroVoice(
            model="pt_br-af_bella",
            pipeline_factory=lambda **kw: None,
            weights_dir=empty_weights,
        )
        out_wav = tmp_path / "no_weights.wav"
        with pytest.raises(ModelUnavailable, match="pesos locais offline do kokoro não encontrados"):
            kokoro.speak("Texto de teste", out_wav)
        assert not out_wav.exists()

    def test_kokoro_allow_synthetic_fixture_defaults_to_false_and_wiring_safe(self):
        """R09: allow_synthetic_fixture deve ser False por padrão e na injeção de produção."""
        default_voice = KokoroVoice()
        assert default_voice.allow_synthetic_fixture is False

        # Verifica wiring da composição
        wired_voice = build("voice", "kokoro:pt_br-af_bella")
        assert wired_voice.allow_synthetic_fixture is False

    def test_piper_real_offline_synthesis_container(self, tmp_path: Path):
        """R09: Síntese real offline com PiperVoice pt_BR-faber-medium gerando WAV válido e inteligível."""
        import math

        piper = PiperVoice(model="pt_BR-faber-medium")
        text = (
            "O sistema audiovisual profissional do Faceless Studio sintetiza narração factual "
            "em português brasileiro com alta fidelidade e zero custo operacional."
        )
        out_wav = tmp_path / "real_piper_faber.wav"
        duration = piper.speak(text, out_wav)

        assert duration > 1.0, f"Duração esperada > 1.0s, obtido {duration}s"
        assert out_wav.is_file(), "Arquivo WAV de fala real não foi criado"
        assert out_wav.stat().st_size > 1000, "Arquivo WAV de fala menor que o esperado"

        metrics = inspect_speech_audio(out_wav)
        assert metrics.is_acceptable is True
        assert metrics.is_silent is False
        assert metrics.is_clipped is False
        assert metrics.sample_rate in (22050, 24000, 16000)
        assert metrics.channels == 1
        assert metrics.sample_width == 2

        # Validação de sinal não silencioso (RMS)
        with wave.open(str(out_wav), "rb") as w:
            raw = w.readframes(w.getnframes())
            samples = array.array("h", raw)
            rms = math.sqrt(sum(s * s for s in samples) / float(len(samples)))
            assert rms > 300.0, f"RMS de sinal muito baixo ({rms:.1f}); possível silêncio"

    def test_fallback_voice_kokoro_unavailable_to_real_piper(self, tmp_path: Path):
        """R09: Quando Kokoro está indisponível (offline fechado), FallbackVoice engaja Piper real com auditoria."""
        kokoro_primary = KokoroVoice(model="pt_br-af_bella", allow_synthetic_fixture=False)
        piper_fallback = PiperVoice(model="pt_BR-faber-medium")

        audit_events: list[tuple[str, str]] = []

        def on_fallback_audit(provider_name: str, exc: Exception) -> None:
            audit_events.append((provider_name, type(exc).__name__))

        resilient_voice = FallbackVoice(
            primary=kokoro_primary,
            fallback=piper_fallback,
            on_fallback=on_fallback_audit,
        )

        out_wav = tmp_path / "fallback_audit_piper.wav"
        text = "Narração de contingência utilizando fallback auditado para Piper local."
        duration = resilient_voice.speak(text, out_wav)

        assert duration > 1.0
        assert resilient_voice.last_used == "piper"
        assert len(audit_events) == 1
        assert audit_events[0][0] == "kokoro"
        assert audit_events[0][1] == "ModelUnavailable"

        assert out_wav.is_file()
        metrics = inspect_speech_audio(out_wav)
        assert metrics.is_acceptable is True
        assert metrics.is_silent is False

    def test_kokoro_native_zero_environ_leakage(self, monkeypatch, tmp_path: Path):
        """F1: Garantia de zero vazamento de os.environ após síntese nativa com sucesso ou erro."""
        import os
        import numpy as np

        monkeypatch.setenv("HF_HUB_OFFLINE", "custom_sentinel_value")
        monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

        weights_dir = tmp_path / "mock_weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "kokoro-v0_19.onnx").write_bytes(b"mock_weights")

        chunk = np.ones(12000, dtype=np.float32) * 0.3
        class SuccessPipeline:
            def __call__(self, text, voice, speed):
                return [("gs", "ps", chunk)]

        kokoro = KokoroVoice(
            model="pt_br-af_bella",
            pipeline_factory=lambda **kw: SuccessPipeline(),
            weights_dir=weights_dir,
        )
        out_wav = tmp_path / "leak_test_success.wav"
        kokoro.speak("Teste sem vazamento", out_wav)

        # Verifica preservação de estado prévio do os.environ
        assert os.environ.get("HF_HUB_OFFLINE") == "custom_sentinel_value"
        assert "TRANSFORMERS_OFFLINE" not in os.environ

        # Testa restauração de os.environ sob exceção interna
        class ExplodingPipeline:
            def __call__(self, text, voice, speed):
                raise RuntimeError("Explosão proposital de inferência")

        failing_kokoro = KokoroVoice(
            model="pt_br-af_bella",
            pipeline_factory=lambda **kw: ExplodingPipeline(),
            weights_dir=weights_dir,
        )
        with pytest.raises(ModelUnavailable, match="Explosão proposital"):
            failing_kokoro.speak("Texto sob falha", tmp_path / "fail_leak.wav")

        assert os.environ.get("HF_HUB_OFFLINE") == "custom_sentinel_value"
        assert "TRANSFORMERS_OFFLINE" not in os.environ

    def test_kokoro_native_chunk_types_handling(self, tmp_path: Path):
        """F2: Síntese nativa decodifica com robustez bytes PCM, torch-like, list e tensores 2D (N, 1)."""
        import numpy as np

        weights_dir = tmp_path / "mock_weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "kokoro-v0_19.onnx").write_bytes(b"mock_weights")

        # 1. bytes PCM 16-bit little endian (4000 samples = 8000 bytes)
        raw_pcm_samples = np.array([3000, -3000, 4000, -4000] * 1000, dtype="<i2")
        chunk_bytes = raw_pcm_samples.tobytes()

        # 2. Objeto torch-like com .detach().cpu().numpy()
        class MockTorchTensor:
            def __init__(self, arr):
                self._arr = arr
            def detach(self):
                return self
            def cpu(self):
                return self
            def numpy(self):
                return self._arr

        chunk_torch = MockTorchTensor(np.ones((6000, 1), dtype=np.float32) * 0.2)  # 2D tensor (N, 1)

        # 3. Python list padrão
        chunk_list = [0.15, -0.15] * 3000  # 6000 samples

        # 4. NumPy 1D float32
        chunk_numpy = np.ones(8000, dtype=np.float32) * 0.25

        class MultiTypePipeline:
            def __call__(self, text, voice, speed):
                return [
                    ("g1", "p1", chunk_bytes),
                    ("g2", "p2", chunk_torch),
                    ("g3", "p3", chunk_list),
                    ("g4", "p4", chunk_numpy),
                ]

        total_samples = len(raw_pcm_samples) + 6000 + len(chunk_list) + len(chunk_numpy)  # 24000 samples = 1.0s

        kokoro = KokoroVoice(
            model="pt_br-af_bella",
            pipeline_factory=lambda **kw: MultiTypePipeline(),
            weights_dir=weights_dir,
        )
        out_wav = tmp_path / "multi_type.wav"
        duration = kokoro.speak("Frase com múltiplos formatos de chunk", out_wav)

        assert duration == 1.0
        assert out_wav.is_file()
        with wave.open(str(out_wav), "rb") as w:
            assert w.getnframes() == total_samples
            assert w.getframerate() == 24000
            assert w.getnchannels() == 1
        metrics = inspect_speech_audio(out_wav)
        assert metrics.is_acceptable is True
        assert metrics.is_silent is False
        assert metrics.is_clipped is False

    def test_kokoro_native_silence_fails_closed_and_leaves_no_file(self, tmp_path: Path):
        """F2: Emissão de silêncio anômalo (zeros ou peak < 300) falha fechado e não grava arquivo."""
        import numpy as np

        weights_dir = tmp_path / "mock_weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "kokoro-v0_19.onnx").write_bytes(b"mock_weights")

        class SilentPipeline:
            def __call__(self, text, voice, speed):
                return [("gs", "ps", np.zeros(24000, dtype=np.float32))]

        kokoro = KokoroVoice(
            model="pt_br-af_bella",
            pipeline_factory=lambda **kw: SilentPipeline(),
            weights_dir=weights_dir,
        )
        out_wav = tmp_path / "should_not_exist_silent.wav"
        with pytest.raises(ModelUnavailable, match="silêncio anômalo"):
            kokoro.speak("Texto silencioso", out_wav)

        assert not out_wav.exists(), "Arquivo WAV de áudio mudo não deve ser gravado em disco"

    def test_kokoro_native_overshoot_headroom_normalization(self, tmp_path: Path):
        """F2: Chunks com overshoot de amplitude (> 1.0) sofrem normalização de headroom sem clipping."""
        import numpy as np

        weights_dir = tmp_path / "mock_weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "kokoro-v0_19.onnx").write_bytes(b"mock_weights")

        class OvershootPipeline:
            def __call__(self, text, voice, speed):
                # Float overshoot de 2.5 (muito além de 1.0)
                return [("gs", "ps", np.ones(24000, dtype=np.float32) * 2.5)]

        kokoro = KokoroVoice(
            model="pt_br-af_bella",
            pipeline_factory=lambda **kw: OvershootPipeline(),
            weights_dir=weights_dir,
        )
        out_wav = tmp_path / "overshoot_safe.wav"
        duration = kokoro.speak("Texto de teste com overshoot", out_wav)

        assert duration == 1.0
        assert out_wav.is_file()
        metrics = inspect_speech_audio(out_wav)
        assert metrics.is_acceptable is True
        assert metrics.is_clipped is False
        assert metrics.peak_amplitude <= 30000
        assert metrics.is_silent is False




    @pytest.fixture(autouse=True)
    def setup_wiring(self, tmp_path: Path):
        from renderer.app.studio.composition import Settings, Studio
        studio = Studio(Settings(storage_root=tmp_path / "studio"))
        yield studio
        studio.shutdown()

    def test_build_voice_provider_from_wiring(self):
        piper_inst = build("voice", "piper:pt_BR-faber-medium")
        assert isinstance(piper_inst, Voice)
        assert piper_inst.model == "pt_BR-faber-medium"

        kokoro_inst = build("voice", "kokoro:pt_br-af_bella")
        assert isinstance(kokoro_inst, Voice)
        assert isinstance(kokoro_inst, NeuralVoice)
        assert kokoro_inst.model == "pt_br-af_bella"
