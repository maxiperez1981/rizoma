-- Unificacion semantica de temas, no destructiva.
-- topics.embedding guarda el embedding de la etiqueta; topic_merges mapea cada
-- tema fusionado a su tema canonico. Ningun tema ni arista persona-tema se
-- borra: el grafo aplica el mapa solo cuando se lo pide (unificar=True).
ALTER TABLE topics ADD COLUMN IF NOT EXISTS embedding vector(1536);
CREATE TABLE IF NOT EXISTS topic_merges (
    topic_id UUID PRIMARY KEY REFERENCES topics(id) ON DELETE CASCADE,
    canonical_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    similitud DOUBLE PRECISION,
    umbral DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT now()
);
