-- F10-05/F10-06: budget por canal (hard/soft) e associação de canal YouTube.
-- Segredos NÃO ficam aqui (ver adapter secret_store): só metadados do canal.
CREATE TABLE studio.channel_budgets (
    project_id text PRIMARY KEY REFERENCES studio.projects(id) ON DELETE CASCADE,
    hard_monthly_usd numeric(12,2) NOT NULL CHECK (hard_monthly_usd >= 0),
    soft_monthly_usd numeric(12,2) NOT NULL CHECK (soft_monthly_usd >= 0 AND soft_monthly_usd <= hard_monthly_usd),
    hard_video_usd numeric(12,2) NOT NULL CHECK (hard_video_usd >= 0),
    soft_video_usd numeric(12,2) NOT NULL CHECK (soft_video_usd >= 0 AND soft_video_usd <= hard_video_usd),
    economic_profile text NOT NULL DEFAULT 'BALANCED' CHECK (economic_profile IN ('ECONOMY', 'BALANCED', 'PREMIUM')),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE studio.channel_youtube_channels (
    project_id text PRIMARY KEY REFERENCES studio.projects(id) ON DELETE CASCADE,
    channel_id text NOT NULL CHECK (length(channel_id) BETWEEN 1 AND 128 AND channel_id ~ '^[A-Za-z0-9._-]+$'),
    title text NOT NULL DEFAULT '' CHECK (length(title) <= 200),
    scopes jsonb NOT NULL DEFAULT '[]',
    oauth_status text NOT NULL DEFAULT 'CONNECTED' CHECK (oauth_status IN ('CONNECTED', 'EXPIRED', 'REVOKED', 'ERROR')),
    token_expires_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
