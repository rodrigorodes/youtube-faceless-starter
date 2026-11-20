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
