"""Providers da raiz de composição: catálogo, registro e roteamento de provedores."""
import importlib.util
from collections.abc import Mapping

from ..adapters.google_oauth import GoogleOAuthClient, google_oauth_from_client_secret
from ..adapters.provider_probes import HttpReachableProbe, LocalProviderProbe
from ..application.config import ProviderNotFound, ProjectConfig
from ..application.observability import record_provider_decision
from ..application.production import frozen_provider_selection
from ..domain.provider import (CostEstimate, NoProviderAvailable, ProviderImplementation, ProviderKind,
                               ProviderSpecInvalid)
from ..domain.youtube_oauth import OAuthConfigurationError
from .settings import Settings


# Fornecedores locais/gratuitos: conhecimento do concreto (nome de fornecedor) declarado só
# aqui, na raiz de composição. O domínio recebe o conjunto como política e não cita nomes.
FREE_PROVIDERS = frozenset({"placeholder", "demo", "piper", "kokoro", "stock"})


def _configured_provider_spec(videos, environ: Mapping[str, str], kind: str,
                              project_id: str | None) -> str:
    """Spec efetivo do projeto (comportamento legado, preservado byte a byte sem perfil).

    Projeto ausente cai no padrão do ambiente, como antes; chave desconhecida vira
    ``ProviderNotFound`` (o erro que a execução já publicava).
    """
    project = videos.get_project(project_id) if project_id else None
    try:
        return getattr(ProjectConfig.resolve(project.config if project else {}, environ), kind)
    except ValueError as exc:
        raise ProviderNotFound(str(exc)) from exc


class ProviderRouting:
    """Resolve o provider que a execução usa, consumindo a decisão econômica (F06.T02).

    Sem perfil persistido (`limits_for` devolve None) mantém o comportamento legado: constrói
    exatamente o spec configurado, sem rotear. Com perfil, a decisão de `ProviderService.route`
    é executada; se o provider decidido não construir, a avaliação é refeita **explicitamente**
    excluindo o candidato, e cada tentativa fica auditada. Sem candidato aceitável, o erro de
    política (`NoProviderAvailable`) sobe — nunca há troca silenciosa nem demo/placeholder
    inventado.
    """

    def __init__(self, service, build, configured_spec, limits_for=None, *, production=False):
        self.service = service
        self.build = build
        self.configured_spec = configured_spec
        self.limits_for = limits_for or (lambda project_id: None)
        self.production = bool(production)

    def __call__(self, kind: str, project_id: str | None):
        kind_enum = kind if isinstance(kind, ProviderKind) else ProviderKind(kind)
        # S8: dentro de um run com snapshot, a seleção congelada vence a política viva. O retry
        # não re-resolve: executa exatamente o provider/modelo que foi exibido e aprovado.
        frozen = frozen_provider_selection()
        if frozen:
            spec = frozen.get(kind_enum.value)
            if spec:
                return self._frozen(kind_enum, spec)
        limits = self.limits_for(project_id) if project_id else None
        profile = getattr(limits, "economic_profile", None) if limits is not None else None
        if profile is None:
            return self._legacy(kind_enum, project_id)
        return self._routed(kind_enum, project_id, profile,
                            getattr(limits, "hard_video_usd", None))

    def _frozen(self, kind: ProviderKind, spec: str):
        """Executa a seleção congelada; se ela não construir, recusa — nunca troca em silêncio."""
        try:
            provider = self.build(kind.value, spec)
        except (ProviderNotFound, ProviderSpecInvalid) as exc:
            self._audit(kind, None, spec, None,
                        f"frozen run selection unavailable: {type(exc).__name__}", attempt=1)
            raise
        self._audit(kind, None, spec, provider, "frozen run selection", attempt=1)
        return provider

    def _legacy(self, kind: ProviderKind, project_id: str | None):
        spec = self.configured_spec(kind.value, project_id)
        provider = self.build(kind.value, spec)
        self._audit(kind, None, spec, provider, "no economic profile: configured spec", attempt=1)
        return provider

    def _routed(self, kind: ProviderKind, project_id: str | None, profile, max_cost_usd):
        excluded: tuple[str, ...] = ()
        attempt = 0
        while True:
            attempt += 1
            try:
                decision = self.service.route(project_id, kind, profile, max_cost_usd=max_cost_usd,
                                              production=self.production, exclude=excluded)
            except NoProviderAvailable as exc:
                reason = str(exc)
                if excluded:
                    reason = f"explicit re-evaluation after unavailable {sorted(excluded)}: {reason}"
                self._audit(kind, profile, None, None, reason, attempt=attempt)
                raise
            try:
                provider = self.build(kind.value, decision.primary.spec)
            except (ProviderNotFound, ProviderSpecInvalid) as exc:
                # o provider decidido não constrói: reavaliar é explícito (auditado) e a política
                # continua valendo na próxima tentativa; nunca cair calado no spec configurado.
                reason = (f"decided provider {decision.primary.spec!r} unavailable: "
                          f"{type(exc).__name__}: {exc}")
                self._audit(kind, profile, decision.primary.spec, None, reason, attempt=attempt)
                excluded = (*excluded, decision.primary.name)
                continue
            self._audit(kind, profile, decision.primary.spec, provider, decision.reason,
                        attempt=attempt)
            return provider

    def _audit(self, kind: ProviderKind, profile, candidate, provider, reason, *, attempt):
        name, model = None, ""
        if provider is not None:
            name = getattr(provider, "name", None)
            model = getattr(provider, "model", "")
            name = name if isinstance(name, str) else None
            model = model if isinstance(model, str) else ""
        record_provider_decision(kind=kind.value,
                                 profile=getattr(profile, "value", profile) if profile else None,
                                 candidate=candidate, effective=name, model=model, reason=reason,
                                 attempt=attempt, production=self.production)


