-- PC-01.01: revisão monotônica por cena para CAS unificado de mídia base, trim e camadas.
-- Aditiva (NOT NULL DEFAULT 1); preserva compatibilidade v1/v2 e dados existentes.
--
-- Rollback manual (não destrutivo para dados de cenas/assets):
--   DROP INDEX IF EXISTS studio.ix_scene_assets_scene_role;
--   ALTER TABLE studio.scenes DROP COLUMN IF EXISTS edit_revision;
--   DELETE FROM studio.schema_migrations WHERE version = '0055_scene_edit_revision';

ALTER TABLE studio.scenes
    ADD COLUMN IF NOT EXISTS edit_revision BIGINT NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS ix_scene_assets_scene_role
    ON studio.scene_assets (scene_id, role);
