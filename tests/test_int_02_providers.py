"""Testes de Integração e Estabilização — Onda INT-02 (Providers Reais e Saneamento de Síntese).

Valida os achados A01 e A02 da auditoria INT-01 e R09 (REC-02.05):
- A01: Kokoro recusa gerar tom senoidal silenciosamente em produção; lança ModelUnavailable
  quando o pacote nativo não está instalado. Fixtures sintéticas exigem flag explícita.
- R09: find_spec isolado não valida Kokoro; pesos binários offline locais são obrigatórios.
- Arquivos .json/.txt não qualificam como pesos de inferência.
- Kokoro é registrado em FREE_PROVIDERS e mapeado para LocalProviderProbe.
- Piper é o provedor local offline oficial validado (validated=True) para PT-BR.
- A02: ElevenLabs permanece experimental/opt-in e desabilitado sem credencial ($0.00).
"""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.studio.adapters.voice_kokoro import KokoroVoice, is_kokoro_installed, is_kokoro_offline_ready
from app.studio.adapters.voice_elevenlabs import ElevenLabsVoice
from app.studio.adapters.provider_probes import LocalProviderProbe
from app.studio.application.ports import ModelUnavailable
from app.studio.domain.provider import ProviderKind, ProviderMissingCredential
from app.studio.composition.providers import FREE_PROVIDERS, _provider_implementations, _provider_probes
from app.studio.composition.settings import Settings


def _patch_kokoro_absent(monkeypatch, tmp_path: Path):
    """Auxiliar para garantir deterministicamente ausência de pacote e pesos em qualquer ambiente."""
    orig_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "kokoro" else orig_find_spec(name))
    nonexistent = tmp_path / "nonexistent_kokoro_dir"
    monkeypatch.setenv("KOKORO_WEIGHTS_DIR", str(nonexistent))
    monkeypatch.setenv("KOKORO_MODEL_PATH", str(nonexistent))
    monkeypatch.setattr("app.studio.adapters.voice_kokoro.KOKORO_DEFAULT_WEIGHTS_DIR", nonexistent)


def test_int_02_kokoro_rejects_sine_wave_as_real_speech_when_missing(monkeypatch, tmp_path: Path):
    """A01: Sem o pacote nativo instalado, Kokoro deve falhar fechado com ModelUnavailable (determinístico)."""
    _patch_kokoro_absent(monkeypatch, tmp_path)
    out_file = tmp_path / "kokoro_test.wav"

    voice = KokoroVoice(model="pt_br-af_bella", allow_synthetic_fixture=False)
    with pytest.raises(ModelUnavailable, match="pacote kokoro não instalado no ambiente local"):
        voice.speak("Este texto nunca deve virar uma senoide silenciosa", out_file)

    assert not out_file.exists(), "Não deve criar arquivo WAV senoidal quando não instalado"


def test_int_02_kokoro_synthetic_tone_requires_explicit_fixture_flag(monkeypatch, tmp_path: Path):
    """A01: Tom senoidal determinístico só é emitido se explicitamente configurado para fixture (determinístico)."""
    _patch_kokoro_absent(monkeypatch, tmp_path)
    out_file = tmp_path / "kokoro_fixture.wav"

    voice_fixture = KokoroVoice(model="pt_br-af_bella", allow_synthetic_fixture=True)
    duration = voice_fixture.speak("Texto sintético para teste", out_file)

    assert duration > 0.0
    assert out_file.exists()
    assert out_file.stat().st_size > 44  # Cabeçalho WAV + PCM


def test_int_02_provider_registry_validation_status(monkeypatch, tmp_path: Path):
    """Valida que Kokoro não é publicado como validated=True sem os componentes reais instalados."""
    _patch_kokoro_absent(monkeypatch, tmp_path)
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


