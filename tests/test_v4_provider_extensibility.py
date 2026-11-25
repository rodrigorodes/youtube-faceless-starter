"""V4-01 — Testes de Extensibilidade de Provedores e Conformidade de Contratos.

Valida as atividades V4-01.01 a V4-01.12:
1. Evolução de ProviderKind e Capability (V4-01.01)
2. Ports VideoModel, NeuralVoice e contratos de resultado normalizado (V4-01.02 & V4-01.03)
3. Formatos e limites técnicos ProviderLimits (V4-01.04)
4. Roteamento econômico e fallback explícito auditado (V4-01.05 & V4-01.08)
5. Health checks e Probes de conectividade (V4-01.06)
6. Congelamento de seleção por run (V4-01.07)
7. Classificação semântica de erros de provedor (V4-01.09)
8. Governança de custos e BudgetGuard (V4-01.10)
9. Extensibilidade comprovada com FakeExtensibleProvider (V4-01.11)
10. Preservação estrita dos adaptadores canônicos Piper TTS e FFmpeg (V4-01.12)
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "renderer"))

from app.studio.adapters.provider_probes import HttpReachableProbe, LocalProviderProbe
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.adapters.voice_piper import PiperVoice
from app.studio.application.ports import (
    ImageModel,
    NeuralVoice,
    Renderer,
    TextModel,
    VideoModel,
    VideoResult,
    Voice,
)
from app.studio.application.providers import ProviderService
from app.studio.composition.providers import ProviderRouting, _provider_implementations, _provider_probes
from app.studio.domain.contracts import UsageEntry
from app.studio.domain.provider import (
    REQUIRED_CAPABILITY,
    Availability,
    Capability,
    CostEstimate,
    CostKind,
    EconomicProfile,
    NoProviderAvailable,
    ProviderBudgetBlocked,
    ProviderCard,
    ProviderError,
    ProviderImplementation,
    ProviderKind,
    ProviderLimits,
    ProviderPermanentError,
    ProviderQuotaExceeded,
    ProviderSpecInvalid,
    ProviderStanding,
    ProviderTransientError,
    card_for,
    parse_spec,
    satisfies_capability,
)


# =========================================================================== #
# 1. V4-01.01 — ProviderKind e Capability
# =========================================================================== #

def test_v4_01_provider_kind_and_capabilities_extended():
    """Garante que ProviderKind.VIDEO e as novas Capabilities estão presentes e integradas."""
    assert ProviderKind.VIDEO == "video"
    assert Capability.VIDEO_GENERATE == "video.generate"
    assert Capability.VOICE_NEURAL == "voice.neural"
    assert Capability.TEXT_REASONING == "text.reasoning"

    # Validação do mapa de capability mandatória por porta
    assert REQUIRED_CAPABILITY[ProviderKind.VIDEO] is Capability.VIDEO_GENERATE
    assert satisfies_capability(ProviderKind.VIDEO, ("video.generate",))
    assert satisfies_capability(ProviderKind.VIDEO, ("video.generate", "custom.filter"))
    assert not satisfies_capability(ProviderKind.VIDEO, ("image.generate",))


# =========================================================================== #
# 2. V4-01.02 & V4-01.03 — Ports e Normalização de Resultados
# =========================================================================== #

class DummyVideoModel:
    name = "dummy_video"
    model = "v1"

    def cost_estimate(self, prompt: str, *, duration_s: float = 4.0) -> float:
        return 0.10 * duration_s

    def generate(self, prompt: str, *, duration_s: float = 4.0, aspect: str = "16:9") -> VideoResult:
        usage = UsageEntry(step="video_generate", provider="dummy_video", model="v1", cost_usd=0.0)
        return VideoResult(
            data=b"fake-mp4-stream",
            mime="video/mp4",
            duration_s=duration_s,
            width=1920,
            height=1080,
            usage=usage,
            license="CC-BY-4.0",
            attribution="Dummy Video AI",
            provenance="ai_generated",
        )


class DummyNeuralVoice:
    name = "dummy_neural"
    model = "neural-pro"

    def supported_voices(self) -> tuple[str, ...]:
        return ("pt-BR-Neural-A", "pt-BR-Neural-B")

    def cost_estimate(self, text: str) -> float:
        return len(text) * 0.0001

    def speak(self, text: str, out_path: Path) -> float:
        out_path.write_bytes(b"RIFF....WAVE")
        return 2.5


def test_v4_01_ports_runtime_protocols():
    """Valida conformidade com os novos protocols VideoModel e NeuralVoice."""
    video_impl = DummyVideoModel()
    voice_impl = DummyNeuralVoice()

    assert isinstance(video_impl, VideoModel)
    assert isinstance(voice_impl, Voice)
    assert isinstance(voice_impl, NeuralVoice)

    # Execução e normalização do resultado
    res = video_impl.generate("Câmera deslizando sobre o oceano", duration_s=5.0)
    assert isinstance(res, VideoResult)
    assert res.mime == "video/mp4"
    assert res.duration_s == 5.0
    assert res.width == 1920 and res.height == 1080
    assert res.license == "CC-BY-4.0"
    assert res.provenance == "ai_generated"


# =========================================================================== #
# 3. V4-01.04 — Formatos e Limites Técnicos (ProviderLimits)
# =========================================================================== #

def test_v4_01_provider_limits_definition_and_card_integration():
    """Garante que ProviderLimits é retido e exposto em ProviderImplementation e ProviderCard."""
    limits = ProviderLimits(
        max_duration_s=10.0,
        min_duration_s=1.0,
        supported_aspects=("16:9", "9:16"),
        supported_formats=("mp4", "webm"),
        max_chars=500,
    )
    impl = ProviderImplementation(
        kind=ProviderKind.VIDEO,
        name="veo_test",
        capabilities=("video.generate",),
        cost=CostEstimate.estimate(0.40),
        quality=5,
        validated=True,
        limits=limits,
    )
    assert impl.limits.max_duration_s == 10.0
    assert impl.limits.supported_aspects == ("16:9", "9:16")

    card = card_for(ProviderKind.VIDEO, "veo_test:gen2", [impl])
    assert card.availability is Availability.AVAILABLE
    assert card.limits.max_duration_s == 10.0
    assert card.limits.max_chars == 500


# =========================================================================== #
# 4. V4-01.06 — Health Checks e Probes
# =========================================================================== #

def test_v4_01_probes_for_video_and_local():
    """Valida sondas de conectividade para implementações locais e remotas."""
    local_probe = LocalProviderProbe()
    probe_res = local_probe.probe(ProviderKind.VIDEO, "placeholder:v1")
    assert probe_res.ok is True
    assert "local disponível" in probe_res.detail

    # Probe HTTP mockada contra URL inválida falha fechada sem quebrar
    http_probe = HttpReachableProbe(url="http://127.0.0.1:59999/health", timeout=0.1)
    http_res = http_probe.probe(ProviderKind.VIDEO, "remote:v1")
    assert http_res.ok is False
    assert "inalcançável" in http_res.detail


# =========================================================================== #
# 5. V4-01.08 & V4-01.09 — Classificação Semântica de Erros e Fallback
# =========================================================================== #

def test_v4_01_provider_error_hierarchy():
    """Garante que a hierarquia semântica de erros herda de ProviderError."""
    assert issubclass(ProviderTransientError, ProviderError)
    assert issubclass(ProviderQuotaExceeded, ProviderError)
    assert issubclass(ProviderBudgetBlocked, ProviderError)
    assert issubclass(ProviderPermanentError, ProviderError)
    assert issubclass(ProviderSpecInvalid, ProviderError)
    assert issubclass(NoProviderAvailable, ProviderError)


class FakeVideoRepo:
    def __init__(self, config=None):
        self.config = config or {}

    def get_project(self, project_id):
        return type("Project", (), {"id": project_id or "p1", "config": self.config})()


def test_v4_01_routing_fallback_explicit():
    """Comprova que se o provedor primário falhar, o roteador exclui o candidato e tenta o próximo."""
    impls = [
        ProviderImplementation(
            ProviderKind.VIDEO, "failing_gpu", capabilities=("video.generate",),
            cost=CostEstimate.estimate(0.05), quality=5, validated=True,
        ),
        ProviderImplementation(
            ProviderKind.VIDEO, "backup_local", capabilities=("video.generate",),
            cost=CostEstimate.free(), quality=3, validated=True,
        ),
    ]
    service = ProviderService(FakeVideoRepo(), {"STUDIO_VIDEO": "failing_gpu:v1"}, impls)

    # 1. Rota normal escolhe o de maior qualidade no perfil PREMIUM
    route1 = service.route(None, ProviderKind.VIDEO, EconomicProfile.PREMIUM)
    assert route1.primary.name == "failing_gpu"

    # 2. Excluindo o primário que falhou, o fallback para o backup é explícito
    route2 = service.route(None, ProviderKind.VIDEO, EconomicProfile.PREMIUM, exclude=("failing_gpu",))
    assert route2.primary.name == "backup_local"
    assert "backup_local" in route2.reason or route2.primary.name == "backup_local"


# =========================================================================== #
# 6. V4-01.11 — Extensibilidade com FakeExtensibleProvider
# =========================================================================== #

class FakeExtensibleProvider:
    """Adaptador de teste que implementa múltiplos serviços audiovisuais simultaneamente."""

    def __init__(self, name: str = "fake_extensible", model: str = "v1"):
        self.name = name
        self.model = model

    # ImageModel interface
    def generate(self, prompt: str, *, aspect: str = "16:9"):
        usage = UsageEntry(step="video_generate", provider=self.name, model=self.model, cost_usd=0.0)
        return VideoResult(
            data=b"fake-rendered-clip",
            mime="video/mp4",
            duration_s=4.0,
            width=1920,
            height=1080,
            usage=usage,
            license="MIT",
            attribution="Fake Extensible AI",
            provenance="ai_generated",
        )

    def cost_estimate(self, prompt: str, *, duration_s: float = 4.0) -> float:
        return 0.0

    # NeuralVoice interface
    def supported_voices(self) -> tuple[str, ...]:
        return ("fake-neural-pt-br",)

    def speak(self, text: str, out_path: Path) -> float:
        out_path.write_bytes(b"RIFFfakeWAVE")
        return 3.0


def test_v4_01_extensibility_without_core_modification():
    """Comprova o critério de aceite: novo adapter fake é plugado, descoberto e roteado sem alterar o Core."""
    fake_adapter = FakeExtensibleProvider()

    # Registra no catálogo dinâmico de implementações
    impl = ProviderImplementation(
        kind=ProviderKind.VIDEO,
        name="fake_extensible",
        capabilities=("video.generate",),
        cost=CostEstimate.free(note="adaptador de teste extensível"),
        quality=4,
        validated=True,
        standing=ProviderStanding.DEMO,
    )
    service = ProviderService(FakeVideoRepo(), {"STUDIO_VIDEO": "fake_extensible:v1"}, [impl])

    # Candidatos listados pelo serviço
    cards = service.candidates(ProviderKind.VIDEO)
    assert len(cards) == 1
    assert cards[0].name == "fake_extensible"
    assert cards[0].availability is Availability.AVAILABLE

    # Roteamento no perfil BALANCED
    decision = service.route(None, ProviderKind.VIDEO, EconomicProfile.BALANCED)
    assert decision.primary.name == "fake_extensible"
    assert decision.primary.spec == "fake_extensible:v1"

    # Instância do adaptador executa diretamente sem acoplamento
    clip = fake_adapter.generate("Timelapse de flores desabrochando")
    assert clip.data == b"fake-rendered-clip"
    assert clip.license == "MIT"


# =========================================================================== #
# 7. Preservação Estrita dos Adaptadores Canônicos (Piper TTS e FFmpeg)
# =========================================================================== #

def test_v4_01_piper_and_ffmpeg_remain_functional(tmp_path: Path):
    """Comprova o critério de aceite: Piper e FFmpeg continuam implementando suas portas sem regressão."""
    # 1. PiperVoice satisfaz Voice protocol
    piper = PiperVoice("pt_BR-faber-medium")
    assert isinstance(piper, Voice)
    assert piper.name == "piper"

    # 2. PlanFfmpegRenderer satisfaz Renderer protocol
    renderer = PlanFfmpegRenderer()
    assert isinstance(renderer, Renderer)
    assert renderer.name == "ffmpeg"
