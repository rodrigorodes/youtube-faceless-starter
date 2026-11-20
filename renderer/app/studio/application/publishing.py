"""Aprovação humana, fila de publicação (reivindicar/registrar), miniatura e dados da prévia."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..domain.contracts import Approval, Publication, QaReport, Scene, Video, VideoStatus
from ..domain.publish import (InvalidPublishData, build_description, default_description, default_title, valid_upload_uri, valid_youtube_id,
                              validate_metadata, validate_publish_at, youtube_insert_body)
from .editorial import StateConflict, VideoNotFound, _require_video
from .ports import (ApprovalRepository, AssetRepository, PublicationRepository, RenderJobRepository, RenderStorage, ScriptRepository,
                    SnapshotRepository, ThumbnailMaker, VideoRepository)

Clock = Callable[[], datetime]
SERVABLE = (VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL, VideoStatus.APPROVED, VideoStatus.PUBLISHED)
MAX_ATTEMPTS = 5


class PublicationNotFound(LookupError):
    pass


class PublicationConflict(RuntimeError):
    """O vídeo já tem outro ID do YouTube registrado."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Approve:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, approvals: ApprovalRepository, clock: Clock = _utc_now):
        self.videos, self.scripts, self.approvals, self.clock = videos, scripts, approvals, clock

    def execute(self, video_id: str, *, title: str | None = None, description: str | None = None, tags: list[str] | None = None,
                publish_at: datetime | None = None, override_reason: str | None = None) -> tuple[Video, bool]:
        """Idempotente: vídeo já aprovado/publicado devolve (vídeo, False) sem nova decisão."""
        video = _require_video(self.videos, video_id)
        if video.status in (VideoStatus.APPROVED, VideoStatus.PUBLISHED):
            return video, False
        reason = (override_reason or "").strip()
        if video.status == VideoStatus.AWAITING_APPROVAL:
            override = False
        elif video.status == VideoStatus.RENDERED:
            failures = "; ".join(video.qa_report.failures) if video.qa_report else "no QA report"
            if not reason:
                raise StateConflict(f"the QA failed ({failures}): approving needs override_reason")
            override = True
        else:
            raise StateConflict(f"approve needs AWAITING_APPROVAL (or RENDERED with override_reason), got {video.status.value}")
        script = self.scripts.latest(video_id)
        final_title, final_desc, final_tags = validate_metadata(
            title if title is not None else (video.title or default_title(video.topic)),
            description if description is not None else (video.description or default_description(script.text if script else "")),
            tags if tags is not None else video.tags)
        when = validate_publish_at(publish_at, self.clock())
        if not self.approvals.decide(video_id, video.status, "approved", title=final_title, description=final_desc, tags=final_tags,
                                     publish_at=when, reason=reason, qa_override=override):
            raise StateConflict("the video state changed, reload and try again")
        return _require_video(self.videos, video_id), True


class Reject:
    def __init__(self, videos: VideoRepository, approvals: ApprovalRepository):
        self.videos, self.approvals = videos, approvals

    def execute(self, video_id: str, reason: str = "") -> tuple[Video, bool]:
        video = _require_video(self.videos, video_id)
        if video.status == VideoStatus.REJECTED:
            return video, False
        if video.status not in (VideoStatus.AWAITING_APPROVAL, VideoStatus.RENDERED):
            raise StateConflict(f"reject needs AWAITING_APPROVAL (or RENDERED), got {video.status.value}")
        if not self.approvals.decide(video_id, video.status, "rejected", title=video.title, description=video.description, tags=video.tags,
                                     publish_at=None, reason=reason.strip()[:500], qa_override=False):
            raise StateConflict("the video state changed, reload and try again")
        return _require_video(self.videos, video_id), True


def credits_and_sources(scripts: ScriptRepository, assets: AssetRepository, snaps: SnapshotRepository, video_id: str) -> tuple[list[str], list[str]]:
    credits = []
    for scene in scripts.scenes(video_id):
        asset = assets.get(scene.asset_id) if scene.asset_id else None
        if asset and asset.attribution:
            credits.append(asset.attribution)
    return list(dict.fromkeys(credits)), list(dict.fromkeys(s.url for s in snaps.list(video_id)))


@dataclass(frozen=True)
class ClaimItem:
    publication: Publication
    youtube_body: dict
    file_size: int
    content_type: str
    file_path: str
    thumbnail_path: str


class ClaimPublication:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, jobs: RenderJobRepository,
                 snaps: SnapshotRepository, pubs: PublicationRepository, files: RenderStorage):
        self.videos, self.scripts, self.assets, self.jobs, self.snaps, self.pubs, self.files = videos, scripts, assets, jobs, snaps, pubs, files

    def execute(self, lease_seconds: int = 1800, max_attempts: int = MAX_ATTEMPTS) -> ClaimItem | None:
        pub = self.pubs.claim(lease_seconds, max_attempts)
        if pub is None:
            return None
        video = _require_video(self.videos, pub.video_id)
        output = self.jobs.latest_output(video.id)
        path = self.files.resolve(output.path, "mp4") if output else None
        if path is None:
            self.pubs.fail(pub.id, pub.attempt, "the rendered file is missing")  # nada a enviar: retomar só com render novo + retry
            return None
        credits, sources = credits_and_sources(self.scripts, self.assets, self.snaps, video.id)
        description = build_description(video.description, credits, sources, synthetic=True)
        when = pub.publish_at if pub.publish_at and pub.publish_at > _utc_now() else None  # horário que já passou: fica privado, sem agendar
        body = youtube_insert_body(video.title or default_title(video.topic), description, video.tags, when)
        return ClaimItem(pub, body, Path(path).stat().st_size, "video/mp4", f"/studio/videos/{video.id}/file", f"/studio/videos/{video.id}/thumbnail")


