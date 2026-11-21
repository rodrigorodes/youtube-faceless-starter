"""Caso de uso ``ResolvePlanAssets`` (RP-019..RP-022) — resolve e valida o manifesto.

Camada de aplicação pura: só depende do domínio e da porta ``AssetResolver``. O
resolver concreto (storage/rede) é injetado; aqui decide-se **se** cada asset do plano
serve — disponibilidade, hash, licença, codec, resolução e duração — sem tocar disco.

Fluxo:

1. indexa o manifesto do plano (``AssetManifest``) uma vez;
2. resolve **cada** ``AssetReference`` do manifesto e confere a identidade/licença/
   disponibilidade contra o manifesto (``verify_descriptor``);
3. percorre cada shot e valida a **fitness** ao quadro de saída e ao shot
   (``check_fit``) — considerando ``composition.fit`` e a duração do shot.

O resultado é ``ResolvedAssets``: um descriptor por asset resolvido, pronto para o
executor (RP-05) compilar ``RenderPlan + assets resolvidos`` sem reabrir o manifesto.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..domain.asset_resolver import (
    AssetDescriptor,
    AssetManifest,
    check_fit,
    verify_descriptor,
)
from ..domain.render_plan import RenderPlan
from .ports import AssetResolver


@dataclass(frozen=True)
class ResolvedAssets:
    """Descriptors resolvidos, indexados por ``asset_id``."""

    descriptors: tuple[AssetDescriptor, ...]

    @property
    def by_id(self) -> dict[str, AssetDescriptor]:
        return {d.asset_id: d for d in self.descriptors}

    def get(self, asset_id: str) -> AssetDescriptor | None:
        return self.by_id.get(asset_id)


class ResolvePlanAssets:
    """Resolve e valida o manifesto de um ``RenderPlan`` antes de qualquer render."""

    def __init__(self, resolver: AssetResolver):
        self.resolver = resolver

    def execute(self, plan: RenderPlan) -> ResolvedAssets:
        manifest = AssetManifest.of(plan)
        resolved: dict[str, AssetDescriptor] = {}
        for reference in manifest.references:
            descriptor = self.resolver.resolve(reference)
            verify_descriptor(manifest, descriptor)
            resolved[reference.asset_id] = descriptor
        for scene in plan.timeline.scenes:
            for shot in scene.shots:
                descriptor = resolved[shot.asset_ref]  # o plano garante que existe
                fit = shot.composition.fit if shot.composition is not None else "cover"
                check_fit(descriptor, plan.output, fit=fit, shot_duration_ticks=shot.duration_ticks)
        return ResolvedAssets(tuple(resolved.values()))
