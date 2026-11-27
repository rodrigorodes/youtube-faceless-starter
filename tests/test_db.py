import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402

V, P = "a" * 32, "b" * 32


def table_exists(conn, name):
    return conn.execute("SELECT to_regclass(%s)", (f"studio.{name}",)).fetchone()[0] is not None


def seed_video(conn, video_id=V):
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p') ON CONFLICT DO NOTHING", (P,))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'ADE 2026', 'short')", (video_id, P))
    conn.commit()


def test_migrate_applies_once(conn):
    assert migrate(conn) == ["0001_init", "0002_editorial", "0003_fact_check_version", "0004_asset_credits", "0005_license_nonblank", "0006_render", "0007_publish", "0008_publication_attempt_base", "0010_approval_render", "0011_trends", "0012_categories", "0013_budget_reservations", "0014_ledger_cost_evidence", "0015_ledger_cost_confirmation", "0016_channel_profiles", "0017_paid_operations", "0018_production_runs", "0019_ledger_estimate_and_attribution", "0020_paid_operation_attempt_and_budget_indexes", "0021_channel_pillars_constraints", "0022_channel_management", "0023_longform_script_approval", "0026_analytics_learning", "0027_saas_multiuser_byok", "0028_publication_resilience", "0031_membership_audit", "0032_render_plan_cache", "0033_visual_styles", "0034_channel_style", "0035_youtube_identity", "0036_video_style", "0037_channel_youtube_target", "0038_budget_scope_attribution", "0039_production_run_config", "0040_style_patches", "0041_production_run_operation", "0042_scene_stable_identity", "0043_reopen_approved_video", "0044_script_edit_requests", "0045_publication_intent_destination_metadata", "0046_scene_revisions", "0047_channel_preferences_and_production_mode", "0048_scene_broll", "0049_saved_trends", "0050_scene_assets", "0051_scene_media_intelligence", "0052_video_production_settings", "0053_usage_ledger_category", "0054_paid_operation_external_ref", "0055_scene_edit_revision", "0056_asset_tags"]
    assert migrate(conn) == []


def test_failed_migration_rolls_back_and_is_not_recorded(conn, tmp_path):
    (tmp_path / "0001_broken.sql").write_text("CREATE TABLE studio.half_done(x int);\nSELECT 1/0;")
    with pytest.raises(psycopg.Error):
        migrate(conn, tmp_path)
    conn.rollback()
    assert not table_exists(conn, "half_done")
    # a transação inteira reverteu: nada aplicado e nada registrado (nem a tabela de controle sobra)
    assert not table_exists(conn, "schema_migrations") or conn.execute("SELECT count(*) FROM studio.schema_migrations").fetchone()[0] == 0
    assert migrate(conn) == ["0001_init", "0002_editorial", "0003_fact_check_version", "0004_asset_credits", "0005_license_nonblank", "0006_render", "0007_publish", "0008_publication_attempt_base", "0010_approval_render", "0011_trends", "0012_categories", "0013_budget_reservations", "0014_ledger_cost_evidence", "0015_ledger_cost_confirmation", "0016_channel_profiles", "0017_paid_operations", "0018_production_runs", "0019_ledger_estimate_and_attribution", "0020_paid_operation_attempt_and_budget_indexes", "0021_channel_pillars_constraints", "0022_channel_management", "0023_longform_script_approval", "0026_analytics_learning", "0027_saas_multiuser_byok", "0028_publication_resilience", "0031_membership_audit", "0032_render_plan_cache", "0033_visual_styles", "0034_channel_style", "0035_youtube_identity", "0036_video_style", "0037_channel_youtube_target", "0038_budget_scope_attribution", "0039_production_run_config", "0040_style_patches", "0041_production_run_operation", "0042_scene_stable_identity", "0043_reopen_approved_video", "0044_script_edit_requests", "0045_publication_intent_destination_metadata", "0046_scene_revisions", "0047_channel_preferences_and_production_mode", "0048_scene_broll", "0049_saved_trends", "0050_scene_assets", "0051_scene_media_intelligence", "0052_video_production_settings", "0053_usage_ledger_category", "0054_paid_operation_external_ref", "0055_scene_edit_revision", "0056_asset_tags"]  # e uma migração boa roda normalmente depois


