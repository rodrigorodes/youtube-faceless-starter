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