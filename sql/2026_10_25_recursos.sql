-- Recursos que cada persona pone a disposición de la red, avisos «me sirve» y su seguimiento.
-- Traído de Rizoma Afadeco (sql/2026_10_24_recursos.sql + sql/2026_10_25_seguimiento.sql).
ALTER TABLE users ADD COLUMN IF NOT EXISTS recursos JSON NOT NULL DEFAULT '[]'::json;

CREATE TABLE IF NOT EXISTS recurso_usos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recurso_id VARCHAR(12) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    para_que TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    resultado VARCHAR(20),
    resultado_at TIMESTAMP,
    UNIQUE (owner_id, recurso_id, user_id)
);
CREATE INDEX IF NOT EXISTS recurso_usos_owner ON recurso_usos (owner_id);
