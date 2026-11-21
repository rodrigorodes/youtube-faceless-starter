"""Medição e avaliação do QA do render (RP-030) — o único ponto com ffprobe/ebur128 aqui.

``FfmpegQualityProbe`` mede a mídia renderizada com o ``QaAnalyzer`` (``FfmpegQa``:
ffprobe + ebur128 + silencedetect + blackdetect) e monta a ``QualityEvidence`` — as
métricas e os ``AssetDescriptor`` resolvidos — **sem decidir nada**. O
``FfmpegQualityEvaluator`` junta a medição à política pura (``PlanQualityEvaluator``,
``domain.quality``) e devolve o QualityReport versionado da F6.

Nada de avaliação multimodal aqui: o adaptador só usa ffprobe/ebur128 determinístico. A
avaliação semântica visual exige um provedor de visão e continua declarada fora
(``domain.quality.MULTIMODAL_EVALUATION``). A fiação de qualquer adaptador concreto mora
**só** em ``composition.py``.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from ..application.ports import QaAnalyzer
from ..application.quality import PlanQualityEvaluator
from ..domain.asset_resolver import AssetDescriptor
from ..domain.qa_report import QaReport
from ..domain.quality import QualityEvidence
from ..domain.render_plan import RenderPlan
from .qa_ffmpeg import FfmpegQa


class FfmpegQualityProbe:
    """Mede a evidência do QA (RP-030) sem decidir: só ffprobe/ebur128 determinístico."""

    def __init__(self, analyzer: QaAnalyzer | None = None, clock=None):
        self.analyzer = analyzer or FfmpegQa()
        self._clock = clock

    def measure(self, *, media_path: Path, narration_path: Path | None = None,
                descriptors: Sequence[AssetDescriptor] = (), render_id: str, checksum: str) -> QualityEvidence:
        metrics = self.analyzer.analyze(Path(media_path), narration=narration_path)
        return QualityEvidence(
            render_id=render_id,
            checksum=checksum,
            media=dict(metrics),
            assets=tuple(descriptors),
            generated_at=self._clock() if self._clock else datetime.now(timezone.utc),
        )


class FfmpegQualityEvaluator:
    """QualityEvaluator de ponta a ponta: mede a mídia e aplica a política do plano."""

    def __init__(self, probe: FfmpegQualityProbe | None = None,
                 evaluator: PlanQualityEvaluator | None = None):
        self.probe = probe or FfmpegQualityProbe()
        self.evaluator = evaluator or PlanQualityEvaluator()

    def evaluate(self, plan: RenderPlan, *, media_path: Path, narration_path: Path | None = None,
                 descriptors: Sequence[AssetDescriptor] = (), render_id: str,
                 checksum: str) -> QaReport:
        evidence = self.probe.measure(media_path=media_path, narration_path=narration_path,
                                      descriptors=descriptors, render_id=render_id, checksum=checksum)
        return self.evaluator.evaluate(plan, evidence)
