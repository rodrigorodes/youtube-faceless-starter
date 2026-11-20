"""Testes da camada de aplicação (perfil de canal) com repositórios falsos: sem banco."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.channels import (  # noqa: E402
    CreateChannelProfile,
    GetChannelProfile,
    ListChannelProfiles,
    UpdateChannelProfile,
)
from app.studio.application.errors import ProjectNotFound  # noqa: E402
from app.studio.domain.channel import (  # noqa: E402
    ChannelFieldInvalid,
    ChannelProfile,
    ChannelVersionConflict,
    DuplicateChannelProfile,
)
from app.studio.domain.ids import InvalidId  # noqa: E402

PID = "a" * 32
CID = "b" * 32


class FakeVideoRepo:
    def __init__(self, project_ids=()):
        self.project_ids = set(project_ids)

    def get_project(self, project_id):
        return object() if project_id in self.project_ids else None


class FakeChannelRepo:
    def __init__(self, profiles=None):
        self.profiles = list(profiles or [])
        self.calls = []

    def create(self, project_id, name, **options):
        self.calls.append(("create", project_id, name, options))
        p = ChannelProfile(id=CID, project_id=project_id, name=name, **options)
        self.profiles.append(p)
        return p

    def get_by_project(self, project_id):
        self.calls.append(("get_by_project", project_id))
        return next((p for p in self.profiles if p.project_id == project_id), None)

    def list(self, include_archived=False):
        self.calls.append(("list", include_archived))
        if include_archived:
            return list(self.profiles)
        return [p for p in self.profiles if not p.archived]

    def update(self, profile_id, expected_version, changes):
        self.calls.append(("update", profile_id, expected_version, changes))
        current = next((p for p in self.profiles if p.id == profile_id), None)
        if current is None:
            return None
        if current.version != expected_version:
            raise ChannelVersionConflict(f"expected {expected_version}, found {current.version}")
        return current


def test_create_requires_existing_project():
    repo = FakeChannelRepo()
    with pytest.raises(ProjectNotFound):
        CreateChannelProfile(repo, FakeVideoRepo()).execute(PID, "Canal")
    assert repo.calls == []

    videos = FakeVideoRepo([PID])
    created = CreateChannelProfile(repo, videos).execute(PID, "Canal", strategy="nicho")
    assert created.project_id == PID
    assert repo.calls[0][0] == "create"
    assert repo.calls[0][3] == {"strategy": "nicho"}


def test_create_validates_id_before_repo():
    repo = FakeChannelRepo()
    with pytest.raises(InvalidId):
        CreateChannelProfile(repo, FakeVideoRepo([PID])).execute("not-an-id", "Canal")
    assert repo.calls == []


def test_create_rejects_unknown_option_before_repo():
    repo = FakeChannelRepo()
    with pytest.raises(ValueError):
        CreateChannelProfile(repo, FakeVideoRepo([PID])).execute(PID, "Canal", bogus=1)
    assert repo.calls == []


def test_create_propagates_duplicate_conflict():
    class DupRepo(FakeChannelRepo):
        def create(self, project_id, name, **options):
            raise DuplicateChannelProfile("already exists")

    with pytest.raises(DuplicateChannelProfile):
        CreateChannelProfile(DupRepo(), FakeVideoRepo([PID])).execute(PID, "Canal")


def test_get_returns_profile_and_guard_project():
    existing = ChannelProfile(id=CID, project_id=PID, name="Canal")
    repo = FakeChannelRepo([existing])
    assert GetChannelProfile(repo, FakeVideoRepo([PID])).execute(PID) is existing
    with pytest.raises(ProjectNotFound):
        GetChannelProfile(repo, FakeVideoRepo()).execute(PID)
    with pytest.raises(InvalidId):
        GetChannelProfile(repo, FakeVideoRepo([PID])).execute("bad")


def test_list_forwards_include_archived():
    archived = ChannelProfile(id=CID, project_id=PID, name="Antigo", archived=True)
    repo = FakeChannelRepo([archived])
    assert ListChannelProfiles(repo).execute() == []
    assert ListChannelProfiles(repo).execute(include_archived=True) == [archived]
    assert repo.calls == [("list", False), ("list", True)]


def test_list_rejects_non_boolean_include_archived():
    repo = FakeChannelRepo()
    for bad in ("yes", 1, None):
        with pytest.raises(ChannelFieldInvalid):
            ListChannelProfiles(repo).execute(include_archived=bad)  # type: ignore[arg-type]
    assert repo.calls == []


def test_update_rejects_unknown_fields_before_repo():
    repo = FakeChannelRepo()
    with pytest.raises(ValueError):
        UpdateChannelProfile(repo).execute(CID, {"nope": 1}, 1)
    assert repo.calls == []


def test_update_forwards_changes_and_version():
    repo = FakeChannelRepo([ChannelProfile(id=CID, project_id=PID, name="Canal")])
    UpdateChannelProfile(repo).execute(CID, {"name": "Canal 2"}, 1)
    assert repo.calls == [("update", CID, 1, {"name": "Canal 2"})]


def test_update_propagates_version_conflict():
    repo = FakeChannelRepo([ChannelProfile(id=CID, project_id=PID, name="Canal", version=2)])
    with pytest.raises(ChannelVersionConflict):
        UpdateChannelProfile(repo).execute(CID, {"name": "x"}, 1)
