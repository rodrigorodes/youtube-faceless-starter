"""Grafo de dependências e invalidação seletiva do Render Plan (RP-028/RP-029) — domínio puro.

O Render Plan é um documento **versionado** (RP-027): o mesmo *plano lógico* evolui por
revisões e cada revisão produz artefatos. Regenerar tudo a cada edição seria caro e mentiria
sobre o custo; a fatia 7 modela **o que precisa ser refeito** quando o plano muda.

Identidade **lógica vs. física** (design §5.5):

- **lógica** — ``NodeId(kind, key)``: plano/revisão/cena/shot. Estável entre revisões.
- **física** — o ``fingerprint`` (sha256) do *conteúdo* do nó: hash do asset, modo de
  movimento, duração, legendas relativas, parâmetros da trilha. Mudou o conteúdo, mudou o
  fingerprint.

O grafo é **direcionado**: cada nó depende dos nós cujo conteúdo consome. Um nó é
**invalidado** quando (a) o próprio fingerprint mudou, (b) é novo, ou (c) algum dos seus
dependentes foi invalidado (propagação transitiva). Como a dependência é unidirecional,
mudar a cena A invalida os nós de A e os agregadores (concat/final) que dependem deles —
**sem** tocar nos nós das **outras** cenas.

Ponto que torna a invalidação seletiva real (e não cosmética): o fingerprint dos nós por
cena/shot usa apenas conteúdo **relativo** — nunca a posição absoluta na timeline. Assim,
esticar a cena A desloca a cena B no tempo, mas o segmento de vídeo de B continua idêntico e
**reusável** (é o mesmo quadro, só em outra posição da montagem). Isso é o que o compilador já
garante: ``ShotExecution.args`` não carrega o ``start_tick`` absoluto.

Limites explícitos: este módulo não toca mídia, FFmpeg, banco nem provedor. Ele **decide** o
que reusar; persistir e executar são de outras camadas. A recomposição final (concat +
mixagem) é tratada como qualquer outro nó: só é reusada quando **nada** mudou.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .render_plan import RenderPlan

NodeKind = Literal["narration", "visual", "music", "concat", "final"]


def _fingerprint(*parts: object) -> str:
    """sha256 canônico de um conteúdo: mesma entrada, mesmo hash; ordem estável."""
    canonical = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_params(params: Mapping[str, object] | None) -> tuple:
    """Parâmetros de áudio numa forma canônica: pares ``(chave, valor)`` ordenados."""
    return tuple(sorted((str(key), value) for key, value in (params or {}).items()))


def narration_fingerprint(narration: str, voice: str = "", params: Mapping[str, object] | None = None) -> str:
    """Fingerprint da **entrada** da narração: texto + identidade da voz + parâmetros de áudio.

    Propositalmente **sem** a duração da fala: ela é **saída** do TTS, então incluí-la tornaria o
    acerto de cache indecidível antes de sintetizar (o gap declarado da RP-06b). Aqui mudar o
    texto, a voz ou um parâmetro que altera o áudio invalida a narração; alongar a fala sem mudar
    a entrada **não** invalida — o WAV antigo continua reusável. É esta função que o ``RunRender``
    consulta (sem plano) e o grafo usa (com plano), para as duas decisões concordarem.
    """
    text = " ".join(str(narration).split())
    voices = ((voice, _canonical_params(params)),) if voice else ()
    return _fingerprint("narration", text, voices)


@dataclass(frozen=True, order=True)
class NodeId:
    """Identidade **lógica** de um nó do grafo: o tipo, independente de revisão/artefato."""

    kind: NodeKind
    key: str


@dataclass(frozen=True)
class PlanArtifact:
    """Registro **físico** de um artefato: hash do conteúdo + codec + localização (design §5.5)."""

    content_sha256: str
    location: str
    codec: str | None = None
    media_type: str | None = None
    byte_size: int | None = None


@dataclass(frozen=True)
class CacheEntry:
    """Ligação entre a identidade **lógica** (``node``) e o artefato **físico** produzido.

    ``fingerprint`` é o hash do conteúdo do nó na revisão em que o artefato foi produzido; a
    igualdade de fingerprint entre revisões é o que caracteriza um acerto de cache.
    """

    plan_id: str
    node: NodeId
    fingerprint: str
    artifact_sha256: str
    artifact_uri: str
    revision: int


@dataclass(frozen=True)
class CacheNode:
    """Um nó: o que ele é (``node``), o hash do seu conteúdo (``fingerprint``) e do que depende."""

    node: NodeId
    fingerprint: str
    depends_on: tuple[NodeId, ...] = ()


@dataclass(frozen=True)
class DependencyGraph:
    """Grafo determinístico de uma revisão do plano (nós ordenados por ``NodeId``)."""

    nodes: tuple[CacheNode, ...]

    def by_id(self) -> dict[NodeId, CacheNode]:
        return {item.node: item for item in self.nodes}

    def fingerprint(self, node: NodeId) -> str | None:
        item = self.by_id().get(node)
        return item.fingerprint if item is not None else None

    def kinds(self) -> dict[NodeKind, tuple[NodeId, ...]]:
        grouped: dict[NodeKind, list[NodeId]] = {}
        for item in self.nodes:
            grouped.setdefault(item.node.kind, []).append(item.node)
        return {kind: tuple(nodes) for kind, nodes in grouped.items()}


@dataclass(frozen=True)
class CachePolicy:
    """Política de cache **explícita** (RP-029).

    ``reusable_kinds`` é o conjunto de tipos de nó cujo artefato pode ser **reusado** quando o
    conteúdo (fingerprint) e os dependentes não mudam. Por padrão, todos os tipos são
    reusáveis — inclusive ``concat``/``final``, que só são reaproveitados quando **nada** mudou;
    a menor alteração de cena os invalida por dependência, que é exatamente o aceite ("a
    composição final pode continuar necessária"). Restringir o conjunto força a regeneração
    mesmo com conteúdo idêntico (cache desligado para aquele tipo).
    """

    reusable_kinds: frozenset[NodeKind] = frozenset({"narration", "visual", "music", "concat", "final"})

    def reusable(self, kind: NodeKind) -> bool:
        return kind in self.reusable_kinds


@dataclass(frozen=True)
class Invalidation:
    """Resultado da comparação revisão-a-revisão.

    ``invalidated`` = precisa (re)gerar o artefato. ``reusable`` = cache **hit**: fingerprint
    igual ao da revisão anterior, nenhum dependente invalidado e o tipo é reusável pela
    política. ``added``/``changed``/``removed`` permitem explicar *por que* cada nó caiu.
    """

    invalidated: frozenset[NodeId]
    reusable: frozenset[NodeId]
    added: frozenset[NodeId] = frozenset()
    changed: frozenset[NodeId] = frozenset()
    removed: frozenset[NodeId] = frozenset()

    @property
    def cache_hits(self) -> frozenset[NodeId]:
        """Alias explícito: um nó reusável é um acerto de cache."""
        return self.reusable


def plan_graph(plan: RenderPlan, *, labels: Mapping[str, str] | None = None) -> DependencyGraph:
    """Constrói o grafo de dependências de uma revisão do ``RenderPlan``.

    ``labels`` é o selo editorial por cena — a mesma apresentação que o compilador recebe
    (``compile_render_plan(..., labels=...)``) e que **não** faz parte do contrato do plano;
    entra como parâmetro para o fingerprint do segmento visual não ignorar o selo.
    """
    if not isinstance(plan, RenderPlan):
        raise TypeError("plan_graph expects a RenderPlan")
    badges = {str(scene_id): str(label) for scene_id, label in (labels or {}).items()}
    manifest = {reference.asset_id: reference for reference in plan.asset_manifest}
    disclosure = plan.output.disclosure
    voice_params_by_ref = {source.source_id: source.params for source in plan.generated_audio if source.kind == "voice"}

    subtitles_by_scene: dict[str, list] = {}
    for cue in plan.timeline.subtitles:
        subtitles_by_scene.setdefault(cue.scene_id, []).append(cue)
    narration_by_scene: dict[str, list] = {}
    for cue in plan.timeline.narration:
        narration_by_scene.setdefault(cue.scene_id, []).append(cue)

    nodes: list[CacheNode] = []
    scenes = sorted(plan.timeline.scenes, key=lambda scene: (scene.start_tick, scene.scene_id))

    for scene in scenes:
        subtitle_texts = tuple(
            cue.text for cue in sorted(subtitles_by_scene.get(scene.scene_id, []), key=lambda c: (c.start_tick, c.text))
        )
        narration_cues = sorted(narration_by_scene.get(scene.scene_id, []), key=lambda c: (c.start_tick, c.source_ref))
        # Fingerprint da narração: **entrada** — texto falado (que se reflete nas legendas) e a
        # voz (source_ref + parâmetros que mudam o áudio). **Sem** `duration_ticks` (saída do
        # TTS) nem tempo absoluto: mover/esticar a cena não muda a fala, e o reúso é decidível
        # antes de sintetizar (RP-06c). O texto usa os trechos de legenda que o compilador queima.
        narration_id = NodeId("narration", scene.scene_id)
        narration_cue = narration_cues[0] if narration_cues else None
        nodes.append(
            CacheNode(
                node=narration_id,
                fingerprint=narration_fingerprint(
                    " ".join(subtitle_texts),
                    narration_cue.source_ref if narration_cue else "",
                    voice_params_by_ref.get(narration_cue.source_ref) if narration_cue else None,
                ),
            )
        )
        for shot in sorted(scene.shots, key=lambda s: (s.start_tick, s.shot_id)):
            reference = manifest.get(shot.asset_ref)
            content_sha256 = reference.content_sha256 if reference is not None else ""
            media_type = reference.media_type if reference is not None else ""
            # Legendas deste shot, com janela **relativa** ao shot (é o que o compilador queima).
            captions = tuple(
                (cue.text, cue.start_tick - shot.start_tick, cue.duration_ticks)
                for cue in sorted(subtitles_by_scene.get(scene.scene_id, []), key=lambda c: (c.start_tick, c.text))
                if shot.start_tick <= cue.start_tick < shot.start_tick + shot.duration_ticks
            )
            visual_id = NodeId("visual", shot.shot_id)
            nodes.append(
                CacheNode(
                    node=visual_id,
                    fingerprint=_fingerprint(
                        "visual",
                        shot.asset_ref,
                        content_sha256,
                        media_type,
                        shot.effects.motion,
                        shot.composition.fit if shot.composition is not None else None,
                        shot.transition.kind if shot.transition is not None else None,
                        shot.transition.duration_ticks if shot.transition is not None else 0,
                        shot.duration_ticks,
                        shot.start_tick - scene.start_tick,  # relativo à cena, não à timeline
                        badges.get(scene.scene_id, ""),
                        disclosure,
                        captions,
                    ),
                )
            )

    music_ids: list[NodeId] = []
    for source in sorted(plan.generated_audio, key=lambda s: (s.kind, s.source_id)):
        if source.kind != "music":
            continue
        music_id = NodeId("music", source.source_id)
        nodes.append(
            CacheNode(
                node=music_id,
                fingerprint=_fingerprint("music", source.source_id, source.silent, sorted(source.params.items()), source.duration_ticks),
            )
        )
        music_ids.append(music_id)

    visual_nodes = sorted(item.node for item in nodes if item.node.kind == "visual")
    narration_nodes = sorted(item.node for item in nodes if item.node.kind == "narration")
    concat_id = NodeId("concat", "video")
    nodes.append(
        CacheNode(
            node=concat_id,
            # A montagem depende do conjunto ordenado de segmentos (ids + durações), não do conteúdo.
            fingerprint=_fingerprint(
                "concat",
                tuple((shot.shot_id, shot.duration_ticks) for shot in _ordered_shots(plan)),
            ),
            depends_on=tuple(visual_nodes),
        )
    )
    final_id = NodeId("final", "video")
    nodes.append(
        CacheNode(
            node=final_id,
            fingerprint=_fingerprint(
                "final",
                plan.output.format.value,
                plan.output.width,
                plan.output.height,
                plan.output.disclosure,
                plan.timeline.timebase.fps_num,
                plan.timeline.timebase.fps_den,
                plan.timeline.timebase.ticks_per_second,
                plan.timeline.duration_ticks,
            ),
            depends_on=(concat_id, *narration_nodes, *music_ids),
        )
    )
    return DependencyGraph(nodes=tuple(sorted(nodes, key=lambda item: item.node)))


def selective_invalidation(
    previous: DependencyGraph | None, current: DependencyGraph, *, policy: CachePolicy | None = None
) -> Invalidation:
    """Compara duas revisões e devolve o que regenerar e o que reusar (cache hit).

    ``previous is None`` significa "primeira revisão": nada é reusável e todo nó é novo.
    """
    policy = policy or CachePolicy()
    current_by = current.by_id()
    previous_by = previous.by_id() if previous is not None else {}

    added = frozenset(node for node in current_by if node not in previous_by)
    removed = frozenset(node for node in previous_by if node not in current_by)
    changed = frozenset(
        node for node, item in current_by.items()
        if node in previous_by and previous_by[node].fingerprint != item.fingerprint
    )

    invalidated: set[NodeId] = set(added) | set(changed)
    invalidated |= {node for node in current_by if not policy.reusable(node.kind)}
    # Propagação transitiva: um nó cujo dependente precisa ser regerado também precisa.
    frontier = True
    while frontier:
        frontier = False
        for node, item in current_by.items():
            if node in invalidated:
                continue
            if any(dependency in invalidated for dependency in item.depends_on):
                invalidated.add(node)
                frontier = True

    reusable = frozenset(node for node in current_by if node not in invalidated)
    return Invalidation(
        invalidated=frozenset(invalidated),
        reusable=reusable,
        added=added,
        changed=changed,
        removed=removed,
    )


def _ordered_shots(plan: RenderPlan):
    pairs = [(scene, shot) for scene in plan.timeline.scenes for shot in scene.shots]
    pairs.sort(key=lambda pair: (pair[1].start_tick, pair[0].scene_id, pair[1].shot_id))
    return [shot for _scene, shot in pairs]
