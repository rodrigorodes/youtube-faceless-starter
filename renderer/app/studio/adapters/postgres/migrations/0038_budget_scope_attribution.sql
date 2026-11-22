-- F01.T03 — atribuição explícita de escopo no orçamento (ADR-002).
--
-- Antes desta migração os limites do canal eram aplicados contra o gasto GLOBAL: `channel_guard_limits`
-- levava o hard do canal ao guard, mas `_reserve_within` media `usage_ledger` inteiro. Resultado: o gasto
-- do canal A consumia o teto do canal B. Separar exige saber a que escopo cada linha pertence, e isso
-- tem de ser explícito no banco — não inferido de joins na hora da leitura.
--
-- Escopos (uma coluna nova, nula = escopo GLOBAL):
--   project_id NOT NULL  -> gasto/reserva do canal daquele projeto
--   project_id NULL      -> escopo global explícito (operação sem vídeo, ou lançamento legado sem vídeo)
--
-- A migração é ADITIVA: nenhuma coluna/linha é removida, nenhum valor existente muda de significado.
-- `budget_reservations.monthly_limit_usd`/`video_limit_usd` continuam sendo os tetos DO CANAL; o teto
-- global é política das settings (não é persistido por linha, para que replay com outra settings não
-- vire conflito de idempotência).
--
-- Custo operacional: ADD COLUMN com REFERENCES é metadata-only no PostgreSQL >= 11 (FK nula não é
-- validada linha a linha além do scan trivial); os UPDATEs de backfill varrem as três tabelas sob
-- escrita. Em tabela grande, rodar o backfill em lotes fora do horário de pico.
--
-- Rollback manual (não executado automaticamente; preserva histórico):
--   DROP TRIGGER studio.usage_ledger_project_attribution ON studio.usage_ledger;
--   DROP FUNCTION studio.assign_ledger_project();
--   DROP INDEX studio.usage_ledger_project_created_idx;
--   DROP INDEX studio.budget_reservations_project_created_idx;
--   DROP INDEX studio.paid_operations_project_idx;
--   ALTER TABLE studio.usage_ledger DROP COLUMN project_id;
--   ALTER TABLE studio.budget_reservations DROP COLUMN project_id;
--   ALTER TABLE studio.paid_operations DROP COLUMN project_id;

ALTER TABLE studio.usage_ledger
    ADD COLUMN project_id text REFERENCES studio.projects(id) ON DELETE RESTRICT;
ALTER TABLE studio.budget_reservations
    ADD COLUMN project_id text REFERENCES studio.projects(id) ON DELETE RESTRICT;
ALTER TABLE studio.paid_operations
    ADD COLUMN project_id text REFERENCES studio.projects(id) ON DELETE RESTRICT;

-- Backfill das linhas antigas: quem tem vídeo recebe o projeto do vídeo; quem não tem permanece
-- explicitamente global (NULL). Nenhum valor de custo ou limite é reescrito.
UPDATE studio.usage_ledger ul
   SET project_id = v.project_id
  FROM studio.videos v
 WHERE v.id = ul.video_id AND ul.project_id IS NULL;

UPDATE studio.budget_reservations br
   SET project_id = v.project_id
  FROM studio.videos v
 WHERE v.id = br.video_id AND br.project_id IS NULL;

UPDATE studio.paid_operations po
   SET project_id = v.project_id
  FROM studio.videos v
 WHERE v.id = po.video_id AND po.project_id IS NULL;

-- Todo lançamento novo herda a atribuição do vídeo, inclusive os caminhos legados que só gravam
-- `video_id` (`PostgresUsageRepository.record`). O vídeo é autoritativo: um valor divergente informado
-- pelo chamador é sobrescrito, nunca aceito. Sem vídeo, a linha é do escopo global (NULL).
CREATE FUNCTION studio.assign_ledger_project() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.video_id IS NOT NULL THEN
        SELECT v.project_id INTO NEW.project_id FROM studio.videos v WHERE v.id = NEW.video_id;
    ELSE
        NEW.project_id := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER usage_ledger_project_attribution
    BEFORE INSERT ON studio.usage_ledger
    FOR EACH ROW EXECUTE FUNCTION studio.assign_ledger_project();

-- Leitura do teto por escopo: soma do mês por projeto e listagem global.
CREATE INDEX usage_ledger_project_created_idx ON studio.usage_ledger(project_id, created_at);
CREATE INDEX budget_reservations_project_created_idx ON studio.budget_reservations(project_id, created_at);
CREATE INDEX paid_operations_project_idx ON studio.paid_operations(project_id);