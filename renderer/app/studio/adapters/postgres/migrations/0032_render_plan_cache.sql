-- RP-06 (fatia 7): versionamento do Render Plan (RP-027) e índice de cache da regeneração
-- seletiva (RP-028/RP-029). Migração **aditiva**: nenhuma tabela existente muda e nenhum
-- caminho antigo é removido. Aplique-a antes do código que a usa (o código antigo a ignora).
--
-- Identidade **lógica** (plano/revisão/cena/shot) mora em `render_plans` (o documento por
-- revisão) e em `render_cache_entries` (o nó por tipo/chave). Identidade **física**
-- (hash/codec/localização) mora em `plan_artifacts`. As duas nunca se confundem (design §5.5).
CREATE TABLE studio.render_plans (
    plan_id text NOT NULL CHECK (length(plan_id) BETWEEN 1 AND 200 AND btrim(plan_id) <> ''),
    revision integer NOT NULL CHECK (revision >= 1),
    schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version >= 1),
    project_id text NOT NULL CHECK (length(project_id) BETWEEN 1 AND 200 AND btrim(project_id) <> ''),
    -- Integridade referencial: o plano pertence a um vídeo real. RESTRICT preserva a revisão.
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    -- O documento canônico da revisão. Guardar o JSONB versionado evita "segunda verdade" no schema.
    document jsonb NOT NULL CHECK (jsonb_typeof(document) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (plan_id, revision)
);

-- Registro físico por hash/codec/localização: um artefato é o mesmo independente da revisão que o
-- referenciou. `location` distingue o mesmo conteúdo em pontos diferentes do armazenamento.
CREATE TABLE studio.plan_artifacts (
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    location text NOT NULL CHECK (length(location) BETWEEN 1 AND 2000 AND btrim(location) <> ''),
    codec text CHECK (codec IS NULL OR (length(codec) BETWEEN 1 AND 100 AND btrim(codec) <> '')),
    media_type text CHECK (media_type IS NULL OR media_type IN ('image', 'video', 'graphic', 'text')),
    byte_size bigint CHECK (byte_size IS NULL OR byte_size >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (content_sha256, location)
);

-- Artefato produzido por um nó lógico numa revisão: é o índice que responde "posso reusar?".
-- A mesma chave lógica pode ter várias linhas (uma por fingerprint histórico); `entries()` lê a
-- de maior revisão. O fingerprint é o hash do conteúdo do nó — não a revisão.
CREATE TABLE studio.render_cache_entries (
    plan_id text NOT NULL,
    revision integer NOT NULL CHECK (revision >= 1),
    node_kind text NOT NULL CHECK (node_kind IN ('narration', 'visual', 'music', 'concat', 'final')),
    node_key text NOT NULL CHECK (length(node_key) BETWEEN 1 AND 200 AND btrim(node_key) <> ''),
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    artifact_sha256 text NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    artifact_uri text NOT NULL CHECK (length(artifact_uri) BETWEEN 1 AND 2000 AND btrim(artifact_uri) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (plan_id, node_kind, node_key, fingerprint),
    -- O artefato pertence a uma revisão persistida: nada de cache apontando para plano inexistente.
    FOREIGN KEY (plan_id, revision) REFERENCES studio.render_plans(plan_id, revision) ON DELETE RESTRICT
);

-- Leitura quente: o último artefato por nó de um plano (índice cobre o DISTINCT ON).
CREATE INDEX render_cache_entries_latest_idx
    ON studio.render_cache_entries (plan_id, node_kind, node_key, revision DESC);

-- Rollback manual (ordem reversa das FKs; o DELETE em schema_migrations é obrigatório, senão
-- migrate() considera a versão aplicada e nunca recria as tabelas):
--   DROP TABLE studio.render_cache_entries;
--   DROP TABLE studio.plan_artifacts;
--   DROP TABLE studio.render_plans;
--   DELETE FROM studio.schema_migrations WHERE version = '0032_render_plan_cache';
