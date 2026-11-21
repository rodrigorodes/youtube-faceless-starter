-- L2: auditoria das mutações de vínculo (Equipe). Registra QUEM mudou o quê.
-- O vínculo pode ser removido depois; por isso membership_id não tem FK (o registro sobrevive).
-- Nenhum segredo entra aqui: só o ator, a ação e o papel resultante/registrado.

CREATE TABLE studio.membership_audit (
    id bigserial PRIMARY KEY,
    organization_id text NOT NULL REFERENCES studio.organizations(id) ON DELETE CASCADE,
    membership_id text NOT NULL CHECK (membership_id ~ '^[0-9a-f]{32}$'),
    actor_user_id text REFERENCES studio.users(id) ON DELETE SET NULL,
    action text NOT NULL CHECK (action IN ('invited', 'role_changed', 'removed')),
    role text CHECK (role IN ('owner', 'editor', 'reviewer', 'viewer')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX membership_audit_org_idx ON studio.membership_audit (organization_id, created_at);
