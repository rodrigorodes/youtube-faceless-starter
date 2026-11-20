import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.publish import (  # noqa: E402
    InvalidPublishData, build_description, default_title, srt_to_vtt, valid_upload_uri, valid_youtube_id, validate_metadata,
    validate_publish_at, youtube_insert_body,
)

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def test_default_title_is_trimmed_and_capped():
    assert default_title("  ADE 2026  ") == "ADE 2026"
    assert len(default_title("x" * 300)) <= 100 and default_title("x" * 300).endswith("…")


@pytest.mark.parametrize("title", ["", "   ", "a<b", "x>y", "z" * 101])
def test_bad_titles_are_refused(title):
    with pytest.raises(InvalidPublishData):
        validate_metadata(title, "ok", [])


def test_description_and_tags_rules():
    assert validate_metadata(" T ", " d ", [" a ", "b"]) == ("T", "d", ["a", "b"])
    with pytest.raises(InvalidPublishData):
        validate_metadata("T", "<script>", [])
    with pytest.raises(InvalidPublishData):
        validate_metadata("T", "d" * 4001, [])
    with pytest.raises(InvalidPublishData):
        validate_metadata("T", "d", ["a<b"])
    with pytest.raises(InvalidPublishData):
        validate_metadata("T", "d", ["t" * 31])
    with pytest.raises(InvalidPublishData):
        validate_metadata("T", "d", [f"tag{i}" for i in range(16)])
    with pytest.raises(InvalidPublishData):
        validate_metadata("T", "d", ["a,b"])
    assert validate_metadata("T", "d", ["a", "A", " "]) [2] == ["a"]  # dedup sem diferenciar caixa, descarta vazios


def test_publish_at_must_be_aware_future_and_not_absurd():
    ok = NOW + timedelta(hours=2)
    assert validate_publish_at(ok, NOW) == ok
    assert validate_publish_at(ok.astimezone(timezone(timedelta(hours=-3))), NOW) == ok  # normaliza para UTC
    for bad in (datetime(2026, 11, 19, 14, 0), NOW + timedelta(minutes=5), NOW - timedelta(days=1), NOW + timedelta(days=400)):
        with pytest.raises(InvalidPublishData):
            validate_publish_at(bad, NOW)
    assert validate_publish_at(None, NOW) is None


def test_description_adds_credits_sources_and_ai_note_within_the_limit():
    d = build_description("Resumo do evento.", credits=["Foto de A no Pexels", "Foto de A no Pexels", "Foto de B no Pexels"],
                          sources=["https://www.amsterdam-dance-event.nl/en/about"], synthetic=True)
    assert d.startswith("Resumo do evento.") and d.count("Foto de A no Pexels") == 1 and "Foto de B no Pexels" in d
    assert "https://www.amsterdam-dance-event.nl/en/about" in d and "inteligência artificial" in d.lower()
    big = build_description("x" * 6000, credits=["c"] * 3, sources=["https://a.example"], synthetic=True)
    assert len(big) <= 5000 and "https://a.example" in big  # corta o texto-base, não os créditos
    assert "<" not in build_description("a", credits=["x<y>z"], sources=[], synthetic=False)  # YouTube recusa < e >


def test_vtt_conversion():
    srt = "1\n00:00:00,300 --> 00:00:02,500\nOlá, mundo.\n\n2\n00:00:02,500 --> 00:00:04,000\nSegunda.\n"
    assert srt_to_vtt(srt) == "WEBVTT\n\n00:00:00.300 --> 00:00:02.500\nOlá, mundo.\n\n00:00:02.500 --> 00:00:04.000\nSegunda.\n"
    assert srt_to_vtt("") == "WEBVTT\n"


def test_youtube_id_and_upload_uri_validation():
    assert valid_youtube_id("oNQ2KN37sfQ") and not valid_youtube_id("short") and not valid_youtube_id("a" * 11 + "!") and not valid_youtube_id(None)
    good = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=AbC_123-x&part=snippet,status"
    assert valid_upload_uri(good)
    for bad in ("http://www.googleapis.com/upload/youtube/v3/videos?upload_id=a", "https://evil.example/upload/youtube/v3/videos?upload_id=a",
                "https://www.googleapis.com.evil.example/upload/youtube/v3/videos?upload_id=a", "https://user@www.googleapis.com/upload/youtube/v3/videos?upload_id=a",
                "https://www.googleapis.com/upload/youtube/v3/thumbnails/set?upload_id=a", "https://www.googleapis.com/upload/youtube/v3/videos",
                "https://www.googleapis.com:8443/upload/youtube/v3/videos?upload_id=a", "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=a b",
                "", None, "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=a\n"):
        assert not valid_upload_uri(bad), bad


def test_insert_body_is_private_declares_synthetic_and_kids_and_schedules():
    body = youtube_insert_body("T", "D", ["a"], publish_at=None)
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    assert body["snippet"]["title"] == "T" and body["snippet"]["tags"] == ["a"] and body["snippet"]["defaultLanguage"] == "pt-BR"
    when = NOW + timedelta(hours=3)
    body = youtube_insert_body("T", "D", [], publish_at=when)
    assert body["status"]["publishAt"] == "2026-11-19T15:00:00.000Z" and body["status"]["privacyStatus"] == "private" and "tags" not in body["snippet"]
