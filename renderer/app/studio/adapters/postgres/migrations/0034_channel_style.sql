-- VS-02: o canal aponta para o estilo visual (biblioteca compartilhada) — desenho §3.1/§5.
--
-- Migração **aditiva**: coluna anulável, sem backfill. Canal sem estilo continua válido — e o
-- render cai no bundle neutro (`studio-default@1`) enquanto ninguém escolher um estilo.
--
-- `ON DELETE SET NULL`: apagar um estilo **destaca** o canal (não bloqueia) — mais seguro que
-- CASCADE (que apagaria o canal) e que RESTRICT (que impediria limpar a biblioteca). Os estilos
-- são arquivados (soft delete) no uso normal; isto é para a limpeza dura.
ALTER TABLE studio.channel_profiles
    ADD COLUMN style_id text REFERENCES studio.visual_styles(id) ON DELETE SET NULL;

-- Índice parcial: só interessa saber quais canais apontam para um estilo (e é o caminho raro).
CREATE INDEX channel_profiles_style_idx ON studio.channel_profiles (style_id) WHERE style_id IS NOT NULL;
