-- F8: publicação resiliente — intenção imutável de publicação, retry/backoff, DLQ e reconciliação.
-- A intenção é gravada na MESMA transação da aprovação: render_id/checksum não mudam depois.
CREATE TABLE studio.publication_intents (
    video_id text PRIMARY KEY REFERENCES studio.videos(id) ON DELETE RESTRICT,
    render_id text NOT NULL CHECK (render_id ~ '^[0-9a-f]{32}$'),
    media_checksum text NOT NULL CHECK (media_checksum ~ '^[0-9a-f]{64}$'),
    output_asset_id text NOT NULL REFERENCES studio.assets(id) ON DELETE RESTRICT,
    qa_passed boolean NOT NULL,
    qa_override boolean NOT NULL DEFAULT false,
    visibility text NOT NULL CHECK (visibility IN ('private', 'unlisted', 'public')),
    public_confirmed boolean NOT NULL DEFAULT false,
    idempotency_key text NOT NULL UNIQUE CHECK (idempotency_key ~ '^[a-z0-9.:_-]{1,200}$'),
    approved_at timestamptz NOT NULL DEFAULT now(),
    CHECK (visibility <> 'public' OR public_confirmed)
);

ALTER TABLE studio.publications
    ADD COLUMN render_id text CHECK (render_id IS NULL OR render_id ~ '^[0-9a-f]{32}$'),
    ADD COLUMN media_checksum text CHECK (media_checksum IS NULL OR media_checksum ~ '^[0-9a-f]{64}$'),
    ADD COLUMN idempotency_key text UNIQUE CHECK (idempotency_key IS NULL OR idempotency_key ~ '^[a-z0-9.:_-]{1,200}$'),
    ADD COLUMN visibility text NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'unlisted', 'public')),
    ADD COLUMN public_confirmed boolean NOT NULL DEFAULT false,
    ADD COLUMN offset_bytes bigint NOT NULL DEFAULT 0 CHECK (offset_bytes >= 0),
    ADD COLUMN next_attempt_at timestamptz,
    ADD COLUMN failure_class text CHECK (failure_class IN ('TRANSIENT', 'PERMANENT', 'AMBIGUOUS')),
    ADD COLUMN dead_letter boolean NOT NULL DEFAULT false,
    ADD COLUMN remote_state text CHECK (remote_state IN ('NONE', 'SESSION', 'UNKNOWN', 'UPLOADED')),
    ADD CONSTRAINT publications_public_needs_confirmation CHECK (visibility <> 'public' OR public_confirmed);

CREATE INDEX ix_publications_retry_due
    ON studio.publications (next_attempt_at)
    WHERE status IN ('PENDING', 'FAILED') AND NOT dead_letter;