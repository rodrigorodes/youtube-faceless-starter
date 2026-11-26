"""Testes de conformidade para V4-03 — Professional Audio.

Cobre as 18 atividades planejadas em V4-03:
- V4-03.01 a V4-03.07: Catálogo de áudio, tags mood/BPM, verificação de proveniência e licença.
- V4-03.08 a V4-03.10: Timeline multitrack com múltiplas músicas, ambiência e SFX temporizados.
- V4-03.11 a V4-03.14: DSP analítico: ducking inteligente, fades, crossfades, True Peak e ausência de clipping.
- V4-03.15 a V4-03.18: Teste multitrack integrado (aceite formal do backlog V4-03).
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from renderer.app.studio.domain.audio_catalog import (
    AudioCatalog,
    AudioCategory,
    AudioTrack,
)
from renderer.app.studio.domain.audio_dsp import (
    CLIPPING_LIMIT,
    db_to_linear,
    generate_synthetic_sfx,
    generate_synthetic_tone,
    mix_multitrack_pcm,
    save_pcm_as_wav,
)
from renderer.app.studio.domain.audio_multitrack import (
    AudioEvent,
    MultitrackAudioPlan,
    build_multitrack_plan,
    verify_audio_licenses,
)
from renderer.app.studio.domain.voice_audio import inspect_speech_audio


class TestAudioCatalogAndLicensing:
    """V4-03.01 a V4-03.07: Catálogo, metadados, busca contextual e proveniência."""

    def test_audio_track_validation(self):
        # Licença vazia é estritamente proibida
        with pytest.raises(ValueError, match="declare a valid license"):
            AudioTrack(id="t1", category=AudioCategory.MUSIC, title="Sem licença", license="")

        # Duração negativa é proibida
        with pytest.raises(ValueError, match="duration_s cannot be negative"):
            AudioTrack(id="t2", category=AudioCategory.SFX, title="Negativo", license="cc0", duration_s=-1.0)

    def test_catalog_query_and_filtering(self):
        t_ambient = AudioTrack(
            id="ambient_01",
            category=AudioCategory.AMBIENCE,
            title="Deep Space Tone",
            license="cc0",
            duration_s=60.0,
            mood_tags=("ambient", "dark", "space"),
        )
        t_music = AudioTrack(
            id="synthwave_01",
            category=AudioCategory.MUSIC,
            title="Neon Highway",
            license="cc-by",
            duration_s=120.0,
            bpm=128,
            mood_tags=("energetic", "retro", "electronic"),
        )
        t_sfx = AudioTrack(
            id="sfx_whoosh",
            category=AudioCategory.SFX,
            title="Fast Camera Whoosh",
            license="cc0",
            duration_s=0.5,
            mood_tags=("transition", "whoosh"),
        )

        catalog = AudioCatalog(tracks=(t_ambient, t_music, t_sfx))

        # Filtragem por categoria
        music_tracks = catalog.find_tracks(category=AudioCategory.MUSIC)
        assert len(music_tracks) == 1
        assert music_tracks[0].id == "synthwave_01"

        # Filtragem por mood
        ambient_tracks = catalog.find_tracks(mood="space")
        assert len(ambient_tracks) == 1
        assert ambient_tracks[0].id == "ambient_01"

        # Filtragem por BPM range
        bpm_matches = catalog.find_tracks(bpm_range=(120, 130))
        assert len(bpm_matches) == 1
        assert bpm_matches[0].bpm == 128

        # Busca inexistente
        assert catalog.find_tracks(mood="classical") == []

    def test_license_verification(self):
        licensed_track = AudioTrack(id="m_valid", category=AudioCategory.MUSIC, title="M", license="cc0")
        catalog = AudioCatalog(tracks=(licensed_track,))

        plan_valid = MultitrackAudioPlan(
            total_duration_s=10.0,
            music_events=(
                AudioEvent(id="e1", track_id="m_valid", category=AudioCategory.MUSIC, start_s=0.0, duration_s=10.0),
            ),
        )
        assert verify_audio_licenses(plan_valid, catalog) == []

        # Faixa ausente no catálogo
        plan_missing = MultitrackAudioPlan(
            total_duration_s=10.0,
            music_events=(
                AudioEvent(id="e2", track_id="m_unknown", category=AudioCategory.MUSIC, start_s=0.0, duration_s=10.0),
            ),
        )
        violations = verify_audio_licenses(plan_missing, catalog)
        assert len(violations) == 1
        assert "not found in registered audio catalog" in violations[0]


class TestDspAndMultitrackMixing:
    """V4-03.11 a V4-03.14: Geração de tons, ducking, fades e True Peak."""

    def test_db_to_linear(self):
        assert math.isclose(db_to_linear(0.0), 1.0)
        assert math.isclose(db_to_linear(-6.0), 0.501187, rel_tol=1e-3)
        assert math.isclose(db_to_linear(-20.0), 0.10, rel_tol=1e-3)

    def test_generate_synthetic_sfx(self):
        whoosh = generate_synthetic_sfx("whoosh", duration_s=0.5, sample_rate=24000)
        assert len(whoosh) == 12000
        assert max(abs(s) for s in whoosh) > 2000

        ding = generate_synthetic_sfx("ding", duration_s=0.4, sample_rate=24000)
        assert len(ding) == 9600
        assert max(abs(s) for s in ding) > 5000

        pop = generate_synthetic_sfx("pop", duration_s=0.2, sample_rate=24000)
        assert len(pop) == 4800

    def test_ducking_attenuation_during_speech(self):
        """Comprova que a música sofre atenuação (ducking) especificamente durante a locução."""
        # 10 segundos totais
        # Fala nos segundos 2.0 a 6.0
        voice_event = AudioEvent(id="v1", track_id="voice_speech", category=AudioCategory.VOICE, start_s=2.0, duration_s=4.0)
        music_event = AudioEvent(id="m1", track_id="bg_music", category=AudioCategory.MUSIC, start_s=0.0, duration_s=10.0, ducked=True)

        plan = MultitrackAudioPlan(
            total_duration_s=10.0,
            voice_events=(voice_event,),
            music_events=(music_event,),
            ducking_attenuation_db=-12.0,  # ~0.25 de ganho durante a fala
        )

        sample_rate = 1000  # taxa simplificada para cálculo
        music_samples = [10000] * (10 * sample_rate)
        voice_samples = [0] * (4 * sample_rate)  # só marca presença

        mixed, _ = mix_multitrack_pcm(
            plan=plan,
            track_samples_map={"bg_music": music_samples, "voice_speech": voice_samples},
            sample_rate=sample_rate,
        )

        # No segundo 1.0 (sem fala): ganho integral da música (10000)
        sample_at_1s = mixed[1 * sample_rate]
        # No segundo 4.0 (com fala): ganho atenuado pelo ducking (~2500)
        sample_at_4s = mixed[4 * sample_rate]

        assert sample_at_1s > 9000
        assert 2000 < sample_at_4s < 3000
        assert sample_at_4s < (sample_at_1s * 0.35)


class TestMultitrackAcceptanceCriteria:
    """V4-03.18 — Aceite da V4-03:

    Fixture completa com:
    - 1 voz de narração
    - 2 músicas com crossfade entre elas
    - 1 ambiência contínua
    - 2 efeitos SFX temporizados
    - Sem clipping digital (peak < 32760)
    - Licenças comprovadas
    - Duração total preservada
    """

    def test_full_multitrack_audiovisual_mix(self, tmp_path: Path):
        sample_rate = 24000
        total_duration = 12.0  # 12 segundos de timeline

        # Catálogo com licenças válidas
        cat = AudioCatalog(tracks=(
            AudioTrack(id="m_theme_a", category=AudioCategory.MUSIC, title="Theme Intro", license="cc0", duration_s=7.0),
            AudioTrack(id="m_theme_b", category=AudioCategory.MUSIC, title="Theme Climax", license="cc-by", duration_s=7.0),
            AudioTrack(id="amb_room", category=AudioCategory.AMBIENCE, title="Studio Air", license="cc0", duration_s=12.0),
            AudioTrack(id="sfx_whoosh", category=AudioCategory.SFX, title="Whoosh", license="cc0", duration_s=0.5),
            AudioTrack(id="sfx_ding", category=AudioCategory.SFX, title="Ding", license="cc0", duration_s=0.4),
        ))

        # Eventos
        # Voz falando de 2s a 5s e de 7s a 10s
        voice_events = [
            AudioEvent(id="v1", track_id="voice", category=AudioCategory.VOICE, start_s=2.0, duration_s=3.0),
            AudioEvent(id="v2", track_id="voice", category=AudioCategory.VOICE, start_s=7.0, duration_s=3.0),
        ]
        # 2 Músicas com overlap de 1s para crossfade (0s-7s e 6s-12s)
        music_tracks = [
            ("m_theme_a", 0.0, 7.0),
            ("m_theme_b", 6.0, 6.0),
        ]
        # SFX nos momentos 1.9s (início da 1ª fala) e 5.9s (transição musical)
        sfx_cues = [
            ("sfx_whoosh", 1.9),
            ("sfx_ding", 5.9),
        ]

        plan = build_multitrack_plan(
            total_duration_s=total_duration,
            voice_events=voice_events,
            music_tracks=music_tracks,
            ambience_track_id="amb_room",
            sfx_cues=sfx_cues,
            catalog=cat,
        )

        # 1. Comprovação de licença
        license_violations = verify_audio_licenses(plan, cat)
        assert license_violations == [], f"Licenças inválidas encontradas: {license_violations}"

        # 2. Geração de amostras para mixagem
        samples_voice = generate_synthetic_tone(duration_s=3.0, freq_hz=220.0, sample_rate=sample_rate, gain_db=0.0)
        samples_music_a = generate_synthetic_tone(duration_s=7.0, freq_hz=330.0, sample_rate=sample_rate, gain_db=-6.0)
        samples_music_b = generate_synthetic_tone(duration_s=6.0, freq_hz=440.0, sample_rate=sample_rate, gain_db=-6.0)
        samples_ambience = generate_synthetic_tone(duration_s=12.0, freq_hz=110.0, sample_rate=sample_rate, gain_db=-18.0)
        samples_whoosh = generate_synthetic_sfx("whoosh", duration_s=0.5, sample_rate=sample_rate)
        samples_ding = generate_synthetic_sfx("ding", duration_s=0.4, sample_rate=sample_rate)

        track_samples = {
            "voice": samples_voice,
            "m_theme_a": samples_music_a,
            "m_theme_b": samples_music_b,
            "amb_room": samples_ambience,
            "sfx_whoosh": samples_whoosh,
            "sfx_ding": samples_ding,
        }

        # 3. Execução da mixagem multitrack
        mixed_pcm, metrics = mix_multitrack_pcm(plan, track_samples, sample_rate=sample_rate)

        # 4. Asserções do critério de aceite
        assert metrics["duration_s"] == total_duration
        assert metrics["is_clipped"] is False
        assert metrics["peak_amplitude"] < CLIPPING_LIMIT
        assert metrics["true_peak_dbtp"] <= 0.0

        # Gravação e inspeção física do arquivo WAV
        wav_path = tmp_path / "final_multitrack_mix.wav"
        save_pcm_as_wav(mixed_pcm, wav_path, sample_rate=sample_rate)
        assert wav_path.is_file()

        audio_metrics = inspect_speech_audio(wav_path)
        assert audio_metrics.duration_s == total_duration
        assert audio_metrics.is_clipped is False
        assert audio_metrics.is_silent is False
        assert audio_metrics.is_acceptable is True
