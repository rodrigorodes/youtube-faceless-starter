-- Faceless Studio: schema inicial. IDs são uuid4().hex (32 hex minúsculos).
CREATE TABLE studio.projects (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    niche text NOT NULL DEFAULT '',
    language text NOT NULL DEFAULT 'pt-BR',
    budget_usd_month numeric(12,2) NOT NULL DEFAULT 15 CHECK (budget_usd_month >= 0),
    config jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE studio.videos (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE RESTRICT,
    topic text NOT NULL CHECK (length(topic) BETWEEN 3 AND 300),
    format text NOT NULL CHECK (format IN ('short', 'long')),
    status text NOT NULL DEFAULT 'IDEA' CHECK (status IN ('IDEA','SCRIPTED','FACT_CHECKED','STORYBOARDED','ASSETS_READY',
        'RENDERED','AWAITING_APPROVAL','APPROVED','PUBLISHED','REJECTED','FAILED')),
    title text NOT NULL DEFAULT '',
    description text NOT NULL DEFAULT '',
    tags jsonb NOT NULL DEFAULT '[]',
    privacy text NOT NULL DEFAULT 'private' CHECK (privacy IN ('private', 'unlisted', 'public')),
    qa_report jsonb,
    schema_version int NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX videos_status_idx ON studio.videos (status);

CREATE TABLE studio.scripts (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    version int NOT NULL CHECK (version >= 1),
    text text NOT NULL,
    claim_ids jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (video_id, version)
);

CREATE TABLE studio.assets (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    kind text NOT NULL CHECK (kind IN ('image', 'voice', 'music', 'clip', 'thumbnail')),
    cache_key text NOT NULL UNIQUE CHECK (cache_key ~ '^[0-9a-f]{64}$'),
    path text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    license text NOT NULL CHECK (license <> ''),
    cost_usd numeric(12,6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE studio.scenes (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    idx int NOT NULL CHECK (idx >= 0),
    narration text NOT NULL,
    caption text NOT NULL DEFAULT '',
    label text NOT NULL DEFAULT '',
    image_prompt text NOT NULL,
    asset_id text REFERENCES studio.assets(id) ON DELETE RESTRICT,
    duration_s real CHECK (duration_s >= 0),
    UNIQUE (video_id, idx)
);

CREATE TABLE studio.render_jobs (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    attempt int NOT NULL DEFAULT 1 CHECK (attempt >= 1),
    input_hash text NOT NULL DEFAULT '',
    output_asset_id text REFERENCES studio.assets(id) ON DELETE RESTRICT,
    error text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE studio.publications (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    video_id text NOT NULL UNIQUE REFERENCES studio.videos(id) ON DELETE RESTRICT,
    youtube_video_id text,
    upload_uri text,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'UPLOADING', 'UPLOADED', 'FAILED')),
    publish_at timestamptz,
    privacy text NOT NULL DEFAULT 'private' CHECK (privacy IN ('private', 'unlisted', 'public')),
    thumbnail_set boolean NOT NULL DEFAULT false,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE studio.source_snapshots (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    video_id text REFERENCES studio.videos(id) ON DELETE RESTRICT,
    url text NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    text text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE studio.step_runs (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    step text NOT NULL,
    attempt int NOT NULL CHECK (attempt >= 1),
    status text NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    input_hash text NOT NULL DEFAULT '',
    error_class text,
    error_message text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE (video_id, step, attempt)
);

CREATE TABLE studio.usage_ledger (
    id bigserial PRIMARY KEY,
    video_id text REFERENCES studio.videos(id) ON DELETE RESTRICT,
    step text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    input_tokens int CHECK (input_tokens >= 0),
    output_tokens int CHECK (output_tokens >= 0),
    cache_read_tokens int CHECK (cache_read_tokens >= 0),
    cache_write_tokens int CHECK (cache_write_tokens >= 0),
    cost_usd numeric(12,6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE studio.video_metrics (
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    date date NOT NULL,
    views bigint,
    estimated_minutes_watched double precision,
    average_view_duration_s double precision,
    average_view_percentage double precision,
    likes bigint,
    comments bigint,
    shares bigint,
    subscribers_gained bigint,
    PRIMARY KEY (video_id, date)
);
