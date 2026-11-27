-- 0056_asset_tags.sql: persistent asset tags for studio assets (PC-05.02 / V4-11.09)
-- Rollback seguro (não destrutivo para dados de assets):
--   DROP TABLE IF EXISTS studio.asset_tags;
--   DELETE FROM studio.schema_migrations WHERE version = '0056_asset_tags';

CREATE TABLE IF NOT EXISTS studio.asset_tags (
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE CASCADE,
    asset_id text NOT NULL REFERENCES studio.assets(id) ON DELETE CASCADE,
    tag text NOT NULL CHECK (length(tag) BETWEEN 1 AND 64 AND tag ~ '^[a-z0-9][a-z0-9._:-]{0,63}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, asset_id, tag)
);

CREATE INDEX IF NOT EXISTS ix_asset_tags_project_tag_asset
    ON studio.asset_tags (project_id, tag, asset_id);
