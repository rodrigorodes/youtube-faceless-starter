import math
import shutil
import struct
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.studio.api.routes import make_router  # noqa: E402
from app.studio.application.config import register  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402

SOURCE = (
    "Amsterdam Dance Event celebrates 30 years with more than 3,600 artists, 1,300 events and 300 venues across the city.\n"
    "Jean-Michel Jarre opens the festival with a concert at AFAS Live on 21 October to mark 50 years of Oxygène.\n"
)
REF = "https://www.amsterdam-dance-event.nl/en/about"


class ToneVoice:
    """Voz de teste: tom de 1 s (alto), silêncio (`mute`) ou duração fingida de 100 s (`long`, nunca chega ao renderer)."""
    name = "tone"

    def __init__(self, model):
        self.model = model

    def speak(self, text, out_path):
        if self.model == "long":
            return 100.0
        amplitude = 0.0 if self.model == "mute" else 0.4
        rate = 22050
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
            w.writeframes(b"".join(struct.pack("<h", int(32767 * amplitude * math.sin(2 * math.pi * 220 * i / rate))) for i in range(rate)))
        return 1.0


class Boom:
    name = "boom"

    def __init__(self, model):
        pass

    def render(self, spec, out_path):
        raise RuntimeError("ffmpeg falhou de propósito")


class NoSound:
    """Renderer que entrega um vídeo do tamanho certo, mas sem faixa de áudio (defeito que o QA precisa pegar)."""
    name = "nosound"

    def __init__(self, model):
        pass

    def render(self, spec, out_path):
        import subprocess
        from app.studio.domain.render import SIZE
        import shutil as _sh
        _sh.copyfile(spec.speech_wavs[0], spec.work_dir / "narration.wav")  # a voz existe; só o vídeo final sai sem faixa de áudio
        w, h = SIZE[spec.format]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=25", "-t", f"{sum(spec.scene_seconds):.2f}",
                        "-pix_fmt", "yuv420p", str(out_path)], check=True)
        return Path(out_path)


register("voice", "tone", ToneVoice)
register("renderer", "nosound", NoSound)
register("renderer", "boom", Boom)


class SyncExecutor:
    def submit(self, fn, *args):
        fn(*args)

    def shutdown(self, wait=True, cancel_futures=False):
        self.closed = (wait, cancel_futures)


class Deferred:
    def __init__(self):
        self.tasks = []

    def submit(self, fn, *args):
        self.tasks.append((fn, args))

    def run_all(self):
        while self.tasks:
            fn, args = self.tasks.pop(0)
            fn(*args)


def make_client(dsn, tmp_path, voice="tone:ok", renderer="ffmpeg:rich", executor=None, fmt="short"):
    environ = {"STUDIO_TEXT": "demo:x", "STUDIO_IMAGE": "placeholder:gradient", "STUDIO_VOICE": voice, "STUDIO_RENDERER": renderer}
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ=environ, executor=executor or SyncExecutor())
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return TestClient(app), studio


@pytest.fixture()
def migrated(conn):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    return conn


def ready_video(client, name="canal", fmt="short", scenes=2):
    pid = client.post("/studio/projects", json={"name": name}).json()["id"]
    vid = client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": fmt}).json()["id"]
    client.post(f"/studio/videos/{vid}/sources", json={"url": REF, "text": SOURCE})
    client.post(f"/studio/videos/{vid}/script", json={"scene_count": scenes})
    assert client.post(f"/studio/videos/{vid}/fact-check", json={}).status_code == 200
    assert client.post(f"/studio/videos/{vid}/storyboard").status_code == 200
    assert client.post(f"/studio/videos/{vid}/assets").status_code == 200
    return vid


def status(client, vid):
    return client.get(f"/studio/videos/{vid}").json()["status"]


