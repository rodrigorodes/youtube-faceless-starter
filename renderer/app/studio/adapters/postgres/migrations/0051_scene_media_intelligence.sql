ALTER TABLE studio.scenes ADD COLUMN IF NOT EXISTS visual_intent TEXT DEFAULT '';
ALTER TABLE studio.scenes ADD COLUMN IF NOT EXISTS search_queries JSONB DEFAULT '[]'::jsonb;
ALTER TABLE studio.scene_revisions ADD COLUMN IF NOT EXISTS visual_intent TEXT DEFAULT '';
ALTER TABLE studio.scene_revisions ADD COLUMN IF NOT EXISTS search_queries JSONB DEFAULT '[]'::jsonb;
