"""Medição e avaliação do QA do render (RP-030) — o único ponto com ffprobe/ebur128 aqui.

``FfmpegQualityProbe`` mede a mídia renderizada com o ``QaAnalyzer`` (``FfmpegQa``:
ffprobe + ebur128 + silencedetect + blackdetect) e monta a ``QualityEvidence`` — as
métricas e os ``AssetDescriptor`` resolvidos — **sem decidir nada**. O
``FfmpegQualityEvaluator`` junta a medição à política pura (``PlanQualityEvaluator``,
``domain.quality``) e devolve o QualityReport versionado da F6.

``FfmpegOverlayVerifier`` (VE-05) mede o que é **técnico** no overlay, sem IA: extrai
quadros do vídeo renderizado nas bordas da janela planejada e compara-os com a base
(ffprobe/ffmpeg) para provar presença e janela; o tamanho/fit é conferido contra o
manifesto no domínio (``check_fit``). Plano sem overlay devolve sequência vazia, então o
QA de hoje não muda.

Nada de avaliação multimodal aqui: o adaptador só usa ffprobe/ffmpeg determinístico. A
avaliação semântica visual exige um provedor de visão e continua declarada fora
(``NotVerifiedSemanticChecker``/``domain.quality.MULTIMODAL_EVALUATION``). A fiação de
qualquer adaptador concreto mora **só** em ``composition.py``.
"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from ..application.ports import OverlayVerifier, QaAnalyzer, SemanticChecker
from ..application.quality import PlanQualityEvaluator
from ..domain.asset_resolver import AssetDescriptor
from ..domain.qa_report import QaReport
from ..domain.quality import OverlayEvidence, QualityEvidence, SemanticResult
from ..domain.render_plan import RenderPlan
from .qa_ffmpeg import FfmpegQa
from .quality_semantic import NotVerifiedSemanticChecker

# Quadro reduzido em que as bordas do overlay são comparadas (barato e robusto a ruído).
_OVERLAY_GRID = 48
# Diferença média mínima (0..1 por canal) para considerar que uma borda mudou o quadro.
_OVERLAY_FLOOR = 0.02
# A borda precisa mudar mais do que isto vezes a variação típica da base na mesma janela.
_OVERLAY_FACTOR = 3.0
# Diferença por canal (0..255) que conta como pixel alterado no coverage_ratio.
_OVERLAY_CHANNEL_THRESHOLD = 12


class FfmpegQualityProbe:
    """Mede a evidência do QA (RP-030) sem decidir: só ffprobe/ebur128 determinístico."""

    def __init__(self, analyzer: QaAnalyzer | None = None, clock=None):
        self.analyzer = analyzer or FfmpegQa()
        self._clock = clock

    def measure(self, *, media_path: Path, narration_path: Path | None = None,
                descriptors: Sequence[AssetDescriptor] = (), render_id: str, checksum: str,
                overlays: Sequence[OverlayEvidence] = (),
                semantic: SemanticResult | None = None) -> QualityEvidence:
        metrics = self.analyzer.analyze(Path(media_path), narration=narration_path)
        return QualityEvidence(
            render_id=render_id,
            checksum=checksum,
            media=dict(metrics),
            assets=tuple(descriptors),
            generated_at=self._clock() if self._clock else datetime.now(timezone.utc),
            overlays=tuple(overlays),
            semantic=semantic,
        )


def _has_overlay(plan: RenderPlan) -> bool:
    return any(shot.role == "overlay" for scene in plan.timeline.scenes for shot in scene.shots)


def _run_bytes(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("overlay analysis timed out") from None


def _probe_media(path: Path, timeout: int) -> tuple[float, int, int]:
    run = _run_bytes(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
                      "-show_format", str(path)], 60)
    if run.returncode != 0:
        raise RuntimeError("could not read the rendered media file")
    try:
        info = json.loads(run.stdout)
        video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
        duration = float(info["format"]["duration"])
        width, height = int(video["width"]), int(video["height"])
    except (ValueError, KeyError, StopIteration, TypeError):
        raise RuntimeError("could not read the rendered media file") from None
    if duration <= 0 or width <= 0 or height <= 0:
        raise RuntimeError("rendered media has no positive duration or resolution")
    return duration, width, height


def _frame(path: Path, seconds: float, timeout: int) -> bytes:
    run = _run_bytes(["ffmpeg", "-hide_banner", "-loglevel", "error",
                      "-ss", f"{max(0.0, seconds):.3f}", "-i", str(path),
                      "-frames:v", "1", "-vf", f"scale={_OVERLAY_GRID}:{_OVERLAY_GRID}:flags=area",
                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], timeout)
    expected = _OVERLAY_GRID * _OVERLAY_GRID * 3
    if run.returncode != 0 or len(run.stdout) != expected:
        raise RuntimeError("could not extract a frame from the rendered media")
    return run.stdout


def _difference(first: bytes, second: bytes) -> tuple[float, float]:
    """(diferença média por canal em 0..1, fração de pixels alterados)."""
    changed = 0
    total = 0
    pixels = len(first) // 3
    for index in range(0, len(first), 3):
        delta = max(abs(first[index] - second[index]),
                    abs(first[index + 1] - second[index + 1]),
                    abs(first[index + 2] - second[index + 2]))
        total += delta
        if delta > _OVERLAY_CHANNEL_THRESHOLD:
            changed += 1
    return total / (pixels * 255), changed / pixels


def _detect_overlay(path: Path, start_s: float, end_s: float, duration: float,
                    timeout: int) -> tuple[bool | None, float | None, str]:
    """Detecta a camada pelas **descontinuidades** nas bordas da janela planejada.

    Compara o quadro imediatamente antes/à frente da janela com o quadro dentro dela e
    com a variação típica da base no mesmo intervalo. Um overlay em tela cheia produz
    uma borda muito maior do que o movimento da base; se nenhuma borda é detectável
    (janela cobrindo todo o render), a presença não é afirmada.
    """
    margin = min(0.25, max(0.05, (end_s - start_s) / 4))
    # Um pouco antes do fim: `-ss` no fim exato pode cair depois do último quadro.
    limit = max(0.0, duration - 0.1)
    inside_start = min(max(0.0, start_s + margin), limit)
    inside_end = min(max(0.0, end_s - margin), limit)
    before = max(0.0, start_s - margin)
    after = min(limit, end_s + margin)
    baseline_before = max(0.0, before - margin)
    baseline_after = min(limit, after + margin)
    times = {inside_start, inside_end, before, after, baseline_before, baseline_after}
    frames = {moment: _frame(path, moment, timeout) for moment in times}
    boundaries: list[bool] = []
    coverage: float | None = None
    if start_s > 0.0 and before < inside_start:
        mean_diff, changed = _difference(frames[before], frames[inside_start])
        baseline = _difference(frames[baseline_before], frames[before])[0] if baseline_before < before else 0.0
        boundaries.append(mean_diff >= max(_OVERLAY_FLOOR, baseline * _OVERLAY_FACTOR))
        coverage = changed if coverage is None else max(coverage, changed)
    if end_s < duration and inside_end < after:
        mean_diff, changed = _difference(frames[inside_end], frames[after])
        baseline = _difference(frames[after], frames[baseline_after])[0] if after < baseline_after else 0.0
        boundaries.append(mean_diff >= max(_OVERLAY_FLOOR, baseline * _OVERLAY_FACTOR))
        coverage = changed if coverage is None else max(coverage, changed)
    if not boundaries:
        return None, coverage, "the overlay window covers the whole render; there is no boundary to measure"
    return all(boundaries), coverage, "overlay boundary detected at the planned window"


class FfmpegOverlayVerifier:
    """``OverlayVerifier`` técnico: mede presença/janela do overlay no vídeo renderizado."""

    def __init__(self, timeout: int = 120):
        self.timeout = timeout

    def verify(self, plan: RenderPlan, *, media_path: Path,
               descriptors: Sequence[AssetDescriptor] = ()) -> tuple[OverlayEvidence, ...]:
        if not isinstance(plan, RenderPlan):
            raise TypeError("plan must be a RenderPlan")
        planned = [(scene, shot) for scene in plan.timeline.scenes for shot in scene.overlay_shots]
        if not planned:
            return ()
        path = Path(media_path)
        try:
            duration, frame_width, frame_height = _probe_media(path, self.timeout)
        except RuntimeError as exc:
            return tuple(
                OverlayEvidence(
                    shot_id=shot.shot_id, scene_id=scene.scene_id,
                    start_s=shot.start_tick / plan.timeline.ticks_per_second,
                    end_s=(shot.start_tick + shot.duration_ticks) / plan.timeline.ticks_per_second,
                    measured=False, reason=str(exc),
                )
                for scene, shot in planned
            )
        by_id = {descriptor.asset_id: descriptor for descriptor in descriptors}
        tps = plan.timeline.ticks_per_second
        evidence: list[OverlayEvidence] = []
        for scene, shot in planned:
            start_s = shot.start_tick / tps
            end_s = (shot.start_tick + shot.duration_ticks) / tps
            host = scene.host_base_for(shot)
            host_end = (host.start_tick + host.duration_ticks) / tps if host is not None else 0.0
            window_ok = (
                host is not None
                and start_s >= host.start_tick / tps - 0.001
                and end_s <= host_end + 0.001
                and end_s <= duration + 0.001
            )
            try:
                present, coverage, reason = _detect_overlay(path, start_s, end_s, duration, self.timeout)
            except RuntimeError as exc:
                evidence.append(OverlayEvidence(
                    shot_id=shot.shot_id, scene_id=scene.scene_id, start_s=start_s, end_s=end_s,
                    measured=False, reason=str(exc),
                ))
                continue
            if present is None:
                evidence.append(OverlayEvidence(
                    shot_id=shot.shot_id, scene_id=scene.scene_id, start_s=start_s, end_s=end_s,
                    measured=False, reason=reason,
                ))
                continue
            descriptor = by_id.get(shot.asset_ref)
            evidence.append(OverlayEvidence(
                shot_id=shot.shot_id,
                scene_id=scene.scene_id,
                start_s=start_s,
                end_s=end_s,
                present=present,
                window_ok=window_ok,
                coverage_ratio=coverage,
                width=descriptor.width if descriptor is not None else None,
                height=descriptor.height if descriptor is not None else None,
                frame_width=frame_width,
                frame_height=frame_height,
                reason=reason,
            ))
        return tuple(evidence)


class FfmpegQualityEvaluator:
    """QualityEvaluator de ponta a ponta: mede a mídia e aplica a política do plano.

    Quando o plano **não** tem overlay, os verificadores de overlay/semântica não são
    chamados: o QA é exatamente o de hoje. Com overlay, o verificador técnico mede a
    camada e o verificador semântico (default ``NotVerifiedSemanticChecker``) declara
    ``not_verified`` — nunca um "passou" inventado.
    """

    def __init__(self, probe: FfmpegQualityProbe | None = None,
                 evaluator: PlanQualityEvaluator | None = None,
                 overlay_verifier: OverlayVerifier | None = None,
                 semantic_checker: SemanticChecker | None = None):
        self.probe = probe or FfmpegQualityProbe()
        self.evaluator = evaluator or PlanQualityEvaluator()
        self.overlay_verifier = overlay_verifier or FfmpegOverlayVerifier()
        self.semantic_checker = semantic_checker or NotVerifiedSemanticChecker()

    def evaluate(self, plan: RenderPlan, *, media_path: Path, narration_path: Path | None = None,
                 descriptors: Sequence[AssetDescriptor] = (), render_id: str,
                 checksum: str) -> QaReport:
        overlays: tuple[OverlayEvidence, ...] = ()
        semantic: SemanticResult | None = None
        if _has_overlay(plan):
            overlays = tuple(self.overlay_verifier.verify(plan, media_path=media_path, descriptors=descriptors))
            semantic = self.semantic_checker.check(
                plan, media_path=media_path, narration_path=narration_path, descriptors=descriptors,
            )
        evidence = self.probe.measure(media_path=media_path, narration_path=narration_path,
                                      descriptors=descriptors, render_id=render_id, checksum=checksum,
                                      overlays=overlays, semantic=semantic)
        return self.evaluator.evaluate(plan, evidence)
