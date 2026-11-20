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
