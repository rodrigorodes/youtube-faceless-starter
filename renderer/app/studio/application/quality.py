"""Implementação determinística do ``QualityEvaluator`` (RP-030) — aplicação pura.

Decide sobre a evidência **já medida**: delega a política a ``domain.quality`` (severidade
e cobertura) e não toca mídia — quem lê ffprobe/ebur128 é o adaptador
(``adapters/quality_ffmpeg.py``), montado só em ``composition.py``. Nenhuma avaliação
semântica multimodal aqui: sem provedor, a falta continua **declarada**, nunca inventada.
"""
from __future__ import annotations

from ..domain.quality import QualityEvidence, evaluate_quality
from ..domain.qa_report import QaReport
from ..domain.render_plan import RenderPlan


class PlanQualityEvaluator:
    """``QualityEvaluator`` determinístico: plano + evidências → QualityReport (F6)."""

    def evaluate(self, plan: RenderPlan, evidence: QualityEvidence) -> QaReport:
        return evaluate_quality(plan, evidence)
