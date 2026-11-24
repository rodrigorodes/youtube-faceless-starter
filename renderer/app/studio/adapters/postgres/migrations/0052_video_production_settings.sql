-- 0052_video_production_settings.sql: Parâmetros de produção e briefing criativo em studio.videos (Onda 4)
ALTER TABLE studio.videos
    ADD COLUMN IF NOT EXISTS target_duration_s integer DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS pacing_preset text NOT NULL DEFAULT 'dynamic',
    ADD COLUMN IF NOT EXISTS budget_cap_usd numeric(8,2) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS creative_brief jsonb DEFAULT NULL;
