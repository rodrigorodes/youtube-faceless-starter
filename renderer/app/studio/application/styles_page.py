"""Projeção da tela de Estilos (VS-05a) — a biblioteca compartilhada, só com dado real.

A tela é uma **lista**: cada estilo sai com um resumo curto dos parâmetros e **quantos canais
usam** (contagem medida no banco, nunca estimada). Sem medição não há número: um estilo sem canal
aparece como "nenhum canal usa", não como percentual inventado.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..domain.visual_style import VisualStyle
from .ports import VisualStyleRepository

__all__ = ["StyleListItem", "StylesPageView", "BuildStylesPage"]


@dataclass(frozen=True)
class StyleListItem:
    """Um estilo da biblioteca e o uso **medido** dele entre os canais."""

    style: VisualStyle
    channels_using: int


@dataclass(frozen=True)
class StylesPageView:
    items: tuple[StyleListItem, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.items


class BuildStylesPage:
    """Monta a projeção da biblioteca: lista + contagem de uso por estilo."""

    def __init__(self, styles: VisualStyleRepository):
        self.styles = styles

    def execute(self, include_archived: bool = False) -> StylesPageView:
        usage = self.styles.usage_counts()
        items = tuple(
            StyleListItem(style=style, channels_using=usage.get(style.id, 0))
            for style in self.styles.list(include_archived)
        )
        return StylesPageView(items=items)
