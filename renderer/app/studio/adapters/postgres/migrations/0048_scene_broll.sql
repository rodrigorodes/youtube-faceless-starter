-- 0048_scene_broll.sql: Metadados de B-roll por cena (F02/V3)
ALTER TABLE studio.scenes ADD COLUMN IF NOT EXISTS broll_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE studio.scenes ADD COLUMN IF NOT EXISTS broll_note text NULL;
