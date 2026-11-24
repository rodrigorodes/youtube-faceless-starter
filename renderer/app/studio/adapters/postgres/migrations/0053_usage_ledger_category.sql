-- 0053_usage_ledger_category.sql: Rastreabilidade de custos por categoria no usage_ledger (Onda 6)
ALTER TABLE studio.usage_ledger
    ADD COLUMN IF NOT EXISTS category text NOT NULL DEFAULT 'other',
    ADD COLUMN IF NOT EXISTS duration_ms integer DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS attempt integer NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS usage_ledger_category_idx ON studio.usage_ledger(category);
CREATE INDEX IF NOT EXISTS usage_ledger_video_category_idx ON studio.usage_ledger(video_id, category);
