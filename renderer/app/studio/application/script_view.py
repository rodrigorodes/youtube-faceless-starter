"""Visão do Roteiro (F4-07): monta dado real para a tela, ou estado vazio explícito.

Nenhum dado ilustrativo do mockup é fabricado aqui: capítulos, durações, versões,
fact-check e aprovação vêm do que está persistido. Sem roteiro, a visão diz que não há
roteiro — não inventa percentuais nem barras de progresso (o trabalho não é linear).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.longform import ScriptPlan, approval_is_current, review_script
from ..domain.narration_duration import estimate_text_durations
from .editorial import _claims, _require_video
from .longform import DEFAULT_DURATION_TOLERANCE, block_label
from .ports import (
    FactCheckReader,
    LongFormScriptRepository,
    ScriptRepository,
    SnapshotRepository,
    VideoRepository,
)


@dataclass(frozen=True)
class ChapterView:
    index: int
    title: str
    block: str
    block_label: str
    scene_count: int
    estimated_seconds: float


@dataclass(frozen=True)
class VersionView:
    version: int
    current: bool
    approved: bool
    rejected: bool
    superseded: bool
    hash_short: str | None
    content_hash: str | None = None


@dataclass(frozen=True)
class FactCheckView:
    script_version: int
    current: bool
    passed: bool
    overridden: bool


@dataclass(frozen=True)
class ReviewView:
    passed: bool
    structure_ok: bool
    continuity_ok: bool
    duration_ok: bool
    redundant_count: int
    uncited_count: int
    invented_count: int


@dataclass(frozen=True)
class ScriptPageView:
    video_id: str
    topic: str
    has_script: bool
    version: int | None = None
    estimated_seconds: float | None = None
    target_seconds: float | None = None
    words_per_minute: float | None = None
    scene_count: int = 0
    chapter_count: int = 0
    chapters: list[ChapterView] = field(default_factory=list)
    versions: list[VersionView] = field(default_factory=list)
    fact_check: FactCheckView | None = None
    approved: bool = False
    review: ReviewView | None = None


def _hash_short(content_hash: str | None) -> str | None:
    return None if content_hash is None else content_hash[:6] + "…" + content_hash[-3:]


class BuildScriptView:
    """Caso de uso da tela de Roteiro: dado real do roteiro longo, ou o vazio explícito."""

    def __init__(self, videos: VideoRepository, snaps: SnapshotRepository, scripts: ScriptRepository,
                 longform: LongFormScriptRepository, checks: FactCheckReader | None = None,
                 allow_names: frozenset[str] = frozenset(), tolerance: float = DEFAULT_DURATION_TOLERANCE):
        self.videos, self.snaps, self.scripts, self.longform = videos, snaps, scripts, longform
        self.checks, self.allow_names, self.tolerance = checks, allow_names, tolerance

    def execute(self, video_id: str) -> ScriptPageView:
        video = _require_video(self.videos, video_id)
        records = self.longform.list_script_records(video_id)
        if not records:
            return ScriptPageView(video_id=video.id, topic=video.topic, has_script=False)
        latest = records[-1]
        plan = latest.plan
        scenes = self.scripts.scenes(video_id)
        estimated = None
        chapter_views: list[ChapterView] = []
        if plan is not None:
            durations = estimate_text_durations([s.narration for s in scenes], plan.words_per_minute).scene_seconds \
                if scenes else ()
            estimated = sum(durations)
            chapter_views = self._chapters(plan, durations)

        fact_record = self.checks.latest(video_id) if self.checks is not None else None
        fact_check = None
        if fact_record is not None:
            fact_check = FactCheckView(script_version=fact_record.script_version,
                                       current=fact_record.script_version == latest.script.version,
                                       passed=fact_record.report.passed, overridden=fact_record.report.overridden)

        approved = latest.approval is not None and approval_is_current(
            latest.approval, version=latest.script.version, content_hash=latest.content_hash or "")

        review = None
        if plan is not None and scenes:
            snapshots = self.snaps.list(video_id)
            measured = review_script(plan, scenes, sources=[s.text for s in snapshots],
                                     known_claim_ids={c.id for c in _claims(snapshots)},
                                     allow_names=self.allow_names, tolerance=self.tolerance)
            review = ReviewView(passed=measured.passed, structure_ok=measured.structure_ok,
                                continuity_ok=measured.continuity_ok, duration_ok=measured.duration_ok,
                                redundant_count=len(measured.redundant_scene_idxs),
                                uncited_count=len(measured.uncited_scene_idxs),
                                invented_count=len(measured.unsupported))

        versions = [
            VersionView(version=r.script.version, current=r.script.version == latest.script.version,
                        approved=r.approval is not None and r.approval.decision == "approved",
                        rejected=r.approval is not None and r.approval.decision == "rejected",
                        superseded=r.script.version < latest.script.version,
                        hash_short=_hash_short(r.content_hash), content_hash=r.content_hash)
            for r in records
        ]
        return ScriptPageView(
            video_id=video.id, topic=video.topic, has_script=True, version=latest.script.version,
            estimated_seconds=estimated, target_seconds=plan.target_seconds if plan else None,
            words_per_minute=plan.words_per_minute if plan else None,
            scene_count=len(scenes), chapter_count=len(plan.chapters) if plan else 0,
            chapters=chapter_views, versions=versions, fact_check=fact_check, approved=approved, review=review,
        )

    @staticmethod
    def _chapters(plan: ScriptPlan, durations: tuple[float, ...]) -> list[ChapterView]:
        views: list[ChapterView] = []
        cursor = 0
        exact = sum(chapter.scene_count for chapter in plan.chapters) == len(durations)
        for index, chapter in enumerate(plan.chapters):
            if exact:
                estimated = sum(durations[cursor:cursor + chapter.scene_count])
                cursor += chapter.scene_count
            else:
                estimated = chapter.target_seconds
            views.append(ChapterView(index=index, title=chapter.title, block=chapter.block.value,
                                     block_label=block_label(chapter.block), scene_count=chapter.scene_count,
                                     estimated_seconds=estimated))
        return views
