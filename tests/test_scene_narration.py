"""W4.3 (EDIT-02) — pré-escuta e regeneração da narração de uma cena.

Prova o contrato observável: a regeneração mede a duração real, grava em `studio.scenes.duration_s`
e serve o WAV; a pré-escuta devolve 404 quando não há artefato. Nada aqui sintetiza em autosave.
"""
import math
import shutil
import struct
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402

SOURCE = (
    "Amsterdam Dance Event celebrates 30 years with more than 3,600 artists, 1,300 events and 300 venues across the city.\n"
    "Jean-Michel Jarre opens the festival with a concert at AFAS Live on 21 October to mark 50 years of Oxygène.\n"
)
REF = "https://www.amsterdam-dance-event.nl/en/about"


class ToneVoice:
    """Voz de teste: 1 s de tom, devolvendo a duração medida (como um adaptador real)."""

    name = "tone-narr"

    def __init__(self, model):
        self.model = model

    def speak(self, text, out_path):
        rate = 22050
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(b"".join(
                struct.pack("<h", int(32767 * 0.2 * math.sin(2 * math.pi * 220 * i / rate)))
                for i in range(rate)))
        return 1.0


@pytest.fixture(autouse=True)
def _register_tone_voice(registered_providers):
    """Achado 11: registra a voz de teste **dentro** do teste, com restauração do `_REGISTRY`.

    Antes era `register("voice", "tone-narr", ToneVoice)` no nível do módulo: rodava na coleta e
    vazava para `test_port_contracts`, que compara o catálogo do produto com o registro — a mesma
    falha falsa que a fixture `registered_providers` resolveu em `test_editorial_api`/`test_render_api`.
    """
    registered_providers("voice", "tone-narr", ToneVoice)


class SyncExecutor:
    def submit(self, fn, *args):
        fn(*args)

    def shutdown(self, wait=True, cancel_futures=False):
        pass


def make_client(dsn, tmp_path):
    environ = {"STUDIO_TEXT": "demo:x", "STUDIO_IMAGE": "placeholder:gradient",
               "STUDIO_VOICE": "tone-narr:ok", "STUDIO_RENDERER": "ffmpeg:rich"}
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ=environ, executor=SyncExecutor())
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return TestClient(app, headers={"Authorization": "Bearer test-worker-token"}), studio


@pytest.fixture()
def migrated(conn):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    return conn


def scripted_video(client, name="canal", scenes=2):
    pid = client.post("/studio/projects", json={"name": name}).json()["id"]
    vid = client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": "short"}).json()["id"]
    client.post(f"/studio/videos/{vid}/sources", json={"url": REF, "text": SOURCE})
    assert client.post(f"/studio/videos/{vid}/script", json={"scene_count": scenes}).status_code == 201
    return vid


def ready_video(client, name="canal", scenes=2):
    vid = scripted_video(client, name=name, scenes=scenes)
    assert client.post(f"/studio/videos/{vid}/fact-check", json={}).status_code == 200
    assert client.post(f"/studio/videos/{vid}/storyboard").status_code == 200
    assert client.post(f"/studio/videos/{vid}/assets").status_code == 200
    return vid


def test_regenerate_serves_wav_and_records_real_duration(migrated, dsn, tmp_path):
    client, studio = make_client(dsn, tmp_path)
    try:
        vid = scripted_video(client)
        scenes = client.get(f"/studio/videos/{vid}/script").json()["scenes"]
        sid = scenes[0]["id"]
        response = client.post(f"/studio/videos/{vid}/scenes/{sid}/narration/regenerate")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["scene_id"] == sid
        assert 0.9 <= body["duration_s"] <= 1.1
        assert body["audio_url"].endswith(f"/scenes/{sid}/narration.wav")
        row = migrated.execute("SELECT duration_s FROM studio.scenes WHERE id=%s", (sid,)).fetchone()
        assert row is not None and abs(float(row[0]) - body["duration_s"]) < 0.01
        wav = client.get(f"/studio/videos/{vid}/scenes/{sid}/narration.wav")
        assert wav.status_code == 200
        assert wav.headers["content-type"].startswith("audio/wav")
        status = client.get(f"/studio/videos/{vid}/scenes/{sid}/narration")
        assert status.status_code == 200
        assert status.json()["sha256"] == body["sha256"]
    finally:
        studio.shutdown()


def test_prelisten_404_before_any_synthesis(migrated, dsn, tmp_path):
    client, studio = make_client(dsn, tmp_path)
    try:
        vid = scripted_video(client)
        sid = client.get(f"/studio/videos/{vid}/script").json()["scenes"][0]["id"]
        assert client.get(f"/studio/videos/{vid}/scenes/{sid}/narration").status_code == 404
        assert client.get(f"/studio/videos/{vid}/scenes/{sid}/narration.wav").status_code == 404
    finally:
        studio.shutdown()


def test_regenerate_refuses_after_scripted(migrated, dsn, tmp_path):
    client, studio = make_client(dsn, tmp_path)
    try:
        vid = ready_video(client)
        sid = client.get(f"/studio/videos/{vid}/script").json()["scenes"][0]["id"]
        response = client.post(f"/studio/videos/{vid}/scenes/{sid}/narration/regenerate")
        assert response.status_code == 409
        assert "IDEA/SCRIPTED" in response.text
    finally:
        studio.shutdown()


def test_render_records_measured_duration_for_every_scene(migrated, dsn, tmp_path):
    client, studio = make_client(dsn, tmp_path)
    try:
        vid = ready_video(client)
        assert client.post(f"/studio/videos/{vid}/render").status_code == 202
        rows = migrated.execute(
            "SELECT id, duration_s FROM studio.scenes WHERE video_id = %s", (vid,)).fetchall()
        assert rows and all(row[1] is not None for row in rows)
        assert all(float(row[1]) > 0 for row in rows)
    finally:
        studio.shutdown()


def test_unknown_scene_is_rejected(migrated, dsn, tmp_path):
    client, studio = make_client(dsn, tmp_path)
    try:
        vid = scripted_video(client)
        missing = "0" * 32
        response = client.post(f"/studio/videos/{vid}/scenes/{missing}/narration/regenerate")
        assert response.status_code == 422
    finally:
        studio.shutdown()
