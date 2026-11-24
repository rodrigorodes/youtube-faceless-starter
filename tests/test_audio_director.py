from pathlib import Path
import pytest

from app.studio.application.audio_director import AudioDirector, load_music_catalog
from app.studio.domain.music import MusicCatalog, MusicTrack
from app.studio.domain.render_plan import AudioMix


def test_load_music_catalog():
    manifest_path = Path(__file__).resolve().parents[1] / "storage" / "music-candidates" / "manifest.json"
    catalog = load_music_catalog(manifest_path)
    assert isinstance(catalog, MusicCatalog)
    assert len(catalog.tracks) == 6


def test_audio_director_select_track_by_tone():
    manifest_path = Path(__file__).resolve().parents[1] / "storage" / "music-candidates" / "manifest.json"
    catalog = load_music_catalog(manifest_path)

    # Tone: lofi chill
    track_lofi = AudioDirector.select_track("chill lofi beats for study", catalog)
    assert track_lofi is not None
    assert "lofi" in track_lofi.mood_tags or "chill" in track_lofi.mood_tags

    # Tone: scifi dark tension
    track_scifi = AudioDirector.select_track("dark sci-fi tension mystery", catalog)
    assert track_scifi is not None
    assert any(t in track_scifi.mood_tags for t in ("scifi", "dark", "tension"))

    # Tone: cinematic tension
    track_cinematic = AudioDirector.select_track("dramatic cinematic tension", catalog)
    assert track_cinematic is not None
    assert any(t in track_cinematic.mood_tags for t in ("cinematic", "tension", "dramatic"))

    # Tone: space organ
    track_space = AudioDirector.select_track("mysterious space organ journey", catalog)
    assert track_space is not None
    assert any(t in track_space.mood_tags for t in ("space", "mysterious"))


def test_audio_director_fallback_behavior():
    manifest_path = Path(__file__).resolve().parents[1] / "storage" / "music-candidates" / "manifest.json"
    catalog = load_music_catalog(manifest_path)

    # Completely unmatched tone -> returns first track as fallback
    fallback_track = AudioDirector.select_track("completely unmatched tone xyz123", catalog)
    assert fallback_track is not None
    assert fallback_track.id == catalog.tracks[0].id

    # Empty catalog -> returns None
    empty_catalog = MusicCatalog(tracks=())
    assert AudioDirector.select_track("ambient", empty_catalog) is None


def test_audio_director_build_audio_mix_defaults_and_custom():
    mix_default = AudioDirector.build_audio_mix()
    assert isinstance(mix_default, AudioMix)
    assert mix_default.music_gain == 0.35
    assert mix_default.ducking_ratio == 12.0
    assert mix_default.afade_in_s == 0.5
    assert mix_default.afade_out_s == 1.0

    mix_custom = AudioDirector.build_audio_mix(
        music_gain=0.20,
        ducking_ratio=8.0,
        afade_in_s=0.75,
        afade_out_s=1.5,
    )
    assert isinstance(mix_custom, AudioMix)
    assert mix_custom.music_gain == 0.20
    assert mix_custom.ducking_ratio == 8.0
    assert mix_custom.afade_in_s == 0.75
    assert mix_custom.afade_out_s == 1.5
