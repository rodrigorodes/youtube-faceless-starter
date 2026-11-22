-- F05.T02: patch de estilo persistido no canal e no vídeo (ADR fs31-004).
--
-- Patch é **override tipado**, não uma cópia do estilo: guarda só as chaves que a camada
-- personaliza. Nulo (o normal) = herda a camada de baixo; por isso a migração é aditiva e não
-- tem backfill — toda linha existente passa a herdar, sem dado inventado.
--
-- `style_patch_revision` é o token do controle otimista **da escrita do patch** (0 = nunca
-- personalizado). Ele é independente de `channel_profiles.version` (que continua sendo a versão
-- editorial do perfil): personalizar o estilo não reescreve nome, voz nem estratégia, e uma
-- escrita com revisão velha é recusada pelo caso de uso/repositório, nunca sobrescreve.
--
-- CHECK de forma: o banco só aceita objeto JSON não vazio. `{}` seria indistinguível de "herdar",
-- então reset se escreve como NULL (o patch sai da linha) — a semântica não fica ambígua no
-- armazenamento. A allowlist de campos continua sendo do domínio (`StylePatch`), validada antes
-- de gravar; o CHECK é a última barreira contra uma escrita manual fora de contrato.
ALTER TABLE studio.channel_profiles
    ADD COLUMN style_patch jsonb,
    ADD COLUMN style_patch_revision integer NOT NULL DEFAULT 0 CHECK (style_patch_revision >= 0),
    ADD CONSTRAINT channel_profiles_style_patch_object CHECK (
        style_patch IS NULL
        OR (jsonb_typeof(style_patch) = 'object' AND style_patch <> '{}'::jsonb)
    );

ALTER TABLE studio.videos
    ADD COLUMN style_patch jsonb,
    ADD COLUMN style_patch_revision integer NOT NULL DEFAULT 0 CHECK (style_patch_revision >= 0),
    ADD CONSTRAINT videos_style_patch_object CHECK (
        style_patch IS NULL
        OR (jsonb_typeof(style_patch) = 'object' AND style_patch <> '{}'::jsonb)
    );