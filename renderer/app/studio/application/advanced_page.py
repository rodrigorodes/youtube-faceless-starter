"""View model da tela Avançado (F02.T03): diagnóstico real, montado a partir das portas.

Não cria persistência nem novo serviço: junta (a) a configuração efetiva do canal — o mesmo
`ProjectConfig` que a produção usa —, (b) o catálogo de providers com a disponibilidade medida e
(c) a saúde do banco, informada pelo chamador. Nada de chave, token ou saldo: só nome e modelo.

A tela é read-only de propósito: operar providers acontece nas áreas próprias (Produção/Conexões),
com as validações de cada caso de uso.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.ids import check_id
from ..domain.provider import Availability
from .providers import ProviderService

_KIND_LABEL = {"text": "Texto", "image": "Imagem", "voice": "Voz", "renderer": "Render"}


@dataclass(frozen=True)
class AdvancedRow:
    kind: str
    name: str
    availability: str
    cost: str
    quality: str


@dataclass(frozen=True)
class AdvancedPageView:
    projects: list[tuple[str, str]]
    selected_project_id: str
    database_ok: bool
    providers: tuple[AdvancedRow, ...] = ()
    effective: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()


class BuildAdvancedView:
    def __init__(self, providers: ProviderService, projects):
        """`projects` é a porta de leitura dos canais (a mesma da casca), não um repo novo."""
        self.providers = providers
        self.projects = projects

    def execute(self, project_id: str | None, *, database_ok: bool) -> AdvancedPageView:
        p_id = check_id(project_id) if project_id else None
        cards = self.providers.list(p_id)
        rows = tuple(
            AdvancedRow(
                kind=_KIND_LABEL.get(card.kind.value, card.kind.value),
                name=card.spec,
                availability=(("disponível" if card.availability is Availability.AVAILABLE
                               else "indisponível") + (f": {card.reason}" if card.reason else "")),
                cost=card.cost.label,
                quality=str(card.quality),
            )
            for card in cards
        )
        effective: tuple[tuple[str, str], ...] = ()
        notes: list[str] = []
        if p_id is not None:
            configured = self.providers.configured(p_id)
            effective = tuple((_KIND_LABEL.get(kind, kind), spec) for kind, spec in configured.items())
        return AdvancedPageView(projects=self.projects.projects(), selected_project_id=p_id or "",
                                database_ok=database_ok, providers=rows, effective=effective,
                                notes=tuple(notes))