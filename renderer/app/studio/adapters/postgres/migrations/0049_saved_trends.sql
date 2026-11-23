-- 0049_saved_trends.sql: Ideias guardadas (saved_trends) por projeto e vídeo.
CREATE TABLE IF NOT EXISTS studio.saved_trends (
    project_id text NOT NULL,
    video_id text NOT NULL,
    title text NOT NULL,
    channel_title text,
    thumbnail_url text,
    video_url text,
    duration text NOT NULL DEFAULT '',
    views bigint NOT NULL DEFAULT 0,
    category_name text,
    score int NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, video_id)
);

CREATE INDEX IF NOT EXISTS saved_trends_project_idx ON studio.saved_trends (project_id, created_at DESC);
