-- Perfil de canal (multi-canal): um canal é um projeto e tem no máximo um perfil.
-- O estado atual fica em `channel_profiles`; cada criação/atualização grava um snapshot
-- imutável em `channel_profile_revisions`, o que torna a configuração versionada e auditável.
CREATE TABLE studio.channel_profiles (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    -- unicidade do identificador do canal: um perfil por projeto
    project_id text NOT NULL UNIQUE REFERENCES studio.projects(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(name) >= 1 AND length(name) <= 120),
    strategy text NOT NULL DEFAULT '' CHECK (length(strategy) <= 500),
    language text NOT NULL DEFAULT 'pt-BR' CHECK (length(language) >= 2 AND length(language) <= 20),
    audience text NOT NULL DEFAULT '' CHECK (length(audience) <= 500),
    pillars text[] NOT NULL DEFAULT '{}' CHECK (cardinality(pillars) <= 20),
    narrative text NOT NULL DEFAULT '' CHECK (length(narrative) <= 4000),
    target_duration_s integer NOT NULL DEFAULT 60 CHECK (target_duration_s >= 1 AND target_duration_s <= 36000),
    visual_identity text NOT NULL DEFAULT '' CHECK (length(visual_identity) <= 2000),
    voice text NOT NULL DEFAULT '' CHECK (length(voice) <= 200),
    audio text NOT NULL DEFAULT '' CHECK (length(audio) <= 200),
    thumbnail text NOT NULL DEFAULT '' CHECK (length(thumbnail) <= 2000),
    cta text NOT NULL DEFAULT '' CHECK (length(cta) <= 500),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    archived boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- A listagem de canais ativos ordena por nome: índice parcial evita varrer os arquivados.
CREATE INDEX channel_profiles_active_name_idx ON studio.channel_profiles (name) WHERE archived = false;

CREATE TABLE studio.channel_profile_revisions (
    profile_id text NOT NULL REFERENCES studio.channel_profiles(id) ON DELETE CASCADE,
    version integer NOT NULL CHECK (version >= 1),
    snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, version)
);
