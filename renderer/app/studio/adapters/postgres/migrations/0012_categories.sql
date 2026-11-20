-- Categorias fixas (pilares de conteúdo) por projeto e vinculação de tendências.
CREATE TABLE studio.project_categories (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(name) >= 1 AND length(name) <= 100),
    queries text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, name)
);

CREATE INDEX project_categories_project_id_idx ON studio.project_categories (project_id);

ALTER TABLE studio.trend_topics
    ADD COLUMN category_id text REFERENCES studio.project_categories(id) ON DELETE SET NULL;

CREATE INDEX trend_topics_category_id_idx ON studio.trend_topics (category_id);
