"""RP-027/RP-029 — persistência versionada do Render Plan e índice de cache (Postgres).

Roda só com o banco descartável (`STUDIO_TEST_DSN`/`STUDIO_BUDGET_DISPOSABLE_DSN` + prova).
Prova que a identidade **lógica** (plano/revisão/nó) e a **física** (hash/codec/localização)
são persistidas separadamente e que o ciclo de regeneração seletiva funciona ponta a ponta.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.render_plan_repo import PostgresRenderPlanRepository  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.application.render_cache import PlanRegeneration  # noqa: E402
from app.studio.domain.contracts import Asset, AssetKind, VideoFormat  # noqa: E402
from app.studio.domain.render_cache import CacheEntry, NodeId, PlanArtifact, plan_graph  # noqa: E402
from app.studio.domain.render_plan import StyleSnapshot  # noqa: E402
from app.studio.domain.render_plan_builder import (  # noqa: E402
    StoryboardScene,
    asset_reference_for,
    build_render_plan,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
A_VISUAL = NodeId("visual", "shot:scene-01")
B_VISUAL = NodeId("visual", "shot:scene-02")


def image_ref(asset_id, sha, uri):
    return asset_reference_for(
        Asset(id=asset_id, kind=AssetKind.image, cache_key="c" * 64, path=uri,
              provider="p", model="m", license="Imagem gerada por IA"),
        content_sha256=sha, media_type="image",
    )


def plan_for(video_id, *, revision=1, first_text="Primeira cena do vídeo.", second_text="Segunda cena do vídeo."):
    return build_render_plan(
        plan_id=f"plan:{video_id}", revision=revision, project_id="project-001", video_id=video_id,
        format=VideoFormat.short,
        scenes=[
            StoryboardScene(scene_id="scene-01", asset_id="asset-01", narration=first_text, speech_seconds=2.0),
            StoryboardScene(scene_id="scene-02", asset_id="asset-02", narration=second_text, speech_seconds=2.0),
        ],
        assets=[image_ref("asset-01", SHA_A, "img/asset-01.png"), image_ref("asset-02", SHA_B, "img/asset-02.png")],
        style_snapshot=StyleSnapshot(style_id="channel-001", version=3),
    )


def produced(plan):
    return {
        item.node: CacheEntry(plan_id=plan.plan_id, node=item.node, fingerprint=item.fingerprint,
                              artifact_sha256="d" * 64, artifact_uri=f"work/{item.node.kind}/{item.node.key}",
                              revision=plan.revision)
        for item in plan_graph(plan).nodes
    }


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("canal").id, "ADE 2026", VideoFormat.short)
    return {"plans": PostgresRenderPlanRepository(connect), "video": video, "conn": conn}


def test_save_and_load_a_plan_by_revision(env):
    plans, video = env["plans"], env["video"]
    plan = plan_for(video.id)
    plans.save_plan(plan)
    assert plans.get_plan(plan.plan_id, 1) == plan
    assert plans.latest_plan(plan.plan_id) == plan
    assert plans.revisions(plan.plan_id) == [1]
    assert plans.get_plan(plan.plan_id, 99) is None
    assert plans.latest_plan("plan:desconhecido") is None


def test_revisions_accumulate_and_latest_is_the_highest(env):
    plans, video = env["plans"], env["video"]
    first = plan_for(video.id)
    plans.save_plan(first)
    second = plan_for(video.id, revision=2, first_text="Segunda versão da primeira cena.")
    plans.save_plan(second)
    assert plans.revisions(first.plan_id) == [1, 2]
    assert plans.latest_plan(first.plan_id) == second


def test_saving_the_same_revision_is_idempotent(env):
    plans, video = env["plans"], env["video"]
    plan = plan_for(video.id)
    plans.save_plan(plan)
    plans.save_plan(plan)
    assert plans.revisions(plan.plan_id) == [1]
    assert env["conn"].execute("SELECT count(*) FROM studio.render_plans").fetchone()[0] == 1


def test_physical_artifact_registry_is_separate_from_the_logical_node(env):
    plans, video = env["plans"], env["video"]
    plans.save_plan(plan_for(video.id))
    artifact = plans.artifact(SHA_A, "img/asset-01.png")
    assert artifact is not None and artifact.media_type == "image" and artifact.content_sha256 == SHA_A
    assert plans.artifact(SHA_A, "outro/caminho.png") is None  # localização faz parte da identidade física
    # o mesmo conteúdo em duas localizações são dois artefatos físicos
    assert plans.artifact(SHA_A, "img/asset-01.png") == artifact


def test_entries_returns_the_most_recent_artifact_per_node(env):
    plans, video = env["plans"], env["video"]
    plan1 = plan_for(video.id)
    plans.save_plan(plan1)
    plans.record_entry(CacheEntry(plan_id=plan1.plan_id, node=A_VISUAL, fingerprint="1" * 64,
                                  artifact_sha256="a" * 64, artifact_uri="work/old", revision=1))
    plan2 = plan_for(video.id, revision=2, first_text="Nova narração para a primeira cena.")
    plans.save_plan(plan2)
    plans.record_entry(CacheEntry(plan_id=plan2.plan_id, node=A_VISUAL, fingerprint="2" * 64,
                                  artifact_sha256="b" * 64, artifact_uri="work/new", revision=2))
    entries = plans.entries(plan1.plan_id)
    assert entries[A_VISUAL].fingerprint == "2" * 64 and entries[A_VISUAL].artifact_uri == "work/new"


def test_cache_entry_requires_a_persisted_revision(env):
    plans, video = env["plans"], env["video"]
    plan = plan_for(video.id)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        plans.record_entry(CacheEntry(plan_id=plan.plan_id, node=A_VISUAL, fingerprint="1" * 64,
                                      artifact_sha256="a" * 64, artifact_uri="work/x", revision=1))
    env["conn"].rollback()


def test_full_regeneration_cycle_against_the_repository(env):
    plans, video = env["plans"], env["video"]
    regeneration = PlanRegeneration(plans)
    first = plan_for(video.id)
    regeneration.commit(first, produced(first))

    identical = regeneration.decide(plan_for(video.id, revision=2))
    assert identical.previous_revision == 1
    assert identical.invalidated == () and A_VISUAL in identical.cache_hits

    changed = regeneration.decide(plan_for(video.id, revision=2, first_text="Primeira cena reescrita por completo."))
    assert A_VISUAL in changed.invalidated
    assert B_VISUAL in changed.cache_hits
    assert changed.final_recompose is True


def test_batch_registration_writes_entries_and_artifacts_idempotently(env):
    """RP-06b: o executor registra a revisão inteira numa transação só (índice lógico + físico)."""
    plans, video = env["plans"], env["video"]
    plan = plan_for(video.id)
    plans.save_plan(plan)
    entries = [
        CacheEntry(plan_id=plan.plan_id, node=A_VISUAL, fingerprint="1" * 64,
                   artifact_sha256="a" * 64, artifact_uri="work/scene_000.mp4", revision=1),
        CacheEntry(plan_id=plan.plan_id, node=B_VISUAL, fingerprint="2" * 64,
                   artifact_sha256="b" * 64, artifact_uri="work/scene_001.mp4", revision=1),
    ]
    plans.record_entries(entries)
    stored = plans.entries(plan.plan_id)
    assert stored[A_VISUAL].artifact_uri == "work/scene_000.mp4" and stored[B_VISUAL].artifact_sha256 == "b" * 64

    artifacts = [PlanArtifact(content_sha256="c" * 64, location="work/scene_000.mp4", codec="h264",
                              media_type="video", byte_size=123)]
    plans.record_artifacts(artifacts)
    assert plans.artifact("c" * 64, "work/scene_000.mp4").codec == "h264"
    plans.record_artifacts(artifacts), plans.record_entries(entries)  # repetir é idempotente
    assert env["conn"].execute("SELECT count(*) FROM studio.plan_artifacts WHERE content_sha256 = %s",
                               ("c" * 64,)).fetchone()[0] == 1


def test_executor_reuses_the_unchanged_scene_against_the_real_repository(env, tmp_path):
    """O reúso roda contra o Postgres real (documento JSONB → grafo), não só contra o fake."""
    import math
    import struct
    import wave
    from PIL import Image

    from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
    from app.studio.application.ports import RenderSpec
    from app.studio.domain.contracts import Scene
    from app.studio.domain.render import SIZE, make_cues, scene_length

    video = env["video"]

    def tone(path, seconds=1.2, rate=22050):
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
            n = int(seconds * rate)
            w.writeframes(b"".join(struct.pack("<h", int(32767 * 0.4 * math.sin(2 * math.pi * 220 * i / rate))) for i in range(n)))

    def spec_for(texts):
        scenes, images, wavs, lengths, cues, offset = [], [], [], [], [], 0.0
        for idx, text in enumerate(texts):
            asset_id = f"{idx + 1:032x}"
            image = tmp_path / f"img{idx}.png"
            Image.new("RGB", SIZE[VideoFormat.short], (20 + 30 * idx, 80, 160)).save(image)
            wav = tmp_path / f"s{idx}.wav"
            tone(wav)
            length = scene_length(1.2)
            scenes.append(Scene(id=asset_id, video_id=video.id, idx=idx, narration=text, label="QUA", caption="x",
                                image_prompt="prompt de imagem válido", claim_ids=["c"], asset_id=asset_id))
            images.append(image), wavs.append(wav), lengths.append(length)
            cues += make_cues(text, offset, 1.2)
            offset += length
        return RenderSpec(scenes=scenes, images=images, speech_wavs=wavs, scene_seconds=lengths, cues=cues,
                          format=VideoFormat.short, music=True, work_dir=tmp_path / "work")

    class StubRunner:
        def __init__(self):
            self.calls = []

        def __call__(self, cmd, timeout=600):
            self.calls.append(list(cmd))
            from pathlib import Path
            Path(cmd[-1]).write_bytes(b"stub")

    (tmp_path / "work").mkdir(exist_ok=True)
    runner = StubRunner()
    renderer = PlanFfmpegRenderer(runner=runner, plans=env["plans"], cache_root=tmp_path / "cache")
    renderer.render(spec_for(("Primeira cena do vídeo.", "Segunda cena do vídeo.")), tmp_path / "work" / "final.mp4")
    assert len(runner.calls) == 4

    runner.calls.clear()
    renderer.render(spec_for(("Primeira cena reescrita por completo.", "Segunda cena do vídeo.")), tmp_path / "work" / "final.mp4")
    outputs = [call[-1] for call in runner.calls]
    assert len(runner.calls) == 3 and str(tmp_path / "work" / "scene_001.mp4") not in outputs


def test_constraints_reject_bad_nodes_and_documents(env):
    plans, video = env["plans"], env["video"]
    plan = plan_for(video.id)
    plans.save_plan(plan)

    def insert(kind, fingerprint="a" * 64):
        env["conn"].execute(
            "INSERT INTO studio.render_cache_entries(plan_id, revision, node_kind, node_key, fingerprint, "
            "artifact_sha256, artifact_uri) VALUES (%s, 1, %s, 'x', %s, %s, 'uri')",
            (plan.plan_id, kind, fingerprint, "a" * 64))

    with pytest.raises(psycopg.errors.CheckViolation):
        insert("narração")  # kind fora da whitelist
    env["conn"].rollback()
    plans.save_plan(plan)
    with pytest.raises(psycopg.errors.CheckViolation):
        insert("visual", fingerprint="nao-hex")  # fingerprint tem de ser sha256 hex
    env["conn"].rollback()
    plans.save_plan(plan)
    with pytest.raises(psycopg.errors.CheckViolation):
        env["conn"].execute(
            "INSERT INTO studio.render_plans(plan_id, revision, project_id, video_id, document) "
            "VALUES ('plan:x', 0, 'p', %s, '{}')", (video.id,))  # revisão tem de ser >= 1
