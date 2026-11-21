-- YT-02: o canal do estúdio aponta para **qual** canal do YouTube ele publica.
--
-- Migração **aditiva**: coluna anulável, sem backfill. Canal sem destino continua válido —
-- e a publicação segue pelo caminho antigo (`channel_youtube_channels`, por projeto) até a
-- fatia que religa o `RunPublication` (YT-03). Aqui só se grava a referência.
--
-- A FK é para `studio.youtube_channels(youtube_channel_id)` (a identidade oficial, `UC...`),
-- não para a conta nem para a autorização: o canal do estúdio aponta para o canal, e o vínculo
-- com a autorização (`channel_authorizations`) é resolvido à parte por quem publica.
--
-- `ON DELETE SET NULL`: apagar a identidade do YouTube **destaca** o canal do estúdio (não
-- bloqueia a limpeza nem apaga o canal). Mesma escolha da referência ao estilo (0034).
ALTER TABLE studio.channel_profiles
    ADD COLUMN youtube_channel_id text REFERENCES studio.youtube_channels(youtube_channel_id) ON DELETE SET NULL;

-- Índice parcial: só interessa saber quais canais apontam para um canal do YouTube (caminho raro).
CREATE INDEX channel_profiles_youtube_channel_idx
    ON studio.channel_profiles (youtube_channel_id) WHERE youtube_channel_id IS NOT NULL;
