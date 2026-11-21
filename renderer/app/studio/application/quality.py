"""Política determinística de QA do plano (RP-030) — aplicação pura.

Decide sobre a evidência **já medida**: delega a política a ``domain.quality`` (severidade
e cobertura) e não toca mídia — quem lê ffprobe/ebur128 e resolve os assets é o adaptador
(``adapters/quality_ffmpeg.py``, a implementação da porta ``QualityEvaluator``), montado só
em ``composition.py``. Nenhuma avaliação semântica multimodal aqui: sem provedor, a falta
continua **declarada**, nunca inventada.
"""
from __future__ import annotations

from ..domain.quality import QualityEvidence, evaluate_quality
from ..domain.qa_report import QaReport
from ..domain.render_plan import RenderPlan


class PlanQualityEvaluator:
    """Política pura do QA: plano + evidência já medida → QualityReport (F6).

    É a decisão que o adaptador de mídia (``FfmpegQualityEvaluator``) usa depois de medir;
    não é, em si, a porta ``QualityEvaluator`` (que também mede a mídia e resolve assets).
    """

    def evaluate(self, plan: RenderPlan, evidence: QualityEvidence) -> QaReport:
        return evaluate_quality(plan, evidence)
