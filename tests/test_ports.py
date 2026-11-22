import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application import config  # noqa: E402
from app.studio.application.config import ProjectConfig, ProviderNotFound, build, register  # noqa: E402
from app.studio.application.errors import VisualStyleNotFound  # noqa: E402
from app.studio.application.use_cases import CreateProject, CreateVideo, ProjectNotFound, TransitionVideo  # noqa: E402
from app.studio.domain.contracts import Project, Video, VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.states import InvalidTransition  # noqa: E402
from app.studio.domain.visual_style import VisualStyle, VisualStyleArchived  # noqa: E402


class FakeRepo:
    def __init__(self, status=VideoStatus.IDEA):
        self.status, self.projects = status, {}

    def create_project(self, name, niche="", language="pt-BR"):
        p = Project(id="p" * 32, name=name, niche=niche, language=language)
        self.projects[p.id] = p
        return p

    def get_project(self, project_id):
        return self.projects.get(project_id)

    def create_video(self, project_id, topic, fmt, style_id=None):
        return Video(id="v" * 32, project_id=project_id, topic=topic, format=fmt, style_id=style_id)

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


class FakeStyles:
    """Porta mínima da biblioteca para o caso de uso (F02.T02) — sem banco."""

    def __init__(self, *styles):
        self.items = {s.id: s for s in styles}

    def get(self, style_id):
        return self.items.get(style_id)


STYLE_ID = "ab" * 16


def _style(style_id=STYLE_ID, name="Cinema Noturno", archived=False):
    return VisualStyle(id=style_id, name=name, archived=archived)


def test_create_video_with_a_real_style_validates_and_persists_it():
    """G15/F02.T02: o estilo escolhido é conferido na aplicação e gravado na criação."""
    repo = FakeRepo()
    styles = FakeStyles(_style())
    p = CreateProject(repo).execute("canal")
    video = CreateVideo(repo, styles).execute(p.id, "ADE 2026", VideoFormat.short, STYLE_ID)
    assert video.style_id == STYLE_ID
    # sem escolha explícita continua herdando o canal (nenhum style_id)
    assert CreateVideo(repo, styles).execute(p.id, "ADE 2026", VideoFormat.short).style_id is None


def test_create_video_refuses_unknown_and_archived_styles_before_persisting():
    repo = FakeRepo()
    p = CreateProject(repo).execute("canal")
    with pytest.raises(VisualStyleNotFound):
        CreateVideo(repo, FakeStyles()).execute(p.id, "ADE 2026", VideoFormat.short, "f" * 32)
    archived = FakeStyles(_style(archived=True))
    with pytest.raises(VisualStyleArchived):
        CreateVideo(repo, archived).execute(p.id, "ADE 2026", VideoFormat.short, STYLE_ID)
    with pytest.raises(VisualStyleNotFound):  # sem biblioteca injetada, falha fechado
        CreateVideo(repo).execute(p.id, "ADE 2026", VideoFormat.short, STYLE_ID)


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
    env = {"STUDIO_TEXT": "opencode:a"}
    assert ProjectConfig.resolve({"text": "gemini:b"}, env).text == "gemini:b"
    assert ProjectConfig.resolve({}, env).text == "opencode:a"
    assert ProjectConfig.resolve({}, {}).renderer == "ffmpeg:rich"


def test_project_config_rejects_unknown_key():
    with pytest.raises(ValueError):
        ProjectConfig.resolve({"textt": "x:y"}, {})
