import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application import config  # noqa: E402
from app.studio.application.config import ProjectConfig, ProviderNotFound, build, register  # noqa: E402
from app.studio.application.use_cases import CreateProject, CreateVideo, ProjectNotFound, TransitionVideo  # noqa: E402
from app.studio.domain.contracts import Project, Video, VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.states import InvalidTransition  # noqa: E402


class FakeRepo:
    def __init__(self, status=VideoStatus.IDEA):
        self.status, self.projects = status, {}

    def create_project(self, name, niche="", language="pt-BR"):
        p = Project(id="p" * 32, name=name, niche=niche, language=language)
        self.projects[p.id] = p
        return p

    def get_project(self, project_id):
        return self.projects.get(project_id)

    def create_video(self, project_id, topic, fmt):
        return Video(id="v" * 32, project_id=project_id, topic=topic, format=fmt)

    def get_video(self, video_id):
        return None

    def transition_video(self, video_id, expected, new):
        if self.status != expected:
            return False
        self.status = new
        return True


class FakeText:
    name = "fake"

    def __init__(self, model):
        self.model = model


def test_transition_use_case_with_fake_repo_needs_no_database():
    repo = FakeRepo()
    assert TransitionVideo(repo).execute("v" * 32, VideoStatus.IDEA, VideoStatus.SCRIPTED) is True
    assert TransitionVideo(repo).execute("v" * 32, VideoStatus.IDEA, VideoStatus.SCRIPTED) is False  # perdeu a corrida
    with pytest.raises(InvalidTransition):
        TransitionVideo(repo).execute("v" * 32, VideoStatus.RENDERED, VideoStatus.APPROVED)


def test_create_video_requires_existing_project():
    repo = FakeRepo()
    with pytest.raises(ProjectNotFound):
        CreateVideo(repo).execute("x" * 32, "ADE 2026", VideoFormat.short)
    p = CreateProject(repo).execute("canal")
    assert CreateVideo(repo).execute(p.id, "ADE 2026", VideoFormat.short).status == VideoStatus.IDEA


def test_registry_builds_by_name_and_rejects_unknown():
    register("text", "fake", FakeText)
    built = build("text", "fake:model:free")
    assert built.name == "fake" and built.model == "model:free"  # só o primeiro ":" separa
    for bad in ("text", "naoexiste:m", "fake"):
        with pytest.raises(ProviderNotFound):
            build("text" if bad != "text" else "kind-inexistente", bad)
    with pytest.raises(ProviderNotFound):
        build("coisa", "fake:m")


def test_project_config_overrides_env_defaults(monkeypatch):
    monkeypatch.setenv("STUDIO_TEXT", "opencode:a")
    assert ProjectConfig.resolve({"text": "gemini:b"}).text == "gemini:b"
    assert ProjectConfig.resolve({}).text == "opencode:a"
    assert ProjectConfig.resolve({}).renderer == "ffmpeg:rich"


def test_project_config_rejects_unknown_key():
    with pytest.raises(ValueError):
        ProjectConfig.resolve({"textt": "x:y"})
