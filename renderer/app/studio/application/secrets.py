"""Configuração pública do projeto (F10-07): só portas de provider, nunca segredos."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import ValidationError

from ..domain.ids import check_id
from ..domain.provider import ProviderImplementation, ProviderKind, parse_spec, registered_names
from ..domain.secrets import sanitize_project_config
from .config import KINDS, ProjectConfig
from .errors import InvalidInput, ProjectNotFound
from .ports import VideoRepository

# O modelo é opcional porque `demo:` (e `demo`, `placeholder`, `piper`) são specs legítimos do
# catálogo: a mensagem só é verdadeira se prometer `<provedor>` e `<provedor>:<modelo>`.
_VALUES_MESSAGE = ("project config values must be non-empty provider specs "
                   "like '<provider>' or '<provider>:<model>'")


class GetPublicProjectConfig:
    """Lê o `Project.config` e devolve a lista branca que pode ir ao browser."""

    def __init__(self, videos: VideoRepository):
        self.videos = videos

    def execute(self, project_id: str) -> dict[str, object]:
        p_id = check_id(project_id)
        project = self.videos.get_project(p_id)
        if project is None:
            raise ProjectNotFound(p_id)
        return {"project_id": p_id, "config": sanitize_project_config(project.config)}


class SetPublicProjectConfig:
    """Escreve o `Project.config` (o override por projeto), validando as quatro portas de provider.

    A validação é em três camadas: `ProjectConfig` exige as quatro portas (`extra="forbid"`,
    chave desconhecida recusada com 422 sem ecoar a chave/valor recusado); `parse_spec` exige um
    spec `<provedor>[:<modelo>]` não vazio (o modelo é opcional); e o catálogo de implementações
    recusa cedo um provedor que não existe — em vez de salvar e quebrar depois em `provider_for`
    (`ProviderNotFound`, em tempo de render). Um provedor registrado porém não validado (ex.:
    `veo`) é **aceito**: o `GET`/catálogo mostra o motivo real (UNAVAILABLE). O retorno é sempre
    sanitizado.
    """

    def __init__(self, videos: VideoRepository,
                 implementations: Sequence[ProviderImplementation] = ()):
        # `implementations` vem do composition (o catálogo já montado): a camada de aplicação
        # não importa adapters. É a mesma fonte de verdade que os cartões/roteamento usam.
        self.videos = videos
        self.implementations = tuple(implementations)

    def _registered(self, kind: str) -> tuple[str, ...]:
        return registered_names(self.implementations, ProviderKind(kind))

    def execute(self, project_id: str, config: Mapping[str, object]) -> dict[str, object]:
        p_id = check_id(project_id)
        if not isinstance(config, Mapping):
            raise InvalidInput("project config must be an object")
        unknown = set(config) - set(KINDS)
        if unknown:
            raise InvalidInput(f"unknown config keys: {sorted(unknown)}")  # só os nomes, nunca os valores
        missing = set(KINDS) - set(config)
        if missing:
            raise InvalidInput(f"config must define every provider port: {sorted(missing)} missing")
        try:
            validated = ProjectConfig.model_validate(dict(config))
        except ValidationError as exc:
            raise InvalidInput(_VALUES_MESSAGE) from exc
        overrides: dict[str, str] = {}
        for kind in KINDS:
            spec = getattr(validated, kind).strip()
            name, _model = parse_spec(spec)  # spec inválida -> ProviderSpecInvalid (a API responde 422)
            registered = self._registered(kind)
            if name not in registered:
                options = ", ".join(registered) if registered else "none"
                # mensagem útil e SEM o valor ofensor: diz a porta e os provedores que existem.
                raise InvalidInput(f"unknown {kind} provider; registered providers are: {options}")
            overrides[kind] = spec
        project = self.videos.set_project_config(p_id, overrides)
        if project is None:
            raise ProjectNotFound(p_id)
        return {"project_id": p_id, "config": sanitize_project_config(project.config)}
