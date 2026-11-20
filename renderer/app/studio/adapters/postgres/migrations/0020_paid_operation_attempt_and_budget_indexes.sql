-- Correção operacional da fatia A.
--
-- I1: `attempt` registra quantas vezes a operação foi reaberta depois de RELEASED (nenhum efeito
-- externo comprovado). CONFIRMED continua terminal; UNCERTAIN continua bloqueado até reconciliação.
-- ADD COLUMN com default constante é metadata-only no PostgreSQL >= 11, mas ainda toma ACCESS
-- EXCLUSIVE por um instante (bloqueia leitura/escrita enquanto altera o catálogo).
ALTER TABLE studio.paid_operations
    ADD COLUMN attempt integer NOT NULL DEFAULT 1,
    ADD CONSTRAINT paid_operations_attempt_check CHECK (attempt >= 1);

-- I2/performance: índices das consultas do teto (mês corrente por created_at, total por video_id)
-- e da varredura de operações RESERVED paradas (state + updated_at).
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