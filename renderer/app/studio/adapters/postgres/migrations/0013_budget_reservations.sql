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
