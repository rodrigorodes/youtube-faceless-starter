-- F9-01/F9-02/F9-05/F9-06: medição ligada a versões, experimento e decisão de revisão.
--
-- A observação guarda o valor medido OU o motivo de não estar disponível — nunca os dois e
-- nunca zero no lugar de ausência. `script_version` tem FK composta para `scripts(video_id,
-- version)`: versão inventada é recusada pelo banco. `brief_version`/`packaging_version`
-- existem como colunas porque a atribuição já os nomeia; ficam nulos até essas persistências
-- existirem, e `missing_links` registra o motivo de cada ausência.
CREATE TABLE studio.metric_observations (
    observation_id text PRIMARY KEY CHECK (observation_id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE RESTRICT,
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    youtube_video_id text CHECK (youtube_video_id IS NULL OR youtube_video_id ~ '^[A-Za-z0-9_-]{11}$'),
    pillar_id text REFERENCES studio.project_categories(id) ON DELETE SET NULL,
    metric text NOT NULL CHECK (metric IN ('views', 'impressions', 'ctr', 'average_view_percentage',
        'average_view_duration_s', 'estimated_minutes_watched', 'likes', 'comments', 'shares',
        'subscribers_gained')),
    unit text NOT NULL CHECK (btrim(unit) <> ''),
    value double precision,
    unavailable_reason text,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    source text NOT NULL CHECK (btrim(source) <> ''),
    origin text NOT NULL CHECK (origin IN ('youtube_analytics_api', 'unknown_origin')),
    script_version int CHECK (script_version >= 1),
    brief_version int CHECK (brief_version >= 1),
    packaging_version int CHECK (packaging_version >= 1),
    publication_id text REFERENCES studio.publications(id) ON DELETE RESTRICT,
    missing_links jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(missing_links) = 'array'),
    experiment_id text,
    variant_id text,
    collected_at timestamptz NOT NULL,
    CHECK (window_start < window_end),
    CHECK ((value IS NULL) <> (unavailable_reason IS NULL)),
    CHECK (value IS NULL OR (value >= 0 AND value < 'Infinity'::float8 AND value <> 'NaN'::float8)),
    CHECK (youtube_video_id IS NULL OR publication_id IS NOT NULL),
    CHECK ((experiment_id IS NULL) = (variant_id IS NULL)),
    CONSTRAINT metric_observations_script_version_fk
        FOREIGN KEY (video_id, script_version) REFERENCES studio.scripts(video_id, version),
    UNIQUE (video_id, metric, window_start, window_end, source, origin)
);

CREATE INDEX metric_observations_project_window_idx
    ON studio.metric_observations (project_id, window_end DESC);
CREATE INDEX metric_observations_video_metric_idx
    ON studio.metric_observations (video_id, metric, window_start);

-- Histórico de experimentos de thumbnail/título. A API do YouTube Analytics não oferece A/B
-- nesta integração: `platform_ab_supported` é travado em falso e a rotação é manual/aprovada.
CREATE TABLE studio.analytics_experiments (
    experiment_id text PRIMARY KEY CHECK (experiment_id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE RESTRICT,
    video_id text NOT NULL REFERENCES studio.videos(id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN ('thumbnail', 'title')),
    status text NOT NULL CHECK (status IN ('planned', 'running', 'finished', 'abandoned')),
    platform_ab_supported boolean NOT NULL DEFAULT false CHECK (platform_ab_supported = false),
    platform_note text NOT NULL CHECK (btrim(platform_note) <> ''),
    approved_by text NOT NULL CHECK (btrim(approved_by) <> ''),
    approved_at timestamptz NOT NULL DEFAULT now(),
    window_start timestamptz,
    window_end timestamptz,
    conclusion text,
    conclusion_confidence text CHECK (conclusion_confidence IN ('low', 'medium', 'high')),
    conclusion_basis text,
    conclusion_observation_ids text[] NOT NULL DEFAULT '{}',
    concluded_by text,
    concluded_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((window_start IS NULL) = (window_end IS NULL)),
    CHECK (window_start IS NULL OR window_start < window_end),
    CHECK (status NOT IN ('running', 'finished') OR window_start IS NOT NULL),
    CHECK (status <> 'finished' OR (conclusion IS NOT NULL AND conclusion_confidence IS NOT NULL
        AND conclusion_basis IS NOT NULL AND concluded_by IS NOT NULL AND concluded_at IS NOT NULL
        AND cardinality(conclusion_observation_ids) >= 1)),
    CHECK (status = 'finished' OR conclusion IS NULL)
);

CREATE TABLE studio.analytics_experiment_variants (
    experiment_id text NOT NULL REFERENCES studio.analytics_experiments(experiment_id) ON DELETE CASCADE,
    variant_id text NOT NULL CHECK (btrim(variant_id) <> ''),
    label text NOT NULL CHECK (btrim(label) <> ''),
    is_control boolean NOT NULL DEFAULT false,
    PRIMARY KEY (experiment_id, variant_id)
);

-- Um único controle por experimento, garantido pelo banco (o domínio repete a checagem).
CREATE UNIQUE INDEX analytics_experiment_one_control_idx
    ON studio.analytics_experiment_variants (experiment_id) WHERE is_control;

CREATE INDEX analytics_experiments_project_created_idx
    ON studio.analytics_experiments (project_id, created_at DESC);

-- Uma observação ligada a experimento tem de apontar para uma variante real desse experimento.
ALTER TABLE studio.metric_observations
    ADD CONSTRAINT metric_observations_experiment_variant_fk
    FOREIGN KEY (experiment_id, variant_id)
    REFERENCES studio.analytics_experiment_variants (experiment_id, variant_id);

-- Decisão de revisão da recomendação. Não existe "applied": aplicar exige edição manual do
-- perfil do canal em outra tela; esta tabela é só o registro auditável da recusa/aceite.
CREATE TABLE studio.analytics_recommendation_decisions (
    recommendation_id text PRIMARY KEY CHECK (recommendation_id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE RESTRICT,
    decision text NOT NULL CHECK (decision IN ('accepted_for_review', 'rejected')),
    decided_by text NOT NULL CHECK (btrim(decided_by) <> ''),
    decided_at timestamptz NOT NULL DEFAULT now(),
    evidence jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array')
);

CREATE INDEX analytics_recommendation_decisions_project_idx
    ON studio.analytics_recommendation_decisions (project_id, decided_at DESC);