def test_creates_all_tables(conn):
    migrate(conn)
    for t in ("projects", "videos", "scripts", "scenes", "assets", "render_jobs", "publications",
              "source_snapshots", "step_runs", "usage_ledger", "video_metrics", "fact_checks", "trend_topics",
              "project_categories", "budget_reservations", "channel_profiles", "channel_profile_revisions",
              "paid_operations", "production_runs", "stage_executions", "production_outbox",
              "channel_budgets", "channel_youtube_channels", "organizations", "workspaces",
              "users", "memberships", "byok_keys", "byok_key_audit", "metric_observations",
              "analytics_experiments", "analytics_experiment_variants",
              "analytics_recommendation_decisions", "publication_intents", "membership_audit",
              "render_plans", "plan_artifacts", "render_cache_entries",
              "visual_styles", "visual_style_revisions",
              "google_accounts", "oauth_grants", "youtube_channels", "channel_authorizations",
              "script_edit_requests", "approval_history", "scene_revisions", "asset_tags"):
        assert table_exists(conn, t), t


def test_publication_unique_per_video(conn):
    migrate(conn)
    seed_video(conn)
    conn.execute("INSERT INTO studio.publications(id, video_id) VALUES (%s, %s)", ("c" * 32, V))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO studio.publications(id, video_id) VALUES (%s, %s)", ("d" * 32, V))


@pytest.mark.parametrize("sql,params,error", [
    ("INSERT INTO studio.projects(id, name) VALUES ('x', 'y')", (), psycopg.errors.CheckViolation),
    ("INSERT INTO studio.videos(id, project_id, topic, format, status) VALUES (%s, %s, 'abc', 'short', 'NOPE')", ("e" * 32, P), psycopg.errors.CheckViolation),
    ("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd) VALUES ('s', 'p', 'm', -1)", (), psycopg.errors.CheckViolation),
    ("INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) VALUES (%s, 'image', %s, 'x', 'p', 'm', '')", ("f" * 32, "1" * 64), psycopg.errors.CheckViolation),
    ("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'abc', 'short')", ("e" * 32, "9" * 32), psycopg.errors.ForeignKeyViolation),
])
def test_constraints_reject_bad_rows(conn, sql, params, error):
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p')", (P,))
    with pytest.raises(error):
        conn.execute(sql, params)


def test_new_video_defaults_to_private_idea(conn):
    migrate(conn)
    seed_video(conn)
    assert conn.execute("SELECT status, privacy FROM studio.videos WHERE id=%s", (V,)).fetchone() == ("IDEA", "private")


def test_scene_index_and_cache_key_unique(conn):
    migrate(conn)
    seed_video(conn)
    ins = "INSERT INTO studio.scenes(id, video_id, idx, narration, image_prompt) VALUES (%s, %s, 0, 'narração', 'prompt de imagem')"
    conn.execute(ins, ("1" * 32, V))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(ins, ("2" * 32, V))


def test_fact_check_override_needs_reason_in_db(conn):
    migrate(conn)
    seed_video(conn)
    ins = "INSERT INTO studio.fact_checks(id, video_id, passed, overridden, override_reason, report) VALUES (%s, %s, true, %s, %s, '{}')"
    conn.execute(ins, ("1" * 32, V, False, None))
    conn.execute(ins, ("2" * 32, V, True, "revisado"))
    for reason in (None, "", "   "):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(ins, ("3" * 32, V, True, reason))
        conn.rollback()


def test_scene_claim_ids_and_snapshot_dedupe(conn):
    migrate(conn)
    seed_video(conn)
    conn.execute("INSERT INTO studio.scenes(id, video_id, idx, narration, image_prompt, claim_ids) VALUES (%s, %s, 0, 'narração', 'prompt de imagem', '[\"abc\"]')", ("4" * 32, V))
    snap = "INSERT INTO studio.source_snapshots(id, video_id, url, content_sha256, text) VALUES (%s, %s, 'https://x.example', %s, 't')"
    conn.execute(snap, ("5" * 32, V, "a" * 64))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(snap, ("6" * 32, V, "a" * 64))


