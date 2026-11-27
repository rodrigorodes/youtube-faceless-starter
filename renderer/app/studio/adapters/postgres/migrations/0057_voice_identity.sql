-- 0057_voice_identity.sql: voice settings and channel vocal identity persistence (PC-03.01 / V4-02.05 / V4-02.06)
-- Rollback seguro:
--   ALTER TABLE studio.channel_profiles DROP COLUMN IF EXISTS voice_settings;
--   ALTER TABLE studio.videos DROP COLUMN IF EXISTS voice_settings;
--   ALTER TABLE studio.scenes DROP COLUMN IF EXISTS voice_settings;
--   DELETE FROM studio.schema_migrations WHERE version = '0057_voice_identity';

ALTER TABLE studio.channel_profiles
    ADD COLUMN IF NOT EXISTS voice_settings JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE studio.videos
    ADD COLUMN IF NOT EXISTS voice_settings JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE studio.scenes
    ADD COLUMN IF NOT EXISTS voice_settings JSONB NOT NULL DEFAULT '{}'::jsonb;
