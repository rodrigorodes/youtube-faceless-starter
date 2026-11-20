import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.category_repo import PostgresCategoryRepository  # noqa: E402
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.domain.categories import (  # noqa: E402
    CategoryNameInvalid,
    DuplicateCategoryName,
    ProjectCategory,
)


@pytest.fixture()
def cat_env(conn, dsn):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    repo = PostgresCategoryRepository(connect)
    project = videos.create_project("Canal Pillars", niche="Tecnologia", language="pt-BR")
    return {"repo": repo, "project_id": project.id, "conn": conn, "connect": connect, "videos": videos}


def test_create_and_get_category(cat_env):
    repo = cat_env["repo"]
    p_id = cat_env["project_id"]

    cat = repo.save(p_id, "Inteligência Artificial", ["IA", "LLMs", "Machine Learning"])

    assert isinstance(cat, ProjectCategory)
    assert len(cat.id) == 32
    assert cat.project_id == p_id
    assert cat.name == "Inteligência Artificial"
    assert cat.queries == ["IA", "LLMs", "Machine Learning"]
    assert cat.created_at is not None
    assert cat.updated_at is not None

    fetched = repo.get(cat.id)
    assert fetched is not None
    assert fetched.id == cat.id
    assert fetched.name == cat.name
    assert fetched.queries == ["IA", "LLMs", "Machine Learning"]
    assert fetched.created_at == cat.created_at
    assert fetched.updated_at == cat.updated_at


def test_get_non_existent_category_returns_none(cat_env):
    repo = cat_env["repo"]
    assert repo.get("0" * 32) is None


def test_list_categories_by_project(cat_env):
    repo = cat_env["repo"]
    p_id = cat_env["project_id"]
    videos = cat_env["videos"]
    other_project = videos.create_project("Outro Canal", niche="Finanças", language="pt-BR")

    assert repo.list(p_id) == []

    cat1 = repo.save(p_id, "Hardware", ["GPUs", "CPUs"])
    cat2 = repo.save(p_id, "Software", ["Python", "Rust"])
    repo.save(other_project.id, "Cripto", ["Bitcoin"])

    cats = repo.list(p_id)
    assert len(cats) == 2
    assert [c.name for c in cats] == ["Hardware", "Software"]
    assert all(c.project_id == p_id for c in cats)

    other_cats = repo.list(other_project.id)
    assert len(other_cats) == 1
    assert other_cats[0].name == "Cripto"


def test_update_category_name_and_queries(cat_env):
    repo = cat_env["repo"]
    p_id = cat_env["project_id"]

    cat = repo.save(p_id, "Tech", ["AI"])
    original_id = cat.id
    original_created_at = cat.created_at

    updated = repo.save(p_id, "Tecnologia e Futuro", ["IA", "Robótica"], category_id=cat.id)

    assert updated.id == original_id
    assert updated.name == "Tecnologia e Futuro"
    assert updated.queries == ["IA", "Robótica"]
    assert updated.created_at == original_created_at

    fetched = repo.get(original_id)
    assert fetched is not None
    assert fetched.name == "Tecnologia e Futuro"
    assert fetched.queries == ["IA", "Robótica"]


def test_duplicate_category_name_in_same_project_raises(cat_env):
    repo = cat_env["repo"]
    p_id = cat_env["project_id"]

    repo.save(p_id, "Inovação", ["Startups"])

    with pytest.raises(DuplicateCategoryName):
        repo.save(p_id, "Inovação", ["Novas ideias"])


def test_update_to_conflicting_name_raises(cat_env):
    repo = cat_env["repo"]
    p_id = cat_env["project_id"]

    cat1 = repo.save(p_id, "Tema A", ["q1"])
    cat2 = repo.save(p_id, "Tema B", ["q2"])

    with pytest.raises(DuplicateCategoryName):
        repo.save(p_id, "Tema A", ["q2_updated"], category_id=cat2.id)


def test_same_category_name_in_different_projects_allowed(cat_env):
    repo = cat_env["repo"]
    p_id1 = cat_env["project_id"]
    videos = cat_env["videos"]
    p_id2 = videos.create_project("Segundo Canal", niche="Tech", language="pt-BR").id

    cat1 = repo.save(p_id1, "Geral", ["notícias"])
    cat2 = repo.save(p_id2, "Geral", ["notícias"])

    assert cat1.id != cat2.id
    assert cat1.name == cat2.name == "Geral"


def test_invalid_category_names_raise(cat_env):
    repo = cat_env["repo"]
    p_id = cat_env["project_id"]

    for invalid_name in ["", "   ", "a" * 101, None]:
        with pytest.raises(CategoryNameInvalid):
            repo.save(p_id, invalid_name, ["test"])


def test_delete_category(cat_env):
    repo = cat_env["repo"]
    p_id = cat_env["project_id"]

    cat = repo.save(p_id, "Temporário", ["temp"])
    assert repo.get(cat.id) is not None

    deleted = repo.delete(cat.id)
    assert deleted is True
    assert repo.get(cat.id) is None

    # Deleting non-existent returns False
    assert repo.delete(cat.id) is False
    assert repo.delete("f" * 32) is False


def test_delete_category_nullifies_trend_topics(cat_env):
    repo = cat_env["repo"]
    p_id = cat_env["project_id"]
    conn = cat_env["conn"]

    cat = repo.save(p_id, "Música", ["clipe"])
    trend_id = "5" * 32

    conn.execute(
        """INSERT INTO studio.trend_topics(
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, category_id
        ) VALUES (%s, %s, 'Novo Hit', 'novo_hit', 'yt', 'https://youtube.com', now(), now(), now(), %s)""",
        (trend_id, p_id, cat.id),
    )
    conn.commit()

    row = conn.execute("SELECT category_id FROM studio.trend_topics WHERE id = %s", (trend_id,)).fetchone()
    assert row[0] == cat.id

    assert repo.delete(cat.id) is True

    row_after = conn.execute("SELECT category_id FROM studio.trend_topics WHERE id = %s", (trend_id,)).fetchone()
    assert row_after[0] is None
