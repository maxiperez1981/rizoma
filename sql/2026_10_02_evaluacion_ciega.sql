-- Evaluacion humana a ciegas de pares de personas.
-- tipo: similitud (el mas parecido por embeddings), indirecto (mejor camino del
-- grafo) o control (al azar, sin temas en comun). El evaluador no ve el tipo.
CREATE TABLE IF NOT EXISTS blind_pairs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    a_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    b_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tipo VARCHAR(20) NOT NULL,
    alcance VARCHAR(80) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT now()
);
CREATE TABLE IF NOT EXISTS blind_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pair_id UUID NOT NULL REFERENCES blind_pairs(id) ON DELETE CASCADE,
    rater_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comentario TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE (pair_id, rater_id)
);
CREATE INDEX IF NOT EXISTS ix_blind_ratings_pair ON blind_ratings(pair_id);
