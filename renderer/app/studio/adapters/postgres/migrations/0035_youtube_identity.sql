-- Identidade de publicação do YouTube: conta → autorizações → canais (YT-01).
-- Desenho: docs/superpowers/specs/2026-11-21-youtube-account-grants-design.md
--
-- Migração **aditiva**: não remove `channel_youtube_channels` (o caminho atual continua de pé
-- até a fatia que religa a publicação). O modelo novo separa quatro coisas que hoje são uma só:
--   GoogleAccount        — a identidade (e-mail); não é dona da autorização.
--   OAuthGrant           — a autorização independente (escopos/status/expiração; tokens no vault).
--   YouTubeChannel       — a identidade oficial do canal (`UC...`), distinta da conta.
--   ChannelAuthorization — o vínculo **validado** entre uma autorização e um canal.
--
-- O princípio: cada canal publicado tem uma autorização validada para ele; nunca se presume
-- que uma autorização seja intercambiável entre canais.
CREATE TABLE studio.google_accounts (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    email text NOT NULL CHECK (length(btrim(email)) BETWEEN 3 AND 320),
    display_name text NOT NULL DEFAULT '' CHECK (length(display_name) <= 200),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Uma conta por e-mail (sem distinguir caixa): conectar de novo atualiza, não duplica.
CREATE UNIQUE INDEX google_accounts_email_idx ON studio.google_accounts (lower(btrim(email)));

-- Autorização independente. Os tokens (access/refresh) ficam no vault, com escopo próprio
-- (`oauth_grant:{id}`); aqui só metadados. `status` é o estado declarado; o efetivo é derivado
-- na leitura (sem credencial → DISCONNECTED; vencido → EXPIRED; revogado → REVOKED).
CREATE TABLE studio.oauth_grants (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    account_id text NOT NULL REFERENCES studio.google_accounts(id) ON DELETE CASCADE,
    scopes jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(scopes) = 'array'),
    status text NOT NULL DEFAULT 'CONNECTED'
        CHECK (status IN ('CONNECTED', 'EXPIRED', 'REVOKED', 'ERROR')),
    token_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Identidade **oficial** do canal: o id do YouTube (`UC...`), global e independente da conta.
-- Um canal pode ser alcançado por mais de uma autorização (conta trocada, reconsentimento);
-- por isso a identidade não é propriedade da autorização.
CREATE TABLE studio.youtube_channels (
    youtube_channel_id text PRIMARY KEY
        CHECK (length(btrim(youtube_channel_id)) BETWEEN 1 AND 128),
    title text NOT NULL DEFAULT '' CHECK (length(title) <= 200),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- O vínculo **validado** entre uma autorização e um canal. É a afirmação "esta credencial foi
-- conferida e resolve para este canal"; `validated_at` é quando essa conferência ocorreu.
-- Não se presume o vínculo: ele é registrado depois de verificado.
CREATE TABLE studio.channel_authorizations (
    grant_id text NOT NULL REFERENCES studio.oauth_grants(id) ON DELETE CASCADE,
    youtube_channel_id text NOT NULL REFERENCES studio.youtube_channels(youtube_channel_id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'CONNECTED'
        CHECK (status IN ('CONNECTED', 'EXPIRED', 'REVOKED', 'ERROR')),
    validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (grant_id, youtube_channel_id)
);

-- A publicação procura "qual autorização valida este canal?": o índice serve essa consulta.
CREATE INDEX channel_authorizations_channel_idx ON studio.channel_authorizations (youtube_channel_id);
