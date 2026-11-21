"""Casos de uso da biblioteca de estilos visuais (VS-05a) — a superfície da tela de Estilos.

Dependem apenas da porta `VisualStyleRepository` e do domínio. O estilo é **compartilhado**: a
biblioteca não pertence a um canal, então nenhum caso de uso aqui exige um `project_id`. Erros
explícitos vêm do domínio/erros de aplicação: nome/params inválidos (`VisualStyleNameInvalid`/
`VisualStyleParamsInvalid`), campo de edição desconhecido (`VisualStyleFieldInvalid`), conflito
de versão (`VisualStyleVersionConflict`), nome ativo duplicado (`DuplicateVisualStyle`) e estilo
inexistente (`VisualStyleNotFound`, levantado pela API ao ler `None`).
"""
from __future__ import annotations

from collections.abc import Mapping

from ..domain.ids import check_id
from ..domain.visual_style import (
    UPDATABLE_FIELDS,
    VisualStyle,
    VisualStyleArchive,
    VisualStyleFieldInvalid,
    validate_version,
)
from .ports import VisualStyleRepository


class CreateVisualStyle:
    def __init__(self, repo: VisualStyleRepository):
        self.repo = repo

    def execute(self, name: str, params: Mapping[str, object] | None = None) -> VisualStyle:
        return self.repo.create(name, params=dict(params) if params is not None else {})


class GetVisualStyle:
    def __init__(self, repo: VisualStyleRepository):
        self.repo = repo

    def execute(self, style_id: str) -> VisualStyle | None:
        return self.repo.get(check_id(style_id))


class ListVisualStyles:
    def __init__(self, repo: VisualStyleRepository):
        self.repo = repo

    def execute(self, include_archived: bool = False) -> list[VisualStyle]:
        if not isinstance(include_archived, bool):
            raise VisualStyleFieldInvalid("include_archived must be a boolean")
        return self.repo.list(include_archived)


class UpdateVisualStyle:
    def __init__(self, repo: VisualStyleRepository):
        self.repo = repo

    def execute(self, style_id: str, changes: Mapping[str, object], expected_version: int) -> VisualStyle | None:
        sid = check_id(style_id)
        version = validate_version(expected_version)
        unknown = set(changes) - set(UPDATABLE_FIELDS)
        if unknown:
            raise VisualStyleFieldInvalid(f"unknown visual style fields: {sorted(unknown)}")
        return self.repo.update(sid, version, dict(changes))


class ArchiveVisualStyle:
    """Arquiva (soft delete) e devolve quantos vínculos foram limpos (VS-05c).

    O estilo arquivado some da lista padrão e libera o nome; na mesma transação os canais e vídeos
    que o usavam passam a ``NULL`` (canal ao padrão do estúdio, vídeo a herdar do canal). O
    ``cleared_links`` do resultado é a medição real da limpeza.
    """

    def __init__(self, repo: VisualStyleRepository):
        self.repo = repo

    def execute(self, style_id: str) -> VisualStyleArchive | None:
        return self.repo.archive(check_id(style_id))


class VisualStyleUsage:
    """Quantos canais usam cada estilo — leitura medida, nunca estimada."""

    def __init__(self, repo: VisualStyleRepository):
        self.repo = repo

    def execute(self) -> dict[str, int]:
        return self.repo.usage_counts()
