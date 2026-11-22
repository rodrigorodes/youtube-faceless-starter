"""Leitura da aba Composição (W2.3): o que o Render Plan persistido tem, sem editar.

A tela de Composição mostra **tracks e shots do plano persistido** — a revisão mais recente de
``plan:{video_id}`` (a mesma identidade lógica que o executor grava). Nada de timeline
ilustrativa: só as tracks que o plano declara (a de overlay só existe quando há overlay) e os
shots com cena, papel (``base``/``overlay``), ``z_index``, janela e se estão ativos. Sem plano, a
visão é ``None`` e a tela diz que ainda não há plano de composição.

``BuildCompositionView`` depende **só** da porta ``RenderPlanRepository``: a rota não consulta o
banco nem monta SQL. É leitura pura — a edição por cena é a onda 4 e não passa por aqui.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.render_plan import RenderPlan
from .ports import RenderPlanRepository

__all__ = ["plan_id_for_video", "CompositionShotView", "CompositionTrackView",
           "CompositionView", "BuildCompositionView"]


def plan_id_for_video(video_id: str) -> str:
    """Identidade lógica do plano de um vídeo — a mesma convenção do executor FFmpeg."""
    return f"plan:{video_id}"


@dataclass(frozen=True)
class CompositionShotView:
    """Um shot do plano, já localizado na cena e com a janela em segundos (além dos ticks)."""

    shot_id: str
    scene_id: str
    role: str
    z_index: int
    start_seconds: float
    end_seconds: float
    active: bool
    asset_ref: str

    @property
    def window_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass(frozen=True)
class CompositionTrackView:
    """Uma track declarada pelo plano.

    ``role`` distingue a faixa visual de base da de overlay (``—`` nas faixas de narração e
    legenda, que não hospedam shots). ``active`` é ter conteúdo real: shots ou cues — uma track
    declarada mas vazia é mostrada como inativa, não escondida.
    """

    track_id: str
    kind: str
    role: str
    shots: tuple[CompositionShotView, ...] = field(default_factory=tuple)
    cue_count: int = 0

    @property
    def active(self) -> bool:
        return bool(self.shots) or self.cue_count > 0


@dataclass(frozen=True)
class CompositionView:
    """Projeção de leitura do plano: revisão, tracks e shots (sem nenhum controle de edição)."""

    video_id: str
    plan_id: str
    revision: int
    ticks_per_second: int
    tracks: tuple[CompositionTrackView, ...]
    shots: tuple[CompositionShotView, ...]


def _track_role(shots: tuple[CompositionShotView, ...]) -> str:
    """Papel da track derivado dos seus shots: base, overlay, misto (não deveria ocorrer) ou —."""
    roles = {shot.role for shot in shots}
    if roles == {"base"}:
        return "base"
    if roles == {"overlay"}:
        return "overlay"
    if roles:
        return "/".join(sorted(roles))
    return "—"


def _project(plan: RenderPlan) -> CompositionView:
    tps = plan.timeline.ticks_per_second
    shots_by_track: dict[str, list[CompositionShotView]] = {
        track.track_id: [] for track in plan.timeline.tracks
    }
    cues_by_track: dict[str, int] = {}
    for cue in plan.timeline.narration:
        cues_by_track[cue.track_id] = cues_by_track.get(cue.track_id, 0) + 1
    for cue in plan.timeline.subtitles:
        cues_by_track[cue.track_id] = cues_by_track.get(cue.track_id, 0) + 1

    shots: list[CompositionShotView] = []
    for scene in plan.timeline.scenes:
        scene_start = scene.start_tick
        scene_end = scene.start_tick + scene.duration_ticks
        for shot in sorted(scene.shots, key=lambda s: (s.start_tick, s.z_index, s.shot_id)):
            end_tick = shot.start_tick + shot.duration_ticks
            view = CompositionShotView(
                shot_id=shot.shot_id,
                scene_id=scene.scene_id,
                role=shot.role,
                z_index=shot.z_index,
                start_seconds=shot.start_tick / tps,
                end_seconds=end_tick / tps,
                # Derivado do plano: o shot ativo é o que cai inteiro na janela da sua cena.
                # Num plano válido é sempre ``True`` — a coluna existe para não inventar um
                # botão liga/desliga que o plano não tem.
                active=scene_start <= shot.start_tick and end_tick <= scene_end,
                asset_ref=shot.asset_ref,
            )
            shots.append(view)
            shots_by_track.setdefault(shot.track_id, []).append(view)

    tracks = tuple(
        CompositionTrackView(
            track_id=track.track_id,
            kind=track.kind,
            role=_track_role(tuple(shots_by_track.get(track.track_id, ()))),
            shots=tuple(shots_by_track.get(track.track_id, ())),
            cue_count=cues_by_track.get(track.track_id, 0),
        )
        for track in plan.timeline.tracks
    )
    return CompositionView(
        video_id=plan.video_id,
        plan_id=plan.plan_id,
        revision=plan.revision,
        ticks_per_second=tps,
        tracks=tracks,
        shots=tuple(shots),
    )


class BuildCompositionView:
    """Caso de uso da aba Composição: a última revisão do plano, ou ``None`` (vazio explícito)."""

    def __init__(self, plans: RenderPlanRepository):
        self.plans = plans

    def execute(self, video_id: str) -> CompositionView | None:
        plan = self.plans.latest_plan(plan_id_for_video(video_id))
        return None if plan is None else _project(plan)
