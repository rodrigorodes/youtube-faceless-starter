-- 0050_scene_assets.sql: Persistência de múltiplos assets por cena (F01/Onda 1)
CREATE TABLE IF NOT EXISTS studio.scene_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scene_id VARCHAR(64) NOT NULL REFERENCES studio.scenes(id) ON DELETE CASCADE,
    asset_id VARCHAR(64) REFERENCES studio.assets(id) ON DELETE SET NULL,
    position INT NOT NULL CHECK (position >= 0),
    start_s NUMERIC(8,3) NOT NULL CHECK (start_s >= 0),
    end_s NUMERIC(8,3) NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'base',
    motion VARCHAR(16) NOT NULL DEFAULT 'none',
    transition_kind VARCHAR(16) NOT NULL DEFAULT 'none',
    transition_duration_s NUMERIC(8,3) NOT NULL DEFAULT 0.0 CHECK (transition_duration_s >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_scene_asset_pos UNIQUE (scene_id, position),
    CONSTRAINT ck_scene_asset_timing CHECK (end_s > start_s)
);

CREATE INDEX IF NOT EXISTS ix_scene_assets_scene_id ON studio.scene_assets (scene_id);
CREATE INDEX IF NOT EXISTS ix_scene_assets_asset_id ON studio.scene_assets (asset_id);
