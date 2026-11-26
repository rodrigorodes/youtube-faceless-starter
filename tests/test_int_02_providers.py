"""Testes de Integração e Estabilização — Onda INT-02 (Providers Reais e Saneamento de Síntese).

Valida os achados A01 e A02 da auditoria INT-01:
- A01: Kokoro recusa gerar tom senoidal silenciosamente em produção; lança ModelUnavailable
  quando o pacote nativo não está instalado. Fixtures sintéticas exigem flag explícita.
- Kokoro é registrado como validated=False quando os pesos/pacote não estão presentes.
- Piper é o provedor local offline oficial validado (validated=True) para PT-BR.
- A02: ElevenLabs permanece experimental/opt-in e desabilitado sem credencial ($0.00).
"""
from pathlib import Path
import pytest

from app.studio.adapters.voice_kokoro import KokoroVoice, is_kokoro_installed
from app.studio.adapters.voice_elevenlabs import ElevenLabsVoice
from app.studio.application.ports import ModelUnavailable
from app.studio.domain.provider import ProviderKind, ProviderMissingCredential
from app.studio.composition.providers import _provider_implementations
from app.studio.composition.settings import Settings


def test_int_02_kokoro_rejects_sine_wave_as_real_speech_when_missing(tmp_path: Path):
    """A01: Sem o pacote nativo instalado, Kokoro deve falhar fechado com ModelUnavailable."""
    out_file = tmp_path / "kokoro_test.wav"

    if not is_kokoro_installed():
        # Modo produção padrão (allow_synthetic_fixture=False)
        voice = KokoroVoice(model="pt_br-af_bella", allow_synthetic_fixture=False)

        with pytest.raises(ModelUnavailable, match="pacote kokoro não instalado no ambiente local"):
            voice.speak("Este texto nunca deve virar uma senoide silenciosa", out_file)

        assert not out_file.exists(), "Não deve criar arquivo WAV senoidal quando não instalado"


def test_int_02_kokoro_synthetic_tone_requires_explicit_fixture_flag(tmp_path: Path):
    """A01: Tom senoidal determinístico só é emitido se explicitamente configurado para fixture."""
    out_file = tmp_path / "kokoro_fixture.wav"

    if not is_kokoro_installed():
        # Modo fixture de teste autorizada
        voice_fixture = KokoroVoice(model="pt_br-af_bella", allow_synthetic_fixture=True)
        duration = voice_fixture.speak("Texto sintético para teste", out_file)

        assert duration > 0.0
        assert out_file.exists()
        assert out_file.stat().st_size > 44  # Cabeçalho WAV + PCM


def test_int_02_provider_registry_validation_status():
    """Valida que Kokoro não é publicado como validated=True sem os componentes reais instalados."""
    settings = Settings(
        database_url="postgresql://fake",
        storage_root=Path("/tmp/storage"),
    )
    impls = _provider_implementations(settings)
    by_kind_name = {(impl.kind, impl.name): impl for impl in impls}

    # Piper deve ser validado localmente (gratuito e offline)
    piper = by_kind_name[(ProviderKind.VOICE, "piper")]
    assert piper.validated is True
    assert piper.cost.kind.value == "FREE"

    # Kokoro deve refletir o estado real do ambiente
    kokoro = by_kind_name[(ProviderKind.VOICE, "kokoro")]
    if not is_kokoro_installed():
        assert kokoro.validated is False
        assert "pacote kokoro não instalado" in (kokoro.reason or "")

    # ElevenLabs deve ser desabilitado/experimental por padrão
    elevenlabs = by_kind_name[(ProviderKind.VOICE, "elevenlabs")]
    assert elevenlabs.validated is False


def test_int_02_elevenlabs_opt_in_and_network_isolation(tmp_path: Path):
    """A02: ElevenLabs sem credencial falha com ProviderMissingCredential e nunca faz tráfego externo."""
    out_file = tmp_path / "eleven_test.wav"

    # Sem chave de API
    voice_no_key = ElevenLabsVoice(api_key=None)
    with pytest.raises(ProviderMissingCredential, match="ELEVENLABS_API_KEY ausente"):
        voice_no_key.speak("Tentativa de síntese sem chave", out_file)

    # Com chave mas sem permissão de execução em rede
    voice_with_key = ElevenLabsVoice(api_key="sk-fake-key-test")
    with pytest.raises(NotImplementedError, match="requires explicit remote authorization"):
        voice_with_key.speak("Tentativa de síntese remota em teste", out_file)