def test_asset_license_blank_rejected_and_credits_stored(conn):
    migrate(conn)
    ins = "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license, attribution, source_url) VALUES (%s, 'image', %s, 'x', 'p', 'm', %s, %s, %s)"
    conn.execute(ins, ("1" * 32, "a" * 64, "Pexels License", "Foto de Fulano", "https://x.example"))
    for lic in ("", "   "):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(ins, ("2" * 32, "b" * 64, lic, "", ""))
        conn.rollback()
        migrate(conn)


def test_project_categories_constraints_and_trend_link(conn):
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p') ON CONFLICT DO NOTHING", (P,))
    cat_id = "1" * 32
    conn.execute(
        "INSERT INTO studio.project_categories(id, project_id, name, queries) VALUES (%s, %s, %s, %s)",
        (cat_id, P, "Tech", ["AI", "Python"])
    )
    # duplicate (project_id, name) should fail
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO studio.project_categories(id, project_id, name) VALUES (%s, %s, %s)",
            ("2" * 32, P, "Tech")
        )
    conn.rollback()
    migrate(conn)

    # Empty name should fail
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p') ON CONFLICT DO NOTHING", (P,))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO studio.project_categories(id, project_id, name) VALUES (%s, %s, %s)",
            ("3" * 32, P, "")
        )
    conn.rollback()
    migrate(conn)

    # Re-insert cat
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p') ON CONFLICT DO NOTHING", (P,))
    conn.execute(
        "INSERT INTO studio.project_categories(id, project_id, name, queries) VALUES (%s, %s, %s, %s)",
        (cat_id, P, "Tech", ["AI"])
    )
    # trend topic can link to category_id
    trend_id = "4" * 32
    conn.execute(
        """INSERT INTO studio.trend_topics(
            id, project_id, topic, topic_key, source_name, source_url,
            observed_at, window_start, window_end, category_id
        ) VALUES (%s, %s, 'AI News', 'ai_news', 'yt', 'https://youtube.com', now(), now(), now(), %s)""",
        (trend_id, P, cat_id)
    )
    row = conn.execute("SELECT category_id FROM studio.trend_topics WHERE id = %s", (trend_id,)).fetchone()
    assert row[0] == cat_id

    # deleting category should set category_id to NULL
    conn.execute("DELETE FROM studio.project_categories WHERE id = %s", (cat_id,))
    row = conn.execute("SELECT category_id FROM studio.trend_topics WHERE id = %s", (trend_id,)).fetchone()
    assert row[0] is None


def test_asset_tags_constraints_and_cascade(conn):
    migrate(conn)
    pid = "b" * 32
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, %s)", (pid, "Test Project"))
    aid = "a" * 32
    conn.execute(
        "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) "
        "VALUES (%s, 'image', %s, 'path/to/img.png', 'p', 'm', 'CC0-1.0')",
        (aid, "1" * 64),
    )
    conn.commit()

    # Valid tag
    conn.execute("INSERT INTO studio.asset_tags(project_id, asset_id, tag) VALUES (%s, %s, %s)", (pid, aid, "historia"))
    # Duplicate tag fails PK
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO studio.asset_tags(project_id, asset_id, tag) VALUES (%s, %s, %s)", (pid, aid, "historia"))
    conn.rollback()

    # Invalid tags rejected by CHECK constraint:
    for bad_tag in ("", "   ", "UPPERCASE", "with spaces", "has_special!", "a" * 65, "-starts-with-dash"):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("INSERT INTO studio.asset_tags(project_id, asset_id, tag) VALUES (%s, %s, %s)", (pid, aid, bad_tag))
        conn.rollback()

    # Cascade on asset deletion
    conn.execute("INSERT INTO studio.asset_tags(project_id, asset_id, tag) VALUES (%s, %s, %s)", (pid, aid, "computacao"))
    assert conn.execute("SELECT count(*) FROM studio.asset_tags WHERE asset_id = %s", (aid,)).fetchone()[0] == 1
    conn.execute("DELETE FROM studio.assets WHERE id = %s", (aid,))
    assert conn.execute("SELECT count(*) FROM studio.asset_tags WHERE asset_id = %s", (aid,)).fetchone()[0] == 0

