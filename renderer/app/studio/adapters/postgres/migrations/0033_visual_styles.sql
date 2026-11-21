-- Estilos visuais do canal (biblioteca compartilhada) — desenho
-- docs/superpowers/specs/2026-11-21-channel-visual-style-design.md (§3)
--
-- Migração **aditiva**: nenhuma tabela existente muda e nenhum caminho antigo é removido.
-- A referência do estilo no canal (`channel_profiles.style_id`) e a resolução no plano vêm
-- nas fatias seguintes (VS-02/VS-03); esta fatia entrega só a biblioteca.
--
-- A biblioteca é **compartilhada**: um estilo é definido uma vez e vários canais apontam para
-- ele. `organization_id` deixa a coluna pronta para a multi-tenancy (hoje vazia/nula: o app é
-- single-tenant, um pool só). O versionamento por snapshot copia o padrão de
-- `channel_profile_revisions`: cada versão guarda o retrato auditável inteiro.
CREATE TABLE studio.visual_styles (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    organization_id text,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    -- Os parâmetros de aparência/som. O documento canônico fica aqui (nunca "segunda verdade"
    -- em colunas): assim a extensão (`extra`) cresce sem migração.
    params jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(params) = 'object'),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    archived boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Um nome ativo por vez (o arquivado libera o nome para reúso) — o produtor não tem dois
-- "Documentário" indistinguíveis na lista.
CREATE UNIQUE INDEX visual_styles_active_name_idx ON studio.visual_styles (lower(btrim(name)))
    WHERE archived = false;

-- Snapshot auditável por versão: o retrato do estilo quando aquela versão valia. É o que permite
-- um vídeo antigo continuar apontando para a versão com que foi renderizado.
CREATE TABLE studio.visual_style_revisions (
    style_id text NOT NULL REFERENCES studio.visual_styles(id) ON DELETE CASCADE,
    version integer NOT NULL CHECK (version >= 1),
    snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (style_id, version)
);
