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

    def test_kokoro_voice_synthesis_and_protocols(self, tmp_path: Path):
        kokoro = KokoroVoice(model="pt_br-af_bella", speed=1.0)
        assert isinstance(kokoro, Voice)
        assert isinstance(kokoro, NeuralVoice)
        assert "pt_br-af_bella" in kokoro.supported_voices()
        assert kokoro.cost_estimate("Qualquer texto") == 0.0

        out_wav = tmp_path / "kokoro_out.wav"
        if not is_kokoro_installed():
            # Sem pacote nativo instalado, recusa gerar senoide silenciosa
            with pytest.raises(ModelUnavailable, match="pacote kokoro não instalado no ambiente local"):
                kokoro.speak("Introdução sobre computação clássica e algoritmos modernos.", out_wav)

            # Fixture autorizada permite sintetizar tom para testes de pipeline
            kokoro_fixture = KokoroVoice(model="pt_br-af_bella", speed=1.0, allow_synthetic_fixture=True)
            duration = kokoro_fixture.speak("Introdução sobre computação clássica e algoritmos modernos.", out_wav)
        else:
            duration = kokoro.speak("Introdução sobre computação clássica e algoritmos modernos.", out_wav)

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
