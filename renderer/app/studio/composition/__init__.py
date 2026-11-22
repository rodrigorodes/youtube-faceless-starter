"""Raiz de composição: único lugar que liga casos de uso aos adaptadores concretos.

S4: a implementação é dividida em ``settings`` (configuração tipada), ``providers``
(catálogo e roteamento de provedores) e ``wiring`` (fiação dos casos de uso). Este pacote
reexporta a API pública, preservando ``from app.studio.composition import ...``.
"""
from .settings import (CONNECT_OPTIONS, DEFAULT_ALLOWLIST, DEFAULT_ALLOW_NAMES,
                       PING_TTL_SECONDS, RETRY_SECONDS, Settings, _cap, _csv, _flag,
                       _production_mode)
from .providers import (FREE_PROVIDERS, ProviderRouting, _configured_provider_spec,
                        _provider_implementations, _provider_probes, build_google_oauth)
from .wiring import (Studio, _active_style, _economic_profile_for, _effective_config_for,
                     _style_for_video, _voice_for_config, _voice_for_video, _voice_model,
                     channel_guard_limits)

__all__ = [
    "CONNECT_OPTIONS", "DEFAULT_ALLOWLIST", "DEFAULT_ALLOW_NAMES", "FREE_PROVIDERS",
    "PING_TTL_SECONDS", "RETRY_SECONDS", "Settings", "Studio", "ProviderRouting",
    "build_google_oauth", "channel_guard_limits",
    "_active_style", "_cap", "_configured_provider_spec", "_csv", "_economic_profile_for",
    "_effective_config_for", "_flag", "_production_mode", "_provider_implementations",
    "_provider_probes", "_style_for_video", "_voice_for_config", "_voice_for_video",
    "_voice_model",
]
