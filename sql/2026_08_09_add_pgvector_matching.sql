ALTER TYPE match_target_type ADD VALUE IF NOT EXISTS 'ai_suggestion';

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE users ADD COLUMN IF NOT EXISTS embedding vector(1536);
ALTER TABLE users ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_users_embedding
    ON users USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE IF NOT EXISTS match_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id_a UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_id_b UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    similarity_score FLOAT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id_a, user_id_b)
);
CREATE INDEX IF NOT EXISTS ix_match_candidates_user_a ON match_candidates(user_id_a);
CREATE INDEX IF NOT EXISTS ix_match_candidates_user_b ON match_candidates(user_id_b);

CREATE TABLE IF NOT EXISTS ai_match_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES match_candidates(id) ON DELETE CASCADE,
    hay_complementariedad BOOLEAN NOT NULL DEFAULT false,
    score_final INTEGER NOT NULL DEFAULT 0,
    explicacion TEXT NOT NULL DEFAULT '',
    relationship_edges JSONB NOT NULL DEFAULT '[]'::jsonb,
    modelo_usado VARCHAR(80) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE ai_match_suggestions ADD COLUMN IF NOT EXISTS relationship_edges JSONB NOT NULL DEFAULT '[]'::jsonb;
CREATE INDEX IF NOT EXISTS ix_ai_match_suggestions_candidate ON ai_match_suggestions(candidate_id);
CREATE INDEX IF NOT EXISTS ix_ai_match_suggestions_created_at ON ai_match_suggestions(created_at);

CREATE OR REPLACE VIEW dashboard_metricas AS
SELECT
    date_trunc('month', s.created_at) AS mes,
    count(*)::int AS sugerencias_totales,
    count(*) FILTER (WHERE o.outcome IN ('useful', 'collaboration'))::int AS vinculos_utiles,
    count(*) FILTER (WHERE o.outcome = 'not_useful')::int AS vinculos_no_utiles,
    count(*) FILTER (WHERE o.outcome = 'collaboration')::int AS colaboraciones_generadas
FROM ai_match_suggestions s
LEFT JOIN match_outcomes o
    ON o.target_type = 'ai_suggestion' AND o.target_id = s.id::text
GROUP BY 1
ORDER BY 1;

COMMIT;
GRANT SELECT, INSERT, UPDATE, DELETE ON match_candidates, ai_match_suggestions TO alma;
GRANT SELECT ON dashboard_metricas TO alma;

