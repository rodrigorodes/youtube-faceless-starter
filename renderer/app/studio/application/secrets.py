"""Configuração pública do projeto (F10-07): só portas de provider, nunca segredos."""
from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from ..domain.ids import check_id
from ..domain.provider import parse_spec
from ..domain.secrets import sanitize_project_config
from .config import KINDS, ProjectConfig
from .errors import InvalidInput, ProjectNotFound
from .ports import VideoRepository


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

    A validação é por `ProjectConfig` (as quatro portas, `extra="forbid"`): chave desconhecida é
    recusada com 422 e a resposta nunca devolve a chave/valor recusado. Cada valor é um spec
    `<provedor>:<modelo>` validado por `parse_spec`. O retorno é sempre sanitizado.
    """

    def __init__(self, videos: VideoRepository):
        self.videos = videos

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
            raise InvalidInput("project config values must be non-empty '<provider>:<model>' strings") from exc
        overrides: dict[str, str] = {}
        for kind in KINDS:
            spec = getattr(validated, kind).strip()
            parse_spec(spec)  # spec inválida -> ProviderSpecInvalid (a API responde 422)
            overrides[kind] = spec
        project = self.videos.set_project_config(p_id, overrides)
        if project is None:
            raise ProjectNotFound(p_id)
        return {"project_id": p_id, "config": sanitize_project_config(project.config)}