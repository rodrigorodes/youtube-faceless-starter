-- W4.2 / ADR-002 (P-04): reabrir vídeo aprovado e não publicado para edição.
--
-- A aprovação deixa de valer para a nova revisão: a linha ativa de `approvals` e a intenção
-- de publicação (`publication_intents`) são MOVIDAS para `approval_history` na mesma
-- transação. Nada é apagado nem reescrito: o histórico guarda render_id, checksum, QA e os
-- metadados exatamente como estavam. A publicação concluída (UPLOADED/PUBLISHED) continua
-- intocável; só a publicação que nunca subiu (PENDING/FAILED/UPLOADING sem upload) é marcada
-- como invalidada, preservando a linha e o `attempt`.
CREATE TABLE studio.approval_history (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    previous_status text NOT NULL CHECK (previous_status IN ('APPROVED', 'PUBLISHED')),
    decision text CHECK (decision IN ('approved', 'rejected')),
    reason text NOT NULL DEFAULT '',
    qa_override boolean NOT NULL DEFAULT false,
    publish_at timestamptz,
    output_asset_id text REFERENCES studio.assets(id) ON DELETE RESTRICT,
    render_id text CHECK (render_id IS NULL OR render_id ~ '^[0-9a-f]{32}$'),
    media_checksum text CHECK (media_checksum IS NULL OR media_checksum ~ '^[0-9a-f]{64}$'),
    qa_passed boolean,
    intent_qa_override boolean,
    visibility text CHECK (visibility IS NULL OR visibility IN ('private', 'unlisted', 'public')),
    public_confirmed boolean,
    idempotency_key text,
    qa_report jsonb,
    approved_at timestamptz,
    archived_at timestamptz NOT NULL DEFAULT now(),
    archive_reason text NOT NULL DEFAULT 'reopen_for_editing'
);
CREATE INDEX ix_approval_history_video ON studio.approval_history (video_id, archived_at DESC);

-- A linha de publicação que nunca subiu não é apagada: fica fora do caminho ativo e preserva
-- o histórico (id, attempt, upload_uri e o que já tiver sido registrado).
ALTER TABLE studio.publications
    ADD COLUMN invalidated_at timestamptz,
    ADD COLUMN invalidation_reason text;
ALTER TABLE studio.publications DROP CONSTRAINT publications_video_id_key;
CREATE UNIQUE INDEX uq_publications_active_video ON studio.publications (video_id) WHERE invalidated_at IS NULL;
