"""Casos de uso de perfis de canal (multi-canal).

Dependem apenas das portas (`ChannelProfileRepository`, `VideoRepository`) e do domínio.
Erros explícitos: conflito de unicidade (`DuplicateChannelProfile`) e de versão
(`ChannelVersionConflict`) vêm do domínio; projeto ausente vira `ProjectNotFound`.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..domain.channel import (
    CREATABLE_FIELDS,
    ChannelFieldInvalid,
    ChannelProfile,
    UPDATABLE_FIELDS,
    validate_version,
)
from ..domain.ids import check_id
from .errors import ProjectNotFound
from .ports import ChannelProfileRepository, VideoRepository


class CreateChannelProfile:
    def __init__(self, repo: ChannelProfileRepository, videos_repo: VideoRepository | None = None):
        self.repo = repo
        self.videos_repo = videos_repo

    def execute(self, project_id: str, name: str, **options: object) -> ChannelProfile:
        p_id = check_id(project_id)
        unknown = set(options) - set(CREATABLE_FIELDS)
        if unknown:
            raise ChannelFieldInvalid(f"unknown channel profile fields: {sorted(unknown)}")
        if self.videos_repo is not None and self.videos_repo.get_project(p_id) is None:
            raise ProjectNotFound(p_id)
        return self.repo.create(p_id, name, **options)


class GetChannelProfile:
    def __init__(self, repo: ChannelProfileRepository, videos_repo: VideoRepository | None = None):
        self.repo = repo
        self.videos_repo = videos_repo

    def execute(self, project_id: str) -> ChannelProfile | None:
        p_id = check_id(project_id)
        if self.videos_repo is not None and self.videos_repo.get_project(p_id) is None:
            raise ProjectNotFound(p_id)
        return self.repo.get_by_project(p_id)


class ListChannelProfiles:
    def __init__(self, repo: ChannelProfileRepository):
        self.repo = repo

    def execute(self, include_archived: bool = False) -> list[ChannelProfile]:
        if not isinstance(include_archived, bool):
            raise ChannelFieldInvalid("include_archived must be a boolean")
        return self.repo.list(include_archived)


class UpdateChannelProfile:
    def __init__(self, repo: ChannelProfileRepository):
        self.repo = repo

    def execute(self, profile_id: str, changes: Mapping[str, object], expected_version: int) -> ChannelProfile | None:
        p_id = check_id(profile_id)
        version = validate_version(expected_version)
        unknown = set(changes) - set(UPDATABLE_FIELDS)
        if unknown:
            raise ChannelFieldInvalid(f"unknown channel profile fields: {sorted(unknown)}")
        return self.repo.update(p_id, version, dict(changes))
