-- Zero legado pode significar custo desconhecido. Só uma confirmação explícita
-- com evidência permite tratá-lo como gratuito; nada é presumido na migração.
ALTER TABLE studio.usage_ledger
    ADD COLUMN cost_zero_evidence text,
    ADD CONSTRAINT usage_ledger_zero_evidence_check
        CHECK (cost_zero_evidence IS NULL OR
               (cost_usd = 0 AND cost_zero_evidence ~ '[^[:space:]]'));
