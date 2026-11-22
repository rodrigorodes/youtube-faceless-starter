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
