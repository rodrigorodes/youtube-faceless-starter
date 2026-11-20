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
