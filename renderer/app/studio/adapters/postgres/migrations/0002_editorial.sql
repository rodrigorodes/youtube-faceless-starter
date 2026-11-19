-- P02: checagem factual, claims por cena e snapshots únicos.
CREATE TABLE studio.fact_checks (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    passed boolean NOT NULL,
    overridden boolean NOT NULL DEFAULT false,
    override_reason text,
    report jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT overridden OR length(btrim(coalesce(override_reason, ''))) > 0)
);
CREATE INDEX fact_checks_video_idx ON studio.fact_checks (video_id, created_at DESC);

ALTER TABLE studio.scenes ADD COLUMN claim_ids jsonb NOT NULL DEFAULT '[]';

CREATE UNIQUE INDEX source_snapshots_unique ON studio.source_snapshots (video_id, url, content_sha256);
