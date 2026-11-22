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