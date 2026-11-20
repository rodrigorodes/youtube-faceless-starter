-- O identificador da tentativa nunca é reutilizado; o limite reinicia em retry manual.
ALTER TABLE studio.publications ADD COLUMN attempt_base integer NOT NULL DEFAULT 0;
ALTER TABLE studio.publications ADD CONSTRAINT publications_attempt_base_valid
    CHECK (attempt_base >= 0 AND attempt_base <= attempt);
