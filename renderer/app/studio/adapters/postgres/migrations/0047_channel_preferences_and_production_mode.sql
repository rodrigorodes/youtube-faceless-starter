-- 0047: Preferências padrão do canal (modo de produção e formato) e modo de produção registrado no vídeo.
-- Transacionalidade e idempotência de criação de canal completo.

ALTER TABLE studio.channel_profiles
    ADD COLUMN default_mode text NOT NULL DEFAULT 'piloto' CHECK (default_mode IN ('piloto', 'diretor')),
    ADD COLUMN default_format text NOT NULL DEFAULT 'short' CHECK (default_format IN ('short', 'long'));

ALTER TABLE studio.videos
    ADD COLUMN production_mode text NOT NULL DEFAULT 'piloto' CHECK (production_mode IN ('piloto', 'diretor'));

CREATE TABLE studio.channel_creation_requests (
    idempotency_key text PRIMARY KEY CHECK (idempotency_key ~ '^[a-z0-9._:-]{1,200}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE CASCADE,
    request_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
