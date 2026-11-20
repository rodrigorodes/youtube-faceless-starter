-- Armazenamento verificado de temas em alta por projeto e janela temporal.
CREATE TABLE studio.trend_topics (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE RESTRICT,
    topic text NOT NULL CHECK (length(topic) BETWEEN 3 AND 300),
    topic_key text NOT NULL CHECK (length(topic_key) >= 1),
    source_name text NOT NULL CHECK (length(source_name) BETWEEN 1 AND 80),
    source_url text NOT NULL CHECK (source_url ~ '^https://'),
    observed_at timestamptz NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    metric_name text,
    metric_value double precision CHECK (metric_value >= 0),
    evidence jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, topic_key, source_name, window_end)
);
CREATE INDEX trend_topics_project_window_idx ON studio.trend_topics (project_id, window_end DESC);
