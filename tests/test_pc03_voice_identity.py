"""PC-03.01 — Canonical Voice Catalog and Channel Vocal Identity with Frozen Run Config.

Test Matrix:
1. Voice Catalog (`GET /studio/voices`):
   - Lists registered canonical voices with language, capabilities, availability, cost.
   - Piper local is marked available=True, supports_emotion=False, supports_pacing=True.
   - Kokoro (weights absent) and ElevenLabs (cloud BYOK) are marked available=False (fail-closed).
2. Voice Preview (`POST /studio/voices/preview`):
   - Valid local Piper voice generates real WAV audio bytes (200, valid RIFF header).
   - Unavailable voice (Kokoro or ElevenLabs) fails closed with 422 before any execution.
   - Unknown voice ID fails closed with 404 or 422.
3. Channel Vocal Identity & Snapshot Freezing:
   - Channel profile persists voice selection and voice_settings.
   - Video run freezes the channel voice in effective_config / run snapshot.
   - Mid-run channel voice modification does not mutate the frozen run configuration.
"""
from __future__ import annotations

import io
from pathlib import Path

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.studio.adapters.postgres.channel_repo import PostgresChannelProfileRepository
from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.api.routes import make_router
from app.studio.composition.settings import Settings
from app.studio.composition.wiring import Studio
from app.studio.domain.contracts import VideoFormat


def _setup_studio(dsn: str, tmp_path: Path):
    with psycopg.connect(dsn) as conn:
        migrate(conn)

    studio = Studio(
        Settings(
            database_url=dsn,
            storage_root=tmp_path,
            publication_enabled=False,
            budget_guard=True,
            max_cost_video=0.0,
            max_cost_month=0.0,
        )
    )
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    c_repo = PostgresChannelProfileRepository(connect)
    return {
        "client": client,
        "studio": studio,
        "v_repo": v_repo,
        "c_repo": c_repo,
        "dsn": dsn,
    }


def test_get_voices_catalog(dsn: str, tmp_path: Path):
    h = _setup_studio(dsn, tmp_path)
    client: TestClient = h["client"]

    r = client.get("/studio/voices")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "voices" in data
    voices = data["voices"]
    assert len(voices) >= 3

    # Piper local must be available
    piper = next((v for v in voices if "piper" in v["voice_id"]), None)
    assert piper is not None
    assert piper["language"] == "pt-BR"
    assert piper["is_local"] is True
    assert piper["supports_emotion"] is False
    assert piper["supports_pacing"] is True

    # Kokoro and ElevenLabs must be fail-closed when unconfigured (inconditional assertion)
    kokoro = next((v for v in voices if "kokoro" in v["voice_id"]), None)
    assert kokoro is not None, "Kokoro deve estar presente no catálogo canônico"
    assert kokoro["is_local"] is True
    assert kokoro["available"] is False

    eleven = next((v for v in voices if "elevenlabs" in v["voice_id"]), None)
    assert eleven is not None, "ElevenLabs deve estar presente no catálogo canônico"
    assert eleven["is_local"] is False
    assert eleven["available"] is False


def test_voice_preview_positive_and_negative(dsn: str, tmp_path: Path):
    h = _setup_studio(dsn, tmp_path)
    client: TestClient = h["client"]

    # Positive: Piper voice preview
    r_pos = client.post(
        "/studio/voices/preview",
        json={"voice_id": "piper:pt_BR-faber-medium", "text": "Teste de voz do estúdio."},
    )
    assert r_pos.status_code == 200, r_pos.text
    assert r_pos.headers["content-type"].startswith("audio/")
    audio_bytes = r_pos.content
    assert len(audio_bytes) > 44  # WAV header + samples
    assert audio_bytes[:4] == b"RIFF"

    # Negative: Unavailable voice fails closed (422)
    r_unavail = client.post(
        "/studio/voices/preview",
        json={"voice_id": "elevenlabs:adam", "text": "Teste de voz."},
    )
    assert r_unavail.status_code == 422, r_unavail.text

    # Negative: Unknown voice ID fails (404/422)
    r_unknown = client.post(
        "/studio/voices/preview",
        json={"voice_id": "unknown:voice_xyz", "text": "Teste de voz."},
    )
    assert r_unknown.status_code in (404, 422), r_unknown.text


