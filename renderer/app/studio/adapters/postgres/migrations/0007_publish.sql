-- P05: decisão humana auditada e fila de publicação com lease.
CREATE TABLE studio.approvals (
    video_id text PRIMARY KEY REFERENCES studio.videos(id) ON DELETE RESTRICT,
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reason text NOT NULL DEFAULT '',
    qa_override boolean NOT NULL DEFAULT false,
    publish_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT qa_override OR reason !~ '^\s*$')
);
ALTER TABLE studio.publications
    ADD COLUMN attempt int NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    ADD COLUMN lease_until timestamptz,
    ADD CONSTRAINT publications_uploaded_has_id CHECK (status <> 'UPLOADED' OR youtube_video_id IS NOT NULL),
    ADD CONSTRAINT publications_youtube_id_format CHECK (youtube_video_id IS NULL OR youtube_video_id ~ '^[A-Za-z0-9_-]{11}$');
CREATE UNIQUE INDEX uq_publications_youtube_id ON studio.publications (youtube_video_id) WHERE youtube_video_id IS NOT NULL;
