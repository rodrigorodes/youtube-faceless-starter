-- ===========================================================================
-- Faceless Studio — DDL consolidado do schema `studio`
--
-- Gerado por scripts/export_schema.py a partir de migrations/*.sql. NÃO EDITE À MÃO.
-- As migrações aparecem em ordem de aplicação e VERBATIM: este é o SQL que cria o
-- schema, na mesma ordem em que db.migrate() o executa (uma transação por arquivo).
--
-- Migrações: 36 (0001_init … 0041_production_run_operation)
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 0001_init.sql
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 0002_editorial.sql
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 0003_fact_check_version.sql
-- ---------------------------------------------------------------------------
-- P02: o relatório de checagem guarda a versão do roteiro que foi checada (auditável na P05).
ALTER TABLE studio.fact_checks ADD COLUMN script_version int CHECK (script_version >= 1);

-- ---------------------------------------------------------------------------
-- 0004_asset_credits.sql
-- ---------------------------------------------------------------------------
-- P03: atribuição e origem do asset; licença não pode ser só espaços.
ALTER TABLE studio.assets
    ADD COLUMN attribution text NOT NULL DEFAULT '',
    ADD COLUMN source_url text NOT NULL DEFAULT '',
    ADD CONSTRAINT assets_license_nonblank CHECK (btrim(license) <> '');

-- ---------------------------------------------------------------------------
-- 0005_license_nonblank.sql
-- ---------------------------------------------------------------------------
-- P03 (revisão): licença só com tab/quebra de linha também é branco (btrim só aparava espaços).
ALTER TABLE studio.assets DROP CONSTRAINT assets_license_nonblank;
ALTER TABLE studio.assets ADD CONSTRAINT assets_license_nonblank CHECK (license !~ '^\s*$');

-- ---------------------------------------------------------------------------
-- 0006_render.sql
-- ---------------------------------------------------------------------------
-- P04: o vídeo final é um asset (kind 'video') e só pode haver um job de render ativo por vídeo.
ALTER TABLE studio.assets DROP CONSTRAINT assets_kind_check;
ALTER TABLE studio.assets ADD CONSTRAINT assets_kind_check CHECK (kind IN ('image', 'voice', 'music', 'clip', 'video', 'thumbnail'));
CREATE UNIQUE INDEX uq_render_jobs_active ON studio.render_jobs (video_id) WHERE status IN ('QUEUED', 'RUNNING');
CREATE INDEX ix_render_jobs_video ON studio.render_jobs (video_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 0007_publish.sql
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 0008_publication_attempt_base.sql
-- ---------------------------------------------------------------------------
-- O identificador da tentativa nunca é reutilizado; o limite reinicia em retry manual.
ALTER TABLE studio.publications ADD COLUMN attempt_base integer NOT NULL DEFAULT 0;
ALTER TABLE studio.publications ADD CONSTRAINT publications_attempt_base_valid
    CHECK (attempt_base >= 0 AND attempt_base <= attempt);

-- ---------------------------------------------------------------------------
-- 0010_approval_render.sql
-- ---------------------------------------------------------------------------
-- NULL identifica decisões legadas sem render comprovado; elas não podem ser publicadas.
ALTER TABLE studio.approvals
    ADD COLUMN output_asset_id text REFERENCES studio.assets(id) ON DELETE RESTRICT;

-- ---------------------------------------------------------------------------
-- 0011_trends.sql
-- ---------------------------------------------------------------------------
-- Armazenamento verificado de temas em alta por projeto e janela temporal.
CREATE TABLE studio.trend_topics (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE RESTRICT,
    topic text NOT NULL CHECK (length(topic) BETWEEN 3 AND 300),
    topic_key text NOT NULL CHECK (length(topic_key) >= 1),
    source_name text NOT NULL CHECK (length(source_name) BETWEEN 1 AND 80),
    source_url text NOT NULL CHECK (source_url ~ '^https://'),
    observed_at timestamptz NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    metric_name text,
    metric_value double precision CHECK (metric_value >= 0),
    evidence jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, topic_key, source_name, window_end)
);
CREATE INDEX trend_topics_project_window_idx ON studio.trend_topics (project_id, window_end DESC);

-- ---------------------------------------------------------------------------
-- 0012_categories.sql
-- ---------------------------------------------------------------------------
-- Categorias fixas (pilares de conteúdo) por projeto e vinculação de tendências.
CREATE TABLE studio.project_categories (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(name) >= 1 AND length(name) <= 100),
    queries text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, name)
);

CREATE INDEX project_categories_project_id_idx ON studio.project_categories (project_id);

ALTER TABLE studio.trend_topics
    ADD COLUMN category_id text REFERENCES studio.project_categories(id) ON DELETE SET NULL;

CREATE INDEX trend_topics_category_id_idx ON studio.trend_topics (category_id);

-- ---------------------------------------------------------------------------
-- 0013_budget_reservations.sql
-- ---------------------------------------------------------------------------
-- Uma reserva permanece ativa enquanto não houver reconciliação implementada.
CREATE TABLE studio.budget_reservations (
    idempotency_key text PRIMARY KEY CHECK (length(idempotency_key) > 0),
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    amount_usd numeric NOT NULL CHECK (amount_usd >= 0 AND amount_usd < 'Infinity'::numeric),
    monthly_limit_usd numeric NOT NULL CHECK (monthly_limit_usd >= 0 AND monthly_limit_usd < 'Infinity'::numeric),
    video_limit_usd numeric NOT NULL CHECK (video_limit_usd >= 0 AND video_limit_usd < 'Infinity'::numeric),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX budget_reservations_video_idx ON studio.budget_reservations(video_id);

-- Escritas legadas do ledger participam do mesmo lock da verificação/reserva.
CREATE FUNCTION studio.lock_budget_ledger() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(726002);
    RETURN NULL;
END;
$$;
CREATE TRIGGER usage_ledger_budget_lock
    BEFORE INSERT OR UPDATE OR DELETE ON studio.usage_ledger
    FOR EACH STATEMENT EXECUTE FUNCTION studio.lock_budget_ledger();

-- ---------------------------------------------------------------------------
-- 0014_ledger_cost_evidence.sql
-- ---------------------------------------------------------------------------
-- Zero legado pode significar custo desconhecido. Só uma confirmação explícita
-- com evidência permite tratá-lo como gratuito; nada é presumido na migração.
ALTER TABLE studio.usage_ledger
    ADD COLUMN cost_zero_evidence text,
    ADD CONSTRAINT usage_ledger_zero_evidence_check
        CHECK (cost_zero_evidence IS NULL OR
               (cost_usd = 0 AND cost_zero_evidence ~ '[^[:space:]]'));

-- ---------------------------------------------------------------------------
-- 0015_ledger_cost_confirmation.sql
-- ---------------------------------------------------------------------------
-- Nenhum lançamento legado é promovido automaticamente a confirmado.
ALTER TABLE studio.usage_ledger
    ADD COLUMN cost_confirmation_kind text,
    ADD COLUMN cost_confirmed_amount numeric(12,6),
    ADD COLUMN cost_confirmation_reference text,
    ADD COLUMN cost_confirmed_by text,
    ADD COLUMN cost_confirmed_at timestamptz,
    ADD CONSTRAINT usage_ledger_cost_confirmation_check CHECK (
        (cost_confirmation_kind IS NULL AND cost_confirmed_amount IS NULL
         AND cost_confirmation_reference IS NULL AND cost_confirmed_by IS NULL
         AND cost_confirmed_at IS NULL)
        OR
        (cost_confirmation_kind IS NOT NULL AND cost_confirmed_amount IS NOT NULL
         AND cost_confirmation_reference IS NOT NULL AND cost_confirmed_by IS NOT NULL
         AND cost_confirmed_at IS NOT NULL
         AND cost_confirmation_reference ~ '[^[:space:]]'
         AND cost_confirmed_by ~ '[^[:space:]]'
         AND cost_usd <> 'NaN'::numeric AND cost_confirmed_amount = cost_usd
         AND ((cost_confirmation_kind = 'ACTUAL' AND cost_usd > 0)
              OR (cost_confirmation_kind = 'FREE' AND cost_usd = 0)))
    );

-- ---------------------------------------------------------------------------
-- 0016_channel_profiles.sql
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 0017_paid_operations.sql
-- ---------------------------------------------------------------------------
-- Intenção de operação paga, ligada 1:1 à reserva ativa (mesma idempotency_key).
-- A reserva (studio.budget_reservations) bloqueia orçamento enquanto ativa; confirmar ou liberar
-- remove a reserva. O estado é persistido para que replay não reexecute a chamada paga.
-- Um resultado ambíguo permanece UNCERTAIN com a reserva ativa até reconciliação explícita.
CREATE TABLE studio.paid_operations (
    idempotency_key text PRIMARY KEY CHECK (length(idempotency_key) > 0),
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    estimate_usd numeric NOT NULL CHECK (estimate_usd >= 0 AND estimate_usd < 'Infinity'::numeric),
    monthly_limit_usd numeric NOT NULL CHECK (monthly_limit_usd >= 0 AND monthly_limit_usd < 'Infinity'::numeric),
    video_limit_usd numeric NOT NULL CHECK (video_limit_usd >= 0 AND video_limit_usd < 'Infinity'::numeric),
    state text NOT NULL CHECK (state IN ('RESERVED', 'CONFIRMED', 'RELEASED', 'UNCERTAIN')),
    confirmed_kind text CHECK (confirmed_kind IN ('ACTUAL', 'FREE')),
    confirmed_amount_usd numeric(12,6),
    ledger_id bigint REFERENCES studio.usage_ledger(id) ON DELETE RESTRICT,
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT paid_operations_settlement_check CHECK (
        (state = 'RESERVED' AND confirmed_kind IS NULL AND confirmed_amount_usd IS NULL
         AND ledger_id IS NULL AND reason IS NULL)
        OR
        (state = 'CONFIRMED' AND confirmed_kind IS NOT NULL AND confirmed_amount_usd IS NOT NULL
         AND ledger_id IS NOT NULL AND reason IS NULL
         AND ((confirmed_kind = 'ACTUAL' AND confirmed_amount_usd > 0)
              OR (confirmed_kind = 'FREE' AND confirmed_amount_usd = 0)))
        OR
        (state IN ('RELEASED', 'UNCERTAIN') AND confirmed_kind IS NULL AND confirmed_amount_usd IS NULL
         AND ledger_id IS NULL AND reason IS NOT NULL AND reason ~ '[^[:space:]]')
    )
);
CREATE INDEX paid_operations_video_idx ON studio.paid_operations(video_id);
CREATE INDEX paid_operations_state_idx ON studio.paid_operations(state);

-- ---------------------------------------------------------------------------
-- 0018_production_runs.sql
-- ---------------------------------------------------------------------------
-- Execução de produção (F1-01/F1-02/F1-06): run idempotente, etapas com lease/fencing e outbox.
-- Migração aditiva: nenhuma tabela existente muda. Aplique-a antes de implantar o código que a usa
-- (o código antigo ignora as tabelas novas). Rollback manual no fim deste arquivo.
CREATE TABLE studio.production_runs (
    run_id text PRIMARY KEY CHECK (run_id ~ '^[0-9a-f]{32}$'),
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    -- Perfil de canal opcional (um canal é um projeto). RESTRICT preserva a trilha da execução.
    channel_id text REFERENCES studio.channel_profiles(id) ON DELETE RESTRICT,
    -- Uma execução por chave: replay devolve a execução existente, nunca cria a segunda.
    -- Defesa em profundidade: o banco repete a whitelist canônica do domínio. O regex ASCII
    -- minúsculo implica NFC, sem espaço/controle/invisível e sem variantes de caixa, fullwidth ou
    -- homóglifos; um INSERT direto fora da forma é recusado.
    idempotency_key text NOT NULL UNIQUE
        CHECK (length(idempotency_key) BETWEEN 1 AND 200 AND idempotency_key ~ '^[a-z0-9._:-]+$'),
    state text NOT NULL DEFAULT 'CREATED'
        CHECK (state IN ('CREATED', 'RUNNING', 'WAITING_HUMAN', 'PAUSED', 'FAILED', 'CANCELLED', 'SUCCEEDED')),
    reason text CHECK (reason IS NULL OR (length(reason) BETWEEN 1 AND 2000 AND btrim(reason) <> '')),
    schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version >= 1),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    -- Pausa humana, falha e cancelamento são persistidos com motivo; os demais estados não exigem.
    CONSTRAINT production_runs_terminal_reason_check CHECK (
        state NOT IN ('WAITING_HUMAN', 'FAILED', 'CANCELLED')
        OR (reason IS NOT NULL AND btrim(reason) <> '')
    )
);
-- Sem índice extra em production_runs: as consultas atuais usam a PK (`run_id`); `video_id` ainda
-- não é filtro de nenhuma consulta do repositório e a coluna é coberta pela FK. Um índice para
-- vídeo/lease entra junto da consulta que o usar (D2/painel), não antes.

CREATE TABLE studio.stage_executions (
    run_id text NOT NULL REFERENCES studio.production_runs(run_id) ON DELETE CASCADE,
    stage_id text NOT NULL CHECK (stage_id IN ('research', 'script', 'factcheck', 'storyboard', 'assets',
                                               'render', 'qa', 'approval', 'publish')),
    state text NOT NULL DEFAULT 'PENDING'
        CHECK (state IN ('PENDING', 'RUNNING', 'WAITING_HUMAN', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'SKIPPED')),
    attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    lease_owner text CHECK (lease_owner IS NULL OR length(lease_owner) BETWEEN 1 AND 200),
    lease_expires_at timestamptz,
    -- Monotônico por etapa: o novo dono incrementa; o dono antigo não escreve mais.
    fencing_token bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    checkpoint jsonb CHECK (checkpoint IS NULL OR jsonb_typeof(checkpoint) = 'object'),
    checkpoint_version integer CHECK (checkpoint_version IS NULL OR checkpoint_version >= 1),
    error text CHECK (error IS NULL OR (length(error) BETWEEN 1 AND 2000 AND btrim(error) <> '')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, stage_id),
    -- Só uma etapa RUNNING tem dono e expiração; ao pausar/concluir/falhar o lease é liberado.
    CONSTRAINT stage_executions_lease_check CHECK (
        (state = 'RUNNING' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (state <> 'RUNNING' AND lease_owner IS NULL AND lease_expires_at IS NULL)
    ),
    CONSTRAINT stage_executions_checkpoint_pair_check CHECK (
        (checkpoint IS NULL AND checkpoint_version IS NULL)
        OR (checkpoint IS NOT NULL AND checkpoint_version IS NOT NULL)
    )
);
-- Nenhum índice de lease: não há varredura por `lease_expires_at` (a etapa é acessada pela PK
-- `(run_id, stage_id)` e a expiração é conferida na própria linha travada). Se D2 introduzir uma
-- consulta de etapa órfã, crie o índice parcial junto dela.

CREATE TABLE studio.production_outbox (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id text NOT NULL REFERENCES studio.production_runs(run_id) ON DELETE CASCADE,
    stage_id text CHECK (stage_id IS NULL OR stage_id IN ('research', 'script', 'factcheck', 'storyboard',
                                                          'assets', 'render', 'qa', 'approval', 'publish')),
    event_type text NOT NULL CHECK (event_type IN ('production.run.created', 'production.run.state_changed',
                                                   'production.stage.claimed', 'production.stage.completed',
                                                   'production.stage.failed', 'production.stage.revoked')),
    event_version integer NOT NULL DEFAULT 1 CHECK (event_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    acked_at timestamptz,
    CONSTRAINT production_outbox_ack_order_check CHECK (acked_at IS NULL OR acked_at >= created_at)
);
-- Consumidores leem só o que ainda não foi confirmado, na ordem de gravação.
CREATE INDEX production_outbox_unacked_idx ON studio.production_outbox (id) WHERE acked_at IS NULL;

-- Rollback manual (seguro enquanto nenhum consumidor depender da outbox; ordem reversa das FKs).
-- O DELETE em schema_migrations é obrigatório: sem ele migrate() considera a versão já aplicada e
-- nunca recria as tabelas.
--   DROP TABLE studio.production_outbox;
--   DROP TABLE studio.stage_executions;
--   DROP TABLE studio.production_runs;
--   DELETE FROM studio.schema_migrations WHERE version = '0018_production_runs';

-- ---------------------------------------------------------------------------
-- 0019_ledger_estimate_and_attribution.sql
-- ---------------------------------------------------------------------------
-- ESTIMATE: custo estimado, sem evidência de cobrança (ex.: preço configurável por imagem).
-- Conta como gasto aproximado no teto — não como desconhecido — e a reconciliação o troca por ACTUAL.
-- Operações pagas e reservas sem vídeo (escopo de projeto) passam a ser permitidas.
ALTER TABLE studio.usage_ledger
    DROP CONSTRAINT IF EXISTS usage_ledger_cost_confirmation_check;
ALTER TABLE studio.usage_ledger
    ADD CONSTRAINT usage_ledger_cost_confirmation_check CHECK (
        (cost_confirmation_kind IS NULL AND cost_confirmed_amount IS NULL
         AND cost_confirmation_reference IS NULL AND cost_confirmed_by IS NULL
         AND cost_confirmed_at IS NULL)
        OR
        (cost_confirmation_kind IS NOT NULL AND cost_confirmed_amount IS NOT NULL
         AND cost_confirmation_reference IS NOT NULL AND cost_confirmed_by IS NOT NULL
         AND cost_confirmed_at IS NOT NULL
         AND cost_confirmation_reference ~ '[^[:space:]]'
         AND cost_confirmed_by ~ '[^[:space:]]'
         AND cost_usd <> 'NaN'::numeric AND cost_confirmed_amount = cost_usd
         AND ((cost_confirmation_kind = 'ACTUAL' AND cost_usd > 0)
              OR (cost_confirmation_kind = 'FREE' AND cost_usd = 0)
              OR (cost_confirmation_kind = 'ESTIMATE' AND cost_usd > 0)))
    );

ALTER TABLE studio.paid_operations
    DROP CONSTRAINT IF EXISTS paid_operations_settlement_check;
ALTER TABLE studio.paid_operations
    DROP CONSTRAINT IF EXISTS paid_operations_confirmed_kind_check;
ALTER TABLE studio.paid_operations
    ALTER COLUMN video_id DROP NOT NULL;
ALTER TABLE studio.paid_operations
    ADD CONSTRAINT paid_operations_confirmed_kind_check CHECK (confirmed_kind IN ('ACTUAL', 'FREE', 'ESTIMATE'));
ALTER TABLE studio.paid_operations
    ADD CONSTRAINT paid_operations_settlement_check CHECK (
        (state = 'RESERVED' AND confirmed_kind IS NULL AND confirmed_amount_usd IS NULL
         AND ledger_id IS NULL AND reason IS NULL)
        OR
        (state = 'CONFIRMED' AND confirmed_kind IS NOT NULL AND confirmed_amount_usd IS NOT NULL
         AND ledger_id IS NOT NULL AND reason IS NULL
         AND ((confirmed_kind = 'ACTUAL' AND confirmed_amount_usd > 0)
              OR (confirmed_kind = 'FREE' AND confirmed_amount_usd = 0)
              OR (confirmed_kind = 'ESTIMATE' AND confirmed_amount_usd > 0)))
        OR
        (state IN ('RELEASED', 'UNCERTAIN') AND confirmed_kind IS NULL AND confirmed_amount_usd IS NULL
         AND ledger_id IS NULL AND reason IS NOT NULL AND reason ~ '[^[:space:]]')
    );

-- Reserva sem vídeo: só o teto mensal a limita (escopo de projeto).
ALTER TABLE studio.budget_reservations
    ALTER COLUMN video_id DROP NOT NULL;

-- ---------------------------------------------------------------------------
-- 0020_paid_operation_attempt_and_budget_indexes.sql
-- ---------------------------------------------------------------------------
-- Correção operacional da fatia A.
--
-- I1: `attempt` registra quantas vezes a operação foi reaberta depois de RELEASED (nenhum efeito
-- externo comprovado). CONFIRMED continua terminal; UNCERTAIN continua bloqueado até reconciliação.
-- Invariante de adapter: reabrir RELEASED não recobra porque a reabertura pressupõe que
-- PreEffectFailure só é levantado ANTES de qualquer efeito externo. Nenhum adapter pode levantar
-- PreEffectFailure depois de um efeito pago já ocorrido; se isso mudar, reabrir vira replay pago.
-- ADD COLUMN com default constante é metadata-only no PostgreSQL >= 11, mas ainda toma ACCESS
-- EXCLUSIVE por um instante (bloqueia leitura/escrita enquanto altera o catálogo). O CHECK
-- (attempt >= 1) criado no mesmo ALTER é VALIDADO por varredura completa da tabela sob ACCESS
-- EXCLUSIVE (~55 ms por 1M de linhas); o custo do ADD COLUMN esconde esse scan. Em tabela grande
-- vale o mesmo padrão da 0019: ADD CONSTRAINT ... CHECK (...) NOT VALID (ACCESS EXCLUSIVE breve,
-- sem varredura) + VALIDATE CONSTRAINT em migração separada (SHARE UPDATE EXCLUSIVE).
ALTER TABLE studio.paid_operations
    ADD COLUMN attempt integer NOT NULL DEFAULT 1,
    ADD CONSTRAINT paid_operations_attempt_check CHECK (attempt >= 1);

-- I2/performance: índices das leituras do pré-check do CostGuard e das listagens de reconciliação.
-- NÃO eliminam a varredura de tabela do cálculo do teto: em `_reserve_within` o aggregate de reserva
-- soma `usage_ledger` com predicados de FILTER que dependem de `bounds` (date_trunc), sem predicado
-- empurrável para índice. Medido com ~50k linhas, o plano continua Seq Scan (~11 ms) com e sem estes
-- índices. Usos reais: `usage_ledger_video_id_idx` por `spent_video`; `usage_ledger_created_at_idx`
-- por `spent_month` e `panel.month_usage`; `paid_operations_state_updated_at_idx` pela consulta de
-- operações RESERVED paradas; `budget_reservations_created_at_idx` pela listagem de reservas antigas.
-- CREATE INDEX (sem CONCURRENTLY, que não roda dentro da transação de migração) toma SHARE lock e
-- bloqueia escritas na tabela durante a construção. Com tabela grande, avalie criar o índice
-- CONCURRENTLY fora da transação de migração antes de aplicar esta versão.
CREATE INDEX usage_ledger_created_at_idx ON studio.usage_ledger(created_at);
CREATE INDEX usage_ledger_video_id_idx ON studio.usage_ledger(video_id);
CREATE INDEX budget_reservations_created_at_idx ON studio.budget_reservations(created_at);
CREATE INDEX paid_operations_state_updated_at_idx ON studio.paid_operations(state, updated_at);

-- Nota operacional sobre a 0019 (já aplicada): DROP/ADD CONSTRAINT usage_ledger_cost_confirmation_check
-- rodou na transação da migração com ACCESS EXCLUSIVE e varredura completa de usage_ledger. Numa
-- tabela grande, o padrão seguro é ADD CONSTRAINT ... CHECK (...) NOT VALID (ACCESS EXCLUSIVE
-- breve, sem varredura) e depois VALIDATE CONSTRAINT em migração separada (SHARE UPDATE EXCLUSIVE,
-- permite leituras/escritas). Aqui a tabela ainda é pequena; não foi necessário.
--
-- Rollback manual (não executado automaticamente):
--   DROP INDEX studio.paid_operations_state_updated_at_idx;
--   DROP INDEX studio.budget_reservations_created_at_idx;
--   DROP INDEX studio.usage_ledger_video_id_idx;
--   DROP INDEX studio.usage_ledger_created_at_idx;
--   ALTER TABLE studio.paid_operations DROP CONSTRAINT paid_operations_attempt_check;
--   ALTER TABLE studio.paid_operations DROP COLUMN attempt;

-- ---------------------------------------------------------------------------
-- 0021_channel_pillars_constraints.sql
-- ---------------------------------------------------------------------------
-- Retrofit do limite de pilares do perfil de canal.
--
-- A 0016 antiga (já aplicada em alguns bancos e registrada em schema_migrations) não tem o CHECK
-- de cardinalidade; editar o arquivo daquela migração não alcança esses bancos, porque o migrador
-- pula versões registradas. Esta migração aditiva garante o limite de 20 pilares e recusa elemento
-- NULL em instalações novas e em bancos que já aplicaram a 0016 antiga.
--
-- Idempotente: a 0016 nova já cria `channel_profiles_pillars_check` inline; o guard `IF NOT EXISTS`
-- por nome e tabela evita constraint duplicada. A cláusula `ADD CONSTRAINT` (sem NOT VALID) valida
-- as linhas existentes dentro da transação da migração; a tabela é pequena, mas isso toma um lock
-- ACCESS EXCLUSIVE em `studio.channel_profiles` durante a validação. Se houver linha legada com
-- mais de 20 pilares ou elemento NULL, a migração falha alto (em vez de truncar silenciosamente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'channel_profiles_pillars_check'
          AND conrelid = 'studio.channel_profiles'::regclass
    ) THEN
        ALTER TABLE studio.channel_profiles
            ADD CONSTRAINT channel_profiles_pillars_check CHECK (cardinality(pillars) <= 20);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'channel_profiles_pillars_not_null_check'
          AND conrelid = 'studio.channel_profiles'::regclass
    ) THEN
        ALTER TABLE studio.channel_profiles
            ADD CONSTRAINT channel_profiles_pillars_not_null_check
            CHECK (array_position(pillars, NULL) IS NULL);
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 0022_channel_management.sql
-- ---------------------------------------------------------------------------
-- F10-05/F10-06: budget por canal (hard/soft) e associação de canal YouTube.
-- Segredos NÃO ficam aqui (ver adapter secret_store): só metadados do canal.
CREATE TABLE studio.channel_budgets (
    project_id text PRIMARY KEY REFERENCES studio.projects(id) ON DELETE CASCADE,
    hard_monthly_usd numeric(12,2) NOT NULL CHECK (hard_monthly_usd >= 0),
    soft_monthly_usd numeric(12,2) NOT NULL CHECK (soft_monthly_usd >= 0 AND soft_monthly_usd <= hard_monthly_usd),
    hard_video_usd numeric(12,2) NOT NULL CHECK (hard_video_usd >= 0),
    soft_video_usd numeric(12,2) NOT NULL CHECK (soft_video_usd >= 0 AND soft_video_usd <= hard_video_usd),
    economic_profile text NOT NULL DEFAULT 'BALANCED' CHECK (economic_profile IN ('ECONOMY', 'BALANCED', 'PREMIUM')),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE studio.channel_youtube_channels (
    project_id text PRIMARY KEY REFERENCES studio.projects(id) ON DELETE CASCADE,
    channel_id text NOT NULL CHECK (length(channel_id) BETWEEN 1 AND 128 AND channel_id ~ '^[A-Za-z0-9._-]+$'),
    title text NOT NULL DEFAULT '' CHECK (length(title) <= 200),
    scopes jsonb NOT NULL DEFAULT '[]',
    oauth_status text NOT NULL DEFAULT 'CONNECTED' CHECK (oauth_status IN ('CONNECTED', 'EXPIRED', 'REVOKED', 'ERROR')),
    token_expires_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 0023_longform_script_approval.sql
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 0026_analytics_learning.sql
-- ---------------------------------------------------------------------------
-- F9-01/F9-02/F9-05/F9-06: medição ligada a versões, experimento e decisão de revisão.
--
-- A observação guarda o valor medido OU o motivo de não estar disponível — nunca os dois e
-- nunca zero no lugar de ausência. `script_version` tem FK composta para `scripts(video_id,
-- version)`: versão inventada é recusada pelo banco. `brief_version`/`packaging_version`
-- existem como colunas porque a atribuição já os nomeia; ficam nulos até essas persistências
-- existirem, e `missing_links` registra o motivo de cada ausência.
CREATE TABLE studio.metric_observations (
    observation_id text PRIMARY KEY CHECK (observation_id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE RESTRICT,
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    youtube_video_id text CHECK (youtube_video_id IS NULL OR youtube_video_id ~ '^[A-Za-z0-9_-]{11}$'),
    pillar_id text REFERENCES studio.project_categories(id) ON DELETE SET NULL,
    metric text NOT NULL CHECK (metric IN ('views', 'impressions', 'ctr', 'average_view_percentage',
        'average_view_duration_s', 'estimated_minutes_watched', 'likes', 'comments', 'shares',
        'subscribers_gained')),
    unit text NOT NULL CHECK (btrim(unit) <> ''),
    value double precision,
    unavailable_reason text,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    source text NOT NULL CHECK (btrim(source) <> ''),
    origin text NOT NULL CHECK (origin IN ('youtube_analytics_api', 'unknown_origin')),
    script_version int CHECK (script_version >= 1),
    brief_version int CHECK (brief_version >= 1),
    packaging_version int CHECK (packaging_version >= 1),
    publication_id text REFERENCES studio.publications(id) ON DELETE RESTRICT,
    missing_links jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(missing_links) = 'array'),
    experiment_id text,
    variant_id text,
    collected_at timestamptz NOT NULL,
    CHECK (window_start < window_end),
    CHECK ((value IS NULL) <> (unavailable_reason IS NULL)),
    CHECK (value IS NULL OR (value >= 0 AND value < 'Infinity'::float8 AND value <> 'NaN'::float8)),
    CHECK (youtube_video_id IS NULL OR publication_id IS NOT NULL),
    CHECK ((experiment_id IS NULL) = (variant_id IS NULL)),
    CONSTRAINT metric_observations_script_version_fk
        FOREIGN KEY (video_id, script_version) REFERENCES studio.scripts(video_id, version),
    UNIQUE (video_id, metric, window_start, window_end, source, origin)
);

CREATE INDEX metric_observations_project_window_idx
    ON studio.metric_observations (project_id, window_end DESC);
CREATE INDEX metric_observations_video_metric_idx
    ON studio.metric_observations (video_id, metric, window_start);

-- Histórico de experimentos de thumbnail/título. A API do YouTube Analytics não oferece A/B
-- nesta integração: `platform_ab_supported` é travado em falso e a rotação é manual/aprovada.
CREATE TABLE studio.analytics_experiments (
    experiment_id text PRIMARY KEY CHECK (experiment_id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE RESTRICT,
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN ('thumbnail', 'title')),
    status text NOT NULL CHECK (status IN ('planned', 'running', 'finished', 'abandoned')),
    platform_ab_supported boolean NOT NULL DEFAULT false CHECK (platform_ab_supported = false),
    platform_note text NOT NULL CHECK (btrim(platform_note) <> ''),
    approved_by text NOT NULL CHECK (btrim(approved_by) <> ''),
    approved_at timestamptz NOT NULL DEFAULT now(),
    window_start timestamptz,
    window_end timestamptz,
    conclusion text,
    conclusion_confidence text CHECK (conclusion_confidence IN ('low', 'medium', 'high')),
    conclusion_basis text,
    conclusion_observation_ids text[] NOT NULL DEFAULT '{}',
    concluded_by text,
    concluded_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((window_start IS NULL) = (window_end IS NULL)),
    CHECK (window_start IS NULL OR window_start < window_end),
    CHECK (status NOT IN ('running', 'finished') OR window_start IS NOT NULL),
    CHECK (status <> 'finished' OR (conclusion IS NOT NULL AND conclusion_confidence IS NOT NULL
        AND conclusion_basis IS NOT NULL AND concluded_by IS NOT NULL AND concluded_at IS NOT NULL
        AND cardinality(conclusion_observation_ids) >= 1)),
    CHECK (status = 'finished' OR conclusion IS NULL)
);

CREATE TABLE studio.analytics_experiment_variants (
    experiment_id text NOT NULL REFERENCES studio.analytics_experiments(experiment_id) ON DELETE CASCADE,
    variant_id text NOT NULL CHECK (btrim(variant_id) <> ''),
    label text NOT NULL CHECK (btrim(label) <> ''),
    is_control boolean NOT NULL DEFAULT false,
    PRIMARY KEY (experiment_id, variant_id)
);

-- Um único controle por experimento, garantido pelo banco (o domínio repete a checagem).
CREATE UNIQUE INDEX analytics_experiment_one_control_idx
    ON studio.analytics_experiment_variants (experiment_id) WHERE is_control;

CREATE INDEX analytics_experiments_project_created_idx
    ON studio.analytics_experiments (project_id, created_at DESC);

-- Uma observação ligada a experimento tem de apontar para uma variante real desse experimento.
ALTER TABLE studio.metric_observations
    ADD CONSTRAINT metric_observations_experiment_variant_fk
    FOREIGN KEY (experiment_id, variant_id)
    REFERENCES studio.analytics_experiment_variants (experiment_id, variant_id);

-- Decisão de revisão da recomendação. Não existe "applied": aplicar exige edição manual do
-- perfil do canal em outra tela; esta tabela é só o registro auditável da recusa/aceite.
CREATE TABLE studio.analytics_recommendation_decisions (
    recommendation_id text PRIMARY KEY CHECK (recommendation_id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE RESTRICT,
    decision text NOT NULL CHECK (decision IN ('accepted_for_review', 'rejected')),
    decided_by text NOT NULL CHECK (btrim(decided_by) <> ''),
    decided_at timestamptz NOT NULL DEFAULT now(),
    evidence jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array')
);

CREATE INDEX analytics_recommendation_decisions_project_idx
    ON studio.analytics_recommendation_decisions (project_id, decided_at DESC);

-- ---------------------------------------------------------------------------
-- 0027_saas_multiuser_byok.sql
-- ---------------------------------------------------------------------------
-- F11-01/02/03/04: tenancy modelado (organização, workspace, usuário, vínculo/papel) e metadados de BYOK.
-- O valor da chave NUNCA entra aqui: só máscara, impressão sha256, coordenada do SecretStore e auditoria.
-- O caminho de tenant é anulável e ainda NÃO é aplicado em runtime: o produto segue mono-usuário
-- até existir sessão/OIDC (F11-02). Nenhuma linha existente é migrada para uma organização inventada.

CREATE TABLE studio.organizations (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE studio.workspaces (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    organization_id text NOT NULL REFERENCES studio.organizations(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, name)
);

CREATE TABLE studio.users (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    email text NOT NULL CHECK (email = lower(email) AND length(email) BETWEEN 3 AND 320),
    display_name text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (email)
);

CREATE TABLE studio.memberships (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    organization_id text NOT NULL REFERENCES studio.organizations(id) ON DELETE CASCADE,
    user_id text NOT NULL REFERENCES studio.users(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('owner', 'editor', 'reviewer', 'viewer')),
    status text NOT NULL DEFAULT 'invited' CHECK (status IN ('active', 'invited')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, user_id)
);

CREATE INDEX memberships_org_role_idx ON studio.memberships (organization_id, role);

CREATE TABLE studio.byok_keys (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    organization_id text NOT NULL REFERENCES studio.organizations(id) ON DELETE CASCADE,
    provider text NOT NULL CHECK (provider ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'),
    -- Só a máscara exibível (nunca o valor): termina nos 4 últimos caracteres ou é toda mascarada.
    mask text NOT NULL CHECK (length(mask) BETWEEN 6 AND 32),
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    secret_scope text NOT NULL CHECK (length(secret_scope) BETWEEN 1 AND 200),
    secret_name text NOT NULL CHECK (secret_name ~ '^[A-Za-z0-9._-]+$'),
    created_by text REFERENCES studio.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    rotated_at timestamptz,
    revoked_at timestamptz,
    last_used_at timestamptz,
    CHECK (rotated_at IS NULL OR rotated_at >= created_at)
);

-- Uma chave ativa por provider/organização; revogada libera o provider para uma nova chave.
CREATE UNIQUE INDEX byok_keys_active_provider_idx
    ON studio.byok_keys (organization_id, provider) WHERE revoked_at IS NULL;

CREATE TABLE studio.byok_key_audit (
    id bigserial PRIMARY KEY,
    organization_id text NOT NULL REFERENCES studio.organizations(id) ON DELETE CASCADE,
    key_id text NOT NULL REFERENCES studio.byok_keys(id) ON DELETE CASCADE,
    actor_user_id text REFERENCES studio.users(id) ON DELETE SET NULL,
    action text NOT NULL CHECK (action IN ('created', 'rotated', 'revoked', 'used')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX byok_key_audit_org_idx ON studio.byok_key_audit (organization_id, created_at);

-- Caminho de tenancy nos registros existentes: anulável de propósito (nada é atribuído em massa).
ALTER TABLE studio.projects
    ADD COLUMN organization_id text REFERENCES studio.organizations(id) ON DELETE RESTRICT;
CREATE INDEX projects_organization_idx ON studio.projects (organization_id);

ALTER TABLE studio.usage_ledger
    ADD COLUMN organization_id text REFERENCES studio.organizations(id) ON DELETE SET NULL,
    ADD COLUMN member_id text REFERENCES studio.users(id) ON DELETE SET NULL;
CREATE INDEX usage_ledger_organization_idx ON studio.usage_ledger (organization_id, created_at);

-- ---------------------------------------------------------------------------
-- 0028_publication_resilience.sql
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 0031_membership_audit.sql
-- ---------------------------------------------------------------------------
-- L2: auditoria das mutações de vínculo (Equipe). Registra QUEM mudou o quê.
-- O vínculo pode ser removido depois; por isso membership_id não tem FK (o registro sobrevive).
-- Nenhum segredo entra aqui: só o ator, a ação e o papel resultante/registrado.

CREATE TABLE studio.membership_audit (
    id bigserial PRIMARY KEY,
    organization_id text NOT NULL REFERENCES studio.organizations(id) ON DELETE CASCADE,
    membership_id text NOT NULL CHECK (membership_id ~ '^[0-9a-f]{32}$'),
    actor_user_id text REFERENCES studio.users(id) ON DELETE SET NULL,
    action text NOT NULL CHECK (action IN ('invited', 'role_changed', 'removed')),
    role text CHECK (role IN ('owner', 'editor', 'reviewer', 'viewer')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX membership_audit_org_idx ON studio.membership_audit (organization_id, created_at);

-- ---------------------------------------------------------------------------
-- 0032_render_plan_cache.sql
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 0033_visual_styles.sql
-- ---------------------------------------------------------------------------
-- Estilos visuais do canal (biblioteca compartilhada) — desenho
-- docs/superpowers/specs/2026-11-21-channel-visual-style-design.md (§3)
--
-- Migração **aditiva**: nenhuma tabela existente muda e nenhum caminho antigo é removido.
-- A referência do estilo no canal (`channel_profiles.style_id`) e a resolução no plano vêm
-- nas fatias seguintes (VS-02/VS-03); esta fatia entrega só a biblioteca.
--
-- A biblioteca é **compartilhada**: um estilo é definido uma vez e vários canais apontam para
-- ele. `organization_id` deixa a coluna pronta para a multi-tenancy (hoje vazia/nula: o app é
-- single-tenant, um pool só). O versionamento por snapshot copia o padrão de
-- `channel_profile_revisions`: cada versão guarda o retrato auditável inteiro.
CREATE TABLE studio.visual_styles (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    organization_id text,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    -- Os parâmetros de aparência/som. O documento canônico fica aqui (nunca "segunda verdade"
    -- em colunas): assim a extensão (`extra`) cresce sem migração.
    params jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(params) = 'object'),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    archived boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Um nome ativo por vez (o arquivado libera o nome para reúso) — o produtor não tem dois
-- "Documentário" indistinguíveis na lista.
CREATE UNIQUE INDEX visual_styles_active_name_idx ON studio.visual_styles (lower(btrim(name)))
    WHERE archived = false;

-- Snapshot auditável por versão: o retrato do estilo quando aquela versão valia. É o que permite
-- um vídeo antigo continuar apontando para a versão com que foi renderizado.
CREATE TABLE studio.visual_style_revisions (
    style_id text NOT NULL REFERENCES studio.visual_styles(id) ON DELETE CASCADE,
    version integer NOT NULL CHECK (version >= 1),
    snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (style_id, version)
);

-- ---------------------------------------------------------------------------
-- 0034_channel_style.sql
-- ---------------------------------------------------------------------------
-- VS-02: o canal aponta para o estilo visual (biblioteca compartilhada) — desenho §3.1/§5.
--
-- Migração **aditiva**: coluna anulável, sem backfill. Canal sem estilo continua válido — e o
-- render cai no bundle neutro (`studio-default@1`) enquanto ninguém escolher um estilo.
--
-- `ON DELETE SET NULL`: apagar um estilo **destaca** o canal (não bloqueia) — mais seguro que
-- CASCADE (que apagaria o canal) e que RESTRICT (que impediria limpar a biblioteca). Os estilos
-- são arquivados (soft delete) no uso normal; isto é para a limpeza dura.
ALTER TABLE studio.channel_profiles
    ADD COLUMN style_id text REFERENCES studio.visual_styles(id) ON DELETE SET NULL;

-- Índice parcial: só interessa saber quais canais apontam para um estilo (e é o caminho raro).
CREATE INDEX channel_profiles_style_idx ON studio.channel_profiles (style_id) WHERE style_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 0035_youtube_identity.sql
-- ---------------------------------------------------------------------------
-- Identidade de publicação do YouTube: conta → autorizações → canais (YT-01).
-- Desenho: docs/superpowers/specs/2026-11-21-youtube-account-grants-design.md
--
-- Migração **aditiva**: não remove `channel_youtube_channels` (o caminho atual continua de pé
-- até a fatia que religa a publicação). O modelo novo separa quatro coisas que hoje são uma só:
--   GoogleAccount        — a identidade (e-mail); não é dona da autorização.
--   OAuthGrant           — a autorização independente (escopos/status/expiração; tokens no vault).
--   YouTubeChannel       — a identidade oficial do canal (`UC...`), distinta da conta.
--   ChannelAuthorization — o vínculo **validado** entre uma autorização e um canal.
--
-- O princípio: cada canal publicado tem uma autorização validada para ele; nunca se presume
-- que uma autorização seja intercambiável entre canais.
CREATE TABLE studio.google_accounts (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    email text NOT NULL CHECK (length(btrim(email)) BETWEEN 3 AND 320),
    display_name text NOT NULL DEFAULT '' CHECK (length(display_name) <= 200),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Uma conta por e-mail (sem distinguir caixa): conectar de novo atualiza, não duplica.
CREATE UNIQUE INDEX google_accounts_email_idx ON studio.google_accounts (lower(btrim(email)));

-- Autorização independente. Os tokens (access/refresh) ficam no vault, com escopo próprio
-- (`oauth_grant:{id}`); aqui só metadados. `status` é o estado declarado; o efetivo é derivado
-- na leitura (sem credencial → DISCONNECTED; vencido → EXPIRED; revogado → REVOKED).
CREATE TABLE studio.oauth_grants (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    account_id text NOT NULL REFERENCES studio.google_accounts(id) ON DELETE CASCADE,
    scopes jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(scopes) = 'array'),
    status text NOT NULL DEFAULT 'CONNECTED'
        CHECK (status IN ('CONNECTED', 'EXPIRED', 'REVOKED', 'ERROR')),
    token_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Identidade **oficial** do canal: o id do YouTube (`UC...`), global e independente da conta.
-- Um canal pode ser alcançado por mais de uma autorização (conta trocada, reconsentimento);
-- por isso a identidade não é propriedade da autorização.
CREATE TABLE studio.youtube_channels (
    youtube_channel_id text PRIMARY KEY
        CHECK (length(btrim(youtube_channel_id)) BETWEEN 1 AND 128),
    title text NOT NULL DEFAULT '' CHECK (length(title) <= 200),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- O vínculo **validado** entre uma autorização e um canal. É a afirmação "esta credencial foi
-- conferida e resolve para este canal"; `validated_at` é quando essa conferência ocorreu.
-- Não se presume o vínculo: ele é registrado depois de verificado.
CREATE TABLE studio.channel_authorizations (
    grant_id text NOT NULL REFERENCES studio.oauth_grants(id) ON DELETE CASCADE,
    youtube_channel_id text NOT NULL REFERENCES studio.youtube_channels(youtube_channel_id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'CONNECTED'
        CHECK (status IN ('CONNECTED', 'EXPIRED', 'REVOKED', 'ERROR')),
    validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (grant_id, youtube_channel_id)
);

-- A publicação procura "qual autorização valida este canal?": o índice serve essa consulta.
CREATE INDEX channel_authorizations_channel_idx ON studio.channel_authorizations (youtube_channel_id);

-- ---------------------------------------------------------------------------
-- 0036_video_style.sql
-- ---------------------------------------------------------------------------
-- VS-02b: override de estilo por vídeo ("o canal herda, o vídeo pode sobrepor").
-- Desenho: docs/superpowers/specs/2026-11-21-channel-visual-style-design.md (§2.3, §3.5).
--
-- Migração **aditiva**: coluna anulável. Nulo (o normal) = o vídeo herda o estilo do canal;
-- preenchido = este vídeo usa um estilo específico, sem mudar o canal.
--
-- `ON DELETE SET NULL`: apagar o estilo **volta o vídeo a herdar** do canal, em vez de bloquear
-- a limpeza ou apagar o vídeo. Mais seguro que CASCADE e que RESTRICT.
ALTER TABLE studio.videos
    ADD COLUMN style_id text REFERENCES studio.visual_styles(id) ON DELETE SET NULL;

CREATE INDEX videos_style_idx ON studio.videos (style_id) WHERE style_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 0037_channel_youtube_target.sql
-- ---------------------------------------------------------------------------
-- YT-02: o canal do estúdio aponta para **qual** canal do YouTube ele publica.
--
-- Migração **aditiva**: coluna anulável, sem backfill. Canal sem destino continua válido —
-- e a publicação segue pelo caminho antigo (`channel_youtube_channels`, por projeto) até a
-- fatia que religa o `RunPublication` (YT-03). Aqui só se grava a referência.
--
-- A FK é para `studio.youtube_channels(youtube_channel_id)` (a identidade oficial, `UC...`),
-- não para a conta nem para a autorização: o canal do estúdio aponta para o canal, e o vínculo
-- com a autorização (`channel_authorizations`) é resolvido à parte por quem publica.
--
-- `ON DELETE SET NULL`: apagar a identidade do YouTube **destaca** o canal do estúdio (não
-- bloqueia a limpeza nem apaga o canal). Mesma escolha da referência ao estilo (0034).
ALTER TABLE studio.channel_profiles
    ADD COLUMN youtube_channel_id text REFERENCES studio.youtube_channels(youtube_channel_id) ON DELETE SET NULL;

-- Índice parcial: só interessa saber quais canais apontam para um canal do YouTube (caminho raro).
CREATE INDEX channel_profiles_youtube_channel_idx
    ON studio.channel_profiles (youtube_channel_id) WHERE youtube_channel_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 0038_budget_scope_attribution.sql
-- ---------------------------------------------------------------------------
-- F01.T03 — atribuição explícita de escopo no orçamento (ADR-002).
--
-- Antes desta migração os limites do canal eram aplicados contra o gasto GLOBAL: `channel_guard_limits`
-- levava o hard do canal ao guard, mas `_reserve_within` media `usage_ledger` inteiro. Resultado: o gasto
-- do canal A consumia o teto do canal B. Separar exige saber a que escopo cada linha pertence, e isso
-- tem de ser explícito no banco — não inferido de joins na hora da leitura.
--
-- Escopos (uma coluna nova, nula = escopo GLOBAL):
--   project_id NOT NULL  -> gasto/reserva do canal daquele projeto
--   project_id NULL      -> escopo global explícito (operação sem vídeo, ou lançamento legado sem vídeo)
--
-- A migração é ADITIVA: nenhuma coluna/linha é removida, nenhum valor existente muda de significado.
-- `budget_reservations.monthly_limit_usd`/`video_limit_usd` continuam sendo os tetos DO CANAL; o teto
-- global é política das settings (não é persistido por linha, para que replay com outra settings não
-- vire conflito de idempotência).
--
-- Custo operacional: ADD COLUMN com REFERENCES é metadata-only no PostgreSQL >= 11 (FK nula não é
-- validada linha a linha além do scan trivial); os UPDATEs de backfill varrem as três tabelas sob
-- escrita. Em tabela grande, rodar o backfill em lotes fora do horário de pico.
--
-- Rollback manual (não executado automaticamente; preserva histórico):
--   DROP TRIGGER studio.usage_ledger_project_attribution ON studio.usage_ledger;
--   DROP FUNCTION studio.assign_ledger_project();
--   DROP INDEX studio.usage_ledger_project_created_idx;
--   DROP INDEX studio.budget_reservations_project_created_idx;
--   DROP INDEX studio.paid_operations_project_idx;
--   ALTER TABLE studio.usage_ledger DROP COLUMN project_id;
--   ALTER TABLE studio.budget_reservations DROP COLUMN project_id;
--   ALTER TABLE studio.paid_operations DROP COLUMN project_id;

ALTER TABLE studio.usage_ledger
    ADD COLUMN project_id text REFERENCES studio.projects(id) ON DELETE RESTRICT;
ALTER TABLE studio.budget_reservations
    ADD COLUMN project_id text REFERENCES studio.projects(id) ON DELETE RESTRICT;
ALTER TABLE studio.paid_operations
    ADD COLUMN project_id text REFERENCES studio.projects(id) ON DELETE RESTRICT;

-- Backfill das linhas antigas: quem tem vídeo recebe o projeto do vídeo; quem não tem permanece
-- explicitamente global (NULL). Nenhum valor de custo ou limite é reescrito.
UPDATE studio.usage_ledger ul
   SET project_id = v.project_id
  FROM studio.videos v
 WHERE v.id = ul.video_id AND ul.project_id IS NULL;

UPDATE studio.budget_reservations br
   SET project_id = v.project_id
  FROM studio.videos v
 WHERE v.id = br.video_id AND br.project_id IS NULL;

UPDATE studio.paid_operations po
   SET project_id = v.project_id
  FROM studio.videos v
 WHERE v.id = po.video_id AND po.project_id IS NULL;

-- Todo lançamento novo herda a atribuição do vídeo, inclusive os caminhos legados que só gravam
-- `video_id` (`PostgresUsageRepository.record`). O vídeo é autoritativo: um valor divergente informado
-- pelo chamador é sobrescrito, nunca aceito. Sem vídeo, a linha é do escopo global (NULL).
CREATE FUNCTION studio.assign_ledger_project() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.video_id IS NOT NULL THEN
        SELECT v.project_id INTO NEW.project_id FROM studio.videos v WHERE v.id = NEW.video_id;
    ELSE
        NEW.project_id := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER usage_ledger_project_attribution
    BEFORE INSERT ON studio.usage_ledger
    FOR EACH ROW EXECUTE FUNCTION studio.assign_ledger_project();

-- Leitura do teto por escopo: soma do mês por projeto e listagem global.
CREATE INDEX usage_ledger_project_created_idx ON studio.usage_ledger(project_id, created_at);
CREATE INDEX budget_reservations_project_created_idx ON studio.budget_reservations(project_id, created_at);
CREATE INDEX paid_operations_project_idx ON studio.paid_operations(project_id);

-- ---------------------------------------------------------------------------
-- 0039_production_run_config.sql
-- ---------------------------------------------------------------------------
-- F03.T02 — configuração efetiva congelada na criação do run (F03.T01 no banco).
--
-- O run nasce com **uma** configuração efetiva: o resolvedor (aplicação) roda antes de qualquer
-- efeito e `create_run` grava o snapshot canônico na MESMA transação do run, das etapas e da
-- outbox. Sem resolvedor, o run é um legado explícito (`config_status = 'legacy'`), sem snapshot:
-- nunca é re-resolvido depois do fato e um replay com configuração é conflito, não upgrade.
--
-- Migração ADITIVA: nenhuma coluna/linha existente muda de significado. As linhas anteriores ficam
-- `legacy` (o DEFAULT preenche a nova coluna) e continuam legíveis; os campos do snapshot são
-- nulos até um run novo nascer resolvido.
--
-- Rollback manual (não executado automaticamente; preserva histórico):
--   ALTER TABLE studio.production_runs DROP CONSTRAINT production_runs_config_snapshot_check;
--   ALTER TABLE studio.production_runs DROP CONSTRAINT production_runs_config_status_check;
--   ALTER TABLE studio.production_runs DROP CONSTRAINT production_runs_config_schema_version_check;
--   ALTER TABLE studio.production_runs DROP COLUMN config_schema_version;
--   ALTER TABLE studio.production_runs DROP COLUMN config_provenance;
--   ALTER TABLE studio.production_runs DROP COLUMN config_hash;
--   ALTER TABLE studio.production_runs DROP COLUMN config_snapshot;
--   ALTER TABLE studio.production_runs DROP COLUMN config_status;
--   DELETE FROM studio.schema_migrations WHERE version = '0039_production_run_config';

ALTER TABLE studio.production_runs
    -- `legacy` é o DEFAULT: todo run criado sem resolvedor declara isso explicitamente.
    ADD COLUMN config_status text NOT NULL DEFAULT 'legacy',
    -- Documento canônico da configuração efetiva (domain.effective_config.canonical_document):
    -- inclui schema_version, editorial, audiovisual, referências, provider_policy e proveniência.
    ADD COLUMN config_snapshot jsonb,
    -- sha256 do documento canônico; identidade determinística da configuração.
    ADD COLUMN config_hash text,
    -- Proveniência em coluna própria para auditoria SQL; é a mesma do documento (nunca divergem).
    ADD COLUMN config_provenance jsonb,
    -- `schema_version` do documento: recusar incompatível na leitura, nunca reinterpretar.
    ADD COLUMN config_schema_version integer;

ALTER TABLE studio.production_runs
    ADD CONSTRAINT production_runs_config_status_check
        CHECK (config_status IN ('legacy', 'resolved')),
    ADD CONSTRAINT production_runs_config_schema_version_check
        CHECK (config_schema_version IS NULL OR config_schema_version >= 1),
    -- Tudo ou nada: `resolved` exige snapshot, hash hexadecimal de 64, proveniência e schema;
    -- `legacy` proíbe qualquer metade de snapshot (o upgrade silencioso é bloqueado pelo banco).
    ADD CONSTRAINT production_runs_config_snapshot_check
        CHECK (
            (config_status = 'legacy'
                AND config_snapshot IS NULL
                AND config_hash IS NULL
                AND config_provenance IS NULL
                AND config_schema_version IS NULL)
            OR (config_status = 'resolved'
                AND config_snapshot IS NOT NULL
                AND jsonb_typeof(config_snapshot) = 'object'
                AND config_hash ~ '^[0-9a-f]{64}$'
                AND config_provenance IS NOT NULL
                AND jsonb_typeof(config_provenance) = 'object'
                AND config_schema_version IS NOT NULL)
        );

-- Sem índice novo: a configuração é lida pela PK do run (`run_id`) na retomada/retry/painel.

-- ---------------------------------------------------------------------------
-- 0040_style_patches.sql
-- ---------------------------------------------------------------------------
-- F05.T02: patch de estilo persistido no canal e no vídeo (ADR fs31-004).
--
-- Patch é **override tipado**, não uma cópia do estilo: guarda só as chaves que a camada
-- personaliza. Nulo (o normal) = herda a camada de baixo; por isso a migração é aditiva e não
-- tem backfill — toda linha existente passa a herdar, sem dado inventado.
--
-- `style_patch_revision` é o token do controle otimista **da escrita do patch** (0 = nunca
-- personalizado). Ele é independente de `channel_profiles.version` (que continua sendo a versão
-- editorial do perfil): personalizar o estilo não reescreve nome, voz nem estratégia, e uma
-- escrita com revisão velha é recusada pelo caso de uso/repositório, nunca sobrescreve.
--
-- CHECK de forma: o banco só aceita objeto JSON não vazio. `{}` seria indistinguível de "herdar",
-- então reset se escreve como NULL (o patch sai da linha) — a semântica não fica ambígua no
-- armazenamento. A allowlist de campos continua sendo do domínio (`StylePatch`), validada antes
-- de gravar; o CHECK é a última barreira contra uma escrita manual fora de contrato.
ALTER TABLE studio.channel_profiles
    ADD COLUMN style_patch jsonb,
    ADD COLUMN style_patch_revision integer NOT NULL DEFAULT 0 CHECK (style_patch_revision >= 0),
    ADD CONSTRAINT channel_profiles_style_patch_object CHECK (
        style_patch IS NULL
        OR (jsonb_typeof(style_patch) = 'object' AND style_patch <> '{}'::jsonb)
    );

ALTER TABLE studio.videos
    ADD COLUMN style_patch jsonb,
    ADD COLUMN style_patch_revision integer NOT NULL DEFAULT 0 CHECK (style_patch_revision >= 0),
    ADD CONSTRAINT videos_style_patch_object CHECK (
        style_patch IS NULL
        OR (jsonb_typeof(style_patch) = 'object' AND style_patch <> '{}'::jsonb)
    );

-- ---------------------------------------------------------------------------
-- 0041_production_run_operation.sql
-- ---------------------------------------------------------------------------
-- F03.T04 — decisão das operações de lifecycle na outbox existente.
--
-- Pause/resume/retry/regenerate/nova execução gravam `production.run.operation` com motivo,
-- rótulo da operação e a **referência** do snapshot (status + hash). O documento da configuração
-- nunca entra no evento: credencial não tem caminho para a trilha.
--
-- A transição de estado continua sendo escrita atomicamente por `pause_run`/`resume_run`/
-- `cancel_run`/`create_run`; este tipo de evento não substitui nem duplica essa escrita — só
-- registra a decisão que antes não tinha lugar na trilha (notadamente retry/regenerate/legado).
--
-- Migração ADITIVA: o CHECK ganha um valor e nenhum evento existente muda de significado. Não há
-- índice novo: a leitura da trilha já é por `run_id`/ordem de `id` (`production_outbox_unacked_idx`).
--
-- Rollback manual (não executado automaticamente; preserva histórico):
--   DELETE FROM studio.production_outbox WHERE event_type = 'production.run.operation';
--   ALTER TABLE studio.production_outbox DROP CONSTRAINT production_outbox_event_type_check;
--   ALTER TABLE studio.production_outbox ADD CONSTRAINT production_outbox_event_type_check
--       CHECK (event_type IN ('production.run.created', 'production.run.state_changed',
--                             'production.stage.claimed', 'production.stage.completed',
--                             'production.stage.failed', 'production.stage.revoked'));
--   DELETE FROM studio.schema_migrations WHERE version = '0041_production_run_operation';

ALTER TABLE studio.production_outbox
    DROP CONSTRAINT production_outbox_event_type_check,
    ADD CONSTRAINT production_outbox_event_type_check
        CHECK (event_type IN ('production.run.created', 'production.run.state_changed',
                              'production.stage.claimed', 'production.stage.completed',
                              'production.stage.failed', 'production.stage.revoked',
                              'production.run.operation'));