def test_channel_profile_voice_settings_immutability_and_hash():
    from app.studio.domain.channel import ChannelFieldInvalid, ChannelProfile

    p = ChannelProfile(
        id="0" * 32,
        project_id="1" * 32,
        name="Canal Imutável",
        voice="piper:pt_BR-faber-medium",
        voice_settings={"pacing": 1.15, "pitch": 0.0},
    )
    # 1. Objeto deve ser hashable e utilizável em sets/dicts
    s = {p}
    assert p in s

    # 2. Mutação in-place deve falhar com TypeError (MappingProxyType imutável)
    with pytest.raises(TypeError):
        p.voice_settings["pacing"] = 2.0  # type: ignore[index]

    # 3. Tipos não primitivos em voice_settings devem ser recusados com ChannelFieldInvalid
    with pytest.raises(ChannelFieldInvalid, match="primitive scalars"):
        ChannelProfile(
            id="0" * 32,
            project_id="1" * 32,
            name="Canal Inválido",
            voice_settings={"pacing": {"nested": 1}},
        )


def test_channel_voice_identity_and_run_freezing(dsn: str, tmp_path: Path):
    from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository
    from app.studio.domain.effective_config import resolve_effective_config
    from app.studio.domain.run_config import RunConfigStatus

    h = _setup_studio(dsn, tmp_path)
    client: TestClient = h["client"]
    v_repo = h["v_repo"]
    c_repo = h["c_repo"]
    run_repo = PostgresProductionRunRepository(lambda: psycopg.connect(dsn))

    proj = v_repo.create_project("Canal Voz Teste")
    channel = c_repo.create(
        proj.id,
        "Canal Voz",
        voice="piper:pt_BR-faber-medium",
        voice_settings={"pacing": 1.05},
    )
    assert channel.voice == "piper:pt_BR-faber-medium"
    assert channel.voice_settings == {"pacing": 1.05}

    video = v_repo.create_video(proj.id, "Vídeo sobre Roma", VideoFormat.short)

    # 1. Resolver configuração efetiva do vídeo associado ao canal
    config = resolve_effective_config(video=video, channel=channel)
    assert config.voice["model"] == "piper:pt_BR-faber-medium"
    assert config.voice["pacing"] == 1.05
    assert config.provenance["audiovisual.voice.model"] == "channel"

    # 2. Persistir snapshot imutável em ProductionRun
    run_id = "1" * 32
    created_run = run_repo.create_run(run_id, video.id, "run-key-freeze-1", config=config)
    assert created_run.result.value == "CREATED"

    # 3. Mutação posterior no canal via API PATCH
    r_patch = client.patch(
        f"/studio/channels/{channel.id}",
        json={"voice": "piper:pt_BR-jeff-medium", "voice_settings": {"pacing": 1.25}},
    )
    assert r_patch.status_code == 200, r_patch.text
    updated_chan = c_repo.get(channel.id)
    assert updated_chan.voice == "piper:pt_BR-jeff-medium"
    assert updated_chan.voice_settings == {"pacing": 1.25}

    # 4. Prova de isolamento/congelamento: o snapshot do run histórico permanece congelado
    stored_run = run_repo.run_config(run_id)
    assert stored_run is not None
    assert stored_run.status is RunConfigStatus.RESOLVED
    assert stored_run.config.content_hash == config.content_hash
    assert stored_run.config.voice["model"] == "piper:pt_BR-faber-medium"
    assert stored_run.config.voice["pacing"] == 1.05
    assert stored_run.config.voice["model"] != updated_chan.voice


def test_create_channel_via_api_with_voice_settings(dsn: str, tmp_path: Path):
    h = _setup_studio(dsn, tmp_path)
    client: TestClient = h["client"]
    v_repo = h["v_repo"]
    c_repo = h["c_repo"]

    proj = v_repo.create_project("Novo Canal API")
    r_post = client.post(
        f"/studio/projects/{proj.id}/channels",
        json={
            "name": "Canal Criado API",
            "voice": "piper:pt_BR-faber-medium",
            "voice_settings": {"pacing": 1.20, "pitch": -1.5},
        },
    )
    assert r_post.status_code == 201, r_post.text
    chan_id = r_post.json()["id"]
    persisted = c_repo.get(chan_id)
    assert persisted is not None
    assert persisted.voice == "piper:pt_BR-faber-medium"
    assert persisted.voice_settings == {"pacing": 1.20, "pitch": -1.5}