class _Pubs:
    def __init__(self, pubs: PublicationRepository):
        self.pubs = pubs

    def _get(self, publication_id: str) -> Publication:
        pub = self.pubs.get_by_id(publication_id)
        if pub is None:
            raise PublicationNotFound(publication_id)
        return pub


class SetUploadUri(_Pubs):
    def execute(self, publication_id: str, attempt: int, upload_uri: str, replace: bool = False) -> Publication:
        if not valid_upload_uri(upload_uri):
            raise InvalidPublishData("upload_uri is not a YouTube resumable upload session")
        self._get(publication_id)
        pub = self.pubs.set_upload_uri(publication_id, attempt, upload_uri, replace)
        if pub is None:
            raise StateConflict("not the current attempt, or an upload session is already recorded")
        return pub


class MarkUploaded(_Pubs):
    def execute(self, publication_id: str, youtube_video_id: str) -> Publication:
        if not valid_youtube_id(youtube_video_id):
            raise InvalidPublishData("youtube_video_id is not a valid YouTube video id")
        self._get(publication_id)
        pub = self.pubs.mark_uploaded(publication_id, youtube_video_id)  # PublicationConflict se for outro ID
        if pub is None:
            raise PublicationNotFound(publication_id)
        return pub


class MarkFailed(_Pubs):
    def execute(self, publication_id: str, attempt: int, error: str, retryable: bool) -> Publication:
        error = " ".join(error.split())[:500] or "unknown error"
        pub = self._get(publication_id)
        done = self.pubs.release(publication_id, attempt, error) if retryable else self.pubs.fail(publication_id, attempt, error)
        if not done:
            raise StateConflict("the publication is no longer being uploaded by this attempt")
        return self._get(pub.id)


class MarkThumbnail(_Pubs):
    def execute(self, publication_id: str) -> Publication:
        pub = self._get(publication_id)
        if not self.pubs.mark_thumbnail(publication_id):
            raise StateConflict("the video is not uploaded yet")
        return self._get(pub.id)


class RetryPublication:
    def __init__(self, videos: VideoRepository, pubs: PublicationRepository):
        self.videos, self.pubs = videos, pubs

    def execute(self, video_id: str) -> Publication:
        _require_video(self.videos, video_id)
        pub = self.pubs.retry(video_id)
        if pub is None:
            raise StateConflict("there is no FAILED publication to retry")
        return pub


class GetPublication:
    def __init__(self, videos: VideoRepository, pubs: PublicationRepository):
        self.videos, self.pubs = videos, pubs

    def execute(self, video_id: str) -> Publication | None:
        _require_video(self.videos, video_id)
        return self.pubs.get(video_id)


class GetThumbnail:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, files: RenderStorage, maker: ThumbnailMaker):
        self.videos, self.scripts, self.assets, self.files, self.maker = videos, scripts, assets, files, maker

    def execute(self, video_id: str) -> bytes | None:
        video = _require_video(self.videos, video_id)
        if video.status not in SERVABLE:
            return None
        for scene in self.scripts.scenes(video_id):
            asset = self.assets.get(scene.asset_id) if scene.asset_id else None
            if asset:
                return self.maker.make(self.files.image_path(asset.path))
        return None


@dataclass(frozen=True)
class Preview:
    video: Video
    scenes: list[Scene]
    qa: QaReport | None
    has_file: bool
    sources: list[str]
    credits: list[str]
    default_title: str
    default_description: str
    approval: Approval | None
    publication: Publication | None


class GetPreview:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, jobs: RenderJobRepository,
                 snaps: SnapshotRepository, approvals: ApprovalRepository, pubs: PublicationRepository, files: RenderStorage):
        self.videos, self.scripts, self.assets, self.jobs, self.snaps = videos, scripts, assets, jobs, snaps
        self.approvals, self.pubs, self.files = approvals, pubs, files

    def execute(self, video_id: str) -> Preview:
        video = _require_video(self.videos, video_id)
        output = self.jobs.latest_output(video_id) if video.status in SERVABLE else None
        credits, sources = credits_and_sources(self.scripts, self.assets, self.snaps, video_id)
        script = self.scripts.latest(video_id)
        return Preview(video=video, scenes=self.scripts.scenes(video_id), qa=video.qa_report,
                       has_file=bool(output and self.files.resolve(output.path, "mp4")), sources=sources, credits=credits,
                       default_title=video.title or default_title(video.topic),
                       default_description=video.description or default_description(script.text if script else ""),
                       approval=self.approvals.get(video_id), publication=self.pubs.get(video_id))


@dataclass(frozen=True)
class Publishing:
    approve: Approve
    reject: Reject
    claim: ClaimPublication
    set_uri: SetUploadUri
    uploaded: MarkUploaded
    failed: MarkFailed
    thumbnail_set: MarkThumbnail
    retry: RetryPublication
    get: GetPublication
    thumbnail: GetThumbnail
    preview: GetPreview
