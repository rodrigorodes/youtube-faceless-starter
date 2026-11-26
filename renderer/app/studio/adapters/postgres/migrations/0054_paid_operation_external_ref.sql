-- REC-01.02: persistência durável da referência externa do provedor em studio.paid_operations.
-- Aditiva (colunas anuláveis); preserva paid_operations_settlement_check e compatibilidade v1/v2.
--
-- Rollback manual:
--   ALTER TABLE studio.paid_operations DROP COLUMN IF EXISTS submitted_at;
--   ALTER TABLE studio.paid_operations DROP COLUMN IF EXISTS external_reference_id;
--   DELETE FROM studio.schema_migrations WHERE version = '0054_paid_operation_external_ref';

ALTER TABLE studio.paid_operations
    ADD COLUMN external_reference_id text,
    ADD COLUMN submitted_at timestamptz;
