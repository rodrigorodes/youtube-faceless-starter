"""RP-027/RP-028/RP-029 — grafo de dependências e invalidação seletiva (domínio puro).

A prova central desta suíte é a **mutação**: alterar a cena A **não** pode invalidar os nós
da cena B, e vice-versa; sem alteração, o cache **acerta** (hit). Nada aqui toca FFmpeg,
banco ou mídia — o grafo é função pura do plano.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.contracts import Asset, AssetKind, VideoFormat  # noqa: E402
from app.studio.domain.render import split_chunks  # noqa: E402
from app.studio.domain.render_cache import (  # noqa: E402
    CachePolicy,
    DependencyGraph,
    NodeId,
    narration_fingerprint,
    plan_graph,
    selective_invalidation,
)
from app.studio.domain.render_plan import RenderPlan, StyleSnapshot, Transition  # noqa: E402
from app.studio.domain.render_plan_builder import (  # noqa: E402
    StoryboardOverlay,
    StoryboardScene,
    asset_reference_for,
    build_render_plan,
)

SHA_A = "a" * 64
SHA_B = "b" * 64

A_VISUAL = NodeId("visual", "shot:scene-01")
B_VISUAL = NodeId("visual", "shot:scene-02")
A_NARRATION = NodeId("narration", "scene-01")
B_NARRATION = NodeId("narration", "scene-02")
MUSIC = NodeId("music", "music")
CONCAT = NodeId("concat", "video")
FINAL = NodeId("final", "video")


def image_ref(asset_id="asset-01", sha=SHA_A, **overrides):
    reference = asset_reference_for(
        Asset(id=asset_id, kind=AssetKind.image, cache_key="c" * 64, path=f"img/{asset_id}.png",
              provider="p", model="m", license="Imagem gerada por IA"),
        content_sha256=sha, media_type="image",
    )
    return reference.model_copy(update=overrides) if overrides else reference


def two_scene_plan(*, revision=1, first_speech=2.0, second_speech=2.0,
                   first_text="Primeira cena do vídeo.", second_text="Segunda cena do vídeo.",
                   first_voice="", second_voice="",
                   first_sha=SHA_A, second_sha=SHA_B, **overrides):
    scenes = [
        StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration=first_text, speech_seconds=first_speech,
                        voice_id=first_voice),
        StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration=second_text, speech_seconds=second_speech,
                        voice_id=second_voice),
    ]
    data = dict(
        plan_id="plan:video-001",
        revision=revision,
        project_id="project-001",
        video_id="video-001",
        format=VideoFormat.short,
        scenes=scenes,
        assets=[image_ref("asset-01", first_sha), image_ref("asset-02", second_sha)],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=3),
    )
    data.update(overrides)
    return build_render_plan(**data)


# ------------------------------------------------------------------ forma do grafo


def test_graph_carries_logical_nodes_and_content_fingerprints():
    graph = plan_graph(two_scene_plan())
    assert isinstance(graph, DependencyGraph)
    nodes = {item.node for item in graph.nodes}
    assert {A_NARRATION, B_NARRATION, A_VISUAL, B_VISUAL, MUSIC, CONCAT, FINAL} <= nodes
    for item in graph.nodes:
        assert len(item.fingerprint) == 64 and all(c in "0123456789abcdef" for c in item.fingerprint)


def test_graph_is_deterministic_and_sorted_by_logical_id():
    first, second = plan_graph(two_scene_plan()), plan_graph(two_scene_plan())
    assert first == second
    assert [item.node for item in first.nodes] == sorted(item.node for item in first.nodes)


def test_node_identity_is_logical_while_the_fingerprint_is_physical():
    # a mesma cena lógica com outra narração mantém o NodeId e muda só o fingerprint
    base = plan_graph(two_scene_plan())
    edited = plan_graph(two_scene_plan(first_text="Outra narração, agora bem diferente."))
    assert base.fingerprint(A_VISUAL) != edited.fingerprint(A_VISUAL)
    assert base.fingerprint(A_NARRATION) != edited.fingerprint(A_NARRATION)
    assert A_VISUAL in edited.by_id()  # a identidade lógica não mudou


def test_label_fed_to_the_compiler_changes_the_visual_fingerprint():
    plain = plan_graph(two_scene_plan())
    badged = plan_graph(two_scene_plan(), labels={"scene-01": "DADOS"})
    assert plain.fingerprint(A_VISUAL) != badged.fingerprint(A_VISUAL)


# ---------------------------------------------- narração: fingerprint da ENTRADA (RP-06c)
#
# A duração da fala é **saída** do TTS; se ela entra no fingerprint, o acerto de cache da
# narração só é decidível **depois** de sintetizar (o gap da RP-06b). Aqui a narração é
# decidida pela **entrada**: texto + identidade da voz + parâmetros que mudam o áudio.


def test_narration_fingerprint_ignores_the_tts_duration_but_follows_the_text():
    base = plan_graph(two_scene_plan())
    stretched = plan_graph(two_scene_plan(revision=2, first_speech=4.0))  # mesma fala, só mais longa
    assert stretched.fingerprint(A_NARRATION) == base.fingerprint(A_NARRATION)
    assert stretched.fingerprint(B_NARRATION) == base.fingerprint(B_NARRATION)
    rewritten = plan_graph(two_scene_plan(revision=2, first_text="Outra narração, bem diferente da primeira."))
    assert rewritten.fingerprint(A_NARRATION) != base.fingerprint(A_NARRATION)
    assert rewritten.fingerprint(B_NARRATION) == base.fingerprint(B_NARRATION)


def test_changing_the_voice_invalidates_only_that_scene_narration():
    base = plan_graph(two_scene_plan())
    changed = plan_graph(two_scene_plan(revision=2, first_voice="piper:alice"))
    assert changed.fingerprint(A_NARRATION) != base.fingerprint(A_NARRATION)
    assert changed.fingerprint(B_NARRATION) == base.fingerprint(B_NARRATION)


def test_narration_fingerprint_helper_follows_text_and_voice_over_whitespace():
    assert narration_fingerprint("Olá, mundo.", "v1") != narration_fingerprint("Outro texto.", "v1")
    assert narration_fingerprint("Olá, mundo.", "v1") != narration_fingerprint("Olá, mundo.", "v2")
    assert narration_fingerprint("Olá,  mundo.", "v1") == narration_fingerprint("Olá, mundo.", "v1")
    assert narration_fingerprint("Olá, mundo.", "v1", {"model": "a"}) != narration_fingerprint("Olá, mundo.", "v1", {"model": "b"})


def test_plan_graph_uses_the_same_input_fingerprint_the_run_render_consults():
    # o grafo (com plano) e o RunRender (sem plano, só texto/voz) têm de concordar na entrada
    plan = two_scene_plan(first_voice="piper:alice")
    expected = narration_fingerprint(
        " ".join(split_chunks("Primeira cena do vídeo.")), "voice:scene-01", {"voice": "piper:alice"})
    assert plan_graph(plan).fingerprint(A_NARRATION) == expected



def test_asset_content_hash_change_invalidates_only_that_visual():
    base = plan_graph(two_scene_plan())
    swapped = plan_graph(two_scene_plan(first_sha="c" * 64))
    assert base.fingerprint(A_VISUAL) != swapped.fingerprint(A_VISUAL)
    assert base.fingerprint(B_VISUAL) == swapped.fingerprint(B_VISUAL)


# ------------------------------------------------------------------ invalidação seletiva


def test_first_revision_invalidates_everything_and_hits_nothing():
    graph = plan_graph(two_scene_plan())
    result = selective_invalidation(None, graph)
    assert result.invalidated == frozenset(item.node for item in graph.nodes)
    assert result.reusable == frozenset()
    assert FINAL in result.invalidated


def test_nothing_changed_is_a_full_cache_hit():
    graph = plan_graph(two_scene_plan())
    result = selective_invalidation(graph, plan_graph(two_scene_plan()))
    assert result.invalidated == frozenset()
    assert result.reusable == frozenset(item.node for item in graph.nodes)
    assert result.cache_hits == result.reusable


def test_changing_scene_a_reuses_scene_b_narration_and_visual():
    previous = plan_graph(two_scene_plan())
    current = plan_graph(two_scene_plan(revision=2, first_text="Narração completamente reescrita da cena um."))
    result = selective_invalidation(previous, current)
    assert A_NARRATION in result.invalidated and A_VISUAL in result.invalidated
    assert B_NARRATION in result.reusable and B_VISUAL in result.reusable
    assert B_NARRATION not in result.invalidated and B_VISUAL not in result.invalidated


def test_changing_scene_b_reuses_scene_a_narration_and_visual():
    previous = plan_graph(two_scene_plan())
    current = plan_graph(two_scene_plan(revision=2, second_text="Narração completamente reescrita da cena dois."))
    result = selective_invalidation(previous, current)
    assert B_NARRATION in result.invalidated and B_VISUAL in result.invalidated
    assert A_NARRATION in result.reusable and A_VISUAL in result.reusable


def test_absolute_timeline_position_never_invalidates_a_downstream_scene():
    # esticar a cena A desloca a cena B no tempo; o segmento de B é o mesmo (só muda de posição)
    previous = plan_graph(two_scene_plan())
    stretched = plan_graph(two_scene_plan(revision=2, first_speech=4.0))
    assert stretched.fingerprint(A_VISUAL) != previous.fingerprint(A_VISUAL)
    assert stretched.fingerprint(B_VISUAL) == previous.fingerprint(B_VISUAL)
    result = selective_invalidation(previous, stretched)
    assert B_VISUAL in result.reusable and B_NARRATION in result.reusable
    assert A_VISUAL in result.invalidated


def test_final_composition_is_invalidated_when_any_scene_changes():
    previous = plan_graph(two_scene_plan())
    current = plan_graph(two_scene_plan(revision=2, second_text="Outro texto para a cena dois."))
    result = selective_invalidation(previous, current)
    assert CONCAT in result.invalidated and FINAL in result.invalidated
    assert result.cache_hits == result.reusable


def test_dependency_propagates_even_when_the_aggregate_fingerprint_is_unchanged():
    # troca o byte-hash do asset A mantendo a duração: o fingerprint do concat não muda,
    # mas ele depende do segmento de A, então tem de ser invalidado por propagação
    previous = plan_graph(two_scene_plan())
    current = plan_graph(two_scene_plan(revision=2, first_sha="c" * 64))
    assert current.fingerprint(CONCAT) == previous.fingerprint(CONCAT)
    result = selective_invalidation(previous, current)
    assert A_VISUAL in result.invalidated
    assert CONCAT in result.invalidated and FINAL in result.invalidated


def test_policy_can_disable_reuse_for_a_kind():
    graph = plan_graph(two_scene_plan())
    no_cache = CachePolicy(reusable_kinds=frozenset({"music"}))
    result = selective_invalidation(graph, plan_graph(two_scene_plan()), policy=no_cache)
    assert A_VISUAL in result.invalidated and B_VISUAL in result.invalidated
    assert A_NARRATION in result.invalidated and B_NARRATION in result.invalidated
    # music continua reusável quando o conteúdo não muda
    assert MUSIC in result.reusable


def test_added_and_removed_nodes_are_reported():
    previous = plan_graph(two_scene_plan())
    current = plan_graph(
        build_render_plan(
            plan_id="plan:video-001", revision=2, project_id="project-001", video_id="video-001",
            format=VideoFormat.short,
            scenes=[StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration="Segunda cena do vídeo.", speech_seconds=2.0)],
            assets=[image_ref("asset-02", SHA_B)],
            style_snapshot=StyleSnapshot(style_id="channel-001", version=3),
        )
    )
    result = selective_invalidation(previous, current)
    assert A_NARRATION in result.removed and A_VISUAL in result.removed
    assert B_VISUAL not in result.removed
    assert B_VISUAL not in result.invalidated  # a cena que sobrou continua reusável


def test_custom_policy_is_supported_by_construction():
    assert CachePolicy().reusable("final") is True
    assert CachePolicy(reusable_kinds=frozenset()).reusable("final") is False


def test_plan_graph_rejects_a_non_plan():
    with pytest.raises(TypeError):
        plan_graph("not a plan")


# ------------------------------------------- VE-01: overlay dentro do segmento base
#
# O overlay não tem segmento físico: só o shot base vira nó ``visual``. O conteúdo do
# overlay entra no fingerprint do base que o hospeda — adicionar, remover, trocar asset,
# mudar a janela ou o ``z_index`` invalida só aquela cena; reordenar a entrada não muda nada.

SHA_OVERLAY = "c" * 64
SHA_OVERLAY_2 = "d" * 64


def overlay_plan(*, revision=1, overlays=None):
    """Duas cenas base; a cena 1 hospeda o(s) overlay(s) informado(s)."""
    items = overlays if overlays is not None else [
        StoryboardOverlay(scene_id="scene-01", asset_id="asset-overlay", start_s=0.1, duration_s=0.2)
    ]
    return build_render_plan(
        plan_id="plan:video-001",
        revision=revision,
        project_id="project-001",
        video_id="video-001",
        format=VideoFormat.short,
        scenes=[
            StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration="Primeira cena do vídeo.",
                            speech_seconds=2.0),
            StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration="Segunda cena do vídeo.",
                            speech_seconds=2.0),
        ],
        assets=[
            image_ref("asset-01", SHA_A),
            image_ref("asset-02", SHA_B),
            image_ref("asset-overlay", SHA_OVERLAY),
            image_ref("asset-overlay-2", SHA_OVERLAY_2),
        ],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=1),
        overlays=items,
    )


def test_overlay_does_not_create_a_visual_cache_node():
    graph = plan_graph(overlay_plan())
    visual_keys = {node.node.key for node in graph.nodes if node.node.kind == "visual"}
    assert visual_keys == {"shot:scene-01", "shot:scene-02"}
    assert not any(key.startswith("overlay:") for key in visual_keys)


def test_base_visual_fingerprint_tracks_the_hosted_overlay():
    without = plan_graph(two_scene_plan())
    with_overlay = plan_graph(overlay_plan())
    assert without.fingerprint(A_VISUAL) != with_overlay.fingerprint(A_VISUAL)
    # a cena que não hospeda o overlay continua idêntica
    assert without.fingerprint(B_VISUAL) == with_overlay.fingerprint(B_VISUAL)


def test_overlay_asset_window_and_z_index_change_only_the_hosting_base():
    base = plan_graph(overlay_plan())
    variants = [
        overlay_plan(overlays=[StoryboardOverlay(
            scene_id="scene-01", asset_id="asset-overlay-2", start_s=0.1, duration_s=0.2)]),
        overlay_plan(overlays=[StoryboardOverlay(
            scene_id="scene-01", asset_id="asset-overlay", start_s=0.3, duration_s=0.2)]),
        overlay_plan(overlays=[StoryboardOverlay(
            scene_id="scene-01", asset_id="asset-overlay", start_s=0.1, duration_s=0.2, z_index=2)]),
    ]
    for variant in variants:
        graph = plan_graph(variant)
        assert base.fingerprint(A_VISUAL) != graph.fingerprint(A_VISUAL)
        assert base.fingerprint(B_VISUAL) == graph.fingerprint(B_VISUAL)


def test_reordering_the_overlay_input_keeps_the_fingerprint():
    first = StoryboardOverlay(scene_id="scene-01", asset_id="asset-overlay", start_s=0.1, duration_s=0.2)
    second = StoryboardOverlay(scene_id="scene-01", asset_id="asset-overlay-2", start_s=0.5, duration_s=0.2,
                               z_index=2)
    forward = plan_graph(overlay_plan(overlays=[first, second]))
    backward = plan_graph(overlay_plan(overlays=[second, first]))
    assert forward == backward


# ------------------------------------------- W3.2: a transição do plano invalida o segmento
#
# `Shot.transition` entra no fingerprint do nó ``visual``: mudar o fade do segmento re-renderiza
# só aquela cena (a outra continua reusável) — sem isso o cache devolveria um vídeo com o fade
# antigo e a transição "consumida" pelo compilador não valeria no reúso.


def plan_with_transition(*, scene_id="scene-01", kind="fade", duration_ticks=40):
    plan = two_scene_plan()
    transition = Transition(kind=kind, duration_ticks=duration_ticks)
    scenes = []
    for scene in plan.timeline.scenes:
        if scene.scene_id == scene_id:
            shots = [scene.shots[0].model_copy(update={"transition": transition})] + list(scene.shots[1:])
            scene = scene.model_copy(update={"shots": shots})
        scenes.append(scene)
    return plan.model_copy(update={"timeline": plan.timeline.model_copy(update={"scenes": scenes})})


def test_transition_change_invalidates_only_its_scene_visual():
    base = plan_graph(two_scene_plan())
    with_fade = plan_graph(plan_with_transition())
    assert base.fingerprint(A_VISUAL) != with_fade.fingerprint(A_VISUAL)
    assert base.fingerprint(B_VISUAL) == with_fade.fingerprint(B_VISUAL)
    result = selective_invalidation(base, with_fade)
    assert A_VISUAL in result.invalidated
    assert B_VISUAL in result.reusable and B_NARRATION in result.reusable
    assert CONCAT in result.invalidated and FINAL in result.invalidated


def test_transition_duration_change_invalidates_the_scene_visual():
    with_fade = plan_graph(plan_with_transition(duration_ticks=40))
    longer = plan_graph(plan_with_transition(duration_ticks=80))
    assert with_fade.fingerprint(A_VISUAL) != longer.fingerprint(A_VISUAL)
    assert with_fade.fingerprint(B_VISUAL) == longer.fingerprint(B_VISUAL)



# ------------------------------------------- W4.4: troca de mídia por cena (EDIT-03/VE-06)


def test_swapping_one_scene_media_invalidates_only_that_scene_and_the_final():
    """Trocar o asset de UMA cena invalida só a cena trocada e os agregadores (concat/final)."""
    current = plan_graph(build_render_plan(
        plan_id="plan:video-001", revision=2, project_id="project-001", video_id="video-001",
        format=VideoFormat.short,
        scenes=[
            StoryboardScene(scene_id="scene-01", asset_id="asset-03", narration="Primeira cena do vídeo.",
                            speech_seconds=2.0),
            StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration="Segunda cena do vídeo.",
                            speech_seconds=2.0),
        ],
        assets=[image_ref("asset-03", "e" * 64), image_ref("asset-02", SHA_B)],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=3),
    ))
    result = selective_invalidation(plan_graph(two_scene_plan()), current)
    assert result.invalidated == frozenset({A_VISUAL, CONCAT, FINAL})
    assert B_VISUAL in result.reusable and B_NARRATION in result.reusable and A_NARRATION in result.reusable
    assert current.fingerprint(A_VISUAL) != plan_graph(two_scene_plan()).fingerprint(A_VISUAL)
    assert current.fingerprint(B_VISUAL) == plan_graph(two_scene_plan()).fingerprint(B_VISUAL)