def build_google_oauth(settings: "Settings",
                       transport=None) -> GoogleOAuthClient | None:
    """Monta o cliente OAuth a partir do client secret **no caminho original** (somente leitura).

    App ausente/inválido não derruba a composição: devolve None e a API responde 503 com motivo.
    """
    if settings.google_client_secret_file is None:
        return None
    try:
        return google_oauth_from_client_secret(settings.google_client_secret_file,
                                               redirect_uri=settings.google_oauth_redirect_uri,
                                               transport=transport)
    except (OAuthConfigurationError, OSError):
        return None


def _provider_implementations(s: "Settings") -> list[ProviderImplementation]:
    """Implementações registradas e o que cada uma é capaz de fazer (F10-03).

    `validated=False` quando falta credencial ou homologação: o catálogo mostra UNAVAILABLE.
    """
    bridge_ok = bool(s.bridge_token)
    pexels_ok = bool(s.pexels_key)
    pixabay_ok = bool(s.pixabay_key)
    from ..adapters.voice_kokoro import is_kokoro_offline_ready
    kokoro_ok, kokoro_reason = is_kokoro_offline_ready()
    return [
        ProviderImplementation(ProviderKind.TEXT, "opencode",
                               capabilities=("text.generate", "text.json"),
                               cost=CostEstimate.unknown(note="preço do bridge"), quality=4,
                               validated=bridge_ok, reason=None if bridge_ok else "OPENCODE_BRIDGE_TOKEN ausente"),
        ProviderImplementation(ProviderKind.TEXT, "demo", capabilities=("text.generate",),
                               cost=CostEstimate.free(note="texto determinístico local"), quality=1,
                               validated=True),
        ProviderImplementation(ProviderKind.IMAGE, "opencode", capabilities=("image.generate",),
                               cost=CostEstimate.estimate(s.paid_image_usd, note="por imagem"),
                               quality=4, validated=bridge_ok,
                               reason=None if bridge_ok else "OPENCODE_BRIDGE_TOKEN ausente"),
        ProviderImplementation(ProviderKind.IMAGE, "placeholder", capabilities=("image.generate",),
                               cost=CostEstimate.free(note="placeholder local"), quality=1, validated=True),
        ProviderImplementation(ProviderKind.IMAGE, "stock", capabilities=("image.generate",),
                               cost=CostEstimate.free(note="Pexels com licença"), quality=3,
                               validated=pexels_ok, reason=None if pexels_ok else "PEXELS_API_KEY ausente"),
        ProviderImplementation(ProviderKind.IMAGE, "veo", capabilities=("image.generate",),
                               cost=CostEstimate.estimate(s.veo_usd_per_second, note="por segundo"),
                               quality=5, validated=False, reason="provedor experimental, sem homologação"),
        ProviderImplementation(ProviderKind.VOICE, "piper", capabilities=("voice.speak",),
                               cost=CostEstimate.free(note="síntese local"), quality=3, validated=True),
        ProviderImplementation(ProviderKind.VOICE, "kokoro", capabilities=("voice.speak", "voice.neural"),
                               cost=CostEstimate.free(note="síntese neural local"), quality=4,
                               validated=kokoro_ok,
                               reason=None if kokoro_ok else kokoro_reason),
        ProviderImplementation(ProviderKind.VOICE, "elevenlabs", capabilities=("voice.speak", "voice.neural"),
                               cost=CostEstimate.estimate(0.03, note="por 1k caracteres"), quality=5,
                               validated=False, reason="requer BYOK e autorização explícita"),
        ProviderImplementation(ProviderKind.RENDERER, "ffmpeg", capabilities=("render.video",),
                               cost=CostEstimate.free(note="render local"), quality=4, validated=True),
        ProviderImplementation(ProviderKind.SEARCH, "pexels", capabilities=("search.media",),
                               cost=CostEstimate.free(note="busca de mídia gratuita"), quality=4,
                               validated=pexels_ok, reason=None if pexels_ok else "PEXELS_API_KEY ausente"),
        ProviderImplementation(ProviderKind.SEARCH, "pixabay", capabilities=("search.media",),
                               cost=CostEstimate.free(note="busca Pixabay gratuita"), quality=4,
                               validated=pixabay_ok, reason=None if pixabay_ok else "PIXABAY_API_KEY ausente"),
    ]


