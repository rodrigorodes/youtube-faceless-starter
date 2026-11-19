-- P02: o relatório de checagem guarda a versão do roteiro que foi checada (auditável na P05).
ALTER TABLE studio.fact_checks ADD COLUMN script_version int CHECK (script_version >= 1);
