-- VS-02b: override de estilo por vídeo ("o canal herda, o vídeo pode sobrepor").
-- Desenho: docs/superpowers/specs/2026-11-21-channel-visual-style-design.md (§2.3, §3.5).
--
-- Migração **aditiva**: coluna anulável. Nulo (o normal) = o vídeo herda o estilo do canal;
-- preenchido = este vídeo usa um estilo específico, sem mudar o canal.
--
-- `ON DELETE SET NULL`: apagar o estilo **volta o vídeo a herdar** do canal, em vez de bloquear
-- a limpeza ou apagar o vídeo. Mais seguro que CASCADE e que RESTRICT.
ALTER TABLE studio.videos
    ADD COLUMN style_id text REFERENCES studio.visual_styles(id) ON DELETE SET NULL;

CREATE INDEX videos_style_idx ON studio.videos (style_id) WHERE style_id IS NOT NULL;
