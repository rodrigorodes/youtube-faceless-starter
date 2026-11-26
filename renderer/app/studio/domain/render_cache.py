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

from .render_plan import AudioMix, GeneratedAudioSource, RenderPlan, Shot

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


def visual_fingerprint(
    shot: Shot,
    asset_digest: str,
    style_digest: str | None = None,
    *,
    media_type: str = "",
    relative_start_tick: int = 0,
    badge: str = "",
    disclosure: bool = False,
    captions: tuple = (),
    hosted: tuple = (),
) -> str:
    """Fingerprint físico do segmento visual do shot (RP-028/VE-Onda1).

    Combina o conteúdo do asset, movimento, enquadramento, transição (tipo e duração),
    offset temporal do asset (corte no clipe/imagem), duração, posição relativa à cena,
    badges, disclosure, legendas relativas e overlays hospedados.
    Se fornecido, ``style_digest`` invalida o nó quando estilos visuais (cor, fonte) mudam.
    """
    transition_kind = shot.transition.kind if shot.transition is not None else None
    transition_duration = shot.transition.duration_ticks if shot.transition is not None else 0
    comp = shot.composition
    comp_repr = None
    if comp is not None:
        if (getattr(comp, "opacity", 1.0) == 1.0 and
            getattr(comp, "scale", 1.0) == 1.0 and
            getattr(comp, "position_x", 0.5) == 0.5 and
            getattr(comp, "position_y", 0.5) == 0.5):
            comp_repr = comp.fit
        else:
            comp_repr = (comp.fit, comp.opacity, comp.scale, comp.position_x, comp.position_y)

    return _fingerprint(
        "visual",
        shot.asset_ref,
        asset_digest,
        media_type,
        shot.effects.motion,
        comp_repr,
        transition_kind,
        transition_duration,
        shot.asset_offset_ticks,
        shot.duration_ticks,
        relative_start_tick,
        badge,
        disclosure,
        captions,
        hosted,
        style_digest,
    )


def music_fingerprint(
    source: GeneratedAudioSource,
    audio_mix: AudioMix | None = None,
) -> str:
    """Fingerprint físico da trilha musical (RP-028/VE-Onda1).

    Combina os parâmetros determinísticos da síntese/fonte e os parâmetros declarativos
    de mixagem (ganho, ducking, fades, loudnorm) se fornecidos.
    """
    mix_params: tuple | None = None
    if audio_mix is not None:
        if hasattr(audio_mix, "model_dump"):
            mix_params = tuple(sorted(audio_mix.model_dump().items()))
        elif isinstance(audio_mix, Mapping):
            mix_params = tuple(sorted(audio_mix.items()))
        else:
            mix_params = tuple(sorted(vars(audio_mix).items()))
    return _fingerprint(
        "music",
        source.source_id,
        source.silent,
        sorted(source.params.items()),
        source.duration_ticks,
        mix_params,
    )


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

    @classmethod
    def build(
        cls,
        plan: RenderPlan,
        *,
        labels: Mapping[str, str] | None = None,
        style_digest: str | Mapping[str, str] | None = None,
    ) -> DependencyGraph:
        """Constrói o grafo determinístico a partir de um RenderPlan."""
        return plan_graph(plan, labels=labels, style_digest=style_digest)


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


def plan_graph(
    plan: RenderPlan,
    *,
    labels: Mapping[str, str] | None = None,
    style_digest: str | Mapping[str, str] | None = None,
) -> DependencyGraph:
    """Constrói o grafo de dependências de uma revisão do ``RenderPlan``.

    ``labels`` é o selo editorial por cena — a mesma apresentação que o compilador recebe
    (``compile_render_plan(..., labels=...)``) e que **não** faz parte do contrato do plano;
    entra como parâmetro para o fingerprint do segmento visual não ignorar o selo.
    ``style_digest`` permite invalidar os nós visuais quando o estilo visual (legendas/cores)
    muda entre revisões.
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
            if shot.role != "base":
                # VE-01: o overlay não tem segmento físico; só a base vira nó ``visual``.
                continue
            reference = manifest.get(shot.asset_ref)
            content_sha256 = reference.content_sha256 if reference is not None else ""
            media_type = reference.media_type if reference is not None else ""
            # Legendas deste shot, com janela **relativa** ao shot (é o que o compilador queima).
            captions = tuple(
                (cue.text, cue.start_tick - shot.start_tick, cue.duration_ticks)
                for cue in sorted(subtitles_by_scene.get(scene.scene_id, []), key=lambda c: (c.start_tick, c.text))
                if shot.start_tick <= cue.start_tick < shot.start_tick + shot.duration_ticks
            )
            hosted = _hosted_overlays(scene, shot, manifest)
            visual_id = NodeId("visual", shot.shot_id)
            current_style_digest = (
                style_digest.get(shot.shot_id, style_digest.get(scene.scene_id))
                if isinstance(style_digest, Mapping)
                else style_digest
            )
            nodes.append(
                CacheNode(
                    node=visual_id,
                    fingerprint=visual_fingerprint(
                        shot,
                        asset_digest=content_sha256,
                        style_digest=current_style_digest,
                        media_type=media_type,
                        relative_start_tick=shot.start_tick - scene.start_tick,  # relativo à cena, não à timeline
                        badge=badges.get(scene.scene_id, ""),
                        disclosure=disclosure,
                        captions=captions,
                        hosted=hosted,
                    ),
                )
            )

    music_ids: list[NodeId] = []
    audio_mix = getattr(plan, "audio_mix", None)
    for source in sorted(plan.generated_audio, key=lambda s: (s.kind, s.source_id)):
        if source.kind != "music":
            continue
        music_id = NodeId("music", source.source_id)
        nodes.append(
            CacheNode(
                node=music_id,
                fingerprint=music_fingerprint(source, audio_mix=audio_mix),
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
    pairs = [(scene, shot) for scene in plan.timeline.scenes for shot in scene.shots if shot.role == "base"]
    pairs.sort(key=lambda pair: (pair[1].start_tick, pair[0].scene_id, pair[1].shot_id))
    return [shot for _scene, shot in pairs]


def _hosted_overlays(scene, base, manifest: Mapping[str, object]) -> tuple:
    """Overlays hospedados pelo segmento base, na ordem do contrato (§3.4).

    O conteúdo entra no fingerprint do base: adicionar, remover, trocar asset, mudar a
    janela relativa ou o ``z_index`` invalida só aquela cena (VE-01 §5).
    """
    hosted = [overlay for overlay in scene.overlay_shots if scene.host_base_for(overlay) is base]
    hosted.sort(key=lambda overlay: (overlay.z_index, overlay.start_tick, overlay.shot_id))
    entries: list[tuple] = []
    for overlay in hosted:
        reference = manifest.get(overlay.asset_ref)
        entries.append((
            overlay.asset_ref,
            reference.content_sha256 if reference is not None else "",
            reference.media_type if reference is not None else "",
            overlay.z_index,
            overlay.start_tick - base.start_tick,
            overlay.duration_ticks,
            overlay.composition.fit if overlay.composition is not None else None,
        ))
    return tuple(entries)
