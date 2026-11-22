"""RP-029 — política de cache e decisão de regeneração (application pura, sem banco).

Usa um repositório **em memória** para provar o ciclo completo: registrar uma revisão,
decidir a próxima, e ver os acertos de cache. A persistência real é testada em
``tests/test_render_plan_repo.py``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.render_cache import PlanRegeneration  # noqa: E402
from app.studio.domain.contracts import Asset, AssetKind, VideoFormat  # noqa: E402
from app.studio.domain.render_cache import (  # noqa: E402
    CacheEntry,
    CachePolicy,
    NodeId,
    PlanArtifact,
    plan_graph,
)
from app.studio.domain.render_plan import StyleSnapshot  # noqa: E402
from app.studio.domain.render_plan_builder import (  # noqa: E402
    StoryboardScene,
    asset_reference_for,
    build_render_plan,
)

A_VISUAL = NodeId("visual", "shot:scene-01")
B_VISUAL = NodeId("visual", "shot:scene-02")
A_NARRATION = NodeId("narration", "scene-01")
FINAL = NodeId("final", "video")
SHA_A = "a" * 64
SHA_B = "b" * 64


class FakePlanRepository:
    """Repositório em memória: a mesma superfície do Postgres, sem I/O."""

    def __init__(self):
        self.documents: dict[tuple[str, int], object] = {}
        self._entries: dict[str, dict[NodeId, CacheEntry]] = {}
        self.artifacts: dict[tuple[str, str], PlanArtifact] = {}

    def save_plan(self, plan):
        for reference in plan.asset_manifest:
            self.artifacts.setdefault(
                (reference.content_sha256, reference.uri),
                PlanArtifact(reference.content_sha256, reference.uri, media_type=reference.media_type))
        self.documents[(plan.plan_id, plan.revision)] = plan

    def get_plan(self, plan_id, revision):
        return self.documents.get((plan_id, revision))

    def latest_plan(self, plan_id):
        revisions = self.revisions(plan_id)
        return self.documents[(plan_id, revisions[-1])] if revisions else None

    def revisions(self, plan_id):
        return sorted(revision for (pid, revision) in self.documents if pid == plan_id)

    def record_entry(self, entry):
        self._entries.setdefault(entry.plan_id, {})[entry.node] = entry

    def entries(self, plan_id):
        return dict(self._entries.get(plan_id, {}))

    def artifact(self, content_sha256, location):
        return self.artifacts.get((content_sha256, location))


def image_ref(asset_id="asset-01", sha=SHA_A):
    return asset_reference_for(
        Asset(id=asset_id, kind=AssetKind.image, cache_key="c" * 64, path=f"img/{asset_id}.png",
              provider="p", model="m", license="Imagem gerada por IA"),
        content_sha256=sha, media_type="image",
    )


def two_scene_plan(*, revision=1, first_text="Primeira cena do vídeo.", second_text="Segunda cena do vídeo."):
    return build_render_plan(
        plan_id="plan:video-001", revision=revision, project_id="project-001", video_id="video-001",
        format=VideoFormat.short,
        scenes=[
            StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration=first_text, speech_seconds=2.0),
            StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration=second_text, speech_seconds=2.0),
        ],
        assets=[image_ref("asset-01", SHA_A), image_ref("asset-02", SHA_B)],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=3),
    )


def produced(plan):
    """Simula o resultado de um render: um artefato por nó do grafo do plano."""
    return {
        item.node: CacheEntry(plan_id=plan.plan_id, node=item.node, fingerprint=item.fingerprint,
                              artifact_sha256="d" * 64, artifact_uri=f"work/{item.node.kind}/{item.node.key}",
                              revision=plan.revision)
        for item in plan_graph(plan).nodes
    }


def test_first_revision_has_no_previous_and_invalidates_everything():
    decision = PlanRegeneration(FakePlanRepository()).decide(two_scene_plan())
    assert decision.previous_revision is None
    assert decision.cache_hits == ()
    assert A_VISUAL in decision.invalidated and B_VISUAL in decision.invalidated
    assert decision.final_recompose is True


def test_commit_then_identical_revision_is_a_full_cache_hit():
    repo = FakePlanRepository()
    regeneration = PlanRegeneration(repo)
    first = regeneration.commit(two_scene_plan(), produced(two_scene_plan()))
    assert first.previous_revision is None
    assert repo.revisions("plan:video-001") == [1]

    second = regeneration.decide(two_scene_plan(revision=2))
    assert second.previous_revision == 1
    assert second.invalidated == ()
    assert A_VISUAL in second.cache_hits and B_VISUAL in second.cache_hits
    assert second.final_recompose is False
    assert second.to_generate == ()


def test_changing_scene_a_reuses_scene_b_from_the_cache():
    repo = FakePlanRepository()
    regeneration = PlanRegeneration(repo)
    regeneration.commit(two_scene_plan(), produced(two_scene_plan()))

    decision = regeneration.decide(two_scene_plan(revision=2, first_text="Narração da cena um totalmente reescrita."))
    assert A_VISUAL in decision.invalidated and A_NARRATION in decision.invalidated
    assert B_VISUAL in decision.cache_hits and NodeId("narration", "scene-02") in decision.cache_hits
    assert decision.final_recompose is True


def test_reusable_but_unrecorded_artifact_is_a_miss_not_a_hit():
    repo = FakePlanRepository()
    regeneration = PlanRegeneration(repo)
    regeneration.commit(two_scene_plan(), {})  # nada foi produzido/registrado
    decision = regeneration.decide(two_scene_plan(revision=2))
    assert decision.invalidated == ()  # o conteúdo não mudou
    assert decision.cache_hits == ()
    assert set(decision.missing) >= {A_VISUAL, B_VISUAL}
    assert set(decision.to_generate) >= {A_VISUAL, B_VISUAL}


def test_committing_again_records_the_current_revision_without_losing_the_cache():
    repo = FakePlanRepository()
    regeneration = PlanRegeneration(repo)
    regeneration.commit(two_scene_plan(), produced(two_scene_plan()))
    regeneration.commit(two_scene_plan(revision=2), produced(two_scene_plan(revision=2)))
    assert repo.revisions("plan:video-001") == [1, 2]
    decision = regeneration.decide(two_scene_plan(revision=3))
    assert A_VISUAL in decision.cache_hits and B_VISUAL in decision.cache_hits


def test_policy_configured_in_the_use_case_is_honored():
    repo = FakePlanRepository()
    regeneration = PlanRegeneration(repo, policy=CachePolicy(reusable_kinds=frozenset()))
    regeneration.commit(two_scene_plan(), produced(two_scene_plan()))
    decision = regeneration.decide(two_scene_plan(revision=2))
    assert decision.cache_hits == ()
    assert A_VISUAL in decision.invalidated


def test_deciding_on_an_already_committed_revision_compares_against_its_parent():
    repo = FakePlanRepository()
    regeneration = PlanRegeneration(repo)
    regeneration.commit(two_scene_plan(), produced(two_scene_plan()))
    regeneration.commit(two_scene_plan(revision=2), produced(two_scene_plan(revision=2)))
    # decidir a revisão 1 de novo não pode comparar consigo mesma (senão mentiria "tudo mudou")
    decision = regeneration.decide(two_scene_plan())
    assert decision.previous_revision is None
    assert FINAL in decision.invalidated


# --------------------------------------------------------------------------- F03.T03


def test_the_config_snapshot_does_not_change_cache_fingerprints():
    """Aditivo: a referência da configuração não é conteúdo de mídia nem muda o cache."""
    from app.studio.domain.render_plan import ConfigSnapshot

    snapshot = ConfigSnapshot(content_hash="c" * 64, schema_version=1,
                              provenance={"style": "channel"})
    plans = [
        build_render_plan(plan_id="plan-01", revision=1, project_id="project-01", video_id="video-01",
                          format=VideoFormat.short,
                          scenes=[StoryboardScene(scene_id="scene-01", asset_id="asset-01",
                                                  narration="Primeira cena.", speech_seconds=2.0)],
                          assets=[asset_reference_for(Asset(id="asset-01", kind=AssetKind.image, cache_key="k" * 64,
                                                            path="img/a.png", provider="placeholder", model="g",
                                                            license="CC0"), content_sha256=SHA_A)],
                          style_snapshot=StyleSnapshot(style_id="channel-01", version=3)),
        build_render_plan(plan_id="plan-01", revision=1, project_id="project-01", video_id="video-01",
                          format=VideoFormat.short,
                          scenes=[StoryboardScene(scene_id="scene-01", asset_id="asset-01",
                                                  narration="Primeira cena.", speech_seconds=2.0)],
                          assets=[asset_reference_for(Asset(id="asset-01", kind=AssetKind.image, cache_key="k" * 64,
                                                            path="img/a.png", provider="placeholder", model="g",
                                                            license="CC0"), content_sha256=SHA_A)],
                          style_snapshot=StyleSnapshot(style_id="channel-01", version=3),
                          config_snapshot=snapshot),
    ]
    first, second = (plan_graph(item) for item in plans)
    assert second == first
