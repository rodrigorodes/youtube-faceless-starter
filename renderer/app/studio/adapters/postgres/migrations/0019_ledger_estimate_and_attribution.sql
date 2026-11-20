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
