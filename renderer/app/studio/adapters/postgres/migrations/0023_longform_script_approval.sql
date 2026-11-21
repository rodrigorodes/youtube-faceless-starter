-- F4: roteiro longo versionado com plano/hash e aprovação humana presa à versão.
-- O plano/hash vivem em tabela própria ligada a (video_id, version) para não alterar
-- o contrato exportado de `scripts`; a aprovação é gravada por versão e nunca transferida.
CREATE TABLE studio.script_plans (
    video_id text NOT NULL,
    version int NOT NULL CHECK (version >= 1),
    structure jsonb NOT NULL,
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    words_per_minute numeric(6,2) NOT NULL CHECK (words_per_minute > 0),
    target_seconds numeric(8,2) NOT NULL CHECK (target_seconds > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (video_id, version),
    FOREIGN KEY (video_id, version) REFERENCES studio.scripts(video_id, version) ON DELETE CASCADE
);

CREATE TABLE studio.script_approvals (
    video_id text NOT NULL,
    version int NOT NULL CHECK (version >= 1),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reason text NOT NULL DEFAULT '',
    approved_by text NOT NULL CHECK (btrim(approved_by) <> ''),
    approved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (video_id, version),
    CHECK (decision <> 'rejected' OR btrim(reason) <> ''),
    FOREIGN KEY (video_id, version) REFERENCES studio.scripts(video_id, version) ON DELETE CASCADE
);
