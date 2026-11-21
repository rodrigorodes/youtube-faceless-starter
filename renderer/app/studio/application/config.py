"""Configuração por projeto e registro de provedores por nome."""
from collections.abc import Callable, Mapping

from pydantic import BaseModel, ConfigDict

KINDS = ("text", "image", "voice", "renderer")
_DEFAULTS = {
    "text": ("STUDIO_TEXT", "opencode:openai/gpt-6-luna"),
    "image": ("STUDIO_IMAGE", "opencode:openrouter/recraft/recraft-v4.1-flash-v2:free"),
    "voice": ("STUDIO_VOICE", "piper:pt_BR-faber-medium"),
    "renderer": ("STUDIO_RENDERER", "ffmpeg:rich"),
}


class ProviderNotFound(ValueError):
    pass


class ProjectConfig(BaseModel):
    """Cada campo é "<provedor>[:<modelo>]" (o modelo é opcional). O ambiente dá o padrão; o projeto sobrescreve."""
    model_config = ConfigDict(extra="forbid")
    text: str
    image: str
    voice: str
    renderer: str

    @classmethod
    def resolve(cls, overrides: Mapping[str, str], env: Mapping[str, str]) -> "ProjectConfig":
        """`env` é injetado (a composição passa os.environ): a camada de aplicação não lê o ambiente."""
        unknown = set(overrides) - set(KINDS)
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**{k: overrides.get(k) or env.get(var) or default for k, (var, default) in _DEFAULTS.items()})


_REGISTRY: dict[tuple[str, str], Callable[[str], object]] = {}


def register(kind: str, name: str, factory: Callable[[str], object]) -> None:
    _REGISTRY[(kind, name)] = factory


def build(kind: str, spec: str) -> object:
    name, sep, model = spec.partition(":")  # só o primeiro ":" separa (modelos podem conter ":free")
    factory = _REGISTRY.get((kind, name)) if sep and kind in KINDS else None
    if factory is None:
        raise ProviderNotFound(f"no {kind} provider for {spec!r}")
    return factory(model)
