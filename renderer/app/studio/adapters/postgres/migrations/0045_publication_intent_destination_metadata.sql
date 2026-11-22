-- W5.1 (PUB-01): a intenção de publicação passa a lembrar o DESTINO e os METADADOS confirmados.
--
-- A19/A37: mudar o canal do YouTube ou título/descrição/tags/visibilidade depois da confirmação
-- torna a intenção obsoleta; o executor falha fechado e exige confirmação nova. As colunas são
-- anuláveis para não invalidar intenções antigas (gravadas antes desta fatia).
ALTER TABLE studio.publication_intents
    ADD COLUMN youtube_channel_id text,
    ADD COLUMN metadata_fingerprint text
        CHECK (metadata_fingerprint IS NULL OR metadata_fingerprint ~ '^[0-9a-f]{64}$');

-- O arquivo de reabertura (ADR-002) preserva exatamente o que foi confirmado, incluindo o
-- destino e a impressão dos metadados.
ALTER TABLE studio.approval_history
    ADD COLUMN youtube_channel_id text,
    ADD COLUMN metadata_fingerprint text
        CHECK (metadata_fingerprint IS NULL OR metadata_fingerprint ~ '^[0-9a-f]{64}$');
