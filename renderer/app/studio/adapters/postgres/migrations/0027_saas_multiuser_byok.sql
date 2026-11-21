-- F11-01/02/03/04: tenancy modelado (organização, workspace, usuário, vínculo/papel) e metadados de BYOK.
-- O valor da chave NUNCA entra aqui: só máscara, impressão sha256, coordenada do SecretStore e auditoria.
-- O caminho de tenant é anulável e ainda NÃO é aplicado em runtime: o produto segue mono-usuário
-- até existir sessão/OIDC (F11-02). Nenhuma linha existente é migrada para uma organização inventada.

CREATE TABLE studio.organizations (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE studio.workspaces (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    organization_id text NOT NULL REFERENCES studio.organizations(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, name)
);

CREATE TABLE studio.users (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    email text NOT NULL CHECK (email = lower(email) AND length(email) BETWEEN 3 AND 320),
    display_name text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (email)
);

CREATE TABLE studio.memberships (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    organization_id text NOT NULL REFERENCES studio.organizations(id) ON DELETE CASCADE,
    user_id text NOT NULL REFERENCES studio.users(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('owner', 'editor', 'reviewer', 'viewer')),
    status text NOT NULL DEFAULT 'invited' CHECK (status IN ('active', 'invited')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, user_id)
);

CREATE INDEX memberships_org_role_idx ON studio.memberships (organization_id, role);

CREATE TABLE studio.byok_keys (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    organization_id text NOT NULL REFERENCES studio.organizations(id) ON DELETE CASCADE,
    provider text NOT NULL CHECK (provider ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'),
    -- Só a máscara exibível (nunca o valor): termina nos 4 últimos caracteres ou é toda mascarada.
    mask text NOT NULL CHECK (length(mask) BETWEEN 6 AND 32),
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    secret_scope text NOT NULL CHECK (length(secret_scope) BETWEEN 1 AND 200),
    secret_name text NOT NULL CHECK (secret_name ~ '^[A-Za-z0-9._-]+$'),
    created_by text REFERENCES studio.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    rotated_at timestamptz,
    revoked_at timestamptz,
    last_used_at timestamptz,
    CHECK (rotated_at IS NULL OR rotated_at >= created_at)
);

-- Uma chave ativa por provider/organização; revogada libera o provider para uma nova chave.
CREATE UNIQUE INDEX byok_keys_active_provider_idx
    ON studio.byok_keys (organization_id, provider) WHERE revoked_at IS NULL;

CREATE TABLE studio.byok_key_audit (
    id bigserial PRIMARY KEY,
    organization_id text NOT NULL REFERENCES studio.organizations(id) ON DELETE CASCADE,
    key_id text NOT NULL REFERENCES studio.byok_keys(id) ON DELETE CASCADE,
    actor_user_id text REFERENCES studio.users(id) ON DELETE SET NULL,
    action text NOT NULL CHECK (action IN ('created', 'rotated', 'revoked', 'used')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX byok_key_audit_org_idx ON studio.byok_key_audit (organization_id, created_at);

-- Caminho de tenancy nos registros existentes: anulável de propósito (nada é atribuído em massa).
ALTER TABLE studio.projects
    ADD COLUMN organization_id text REFERENCES studio.organizations(id) ON DELETE RESTRICT;
CREATE INDEX projects_organization_idx ON studio.projects (organization_id);

ALTER TABLE studio.usage_ledger
    ADD COLUMN organization_id text REFERENCES studio.organizations(id) ON DELETE SET NULL,
    ADD COLUMN member_id text REFERENCES studio.users(id) ON DELETE SET NULL;
CREATE INDEX usage_ledger_organization_idx ON studio.usage_ledger (organization_id, created_at);