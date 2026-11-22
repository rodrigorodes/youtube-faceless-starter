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