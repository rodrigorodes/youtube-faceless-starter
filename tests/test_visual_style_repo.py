"""Testes de integração do repositório Postgres de estilos visuais (banco descartável)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.channel_repo import PostgresChannelProfileRepository  # noqa: E402
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.visual_style_repo import PostgresVisualStyleRepository  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.visual_style import (  # noqa: E402
    DuplicateVisualStyle,
    VisualStyleParamsInvalid,
    VisualStyleVersionConflict,
)


@pytest.fixture()
def styles(conn, dsn):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    return {"repo": PostgresVisualStyleRepository(connect), "dsn": dsn, "connect": connect,
            "channels": PostgresChannelProfileRepository(connect),
            "videos": PostgresVideoRepository(connect)}


def _rows(dsn, query, params=()):
    with psycopg.connect(dsn) as c, c.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def test_create_reads_back_and_writes_the_first_revision(styles):
    repo = styles["repo"]
    s = repo.create("Documentário Cinemático", params={"music": {"bpm": 110}, "extra": {"lut": "warm"}})
    assert s.version == 1 and s.name == "Documentário Cinemático"
    assert s.params == {"music": {"bpm": 110}, "extra": {"lut": "warm"}}
    assert repo.get(s.id) == s
    assert _rows(styles["dsn"], "select version from studio.visual_style_revisions where style_id=%s", (s.id,)) == [(1,)]


def test_update_bumps_version_and_records_a_new_revision(styles):
    repo = styles["repo"]
    s = repo.create("Vlog Rápido")
    changed = repo.update(s.id, 1, {"params": {"motion": ["zoom_in"]}})
    assert changed.version == 2 and changed.params == {"motion": ["zoom_in"]}
    versions = _rows(styles["dsn"], "select version from studio.visual_style_revisions where style_id=%s order by version", (s.id,))
    assert versions == [(1,), (2,)]


def test_update_with_a_stale_version_is_a_conflict(styles):
    repo = styles["repo"]
    s = repo.create("Estilo")
    repo.update(s.id, 1, {"name": "Estilo v2"})
    with pytest.raises(VisualStyleVersionConflict):
        repo.update(s.id, 1, {"name": "Estilo v3"})


def test_update_of_an_unknown_style_returns_none(styles):
    assert styles["repo"].update("b" * 32, 1, {"name": "x"}) is None


def test_duplicate_active_name_is_refused_but_archiving_frees_it(styles):
    repo = styles["repo"]
    first = repo.create("Cinemático")
    with pytest.raises(DuplicateVisualStyle):
        repo.create("cinemático")  # único sem distinguir caixa
    repo.update(first.id, 1, {"archived": True})
    assert repo.create("Cinemático").id != first.id


def test_list_hides_archived_unless_asked(styles):
    repo = styles["repo"]
    repo.create("A")
    b = repo.create("B")
    repo.update(b.id, 1, {"archived": True})
    assert [s.name for s in repo.list()] == ["A"]
    assert sorted(s.name for s in repo.list(include_archived=True)) == ["A", "B"]


def test_params_are_validated_by_the_domain_on_write(styles):
    with pytest.raises(VisualStyleParamsInvalid):
        styles["repo"].create("Ruim", params={"music": {"bpm": 999}})


def test_create_rejects_unknown_option_fields(styles):
    with pytest.raises(ValueError, match="unknown visual style fields"):
        styles["repo"].create("X", colour="#fff")


def test_usage_counts_counts_only_channels_that_point_to_a_style(styles):
    repo = styles["repo"]
    connect = lambda: psycopg.connect(styles["dsn"])
    videos = PostgresVideoRepository(connect)
    channels = PostgresChannelProfileRepository(connect)
    style = repo.create("Cinemático")
    other = repo.create("Vlog")
    a = videos.create_project("Canal A", niche="", language="pt-BR")
    b = videos.create_project("Canal B", niche="", language="pt-BR")
    c = videos.create_project("Canal C", niche="", language="pt-BR")
    channels.create(a.id, "A", style_id=style.id)
    channels.create(b.id, "B", style_id=style.id)
    channels.create(c.id, "C")  # sem estilo: não conta
    assert repo.usage_counts() == {style.id: 2}  # só a contagem medida
    assert other.id not in repo.usage_counts()


def test_archive_soft_deletes_frees_the_name_and_is_idempotent(styles):
    repo = styles["repo"]
    style = repo.create("Duplicado")
    archived = repo.archive(style.id)
    assert archived.style.archived is True and archived.style.version == 2
    assert repo.get(style.id).archived is True  # a linha continua no banco
    assert [s.id for s in repo.list()] == []  # some da lista padrão, sem apagar
    again = repo.archive(style.id)  # idempotente: não bumpa de novo
    assert again.style.version == 2 and again.style.archived is True
    freed = repo.create("Duplicado")  # o nome ativo é liberado para reúso
    assert freed.id != style.id
    versions = _rows(styles["dsn"], "select version from studio.visual_style_revisions "
                                     "where style_id=%s order by version", (style.id,))
    assert versions == [(1,), (2,)]


def test_archive_clears_the_channel_and_video_links_atomically_and_counts_them(styles):
    repo = styles["repo"]
    connect = lambda: psycopg.connect(styles["dsn"])
    videos = PostgresVideoRepository(connect)
    channels = PostgresChannelProfileRepository(connect)
    style = repo.create("Cinemático")
    other = repo.create("Outro")
    a = videos.create_project("Canal A", niche="", language="pt-BR")
    b = videos.create_project("Canal B", niche="", language="pt-BR")
    channel_a = channels.create(a.id, "A", style_id=style.id)
    channel_b = channels.create(b.id, "B", style_id=style.id)
    video = videos.create_video(a.id, "ADE 2026", VideoFormat.short)
    videos.set_video_style(video.id, style.id)  # override do vídeo apontando para o estilo
    untouched = videos.create_video(b.id, "ADE 2026", VideoFormat.short)
    videos.set_video_style(untouched.id, other.id)  # outro estilo não pode ser tocado

    result = repo.archive(style.id)  # arquiva e limpa na mesma transação (VS-05c)
    assert result.style.archived is True and result.cleared_links == 3  # 2 canais + 1 vídeo
    assert channels.get(channel_a.id).style_id is None  # canal volta ao padrão do estúdio
    assert channels.get(channel_b.id).style_id is None
    assert videos.get_video(video.id).style_id is None  # vídeo volta a herdar do canal
    assert videos.get_video(untouched.id).style_id == other.id  # o outro estilo segue intacto
    # Idempotente: nada aponta mais, então não limpa nada e não bumpa a versão de novo.
    again = repo.archive(style.id)
    assert again.cleared_links == 0 and again.style.version == 2


def test_an_archived_style_never_drives_a_render_even_if_a_link_is_reinserted(styles):
    from app.studio.composition import _style_for_video

    repo = styles["repo"]
    connect = lambda: psycopg.connect(styles["dsn"])
    videos = PostgresVideoRepository(connect)
    channels = PostgresChannelProfileRepository(connect)
    style = repo.create("Cinemático", params={"motion": ["zoom_in"]})
    project = videos.create_project("Canal A", niche="", language="pt-BR")
    channels.create(project.id, "A", style_id=style.id)
    video = videos.create_video(project.id, "ADE 2026", VideoFormat.short)
    repo.archive(style.id)  # limpa os vínculos no arquivamento

    # Simula um escape da limpeza: alguém reinsere os vínculos à mão.
    with psycopg.connect(styles["dsn"]) as c, c.cursor() as cur:
        cur.execute("update studio.channel_profiles set style_id=%s where project_id=%s", (style.id, project.id))
        cur.execute("update studio.videos set style_id=%s where id=%s", (style.id, video.id))

    # A resolução (defesa em profundidade) trata o arquivado como ausente: nada dirige o render.
    fetched = videos.get_video(video.id)
    assert fetched.style_id == style.id and channels.get_by_project(project.id).style_id == style.id
    assert _style_for_video(fetched, channels, repo) is None


def test_archive_of_an_unknown_style_returns_none(styles):
    assert styles["repo"].archive("b" * 32) is None


# ------------------------------------ patches persistidos e troca de base (F05.T02)


def _project(storage, name="Canal História"):
    return storage["videos"].create_project(name, niche="História", language="pt-BR")


def _config(storage, video, channel, *, video_patch=None):
    from app.studio.domain.effective_config import resolve_effective_config

    return resolve_effective_config(
        video=video,
        channel=channel,
        lookup_style=storage["repo"].get,
        video_patch=video_patch,
        channel_patch=channel.style_patch,
    )


def test_switching_the_base_style_keeps_the_patch_applied_and_recomputes_on_read(styles):
    """A base do vídeo mudou: o patch continua, recalculado sobre a base nova (nada copiado)."""
    repo, channels, videos = styles["repo"], styles["channels"], styles["videos"]
    style_a = repo.create("Estilo A", params={"music": {"bpm": 100, "seed": 3}, "motion": ["zoom_in"]})
    style_b = repo.create("Estilo B", params={"music": {"bpm": 140, "seed": 5}, "motion": ["pan_left"]})
    project = _project(styles)
    channel = channels.create(project.id, "História", style_id=style_a.id)
    channels.set_style_patch(channel.id, 0, {"music": {"bpm": 130}})
    video = videos.create_video(project.id, "ADE 2026", VideoFormat.short)

    over_a = _config(styles, video, channels.get(channel.id))
    assert over_a.style.id == style_a.id
    assert dict(over_a.music) == {"bpm": 130, "seed": 3}  # patch manda no bpm; o seed vem da base

    # troca a base de estilo do canal: o patch não foi copiado nem apagado, só recomposto
    channels.update(channel.id, channel.version, {"style_id": style_b.id})
    refreshed = channels.get(channel.id)
    assert refreshed.style_patch.to_mapping() == {"music": {"bpm": 130}}
    over_b = _config(styles, video, refreshed)
    assert over_b.style.id == style_b.id
    assert dict(over_b.music) == {"bpm": 130, "seed": 5}  # o seed agora é o da base nova
    assert over_b.provenance["audiovisual.music.bpm"] == "channel"
    assert over_b.provenance["audiovisual.music.seed"] == "style"

    # o patch guarda só overrides: os parâmetros das bases seguem intactos
    assert repo.get(style_a.id).params == {"music": {"bpm": 100, "seed": 3}, "motion": ["zoom_in"]}
    assert repo.get(style_b.id).params == {"music": {"bpm": 140, "seed": 5}, "motion": ["pan_left"]}


def test_video_patch_wins_over_the_channel_and_reset_falls_back_to_inheriting(styles):
    repo, channels, videos = styles["repo"], styles["channels"], styles["videos"]
    base = repo.create("Estilo", params={"music": {"bpm": 100, "seed": 3}})
    project = _project(styles)
    channel = channels.create(project.id, "História", style_id=base.id)
    channels.set_style_patch(channel.id, 0, {"music": {"bpm": 130}})
    video = videos.create_video(project.id, "ADE 2026", VideoFormat.short)
    channel = channels.get(channel.id)

    saved = videos.set_video_style_patch(video.id, 0, {"music": {"bpm": 150}})
    assert saved.patch.to_mapping() == {"music": {"bpm": 150}}
    assert dict(_config(styles, video, channel, video_patch=saved.patch).music) == {
        "bpm": 150, "seed": 3}

    reset = videos.set_video_style_patch(video.id, saved.revision, None)
    assert reset.patch is None  # voltou a herdar do canal
    assert dict(_config(styles, video, channel, video_patch=reset.patch).music) == {
        "bpm": 130, "seed": 3}


def test_a_new_base_that_rejects_the_patch_fails_loudly_instead_of_being_swallowed(styles):
    """Registra o comportamento: o patch válido na base A é inválido quando a base troca.

    O erro **sobe tipado** (não é engolido): a mesclagem do domínio levanta
    ``VisualStyleParamsInvalid`` — a mesma família de ``StylePatchInvalid`` (que é subclasse) —
    e o ``effective_config`` o reembala em ``EffectiveConfigInvalid`` com a chave ofensora.
    """
    from app.studio.domain.effective_config import EffectiveConfigInvalid
    from app.studio.domain.visual_style import StylePatch, apply_style_patch

    repo, channels, videos = styles["repo"], styles["channels"], styles["videos"]
    accepts = repo.create("Fade", params={"transition": {"kind": "fade", "duration_ticks": 8}})
    rejects = repo.create("Sem transição", params={"transition": {"kind": "none"}})
    project = _project(styles)
    channel = channels.create(project.id, "História", style_id=accepts.id)
    channels.set_style_patch(channel.id, 0, {"transition": {"duration_ticks": 12}})
    video = videos.create_video(project.id, "ADE 2026", VideoFormat.short)
    channel = channels.get(channel.id)

    assert dict(_config(styles, video, channel).transition) == {"kind": "fade", "duration_ticks": 12}

    with pytest.raises(VisualStyleParamsInvalid, match="transition"):
        apply_style_patch(rejects.params, StylePatch.from_mapping(channel.style_patch.to_mapping()))

    channels.update(channel.id, channel.version, {"style_id": rejects.id})
    with pytest.raises(EffectiveConfigInvalid, match="transition"):
        _config(styles, videos.get_video(video.id), channels.get(channel.id))
    # o patch persistido continua lá: a falha é de resolução, não de escrita
    assert channels.get(channel.id).style_patch.to_mapping() == {"transition": {"duration_ticks": 12}}
