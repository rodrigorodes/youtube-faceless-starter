"""Kill-switch de disponibilidade do caminho baseado em plano (RP-032).

O renderer legado **não existe mais**: foi removido na RP-05 (emenda §14 do design), e a
decisão de "manter os dois caminhos atrás de flag" foi revogada pelo usuário. Então
desligar a flag (``STUDIO_RENDER_PLAN_ENABLED=0``) **não** cai para um renderer antigo —
ele não existe. O render é recusado de forma explícita; a disponibilidade volta com o
**redeploy da imagem anterior**. Sem esta peça, "desligar a flag" prometeria um rollback
para um caminho que já não está no código.
"""
from __future__ import annotations

from pathlib import Path


class RenderPlanDisabled(RuntimeError):
    """O caminho baseado em plano está desligado por flag de disponibilidade (RP-032)."""


class DisabledRenderer:
    """Recusa o render quando o caminho de plano está desligado.

    Mesmo ``name`` do renderer real para **não** mudar a identidade do asset de vídeo
    (``cache_key``/``checksum``); o ``render`` levanta antes de tocar qualquer arquivo. O
    ``RunRender`` transforma a exceção em job FAILED com a causa — a produção para, nada é
    publicado por um caminho que ninguém homologou.
    """

    name = "ffmpeg"

    def __init__(self, model: str = "rich"):
        self.model = model

    def render(self, spec, out_path: Path) -> Path:
        raise RenderPlanDisabled(
            "the plan-based renderer is disabled by STUDIO_RENDER_PLAN_ENABLED; "
            "there is no legacy fallback — roll back by redeploying the previous image"
        )

    def qa_inputs(self, spec):
        """Sem render não há plano/descriptors: recusa com a mesma causa do ``render``."""
        raise RenderPlanDisabled(
            "the plan-based renderer is disabled by STUDIO_RENDER_PLAN_ENABLED; "
            "there is no legacy fallback — roll back by redeploying the previous image"
        )