def test_full_render_short_produces_playable_files_and_moves_to_awaiting_approval(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = ready_video(client)
    r = client.post(f"/studio/videos/{vid}/render")
    assert r.status_code == 202 and r.json()["status"] in ("QUEUED", "RUNNING", "SUCCEEDED")
    got = client.get(f"/studio/videos/{vid}/render").json()
    assert got["job"]["status"] == "SUCCEEDED" and got["job"]["output_asset_id"] and got["qa_report"]["passed"] is True, got
    assert got["qa_report"]["metrics"]["width"] == 1080 and got["qa_report"]["metrics"]["height"] == 1920
    assert status(client, vid) == "AWAITING_APPROVAL"
    mp4 = client.get(f"/studio/videos/{vid}/file")
    assert mp4.status_code == 200 and mp4.headers["content-type"] == "video/mp4" and b"ftyp" in mp4.content[:64]
    srt = client.get(f"/studio/videos/{vid}/subtitles")
    assert srt.status_code == 200 and "-->" in srt.text and srt.headers["content-type"].startswith("text/plain")
    assert not list(tmp_path.rglob("work"))  # intermediários descartados
    assert client.post(f"/studio/videos/{vid}/render").status_code == 409  # AWAITING_APPROVAL


def test_long_format_renders_landscape(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = ready_video(client, fmt="long")
    client.post(f"/studio/videos/{vid}/render")
    got = client.get(f"/studio/videos/{vid}/render").json()
    assert got["qa_report"]["passed"] is True and (got["qa_report"]["metrics"]["width"], got["qa_report"]["metrics"]["height"]) == (1920, 1080), got


def test_guards_and_errors(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    pid = client.post("/studio/projects", json={"name": "c"}).json()["id"]
    vid = client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": "short"}).json()["id"]
    assert client.post(f"/studio/videos/{vid}/render").status_code == 409
    assert client.get(f"/studio/videos/{vid}/render").json() == {"job": None, "qa_report": None}
    assert client.get(f"/studio/videos/{vid}/file").status_code == 404 and client.get(f"/studio/videos/{vid}/subtitles").status_code == 404
    for path in ("render", "file", "subtitles"):
        assert client.get(f"/studio/videos/{'0' * 32}/{path}").status_code == 404
        assert client.get(f"/studio/videos/{'A' * 32}/{path}").status_code == 422
    assert client.post(f"/studio/videos/{'0' * 32}/render").status_code == 404
    assert client.post(f"/studio/videos/{'A' * 32}/render").status_code == 422


def test_renderer_failure_is_recorded_and_retry_makes_a_new_attempt(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path, renderer="boom:x")
    vid = ready_video(client)
    assert client.post(f"/studio/videos/{vid}/render").status_code == 202
    job = client.get(f"/studio/videos/{vid}/render").json()["job"]
    assert job["status"] == "FAILED" and "falhou de propósito" in job["error"] and status(client, vid) == "ASSETS_READY"
    assert client.get(f"/studio/videos/{vid}/file").status_code == 404
    client.post(f"/studio/videos/{vid}/render")
    assert client.get(f"/studio/videos/{vid}/render").json()["job"]["attempt"] == 2


def test_video_without_audio_fails_qa_stays_rendered_and_can_be_rendered_again(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path, renderer="nosound:x")
    vid = ready_video(client)
    client.post(f"/studio/videos/{vid}/render")
    got = client.get(f"/studio/videos/{vid}/render").json()
    assert got["job"]["status"] == "SUCCEEDED" and got["qa_report"]["passed"] is False and any("audio" in f for f in got["qa_report"]["failures"]), got
    assert status(client, vid) == "RENDERED" and client.get(f"/studio/videos/{vid}/file").status_code == 200
    again, _ = make_client(dsn, tmp_path)
    assert again.post(f"/studio/videos/{vid}/render").status_code == 202
    assert again.get(f"/studio/videos/{vid}/render").json()["qa_report"]["passed"] is True and status(again, vid) == "AWAITING_APPROVAL"


def test_video_over_the_duration_limit_is_refused_before_rendering(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path, voice="tone:long")
    vid = ready_video(client)
    client.post(f"/studio/videos/{vid}/render")
    job = client.get(f"/studio/videos/{vid}/render").json()["job"]
    assert job["status"] == "FAILED" and "limit" in job["error"] and status(client, vid) == "ASSETS_READY"


def test_render_is_async_and_a_repeated_request_does_not_enqueue_twice(migrated, dsn, tmp_path):
    deferred = Deferred()
    client, _ = make_client(dsn, tmp_path, executor=deferred)
    vid = ready_video(client)
    first = client.post(f"/studio/videos/{vid}/render")
    second = client.post(f"/studio/videos/{vid}/render")
    assert first.status_code == second.status_code == 202 and first.json()["id"] == second.json()["id"] and len(deferred.tasks) == 1
    assert client.get(f"/studio/videos/{vid}/render").json()["job"]["status"] == "QUEUED" and status(client, vid) == "ASSETS_READY"
    deferred.run_all()
    assert client.get(f"/studio/videos/{vid}/render").json()["job"]["status"] == "SUCCEEDED"


def test_jobs_left_running_by_a_previous_process_are_failed_on_startup(migrated, dsn, tmp_path):
    deferred = Deferred()
    client, _ = make_client(dsn, tmp_path, executor=deferred)
    vid = ready_video(client)
    client.post(f"/studio/videos/{vid}/render")  # fica QUEUED: o processo "morre" antes de executar
    restarted, _ = make_client(dsn, tmp_path)
    assert restarted.get(f"/studio/videos/{vid}").status_code == 200
    job = restarted.get(f"/studio/videos/{vid}/render").json()["job"]
    assert job["status"] == "FAILED" and "restart" in job["error"]
    assert restarted.post(f"/studio/videos/{vid}/render").status_code == 202  # e dá para tentar de novo
    assert restarted.get(f"/studio/videos/{vid}/render").json()["job"]["status"] == "SUCCEEDED"


def test_generic_transition_cannot_fake_a_render(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = ready_video(client)
    for new in ("RENDERED", "AWAITING_APPROVAL"):
        assert client.post(f"/studio/videos/{vid}/transition", json={"expected": "ASSETS_READY", "new": new}).status_code == 403
    assert status(client, vid) == "ASSETS_READY"


def test_shutdown_does_not_wait_and_startup_sweeps_leftover_work_dirs(migrated, dsn, tmp_path):
    leftover = tmp_path / "projects" / ("1" * 32) / "videos" / ("2" * 32) / "work" / ("a" * 32)
    leftover.mkdir(parents=True)
    (leftover / "x.wav").write_bytes(b"x")
    client, studio = make_client(dsn, tmp_path)
    assert studio.use_cases() is not None and not leftover.exists() and (tmp_path / "projects" / ("1" * 32)).exists()
    studio.shutdown()  # não levanta nem espera
    assert studio._executor.closed == (False, True)


def test_startup_cleanup_failing_does_not_break_the_app_and_retries_later(migrated, dsn, tmp_path, monkeypatch):
    import psycopg

    from app.studio.adapters.postgres.render_repo import PostgresRenderJobRepository
    monkeypatch.setattr(PostgresRenderJobRepository, "fail_interrupted", lambda self: (_ for _ in ()).throw(psycopg.OperationalError("caiu")))
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ={"STUDIO_TEXT": "demo:x"}, executor=SyncExecutor())
    assert studio.use_cases() is None  # degradado, sem exceção
    monkeypatch.undo()
    studio._retry_at = 0.0
    assert studio.use_cases() is not None
