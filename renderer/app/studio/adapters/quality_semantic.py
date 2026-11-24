"""Adaptador semântico padrão (VE-05): declara a ausência de verificação, não a inventa.

Não existe provedor de visão nesta fatia. O ``SemanticChecker`` honesto devolve
``not_verified`` com motivo — o resultado tipado que o domínio transforma em achado
``info``/``editorial``. Um provedor real (LLM de visão ou heurística) entra como
adapter novo, atrás da **mesma** porta, sem alterar o contrato nem o núcleo puro.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..domain.asset_resolver import AssetDescriptor
from ..domain.quality import SemanticResult
from ..domain.render_plan import RenderPlan


class NotVerifiedSemanticChecker:
    """``SemanticChecker`` default: sem provedor, o resultado é ``not_verified``.

    A honestidade é o ponto: ``not_verified`` nunca vira ``verified`` por omissão e
    nunca produz score visual. O domínio registra o achado informativo e mantém a
    cobertura técnica intacta — a semântica não é usada como gate escondido.
    """

    name = "not_verified"

    def check(self, plan: RenderPlan, *, media_path: Path,
              narration_path: Path | None = None,
              descriptors: Sequence[AssetDescriptor] = ()) -> SemanticResult:
        if not isinstance(plan, RenderPlan):
            raise TypeError("plan must be a RenderPlan")
        return SemanticResult(
            verdict="not_verified",
            reason="no semantic/vision provider is configured; multimodal evaluation is not verified",
        )


class TextCoherenceSemanticChecker:
    """Verificador semântico de coerência textual e editorial (Onda 5)."""

    def __init__(self, text_model: object | None = None) -> None:
        self.text_model = text_model

    def check(self, plan: RenderPlan, *, media_path: Path,
              narration_path: Path | None = None,
              descriptors: Sequence[AssetDescriptor] = ()) -> SemanticResult:
        if not isinstance(plan, RenderPlan):
            raise TypeError("plan must be a RenderPlan")

        all_cues = getattr(plan.timeline, "subtitles", ())
        all_text = " ".join(c.text for c in all_cues if getattr(c, "text", None)).strip()

        if all_cues and not all_text:
            return SemanticResult(verdict="failed", reason="Narração vazia ou sem texto legível nas cenas")

        if self.text_model is None:
            return SemanticResult(
                verdict="not_verified",
                reason="no text model configured for semantic evaluation",
            )

        if not all_text:
            return SemanticResult(verdict="failed", reason="Narração vazia detectada no roteiro")

        try:
            res = self.text_model.generate(f"Avalie a coerência do roteiro: {all_text}")
            text_resp = getattr(res, "text", str(res))
            if "incoerente" in text_resp.lower() or '"coherent": false' in text_resp.lower():
                return SemanticResult(verdict="failed", reason=f"Incoerência semântica: {text_resp}")
            return SemanticResult(verdict="verified", reason="Coerência textual do roteiro verificada com sucesso")
        except Exception as exc:
            return SemanticResult(verdict="not_verified", reason=f"Falha ao avaliar modelo: {exc}")
