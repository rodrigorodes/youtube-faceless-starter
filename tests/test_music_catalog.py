from pathlib import Path
import pytest
from pydantic import ValidationError

from app.studio.domain.music import MusicCatalog, MusicTrack, infer_mood_tags


def test_music_track_model_defaults_and_immutability():
    track = MusicTrack(
        id="track-1",
        title="Ambient Calm",
        creator="Artist A",
        file_path="/storage/track-1.mp3",
        duration_s=120.5,
        sha256="abc123hash",
        mood_tags=("ambient", "calm"),
    )
    assert track.id == "track-1"
    assert track.title == "Ambient Calm"
    assert track.creator == "Artist A"
    assert track.license == "cc0"
    assert track.file_path == "/storage/track-1.mp3"
    assert track.duration_s == 120.5
    assert track.sha256 == "abc123hash"
    assert track.mood_tags == ("ambient", "calm")

    # Default license is cc0 and mood_tags defaults to ()
    track_default = MusicTrack(
        id="track-2",
        title="Default Track",
        creator="Artist B",
        file_path="/storage/track-2.mp3",
        duration_s=60.0,
        sha256="hash2",
    )
    assert track_default.license == "cc0"
    assert track_default.mood_tags == ()


def test_infer_mood_tags_mappings():
    # ambient -> ("ambient", "calm")
    tags = infer_mood_tags("Ambient Tune")
    assert "ambient" in tags
    assert "calm" in tags

    # lofi -> ("lofi", "chill", "relaxed")
    tags = infer_mood_tags("Lofi Chill Beats")
    assert "lofi" in tags
    assert "chill" in tags
    assert "relaxed" in tags

    # sci-fi / scifi -> ("scifi", "dark", "tension")
    tags_scifi = infer_mood_tags("Sci-Fi Mystery")
    assert "scifi" in tags_scifi
    assert "dark" in tags_scifi
    assert "tension" in tags_scifi

    tags_scifi2 = infer_mood_tags("Epic scifi space")
    assert "scifi" in tags_scifi2

    # cinematic / tension -> ("cinematic", "tension", "dramatic")
    tags_cinema = infer_mood_tags("Cinematic Tension Drone")
    assert "cinematic" in tags_cinema
    assert "tension" in tags_cinema
    assert "dramatic" in tags_cinema

    # space / organ -> ("ambient", "space", "mysterious")
    tags_space = infer_mood_tags("Space Organ Music")
    assert "space" in tags_space
    assert "mysterious" in tags_space
    assert "ambient" in tags_space

    # electronic -> ("electronic", "ambient")
    tags_elec = infer_mood_tags("Electronic Soundscape")
    assert "electronic" in tags_elec
    assert "ambient" in tags_elec


def test_music_catalog_from_items_and_filtering():
    items = [
        {
            "openverse_id": "ov-1",
            "file": "track1.mp3",
            "title": "Ambient Meditation",
            "creator": "Zen Master",
            "license": "cc0",
            "duration_ms": 120000,
            "sha256": "sha-1",
            "note": "ambient CC0 track",
        },
        {
            "id": "t-2",
            "file": "track2.mp3",
            "title": "Sci-Fi Thriller",
            "creator": "Future Sound",
            "license": "cc0",
            "duration_s": 85.0,
            "sha256": "sha-2",
            "mood_tags": ["scifi", "action"],
        },
    ]

    base = Path("/opt/music")
    catalog = MusicCatalog.from_items(items, base_dir=base)

    assert len(catalog.tracks) == 2
    t1 = catalog.tracks[0]
    assert t1.id == "ov-1"
    assert t1.file_path == str(base / "track1.mp3")
    assert t1.duration_s == 120.0
    assert "ambient" in t1.mood_tags
    assert "calm" in t1.mood_tags

    t2 = catalog.tracks[1]
    assert t2.id == "t-2"
    assert t2.file_path == str(base / "track2.mp3")
    assert t2.duration_s == 85.0
    assert t2.mood_tags == ("scifi", "action")

    # Filtering
    ambient_tracks = catalog.find_tracks("ambient")
    assert len(ambient_tracks) == 1
    assert ambient_tracks[0].id == "ov-1"

    scifi_tracks = catalog.find_tracks("scifi")
    assert len(scifi_tracks) == 1
    assert scifi_tracks[0].id == "t-2"

    all_tracks = catalog.find_tracks(None)
    assert len(all_tracks) == 2

    none_found = catalog.find_tracks("acoustic-jazz-nonexistent")
    assert none_found == []


def test_music_catalog_from_manifest_file():
    manifest_path = Path(__file__).resolve().parents[1] / "storage" / "music-candidates" / "manifest.json"
    assert manifest_path.exists(), f"manifest.json not found at {manifest_path}"

    catalog = MusicCatalog.load_from_manifest(manifest_path)
    assert len(catalog.tracks) == 6

    for track in catalog.tracks:
        assert track.license == "cc0"
        assert len(track.sha256) == 64
        assert track.duration_s > 0
        assert len(track.mood_tags) > 0
        assert Path(track.file_path).exists(), f"Track audio file does not exist: {track.file_path}"
