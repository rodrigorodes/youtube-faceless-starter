import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import StateConflict, VideoNotFound  # noqa: E402
from app.studio.application.publishing import (  # noqa: E402
    Approve, ClaimPublication, GetPreview, GetPublication, GetThumbnail, MarkFailed, MarkThumbnail, MarkUploaded, PublicationConflict,
    PublicationNotFound, Reject, RetryPublication, SetUploadUri,
)
from app.studio.domain.contracts import (  # noqa: E402
    Approval, Asset, AssetKind, Publication, PublicationStatus, Scene, Script, SourceSnapshot, Video, VideoFormat, VideoStatus,
)
from app.studio.domain.qa_report import QaCoverage, QaFinding, QaReport  # noqa: E402
from app.studio.domain.publish import InvalidPublishData  # noqa: E402

S = VideoStatus
V, P, PUB = "a" * 32, "b" * 32, "c" * 32
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
URI = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=AbC123"
YT = "oNQ2KN37sfQ"


def qa_report(passed=True, failures=()):
    """Relatório de QA versionado (F6) para os vídeos dos fakes deste teste."""
    findings = tuple(QaFinding(finding_id=f"f{index}", check_id="render.media_metrics", category="technical",
                               severity="blocking", evidence=failure, suggested_action="Revisar o render.")
                     for index, failure in enumerate(failures))
    return QaReport(render_id="9" * 32, checksum="8" * 64, generated_at=NOW,
                    coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics",), findings=findings)


class Videos:
    def __init__(self, status=S.AWAITING_APPROVAL, qa=None):
        self.video = Video(id=V, project_id=P, topic="ADE 2026", format=VideoFormat.short, status=status, qa_report=qa)
        self.exists = True

    def get_video(self, video_id):
        return self.video if self.exists else None


class Scripts:
    def latest(self, video_id):
        return Script(id="1" * 32, video_id=V, version=1, text="O Amsterdam Dance Event celebrou 30 anos.")

    def scenes(self, video_id):
        return [Scene(id=f"{i:032x}", video_id=V, idx=i, narration="Narração válida.", image_prompt="prompt de imagem válido", asset_id=f"{i:032x}") for i in range(2)]


class Assets:
    def get(self, asset_id):
        return Asset(id=asset_id, kind=AssetKind.image, cache_key=asset_id * 2, path=f"cache/ab/{asset_id}.png", provider="stock", model="p",
                     license="Pexels License", attribution="Foto de Ana no Pexels (https://pexels.com/@ana)")


class Snaps:
    def list(self, video_id):
        return [SourceSnapshot(id="2" * 32, video_id=V, url="https://www.amsterdam-dance-event.nl/en/about", content_sha256="d" * 64, text="t")]


class Approvals:
    def __init__(self, videos):
        self.videos, self.calls, self.refuse = videos, [], False

    def decide(self, video_id, expected, decision, **kw):
        self.calls.append((expected, decision, kw))
        if self.refuse:
            return False
        v = self.videos.video
        self.videos.video = v.model_copy(update={"status": S.APPROVED if decision == "approved" else S.REJECTED, "title": kw["title"],
                                                 "description": kw["description"], "tags": kw["tags"]})
        return True

    def get(self, video_id):
        return None


class Pubs:
    def __init__(self, publish_at=None):
        self.pub = Publication(id=PUB, video_id=V, status=PublicationStatus.UPLOADING, attempt=1, publish_at=publish_at)
        self.items = {PUB: self.pub}
        self.none = False
        self.calls = []

    def claim(self, lease_seconds, max_attempts):
        self.calls.append(("claim", lease_seconds, max_attempts))
        return None if self.none else self.pub

    def get(self, video_id):
        return self.items.get(PUB)

    def get_by_id(self, publication_id):
        return self.items.get(publication_id)

    def set_upload_uri(self, publication_id, attempt, uri, replace):
        self.calls.append(("uri", attempt, uri, replace))
        if attempt != self.pub.attempt:
            return None
        return self.pub.model_copy(update={"upload_uri": uri})

    def mark_uploaded(self, publication_id, youtube_video_id):
        if self.pub.youtube_video_id not in (None, youtube_video_id):
            raise PublicationConflict("other id")
        self.pub = self.pub.model_copy(update={"youtube_video_id": youtube_video_id, "status": PublicationStatus.UPLOADED})
        self.items[PUB] = self.pub
        return self.pub

    def mark_thumbnail(self, publication_id):
        return self.pub.status == PublicationStatus.UPLOADED

    def release(self, publication_id, attempt, error):
        self.calls.append(("release", attempt, error))
        return attempt == self.pub.attempt

    def fail(self, publication_id, attempt, error):
        if attempt != self.pub.attempt:
            return False
        self.calls.append(("fail", error))
        self.pub = self.pub.model_copy(update={"status": PublicationStatus.FAILED, "error": error})
        self.items[PUB] = self.pub
        return True

    def abort_before_delivery(self, publication_id, attempt):
        self.calls.append(("abort_before_delivery", attempt))
        self.items.pop(publication_id, None)
        return True

    def retry(self, video_id):
        return self.pub if self.pub.status == PublicationStatus.FAILED else None


class Jobs:
    def __init__(self, output=True):
        self.output = output

    def latest_output(self, video_id):
        return Asset(id="9" * 32, kind=AssetKind.video, cache_key="d" * 64, path="projects/p/videos/v/final-x.mp4", provider="ffmpeg", model="f", license="g") if self.output else None

    def approved_output(self, video_id):
        return self.latest_output(video_id)


class Files:
    def __init__(self, tmp, exists=True):
        self.tmp, self.exists = tmp, exists

    def resolve(self, relative, kind):
        if not self.exists:
            return None
        f = self.tmp / "final.mp4"
        f.write_bytes(b"x" * 1234)
        return f

    def image_path(self, relative):
        return self.tmp / relative


class Maker:
    def make(self, image):
        return b"JPEG:" + image.name.encode()


def approver(v, **kw):
    a = Approvals(v)
    return Approve(v, Scripts(), a, clock=lambda: NOW), a


# ---------- approve ----------
def test_approve_awaiting_sets_defaults_and_decides_once():
    v = Videos()
    use, a = approver(v)
    video, changed = use.execute(V, output_asset_id="9" * 32)
    assert changed and video.status == S.APPROVED and video.title == "ADE 2026" and video.description.startswith("O Amsterdam Dance Event")
    kw = a.calls[0][2]
    assert a.calls[0][:2] == (S.AWAITING_APPROVAL, "approved") and kw["qa_override"] is False and kw["publish_at"] is None


def test_approving_twice_decides_only_once():
    v = Videos()
    use, a = approver(v)
    use.execute(V, output_asset_id="9" * 32)
    video, changed = use.execute(V)
    assert not changed and video.status == S.APPROVED and len(a.calls) == 1


def test_approve_uses_the_reviewer_metadata_and_schedule():
    v = Videos()
    use, a = approver(v)
    when = NOW + timedelta(days=1)
    use.execute(V, output_asset_id="9" * 32, title="  Meu título ", description="Resumo", tags=["ade", "ADE", "dança"], publish_at=when)
    kw = a.calls[0][2]
    assert kw["title"] == "Meu título" and kw["tags"] == ["ade", "dança"] and kw["publish_at"] == when


@pytest.mark.parametrize("kw", [{"title": "a<b"}, {"title": " "}, {"tags": ["a,b"]}, {"publish_at": NOW + timedelta(minutes=1)}, {"publish_at": datetime(2027, 1, 1)}])
def test_approve_refuses_bad_metadata_without_deciding(kw):
    v = Videos()
    use, a = approver(v)
    with pytest.raises(InvalidPublishData):
        use.execute(V, output_asset_id="9" * 32, **kw)
    assert a.calls == [] and v.video.status == S.AWAITING_APPROVAL


def test_failed_qa_needs_an_override_reason():
    qa = qa_report(False, ["audio is silent"])
    v = Videos(S.RENDERED, qa)
    use, a = approver(v)
    for reason in (None, "", "   "):
        with pytest.raises(StateConflict, match="override_reason"):
            use.execute(V, override_reason=reason)
    assert a.calls == []
    use.execute(V, output_asset_id="9" * 32, override_reason="narração é intencionalmente baixa")
    assert a.calls[0][0] == S.RENDERED and a.calls[0][2]["qa_override"] is True and a.calls[0][2]["reason"].startswith("narração")


@pytest.mark.parametrize("status", [S.IDEA, S.SCRIPTED, S.FACT_CHECKED, S.STORYBOARDED, S.ASSETS_READY, S.FAILED, S.REJECTED])
def test_approve_only_from_the_review_states(status):
    use, a = approver(Videos(status))
    with pytest.raises(StateConflict):
        use.execute(V, override_reason="x")
    assert a.calls == []


def test_approve_lost_race_and_unknown_video():
    v = Videos()
    use, a = approver(v)
    a.refuse = True
    with pytest.raises(StateConflict, match="changed"):
        use.execute(V, output_asset_id="9" * 32)
    v.exists = False
    with pytest.raises(VideoNotFound):
        use.execute(V)


# ---------- reject ----------
def test_reject_is_idempotent_keeps_reason_and_refuses_approved():
    v = Videos()
    a = Approvals(v)
    reject = Reject(v, a)
    video, changed = reject.execute(V, "  imagem ruim ")
    assert changed and video.status == S.REJECTED and a.calls[0][2]["reason"] == "imagem ruim"
    assert reject.execute(V)[1] is False and len(a.calls) == 1
    v2 = Videos(S.APPROVED)
    with pytest.raises(StateConflict):
        Reject(v2, Approvals(v2)).execute(V)
    v3 = Videos(S.RENDERED, qa_report(False, ["x"]))
    assert Reject(v3, Approvals(v3)).execute(V)[0].status == S.REJECTED


# ---------- claim ----------
def claimer(tmp_path, pubs=None, **kw):
    v = Videos(S.APPROVED)
    v.video = v.video.model_copy(update={"title": "Título", "description": "Resumo", "tags": ["ade"]})
    return ClaimPublication(v, Scripts(), Assets(), Jobs(kw.get("output", True)), Snaps(), pubs or Pubs(), Files(tmp_path, kw.get("exists", True)))


def test_claim_builds_the_youtube_body_with_credits_sources_and_declarations(tmp_path):
    item = claimer(tmp_path).execute(900, 4)
    body = item.youtube_body
    assert item.file_size == 1234 and item.content_type == "video/mp4" and item.file_path == f"/studio/videos/{V}/file?output_asset_id={'9' * 32}" and item.thumbnail_path.endswith("/thumbnail")
    assert body["snippet"]["title"] == "Título" and body["snippet"]["tags"] == ["ade"]
    assert "Foto de Ana no Pexels" in body["snippet"]["description"] and "amsterdam-dance-event.nl" in body["snippet"]["description"]
    assert body["status"]["privacyStatus"] == "private" and body["status"]["containsSyntheticMedia"] is True and "publishAt" not in body["status"]


def test_claim_schedules_only_a_future_time(tmp_path):
    future = datetime.now(timezone.utc) + timedelta(days=2)
    assert claimer(tmp_path, Pubs(publish_at=future)).execute().youtube_body["status"]["publishAt"].endswith("Z")
    pubs = Pubs(publish_at=datetime.now(timezone.utc) - timedelta(hours=1))
    with pytest.raises(StateConflict, match="schedule"):
        claimer(tmp_path, pubs).execute()
    assert pubs.calls[-1][0] == "abort_before_delivery" and PUB not in pubs.items


def test_claim_rejects_time_that_would_be_in_past_after_youtube_second_rounding(tmp_path, monkeypatch):
    now = datetime(2027, 1, 1, 12, 0, 0, 700000, tzinfo=timezone.utc)
    monkeypatch.setattr("app.studio.application.publishing._utc_now", lambda: now)
    pubs = Pubs(publish_at=now + timedelta(milliseconds=200))
    with pytest.raises(StateConflict, match="schedule"):
        claimer(tmp_path, pubs).execute()
    assert pubs.calls[-1][0] == "abort_before_delivery"


def test_schedule_expiring_during_preparation_cancels_before_delivery(tmp_path, monkeypatch):
    now = datetime(2027, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    times = iter([now, now + timedelta(seconds=2)])
    monkeypatch.setattr("app.studio.application.publishing._utc_now", lambda: next(times))
    pubs = Pubs(publish_at=now + timedelta(seconds=1))
    with pytest.raises(StateConflict, match="schedule"):
        claimer(tmp_path, pubs).execute()
    assert PUB not in pubs.items


def test_schedule_expiry_refuses_to_cancel_if_claim_might_have_external_effect(tmp_path):
    pubs = Pubs(publish_at=datetime.now(timezone.utc) - timedelta(hours=1))
    pubs.abort_before_delivery = lambda publication_id, attempt: False
    with pytest.raises(StateConflict, match="cannot be safely cancelled"):
        claimer(tmp_path, pubs).execute()
    assert PUB in pubs.items


def test_claim_fails_closed_when_description_cannot_fit(tmp_path):
    pubs = Pubs()
    use = claimer(tmp_path, pubs)
    use.snaps.list = lambda video_id: [SourceSnapshot(id="2" * 32, video_id=V, url="https://example.org/" + "a" * 5100,
                                                      content_sha256="d" * 64, text="t")]
    assert use.execute() is None
    assert pubs.pub.status == PublicationStatus.FAILED


def test_claim_fails_closed_on_unexpected_preparation_error(tmp_path):
    pubs = Pubs()
    use = claimer(tmp_path, pubs)
    def broken(video_id):
        raise RuntimeError("unavailable")
    use.snaps.list = broken
    with pytest.raises(RuntimeError, match="unavailable"):
        use.execute()
    assert pubs.pub.status == PublicationStatus.FAILED


def test_claim_returns_none_when_nothing_is_pending_and_fails_on_a_missing_file(tmp_path):
    pubs = Pubs()
    pubs.none = True
    assert claimer(tmp_path, pubs).execute() is None
    pubs = Pubs()
    assert claimer(tmp_path, pubs, exists=False).execute() is None
    assert pubs.calls[-1][0] == "fail" and "missing" in pubs.calls[-1][1]


# ---------- registrar ----------
def test_set_upload_uri_validates_the_session_url_and_the_attempt():
    pubs = Pubs()
    use = SetUploadUri(pubs)
    assert use.execute(PUB, 1, URI).upload_uri == URI
    with pytest.raises(InvalidPublishData):
        use.execute(PUB, 1, "https://evil.example/upload/youtube/v3/videos?upload_id=a")
    with pytest.raises(StateConflict):
        use.execute(PUB, 2, URI)
    with pytest.raises(PublicationNotFound):
        use.execute("0" * 32, 1, URI)


def test_mark_uploaded_is_idempotent_and_refuses_another_id():
    pubs = Pubs()
    use = MarkUploaded(pubs)
    assert use.execute(PUB, YT).status == PublicationStatus.UPLOADED
    assert use.execute(PUB, YT).youtube_video_id == YT
    with pytest.raises(PublicationConflict):
        use.execute(PUB, "aaaaaaaaaaa")
    for bad in ("", "curto", "tem espaço!!", "x" * 12):
        with pytest.raises(InvalidPublishData):
            use.execute(PUB, bad)
    with pytest.raises(PublicationNotFound):
        use.execute("0" * 32, YT)


def test_failure_modes_release_the_lease_or_fail_for_good():
    pubs = Pubs()
    use = MarkFailed(pubs)
    use.execute(PUB, 1, "HTTP 503 do YouTube", retryable=True)
    assert pubs.calls[-1][0] == "release" and pubs.pub.status == PublicationStatus.UPLOADING
    use.execute(PUB, 1, "  HTTP 403\nquotaExceeded  ", retryable=False)
    assert pubs.calls[-1] == ("fail", "HTTP 403 quotaExceeded") and pubs.pub.status == PublicationStatus.FAILED
    with pytest.raises(StateConflict):
        MarkFailed(Pubs()).execute(PUB, 9, "x", retryable=True)  # tentativa que não é a atual


def test_thumbnail_flag_needs_an_uploaded_video_and_retry_needs_a_failed_one():
    pubs = Pubs()
    with pytest.raises(StateConflict):
        MarkThumbnail(pubs).execute(PUB)
    MarkUploaded(pubs).execute(PUB, YT)
    MarkThumbnail(pubs).execute(PUB)
    v = Videos(S.APPROVED)
    with pytest.raises(StateConflict):
        RetryPublication(v, Pubs()).execute(V)
    failed = Pubs()
    failed.fail(PUB, 1, "x")
    assert RetryPublication(v, failed).execute(V).id == PUB
    assert GetPublication(v, Pubs()).execute(V).id == PUB


# ---------- miniatura e prévia ----------
def test_thumbnail_comes_from_the_first_scene_and_only_for_reviewable_videos(tmp_path):
    v = Videos(S.AWAITING_APPROVAL)
    use = GetThumbnail(v, Scripts(), Assets(), Files(tmp_path), Maker())
    assert use.execute(V) == b"JPEG:" + f"{0:032x}.png".encode()
    v.video = v.video.model_copy(update={"status": S.ASSETS_READY})
    assert use.execute(V) is None


def test_preview_collects_what_the_reviewer_needs(tmp_path):
    v = Videos(S.AWAITING_APPROVAL, qa_report(True))
    preview = GetPreview(v, Scripts(), Assets(), Jobs(), Snaps(), Approvals(v), Pubs(), Files(tmp_path)).execute(V)
    assert preview.has_file and preview.default_title == "ADE 2026" and preview.default_description.startswith("O Amsterdam")
    assert preview.credits == ["Foto de Ana no Pexels (https://pexels.com/@ana)"] and preview.sources == ["https://www.amsterdam-dance-event.nl/en/about"]
    assert len(preview.scenes) == 2 and preview.qa.is_publishable and preview.approval is None


def test_preview_does_not_offer_revision_when_render_file_is_missing(tmp_path):
    v = Videos(S.RENDERED, qa_report(False, ["audio"]))
    preview = GetPreview(v, Scripts(), Assets(), Jobs(), Snaps(), Approvals(v), Pubs(), Files(tmp_path, exists=False)).execute(V)
    assert not preview.has_file and preview.output_asset_id is None


def test_preview_page_renders_sidebar_navigation(tmp_path):
    """A prévia usa a casca compartilhada — não uma cópia própria da navegação nem da paleta."""
    from app.studio.api.preview import render_preview
    v = Videos(S.AWAITING_APPROVAL, qa_report(True))
    preview = GetPreview(v, Scripts(), Assets(), Jobs(), Snaps(), Approvals(v), Pubs(), Files(tmp_path)).execute(V)
    html_doc, _ = render_preview(preview)

    # Estrutura da casca compartilhada (`api.panel.render_sidebar`).
    assert '<aside class="sidebar" aria-label="Barra lateral">' in html_doc
    assert '<div class="app-layout">' in html_doc
    assert '<main class="main-content">' in html_doc
    assert "Faceless Studio V2" in html_doc and "YouTube Automation" in html_doc

    # Navegação renderizada: mesmos itens das outras telas do painel.
    nav = re.search(r'<nav class="nav" aria-label="Principal">(.*?)</nav>', html_doc, re.S)
    assert nav is not None, "prévia sem a navegação principal da casca"
    labels = " ".join(re.sub(r"<[^>]+>", " ", nav.group(1)).split())
    for expected in ("Início", "Produção", "Tendências", "Vídeos", "Analytics", "Canais", "Estilos", "Equipe"):
        assert expected in labels, f"prévia: '{expected}' fora da casca"
    assert 'href="/studio/panel#trending-section"' in nav.group(1)
    assert 'href="/studio/panel#videos-section"' in nav.group(1)
    assert 'href="/docs"' in html_doc
    assert 'href="http://localhost:5678"' in html_doc

    # A prévia é a página do vídeo: "Vídeos" é o único item ativo.
    assert html_doc.count('aria-current="page"') == 1
    videos_item = next(li for li in re.findall(r"<li>(.*?)</li>", nav.group(1), re.S) if "Vídeos" in li)
    assert 'aria-current="page"' in videos_item

    # Conteúdo da página intacto.
    assert "Painel / Prévia do Vídeo" in html_doc
    assert "Voltar ao Painel" in html_doc

    # A casca antiga e a paleta duplicada saíram desta página.
    for stale in ("FACELESS STUDIO", "Pipeline de Vídeos", "Temas em Alta", "+ Novo Vídeo",
                  "--bg: #0f0f0f", "--surface: #181818"):
        assert stale not in html_doc, f"prévia ainda traz o template antigo: {stale!r}"
    assert "--bg-canvas: #101827" in html_doc  # paleta única da casca



# ---------- F8: visibilidade e confirmação pública ----------
def test_public_approval_requires_an_explicit_second_confirmation():
    from app.studio.domain.publication_policy import PublicConfirmationRequired
    v = Videos()
    use, a = approver(v)
    with pytest.raises(PublicConfirmationRequired):
        use.execute(V, output_asset_id="9" * 32, visibility="public")
    assert a.calls == [] and v.video.status == S.AWAITING_APPROVAL
    use.execute(V, output_asset_id="9" * 32, visibility="public", confirm_public=True)
    assert a.calls[0][2]["visibility"] == "public" and a.calls[0][2]["public_confirmed"] is True
    v2 = Videos()
    use2, a2 = approver(v2)
    use2.execute(V, output_asset_id="9" * 32, visibility="unlisted")
    assert a2.calls[0][2]["visibility"] == "unlisted" and a2.calls[0][2]["public_confirmed"] is False
