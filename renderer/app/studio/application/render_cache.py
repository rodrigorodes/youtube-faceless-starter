"""Decisão de regeneração seletiva do Render Plan (RP-029) — application pura.

Liga o grafo de dependências do domínio (``domain.render_cache``) ao repositório versionado
(``RenderPlanRepository``) e responde à pergunta do botão "regenerar cena": **o que precisa
ser refeito e o que pode ser reusado**.

O ``PlanRegeneration`` não executa FFmpeg nem toca disco: ``decide`` compara a revisão nova
com a anterior (persistida) e cruza com os artefatos já registrados; ``commit`` grava a
revisão e os artefatos produzidos para alimentar o próximo ``decide``. A execução — o render
parcial de verdade — é do executor; aqui só se **decide**.

Limite explícito (honestidade sobre "render parcial"): a recomposição final (concat + mixagem,
nó ``final``) é invalidada por **dependência** sempre que qualquer cena muda. Reusar o MP4
final quando nada mudou é seguro; remendar o MP4 no lugar **não** é feito — o aceite admite a
recomposição, e é o que este módulo declara.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..domain.render_cache import (
    CacheEntry,
    CachePolicy,
    DependencyGraph,
    NodeId,
    plan_graph,
    selective_invalidation,
)
from ..domain.render_plan import RenderPlan
from .ports import RenderPlanRepository

FINAL_NODE = NodeId("final", "video")


@dataclass(frozen=True)
class Regeneration:
    """Resultado do confronto de duas revisões: o que regerar e o que o cache entrega."""

    plan_id: str
    revision: int
    previous_revision: int | None
    invalidated: tuple[NodeId, ...]
    missing: tuple[NodeId, ...]
    cache_hits: tuple[NodeId, ...]
    final_recompose: bool

    @property
    def to_generate(self) -> tuple[NodeId, ...]:
        """Nós que ainda precisam de um render: os invalidados **e** os reusáveis sem artefato."""
        return tuple(sorted(set(self.invalidated) | set(self.missing)))

    @property
    def reused(self) -> tuple[NodeId, ...]:
        return self.cache_hits


class PlanRegeneration:
    """Caso de uso da regeneração seletiva: decide o que reusar e persiste o que foi produzido."""

    def __init__(self, plans: RenderPlanRepository, *, policy: CachePolicy | None = None):
        self.plans = plans
        self.policy = policy or CachePolicy()

    def decide(self, plan: RenderPlan, *, labels: Mapping[str, str] | None = None) -> Regeneration:
        """Decide sem gravar nada: confronta o plano com a última revisão persistida."""
        current = plan_graph(plan, labels=labels)
        previous = self._previous_graph(plan, labels=labels)
        previous_revision = previous[1] if previous is not None else None
        result = selective_invalidation(previous[0] if previous is not None else None, current, policy=self.policy)
        recorded = self.plans.entries(plan.plan_id)

        hits: list[NodeId] = []
        missing: list[NodeId] = []
        for node in sorted(result.reusable):
            entry = recorded.get(node)
            if entry is not None and entry.fingerprint == current.fingerprint(node):
                hits.append(node)
            else:
                missing.append(node)

        invalidated = tuple(sorted(result.invalidated))
        final_recompose = FINAL_NODE in result.invalidated or FINAL_NODE in missing
        return Regeneration(
            plan_id=plan.plan_id,
            revision=plan.revision,
            previous_revision=previous_revision,
            invalidated=invalidated,
            missing=tuple(missing),
            cache_hits=tuple(hits),
            final_recompose=final_recompose,
        )

    def commit(
        self, plan: RenderPlan, produced: Mapping[NodeId, CacheEntry], *, labels: Mapping[str, str] | None = None
    ) -> Regeneration:
        """Grava o plano e os artefatos produzidos; devolve a decisão tomada.

        Nós reusáveis que não foram regerados herdam o artefato já registrado (o cache é
        carregado para frente). Só o fingerprint atual é persistido por nó.
        """
        decision = self.decide(plan, labels=labels)
        current = plan_graph(plan, labels=labels)
        carried = self.plans.entries(plan.plan_id)
        self.plans.save_plan(plan)
        for item in current.nodes:
            entry = produced.get(item.node)
            if entry is None:
                previous_entry = carried.get(item.node)
                if previous_entry is None or previous_entry.fingerprint != item.fingerprint:
                    continue  # sem artefato e sem reuso válido: nada a registrar
                entry = previous_entry
            self.plans.record_entry(
                CacheEntry(
                    plan_id=plan.plan_id,
                    node=item.node,
                    fingerprint=item.fingerprint,
                    artifact_sha256=entry.artifact_sha256,
                    artifact_uri=entry.artifact_uri,
                    revision=plan.revision,
                )
            )
        return decision

    def _previous_graph(self, plan: RenderPlan, *, labels: Mapping[str, str] | None) -> tuple[DependencyGraph, int] | None:
        previous_plan = self.plans.latest_plan(plan.plan_id)
        if previous_plan is None or previous_plan.revision >= plan.revision:
            return None  # primeira revisão, ou já existe uma revisão igual/mais nova: nada a comparar
        return plan_graph(previous_plan, labels=labels), previous_plan.revision
