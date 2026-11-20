import io
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

from PIL import Image  # noqa: E402

from test_render_api import make_client, ready_video, status  # noqa: E402

URI = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=AbC123"
YT = "oNQ2KN37sfQ"


@pytest.fixture()
def migrated(conn):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    return conn


def rendered(client, **kw):
    vid = ready_video(client, **kw)
    assert client.post(f"/studio/videos/{vid}/render").status_code == 202
    return vid


def test_full_flow_approve_twice_publishes_once_and_records_the_id(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = rendered(client)
    assert status(client, vid) == "AWAITING_APPROVAL"
    first = client.post(f"/studio/videos/{vid}/approve", json={"title": "ADE 2026 em 40 segundos", "tags": ["ade", "música"]})
    second = client.post(f"/studio/videos/{vid}/approve")
    assert first.status_code == second.status_code == 200 and first.json()["changed"] is True and second.json()["changed"] is False
    assert second.json()["video"]["title"] == "ADE 2026 em 40 segundos" and status(client, vid) == "APPROVED"
    assert migrated.execute("SELECT count(*) FROM studio.approvals WHERE video_id=%s", (vid,)).fetchone()[0] == 1

    item = client.post("/studio/publications/claim").json()["item"]
    pub = item["publication"]
    assert pub["video_id"] == vid and pub["attempt"] == 1 and item["file_size"] > 1000 and item["file_path"] == f"/studio/videos/{vid}/file"
    body = item["youtube_body"]
    assert body["snippet"]["title"] == "ADE 2026 em 40 segundos" and body["snippet"]["tags"] == ["ade", "música"]
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    assert "Fontes:" in body["snippet"]["description"] and "inteligência artificial" in body["snippet"]["description"]
    assert client.post("/studio/publications/claim").json() == {"item": None}  # lease vigente: nada para outro worker

    pid = pub["id"]
    assert "upload_uri" not in client.post(f"/studio/publications/{pid}/upload-uri", json={"attempt": 1, "upload_uri": URI}).json()
    assert "upload_uri" not in client.get(f"/studio/videos/{vid}/publication").json()
    done = client.post(f"/studio/publications/{pid}/uploaded", json={"youtube_video_id": YT})
    assert done.status_code == 200 and done.json()["status"] == "UPLOADED" and status(client, vid) == "PUBLISHED"
    assert client.post(f"/studio/publications/{pid}/uploaded", json={"youtube_video_id": YT}).status_code == 200  # repetir é seguro
    assert client.post(f"/studio/publications/{pid}/uploaded", json={"youtube_video_id": "aaaaaaaaaaa"}).status_code == 409
    assert client.post(f"/studio/publications/{pid}/thumbnail-set").json()["thumbnail_set"] is True
    assert client.get(f"/studio/videos/{vid}/publication").json()["youtube_video_id"] == YT
    assert client.post("/studio/publications/claim").json() == {"item": None}  # publicado não volta para a fila
    assert YT in client.get(f"/studio/videos/{vid}/preview").text


def test_expired_uploader_is_not_resumed_and_session_is_preserved(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = rendered(client)
    client.post(f"/studio/videos/{vid}/approve")
    pub = client.post("/studio/publications/claim", json={"lease_seconds": 20}).json()["item"]["publication"]
    client.post(f"/studio/publications/{pub['id']}/upload-uri", json={"attempt": 1, "upload_uri": URI})
    migrated.execute("UPDATE studio.publications SET lease_until = now() - interval '1 second'")  # o n8n "morreu": o lease vence
    migrated.commit()
    assert client.post("/studio/publications/claim").json() == {"item": None}
    assert migrated.execute("SELECT upload_uri FROM studio.publications WHERE id=%s", (pub["id"],)).fetchone()[0] == URI
    assert migrated.execute("SELECT count(*) FROM studio.publications").fetchone()[0] == 1


def test_failure_reports(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = rendered(client)
    client.post(f"/studio/videos/{vid}/approve")
    pid = client.post("/studio/publications/claim").json()["item"]["publication"]["id"]
    assert client.post(f"/studio/publications/{pid}/failed", json={"attempt": 1, "error": "HTTP 503", "retryable": True}).json()["status"] == "UPLOADING"
    assert client.post("/studio/publications/claim").json() == {"item": None}
    assert client.post(f"/studio/publications/{pid}/failed", json={"attempt": 2, "error": "wrong attempt", "retryable": False}).status_code == 409
    failed = client.post(f"/studio/publications/{pid}/failed", json={"attempt": 1, "error": "HTTP 403 quotaExceeded", "retryable": False})
    assert failed.json()["status"] == "FAILED" and failed.json()["error"] == "HTTP 403 quotaExceeded"
    assert client.post("/studio/publications/claim").json() == {"item": None}
    assert client.post(f"/studio/videos/{vid}/publication/retry").status_code == 409
    assert client.post("/studio/publications/claim").json() == {"item": None}


def test_inputs_are_validated(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = rendered(client)
    soon = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    for body in ({"title": "a<b"}, {"title": " "}, {"tags": ["a,b"]}, {"publish_at": soon}, {"publish_at": "2030-01-01T10:00:00"}):
        assert client.post(f"/studio/videos/{vid}/approve", json=body).status_code == 422, body
    assert status(client, vid) == "AWAITING_APPROVAL"
    client.post(f"/studio/videos/{vid}/approve", json={"publish_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
    pid = client.post("/studio/publications/claim").json()["item"]["publication"]["id"]
    assert client.post(f"/studio/publications/{pid}/upload-uri", json={"attempt": 1, "upload_uri": "https://evil.example/upload/youtube/v3/videos?upload_id=a"}).status_code == 422
    assert client.post(f"/studio/publications/{pid}/uploaded", json={"youtube_video_id": "curto"}).status_code == 422
    assert client.post(f"/studio/publications/{'0' * 32}/uploaded", json={"youtube_video_id": YT}).status_code == 404
    assert client.post(f"/studio/publications/{'A' * 32}/uploaded", json={"youtube_video_id": YT}).status_code == 422
    assert client.post(f"/studio/publications/{pid}/thumbnail-set").status_code == 409  # ainda não enviado
    assert client.post("/studio/publications/claim", json={"lease_seconds": 1}).status_code == 422
    for path in ("approve", "reject"):
        assert client.post(f"/studio/videos/{'0' * 32}/{path}").status_code == 404
        assert client.post(f"/studio/videos/{'A' * 32}/{path}").status_code == 422


def test_scheduled_publication_carries_publish_at_into_the_youtube_body(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = rendered(client)
    when = datetime.now(timezone.utc) + timedelta(days=1)
    client.post(f"/studio/videos/{vid}/approve", json={"publish_at": when.isoformat()})
    status_ = client.post("/studio/publications/claim").json()["item"]["youtube_body"]["status"]
    assert status_["privacyStatus"] == "private" and status_["publishAt"].endswith("Z") and status_["publishAt"][:13] == when.strftime("%Y-%m-%dT%H")


def test_reject_is_final_and_blocks_publication(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = rendered(client)
    assert client.post(f"/studio/videos/{vid}/reject", json={"reason": "imagem ruim"}).json()["changed"] is True
    assert client.post(f"/studio/videos/{vid}/reject").json()["changed"] is False
    assert client.post(f"/studio/videos/{vid}/approve").status_code == 409 and status(client, vid) == "REJECTED"
    assert client.post("/studio/publications/claim").json() == {"item": None}


def test_qa_failed_video_is_approved_only_with_a_recorded_override(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path, renderer="nosound:x")
    vid = rendered(client)
    assert status(client, vid) == "RENDERED"
    assert client.post(f"/studio/videos/{vid}/approve").status_code == 409
    assert client.post(f"/studio/videos/{vid}/approve", json={"override_reason": "   "}).status_code == 409
    assert status(client, vid) == "RENDERED"
    assert client.post(f"/studio/videos/{vid}/approve", json={"override_reason": "teste de um vídeo sem áudio"}).status_code == 200
    row = migrated.execute("SELECT qa_override, reason FROM studio.approvals WHERE video_id=%s", (vid,)).fetchone()
    assert row == (True, "teste de um vídeo sem áudio") and status(client, vid) == "APPROVED"


def test_generic_transition_cannot_approve_or_publish(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = rendered(client)
    for new in ("APPROVED", "REJECTED", "PUBLISHED"):
        assert client.post(f"/studio/videos/{vid}/transition", json={"expected": "AWAITING_APPROVAL", "new": new}).status_code == 403


def test_preview_page_is_escaped_locked_down_and_complete(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = rendered(client)
    migrated.execute("UPDATE studio.videos SET topic = %s WHERE id = %s", ("<script>alert(1)</script> & \"x\"", vid))
    migrated.commit()
    r = client.get(f"/studio/videos/{vid}/preview")
    page, csp = r.text, r.headers["content-security-policy"]
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html") and "<script>alert(1)" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    nonce = csp.split("script-src 'nonce-")[1].split("'")[0]
    assert f'<script nonce="{nonce}">' in page and "default-src 'none'" in csp and "frame-ancestors 'none'" in csp and r.headers["cache-control"] == "no-store"
    assert f'src="/studio/videos/{vid}/file"' in page and 'kind="captions"' in page and "AWAITING_APPROVAL" in page
    assert 'id="approve"' in page and 'for="title"' in page and 'role="status"' in page and "QA aprovado" in page
    assert client.post(f"/studio/videos/{vid}/approve").status_code == 422  # o título padrão (o tema) tem "<": o revisor precisa corrigir
    assert client.post(f"/studio/videos/{vid}/approve", json={"title": "Título limpo"}).status_code == 200
    approved = client.get(f"/studio/videos/{vid}/preview").text
    assert 'id="approve"' not in approved and "aprovado" in approved  # sem formulário depois da decisão
    assert client.get(f"/studio/videos/{'0' * 32}/preview").status_code == 404 and client.get(f"/studio/videos/{'A' * 32}/preview").status_code == 422


def test_thumbnail_and_vtt_endpoints(migrated, dsn, tmp_path):
    client, _ = make_client(dsn, tmp_path)
    vid = rendered(client)
    t = client.get(f"/studio/videos/{vid}/thumbnail")
    img = Image.open(io.BytesIO(t.content))
    assert t.status_code == 200 and t.headers["content-type"] == "image/jpeg" and img.size == (1280, 720) and img.format == "JPEG" and len(t.content) < 2 * 1024 * 1024
    vtt = client.get(f"/studio/videos/{vid}/subtitles.vtt")
    assert vtt.status_code == 200 and vtt.text.startswith("WEBVTT") and "-->" in vtt.text and vtt.headers["content-type"].startswith("text/vtt")
    pid = client.post("/studio/projects", json={"name": "vazio"}).json()["id"]
    empty = client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": "short"}).json()["id"]
    assert client.get(f"/studio/videos/{empty}/thumbnail").status_code == 404 and client.get(f"/studio/videos/{empty}/subtitles.vtt").status_code == 404
