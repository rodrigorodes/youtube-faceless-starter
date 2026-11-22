-- W4.1 (EDIT-01) — idempotência de edição de roteiro por chave + hash de payload.
--
-- Cada requisição de edição (editar/adicionar/remover/reordenar cena) grava uma linha com o hash
-- canônico do payload e o resultado persistido. Replay da mesma chave com o mesmo hash devolve o
-- resultado gravado (sem criar versão nova); a mesma chave com hash diferente é conflito.
--
-- Migração ADITIVA: cria apenas uma tabela nova. Nenhuma tabela, linha ou coluna existente muda.
-- Não guarda segredo: o payload é representado pelo hash e o resultado são dados editoriais.
--
-- Rollback manual (não executado automaticamente, preserva histórico):
--   DROP TABLE studio.script_edit_requests;
--   DELETE FROM studio.schema_migrations WHERE version = '0044_script_edit_requests';

CREATE TABLE studio.script_edit_requests (
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE CASCADE,
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[a-z0-9._:-]{1,200}$'),
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    result_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (video_id, idempotency_key)
);