def pixabay_media_search(api_key: str):
    """Fábrica do buscador Pixabay para a camada de composição.

    Mantém o import do adapter fora de ``app.studio.api``: a rota de busca recebe o
    buscador pronto, sem tocar em ``adapters`` (guardado por ``tests/test_architecture.py``).
    """
    from ..adapters.media_pixabay import PixabayMediaSearch

    return PixabayMediaSearch(api_key)


def _provider_probes(s: "Settings", implementations) -> dict[tuple[str, str], object]:
    probes: dict[tuple[str, str], object] = {}
    local = {"demo", "placeholder", "piper", "kokoro", "ffmpeg"}
    for impl in implementations:
        if not impl.validated:
            continue
        if impl.name == "opencode":
            probes[(impl.kind.value, impl.name)] = HttpReachableProbe(
                f"{s.bridge_url.rstrip('/')}/health", timeout=3.0)
        elif impl.name == "pixabay":
            probes[(impl.kind.value, impl.name)] = HttpReachableProbe(
                f"https://pixabay.com/api/?key={s.pixabay_key}&per_page=3", timeout=5.0)
        elif impl.name == "pexels":
            probes[(impl.kind.value, impl.name)] = HttpReachableProbe(
                "https://api.pexels.com/v1/search?query=test&per_page=1",
                headers={"Authorization": s.pexels_key}, timeout=5.0)
        elif impl.name in local:
            probes[(impl.kind.value, impl.name)] = LocalProviderProbe()
    return probes
