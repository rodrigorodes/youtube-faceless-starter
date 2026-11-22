-- W4.5 (EDIT-04) — histórico recuperável de revisões de cena.
--
-- Cada versão do roteiro guarda, por cena, o texto falado, a ordem e o vínculo de mídia
-- (`asset_id`), além do que é preciso reconstruir a cena (legenda, rótulo, prompt visual,
-- citações, duração medida e o marcador de mídia a revisar). O snapshot é por
-- `(video_id, version, scene_id)`.
--
-- Como as cenas correntes em `studio.scenes` são reescritas a cada versão (a cena removida sai
-- da projeção), o snapshot é a única memória daquela revisão. Ele é capturado quando a versão
-- deixa de ser a corrente e quando nasce uma nova. A versão corrente também tem snapshot, mas a
-- leitura dela usa as cenas vivas — o snapshot corrente sempre pode ser atualizado.
--
-- `asset_id` fica SEM chave estrangeira de propósito: o histórico registra o vínculo que existia,
-- mesmo que o asset seja removido depois. Quem restaura confere a existência em `studio.assets` e
-- marca a cena como `media_review_required` quando o asset já não existe — o histórico não é
-- reescrito nem apagado.
--
-- Migração ADITIVA: cria apenas uma tabela nova e preenche, para cada vídeo, o snapshot da versão
-- corrente a partir das cenas atuais. Nenhuma tabela, linha ou coluna existente muda; versões
-- antigas sem snapshot continuam legíveis e simplesmente não são restauráveis.
--
-- Rollback manual (não executado automaticamente; preserva histórico):
--   DROP TABLE studio.scene_revisions;
--   DELETE FROM studio.schema_migrations WHERE version = '0045_scene_revisions';

CREATE TABLE studio.scene_revisions (
    video_id text NOT NULL,
    version int NOT NULL CHECK (version >= 1),
    scene_id text NOT NULL CHECK (scene_id ~ '^[0-9a-f]{32}$'),
    idx int NOT NULL CHECK (idx >= 0),
    narration text NOT NULL,
    caption text NOT NULL DEFAULT '',
    label text NOT NULL DEFAULT '',
    image_prompt text NOT NULL,
    claim_ids jsonb NOT NULL DEFAULT '[]',
    asset_id text CHECK (asset_id IS NULL OR asset_id ~ '^[0-9a-f]{32}$'),
    media_review_required boolean NOT NULL DEFAULT false,
    duration_s real CHECK (duration_s IS NULL OR duration_s >= 0),
    captured_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (video_id, version, scene_id),
    FOREIGN KEY (video_id, version) REFERENCES studio.scripts(video_id, version) ON DELETE CASCADE
);
CREATE INDEX ix_scene_revisions_video_version ON studio.scene_revisions (video_id, version, idx);

-- Backfill do que dá para recuperar sem inventar: a versão corrente de cada vídeo ganha o
-- snapshot do estado atual das cenas. Revisões antigas ficam sem snapshot (legado explícito).
INSERT INTO studio.scene_revisions (
    video_id, version, scene_id, idx, narration, caption, label, image_prompt, claim_ids,
    asset_id, media_review_required, duration_s
)
SELECT s.video_id, latest.version, s.id, s.idx, s.narration, s.caption, s.label, s.image_prompt,
       s.claim_ids, s.asset_id, s.media_review_required, s.duration_s
FROM studio.scenes s
JOIN (SELECT video_id, MAX(version) AS version FROM studio.scripts GROUP BY video_id) latest
  ON latest.video_id = s.video_id
ON CONFLICT (video_id, version, scene_id) DO NOTHING;
