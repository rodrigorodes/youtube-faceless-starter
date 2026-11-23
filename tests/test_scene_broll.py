"""B-roll por cena — caso de uso `SetSceneBroll` e rota `POST /videos/{id}/scenes/{id}/broll` (sem banco)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.studio.api.routes import make_router  # noqa: E402
from app.studio.application.editorial import VideoNotFound  # noqa: E402
from app.studio.application.media import (  # noqa: E402
    SceneBrollResult, SceneMediaRefused, SceneNotFound, SetSceneBroll,
)
from app.studio.domain.contracts import Scene, Video, VideoFormat, VideoStatus  # noqa: E402

V, P = "v" * 32, "p" * 32
SCENE = "b" * 32
VID = "a" * 32  # id válido (hex) para a rota


def scene_id(idx: int) -> str:
    return f"{idx:032x}"


class Videos:
    exists = True

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic="ADE 2026", format=VideoFormat.short,
                     status=VideoStatus.STORYBOARDED) if self.exists else None


class Store:
    """Escreve nas mesmas cenas que `scenes()` lê, como o Postgres."""

    def __init__(self, count=2):
        self.state = {i: (False, None) for i in range(count)}
        self.assets = {i: f"{i + 1:032x}" for i in range(count)}
        self.writes = []

    def scenes(self, video_id):
        return [Scene(id=scene_id(i), video_id=V, idx=i, narration=f"Narração {i} válida", image_prompt="wide stage with colorful lights",
                      claim_ids=["c"], asset_id=self.assets[i], broll_enabled=self.state[i][0],
                      broll_note=self.state[i][1]) for i in self.state]

    def set_scene_broll(self, video_id, sid, enabled, note):
        self.writes.append((sid, enabled, note))
        idx = int(sid, 16)
        if idx not in self.state:
            return False
        self.state[idx] = (enabled, note)
        return True


def usecase(store=None, videos=None):
    store = store or Store()
    return SetSceneBroll(videos or Videos(), store, store), store


def test_enable_and_disable_only_the_target_scene_keeping_media():
    uc, store = usecase()
    result = uc.execute(V, scene_id(1), enabled=True, note="plano aberto da cidade")
    assert result == SceneBrollResult(scene_id=scene_id(1), enabled=True, note="plano aberto da cidade", changed=True)
    assert store.state == {0: (False, None), 1: (True, "plano aberto da cidade")}
    assert store.assets == {0: scene_id(1), 1: scene_id(2)}  # mídia intacta
    off = uc.execute(V, scene_id(1), enabled=False, note=None)
    assert off.changed and off.enabled is False and off.note is None
    assert store.state[1] == (False, None)


@pytest.mark.parametrize("raw,expected", [("  inserto  ", "inserto"), ("   ", None), ("", None), (None, None)])
def test_note_is_normalized(raw, expected):
    uc, store = usecase()
    result = uc.execute(V, scene_id(0), enabled=True, note=raw)
    assert result.note == expected
    assert store.state[0] == (True, expected)


def test_note_over_200_chars_is_refused_without_writing():
    uc, store = usecase()
    with pytest.raises(SceneMediaRefused):
        uc.execute(V, scene_id(0), enabled=True, note="x" * 201)
    assert store.writes == []
    assert uc.execute(V, scene_id(0), enabled=True, note="x" * 200).changed is True


def test_same_value_is_idempotent_and_does_not_write():
    uc, store = usecase()
    uc.execute(V, scene_id(0), enabled=True, note="a")
    again = uc.execute(V, scene_id(0), enabled=True, note="  a ")
    assert again.changed is False and len(store.writes) == 1
    assert uc.execute(V, scene_id(1), enabled=False, note=None).changed is False  # default já é desligado
    assert len(store.writes) == 1


def test_unknown_scene_and_video():
    uc, store = usecase()
    with pytest.raises(SceneNotFound):
        uc.execute(V, scene_id(9), enabled=True)
    assert store.writes == []
    videos = Videos()
    videos.exists = False
    uc, _ = usecase(videos=videos)
    with pytest.raises(VideoNotFound):
        uc.execute(V, scene_id(0), enabled=True)


def test_scene_vanishing_between_read_and_write_is_not_found():
    uc, store = usecase()
    store.set_scene_broll = lambda *a: False
    with pytest.raises(SceneNotFound):
        uc.execute(V, scene_id(0), enabled=True)


# ---------- rota ----------
class _Broll:
    def __init__(self, result):
        self.result, self.calls = result, []

    def execute(self, video_id, scene_id, *, enabled, note=None):
        self.calls.append((video_id, scene_id, enabled, note))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Media:
    def __init__(self, broll=None):
        self.broll = broll


class _UseCases:
    def __init__(self, media):
        self.media = media


def client(media):
    app = FastAPI()
    app.include_router(make_router(lambda: _UseCases(media), lambda: True))
    return TestClient(app, headers={"Authorization": "Bearer test-worker-token"})


def test_route_returns_200_with_the_documented_payload():
    broll = _Broll(SceneBrollResult(scene_id=SCENE, enabled=True, note="inserto", changed=True))
    response = client(_Media(broll)).post(f"/studio/videos/{VID}/scenes/{SCENE}/broll",
                                          json={"enabled": True, "note": "inserto"})
    assert response.status_code == 200
    assert response.json() == {"scene_id": SCENE, "enabled": True, "note": "inserto", "changed": True}
    assert broll.calls == [(VID, SCENE, True, "inserto")]


def test_route_unknown_scene_is_404():
    response = client(_Media(_Broll(SceneNotFound(SCENE)))).post(
        f"/studio/videos/{VID}/scenes/{SCENE}/broll", json={"enabled": True})
    assert response.status_code == 404 and response.json()["detail"] == "scene not found"


def test_route_validates_body_and_ids_and_availability():
    ok = _Broll(SceneBrollResult(scene_id=SCENE, enabled=False, note=None, changed=False))
    c = client(_Media(ok))
    assert c.post(f"/studio/videos/{VID}/scenes/{SCENE}/broll", json={"enabled": True, "note": "x" * 201}).status_code == 422
    assert c.post(f"/studio/videos/{VID}/scenes/{SCENE}/broll", json={"note": "a"}).status_code == 422
    assert c.post(f"/studio/videos/not-an-id/scenes/{SCENE}/broll", json={"enabled": True}).status_code == 422
    assert ok.calls == []
    assert client(_Media(None)).post(f"/studio/videos/{VID}/scenes/{SCENE}/broll", json={"enabled": True}).status_code == 503
    assert client(None).post(f"/studio/videos/{VID}/scenes/{SCENE}/broll", json={"enabled": True}).status_code == 503
