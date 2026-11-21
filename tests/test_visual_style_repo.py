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
    return {"repo": PostgresVisualStyleRepository(connect), "dsn": dsn}


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
    assert archived.archived is True and archived.version == 2
    assert repo.get(style.id).archived is True  # a linha continua no banco
    assert [s.id for s in repo.list()] == []  # some da lista padrão, sem apagar
    again = repo.archive(style.id)  # idempotente: não bumpa de novo
    assert again.version == 2 and again.archived is True
    freed = repo.create("Duplicado")  # o nome ativo é liberado para reúso
    assert freed.id != style.id
    versions = _rows(styles["dsn"], "select version from studio.visual_style_revisions "
                                     "where style_id=%s order by version", (style.id,))
    assert versions == [(1,), (2,)]


def test_archive_of_an_unknown_style_returns_none(styles):
    assert styles["repo"].archive("b" * 32) is None
