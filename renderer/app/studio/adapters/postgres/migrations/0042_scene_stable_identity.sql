-- W4.0 (R2) — identidade estável da cena.
--
-- A cena deixa de ser recriada a cada versão: `id` identifica a cena entre versões e `idx` é só
-- a ordem (inserir/reordenar muda a posição, não o id). Quando a narração ou a intenção visual
-- muda, o vínculo de mídia não é mantido às cegas: `asset_id` é limpo e a cena é marcada para
-- revisão (`media_review_required = true`).
--
-- Migração ADITIVA: só acrescenta uma coluna com default. Nenhuma linha existente é apagada,
-- reescrita ou renumerada; cenas já gravadas ficam com `media_review_required = false`.
--
-- Rollback manual (não executado automaticamente; preserva histórico):
--   ALTER TABLE studio.scenes DROP COLUMN media_review_required;
--   DELETE FROM studio.schema_migrations WHERE version = '0042_scene_stable_identity';

ALTER TABLE studio.scenes ADD COLUMN media_review_required boolean NOT NULL DEFAULT false;
