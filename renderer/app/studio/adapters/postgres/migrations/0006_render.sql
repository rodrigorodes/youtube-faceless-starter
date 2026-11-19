-- P04: o vídeo final é um asset (kind 'video') e só pode haver um job de render ativo por vídeo.
ALTER TABLE studio.assets DROP CONSTRAINT assets_kind_check;
ALTER TABLE studio.assets ADD CONSTRAINT assets_kind_check CHECK (kind IN ('image', 'voice', 'music', 'clip', 'video', 'thumbnail'));
CREATE UNIQUE INDEX uq_render_jobs_active ON studio.render_jobs (video_id) WHERE status IN ('QUEUED', 'RUNNING');
CREATE INDEX ix_render_jobs_video ON studio.render_jobs (video_id, created_at DESC);