def test_int_02_kokoro_find_spec_alone_does_not_validate_without_offline_weights(monkeypatch, tmp_path: Path):
    """R09: find_spec('kokoro') sozinho NÃO pode marcar Kokoro como validated=True sem pesos locais."""
    mock_spec = MagicMock()
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: mock_spec if name == "kokoro" else None)

    empty_dir = tmp_path / "empty_kokoro_weights"
    empty_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("KOKORO_WEIGHTS_DIR", str(empty_dir))
    monkeypatch.setenv("KOKORO_MODEL_PATH", str(empty_dir))
    monkeypatch.setattr("app.studio.adapters.voice_kokoro.KOKORO_DEFAULT_WEIGHTS_DIR", empty_dir)

    settings = Settings(
        database_url="postgresql://fake",
        storage_root=Path("/tmp/storage"),
    )
    impls = _provider_implementations(settings)
    kokoro = next(i for i in impls if i.kind == ProviderKind.VOICE and i.name == "kokoro")

    assert kokoro.validated is False, "Kokoro não pode ser validado apenas por find_spec sem pesos locais"
    assert "pesos locais offline do kokoro não encontrados" in (kokoro.reason or "")

    out_file = tmp_path / "fail_closed.wav"
    voice = KokoroVoice(model="pt_br-af_bella", allow_synthetic_fixture=False)
    with pytest.raises(ModelUnavailable, match="pesos locais offline do kokoro não encontrados"):
        voice.speak("Tentativa de síntese sem pesos locais", out_file)
    assert not out_file.exists()


def test_int_02_kokoro_json_or_txt_only_does_not_validate(monkeypatch, tmp_path: Path):
    """F3: Diretório apenas com config.json ou caminho de arquivo .txt não valida pesos."""
    mock_spec = MagicMock()
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: mock_spec if name == "kokoro" else None)

    # 1. Diretório só com arquivo .json
    json_dir = tmp_path / "json_only_dir"
    json_dir.mkdir(parents=True, exist_ok=True)
    (json_dir / "config.json").write_text('{"vocab_size": 1000}', encoding="utf-8")
    monkeypatch.setenv("KOKORO_WEIGHTS_DIR", str(json_dir))
    monkeypatch.setattr("app.studio.adapters.voice_kokoro.KOKORO_DEFAULT_WEIGHTS_DIR", json_dir)

    ready, reason = is_kokoro_offline_ready()
    assert ready is False
    assert "pesos locais offline do kokoro não encontrados" in (reason or "")

    # 2. Arquivo .txt passado diretamente
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("not a model weight", encoding="utf-8")
    monkeypatch.setenv("KOKORO_MODEL_PATH", str(txt_file))

    ready_txt, reason_txt = is_kokoro_offline_ready(custom_dir=txt_file)
    assert ready_txt is False

    voice = KokoroVoice(model="pt_br-af_bella", weights_dir=json_dir)
    out_file = tmp_path / "fail_json.wav"
    with pytest.raises(ModelUnavailable, match="pesos locais offline do kokoro não encontrados"):
        voice.speak("Síntese recusada com config.json", out_file)
    assert not out_file.exists()


def test_int_02_kokoro_validates_only_when_both_package_and_weights_present(monkeypatch, tmp_path: Path):
    """R09: Kokoro só é marcado validated=True quando pacote E pesos offline estiverem presentes."""
    mock_spec = MagicMock()
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: mock_spec if name == "kokoro" else None)

    weights_dir = tmp_path / "valid_kokoro_weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    (weights_dir / "kokoro-v0_19.onnx").write_bytes(b"dummy_kokoro_model_weights_data")
    monkeypatch.setenv("KOKORO_WEIGHTS_DIR", str(weights_dir))

    settings = Settings(
        database_url="postgresql://fake",
        storage_root=Path("/tmp/storage"),
    )
    impls = _provider_implementations(settings)
    kokoro = next(i for i in impls if i.kind == ProviderKind.VOICE and i.name == "kokoro")

    assert kokoro.validated is True
    assert kokoro.reason is None


def test_int_02_kokoro_in_free_providers_and_local_probe(monkeypatch, tmp_path: Path):
    """F3: Kokoro está em FREE_PROVIDERS e quando validado mapeia para LocalProviderProbe."""
    assert "kokoro" in FREE_PROVIDERS

    mock_spec = MagicMock()
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: mock_spec if name == "kokoro" else None)
    weights_dir = tmp_path / "valid_weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    (weights_dir / "model.safetensors").write_bytes(b"mock_safetensors")
    monkeypatch.setenv("KOKORO_WEIGHTS_DIR", str(weights_dir))

    settings = Settings(
        database_url="postgresql://fake",
        storage_root=Path("/tmp/storage"),
    )
    impls = _provider_implementations(settings)
    probes = _provider_probes(settings, impls)

    assert ("voice", "kokoro") in probes
    assert isinstance(probes[("voice", "kokoro")], LocalProviderProbe)
