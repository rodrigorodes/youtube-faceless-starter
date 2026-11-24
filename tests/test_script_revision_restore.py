"""W4.5 (EDIT-04): histórico recuperável de revisões de cena.

Restaurar uma revisão cria uma NOVA versão com o texto, a ordem e os vínculos de mídia da
revisão escolhida — nunca do estado atual. Asset ausente vira ``media_review_required`` e o
histórico não é apagado. Estes testes usam o Postgres descartável de ``tests/conftest.py``.
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.editorial_repo import (  # noqa: E402
    PostgresScriptRepository, PostgresSnapshotRepository,
)
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.application.errors import (  # noqa: E402
    ScriptEditIdempotencyConflict, ScriptRevisionUnavailable,
)
from app.studio.application.longform import RestoreScriptRevision  # noqa: E402
from app.studio.application.ports import SceneDraft  # noqa: E402
from app.studio.domain.claims import extract_claims  # noqa: E402
from app.studio.domain.contracts import VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.longform import Block, Chapter, ScriptPlan  # noqa: E402

H1, H2 = "a" * 64, "b" * 64
PLAN = ScriptPlan(words_per_minute=150, target_seconds=480, chapters=(
    Chapter(title="Abertura", block=Block.HOOK, scene_count=2, target_seconds=80),
    Chapter(title="Contexto", block=Block.CONTEXT, scene_count=3, target_seconds=120),
    Chapter(title="Desenvolvimento", block=Block.DEVELOPMENT, scene_count=5, target_seconds=200),
    Chapter(title="Fecho", block=Block.CTA, scene_count=2, target_seconds=80),
))
SOURCE = "O canal cresceu 42 por cento no ano passado e esse crescimento mudou o mercado inteiro."


def narration(marker: str) -> str:
    # ~102 palavras por cena: 12 cenas ficam dentro da tolerância de ±15% de 480 s a 150 wpm.
    return ("ha " * 100).strip() + f" cena {marker}."


def _drafts(count: int = 12, claim_id: str = "") -> list[SceneDraft]:
    return [SceneDraft(narration(chr(ord("a") + i)), "Legenda", "CEN",
                       f"wide empty stage with colored lights {i}", [claim_id] if claim_id else [])
            for i in range(count)]


def _assign_assets(env, scene_ids: list[str]) -> list[str]:
    """Cria um asset por cena e o vincula diretamente: o teste é do repositório de revisão."""
    asset_ids = []
    for i, scene_id in enumerate(scene_ids):
        asset_id = f"{i + 1:032x}"
        env["conn"].execute(
            "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) "
            "VALUES (%s, 'image', %s, %s, 'p', 'm', 'CC0')",
            (asset_id, f"{i + 1:064x}", f"cache/{i}.png"),
        )
        env["conn"].execute("UPDATE studio.scenes SET asset_id = %s WHERE id = %s", (asset_id, scene_id))
        asset_ids.append(asset_id)
    env["conn"].commit()
    return asset_ids


def _flags(env, video_id: str) -> list[tuple[str, bool]]:
    env["conn"].commit()
    return env["conn"].execute(
        "SELECT id, media_review_required FROM studio.scenes WHERE video_id = %s ORDER BY idx", (video_id,)
    ).fetchall()


def _version_count(env, video_id: str) -> int:
    env["conn"].commit()
    return env["conn"].execute(
        "SELECT count(*) FROM studio.scripts WHERE video_id = %s", (video_id,)
    ).fetchone()[0]


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("canal").id, "Histórico de revisões", VideoFormat.long)
    return {"connect": connect, "conn": conn, "video": video, "videos": videos,
            "scripts": PostgresScriptRepository(connect), "snaps": PostgresSnapshotRepository(connect)}


def _seed_two_versions(env, claim_id: str = ""):
    """v1 com assets; v2 com uma cena reescrita e a ordem trocada. v1 vira histórico."""
    v = env["video"].id
    first = _drafts(12, claim_id)
    env["scripts"].save_planned_version(v, "v1", first, [claim_id] if claim_id else [], PLAN, H1,
                                        VideoStatus.IDEA, VideoStatus.SCRIPTED)
    scene_ids = [s.id for s in env["scripts"].scenes(v)]
    assets = _assign_assets(env, scene_ids)

    second = list(first)
    second[0], second[1] = first[1], first[0]
    second[2] = SceneDraft(narration("reescrita"), "Legenda", "CEN",
                           "wide empty stage with colored lights 2", [claim_id] if claim_id else [])
    env["scripts"].save_planned_version(v, "v2", second, [claim_id] if claim_id else [], PLAN, H2,
                                        VideoStatus.SCRIPTED, VideoStatus.SCRIPTED)
    return first, second, scene_ids, assets


def test_restore_brings_text_order_and_media_from_the_chosen_revision(env):
    first, second, scene_ids, assets = _seed_two_versions(env)
    v = env["video"].id

    # v2 corrente: ordem trocada, uma cena reescrita e sem mídia na cena editada.
    current = env["scripts"].scenes(v)
    assert [s.narration for s in current] == [d.narration for d in second]
    assert [s.asset_id for s in current] == [assets[1], assets[0], None, *assets[3:]]

    outcome = env["scripts"].save_restore(
        v, "restore-1", "d" * 64, expected_version=2, source_version=1,
        text="\n".join(d.narration for d in first), claim_ids=[], plan=PLAN, content_hash=H1,
        expected=VideoStatus.SCRIPTED, new=VideoStatus.SCRIPTED,
    )
    assert outcome is not None and outcome.script.version == 3

    restored = env["scripts"].scenes(v)
    # (a) texto, ordem e asset_id voltam da revisão 1, não do estado atual.
    assert [s.narration for s in restored] == [d.narration for d in first]
    assert [s.idx for s in restored] == list(range(12))
    assert [s.asset_id for s in restored] == assets
    assert [s.id for s in restored] == scene_ids
    assert all(flag is False for _, flag in _flags(env, v))

    # (c) nada é apagado: as duas revisões anteriores continuam recuperáveis.
    assert len(env["scripts"].revision_scenes(v, 1)) == 12
    assert len(env["scripts"].revision_scenes(v, 2)) == 12
    assert [r.script.version for r in env["scripts"].list_script_records(v)] == [1, 2, 3]
    assert _version_count(env, v) == 3


def test_restore_marks_missing_asset_as_media_review_required(env):
    _first, _second, _scene_ids, assets = _seed_two_versions(env)
    v = env["video"].id

    # A mídia some depois de a revisão 1 ser congelada: o snapshot guarda o vínculo, mas o asset
    # não existe mais. A projeção corrente precisa pedir revisão de mídia.
    env["conn"].execute("UPDATE studio.scenes SET asset_id = NULL WHERE video_id = %s", (v,))
    env["conn"].execute("DELETE FROM studio.assets WHERE id = ANY(%s)", (assets,))
    env["conn"].commit()

    outcome = env["scripts"].save_restore(
        v, "restore-missing", "e" * 64, expected_version=2, source_version=1,
        text="t", claim_ids=[], plan=PLAN, content_hash=H1,
        expected=VideoStatus.SCRIPTED, new=VideoStatus.SCRIPTED,
    )
    assert outcome is not None and outcome.script.version == 3

    restored = env["scripts"].scenes(v)
    assert [s.asset_id for s in restored] == [None] * 12
    assert all(flag is True for _, flag in _flags(env, v))
    # O histórico não é reescrito: a revisão 1 ainda registra os assets originais.
    snapshot = env["scripts"].revision_scenes(v, 1)
    assert [s.asset_id for s in snapshot] == assets
    assert all(s.media_review_required is False for s in snapshot)


def test_restore_is_idempotent_and_rejects_stale_cas(env):
    _first, _second, _scene_ids, _assets = _seed_two_versions(env)
    v = env["video"].id
    args = dict(expected_version=2, source_version=1, text="t", claim_ids=[], plan=PLAN,
                content_hash=H1, expected=VideoStatus.SCRIPTED, new=VideoStatus.SCRIPTED)

    first = env["scripts"].save_restore(v, "same-key", "f" * 64, **args)
    replay = env["scripts"].save_restore(v, "same-key", "f" * 64, **args)
    assert first is not None and replay is not None
    assert replay.script.version == first.script.version == 3
    assert _version_count(env, v) == 3  # replay não cria versão nova

    with pytest.raises(ScriptEditIdempotencyConflict):
        env["scripts"].save_restore(v, "same-key", "0" * 64, **args)

    # CAS: a versão corrente mudou depois da leitura; nada é gravado.
    assert env["scripts"].save_restore(v, "stale-key", "1" * 64, **args) is None
    assert _version_count(env, v) == 3


def test_restore_refuses_a_revision_without_snapshot(env):
    _first, _second, _scene_ids, _assets = _seed_two_versions(env)
    v = env["video"].id
    env["conn"].execute("DELETE FROM studio.scene_revisions WHERE video_id = %s AND version = 1", (v,))
    env["conn"].commit()

    with pytest.raises(ScriptRevisionUnavailable):
        env["scripts"].save_restore(
            v, "legacy", "2" * 64, expected_version=2, source_version=1,
            text="t", claim_ids=[], plan=PLAN, content_hash=H1,
            expected=VideoStatus.SCRIPTED, new=VideoStatus.SCRIPTED,
        )
    assert _version_count(env, v) == 2


def test_restore_use_case_creates_a_new_version_from_the_chosen_revision(env):
    v = env["video"].id
    snap = env["snaps"].add(v, "https://example.com/fonte", SOURCE)
    claim_id = extract_claims(snap.id, SOURCE)[0].id
    first, second, _scene_ids, assets = _seed_two_versions(env, claim_id)

    editor = RestoreScriptRevision(env["videos"], env["snaps"], env["scripts"], env["scripts"])
    result = editor.execute_idempotent(v, 1, expected_version=2, idempotency_key="restore-uc")

    assert result.script.version == 3
    assert [s.narration for s in result.scenes] == [d.narration for d in first]
    assert [s.idx for s in result.scenes] == list(range(12))
    assert [s.asset_id for s in result.scenes] == assets
    assert result.review.passed

    # A restauração não copia o estado atual (v2) nem apaga o histórico.
    assert [s.narration for s in env["scripts"].revision_scenes(v, 2)] == [d.narration for d in second]
    assert [s.asset_id for s in env["scripts"].revision_scenes(v, 1)] == assets
    assert _version_count(env, v) == 3


def test_scene_revisions_migration_is_additive_and_backfills_the_current_version(conn, tmp_path):
    """A migração não toca tabelas existentes e dá à versão corrente o snapshot do estado atual."""
    migrations = Path(__file__).resolve().parents[1] / "renderer/app/studio/adapters/postgres/migrations"
    target = "0046_scene_revisions.sql"
    for path in sorted(migrations.glob("*.sql")):
        if path.name < target:
            shutil.copy(path, tmp_path / path.name)
    migrate(conn, tmp_path)

    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, %s)", ("a" * 32, "canal"))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, %s, %s)",
                 ("b" * 32, "a" * 32, "tema do vídeo", "long"))
    conn.execute("INSERT INTO studio.scripts(id, video_id, version, text) VALUES (%s, %s, 1, %s)",
                 ("c" * 32, "b" * 32, "roteiro já existente"))
    conn.execute("INSERT INTO studio.scenes(id, video_id, idx, narration, image_prompt) VALUES (%s, %s, 0, %s, %s)",
                 ("d" * 32, "b" * 32, "narração já existente", "prompt de imagem já existente"))
    conn.commit()

    shutil.copy(migrations / target, tmp_path / target)
    assert migrate(conn, tmp_path) == ["0046_scene_revisions"]
    row = conn.execute(
        "SELECT video_id, version, scene_id, idx, narration, asset_id, media_review_required "
        "FROM studio.scene_revisions"
    ).fetchone()
    assert row == ("b" * 32, 1, "d" * 32, 0, "narração já existente", None, False)
    assert conn.execute("SELECT count(*) FROM studio.scenes").fetchone()[0] == 1

    conn.execute("DELETE FROM studio.scripts WHERE video_id = %s AND version = 1", ("b" * 32,))
    conn.commit()
    assert conn.execute("SELECT count(*) FROM studio.scene_revisions").fetchone()[0] == 0

