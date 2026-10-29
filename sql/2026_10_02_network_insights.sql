-- Hallazgos derivados del grafo, guardados por corrida:
-- demanda_latente (temas con mas deseo de aprender que oferta) y
-- triangulacion (acuerdo entre modelos al juzgar complementariedad).
CREATE TABLE IF NOT EXISTS network_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    corrida_id UUID NOT NULL,
    alcance VARCHAR(80) NOT NULL DEFAULT 'red completa',
    tipo VARCHAR(40) NOT NULL,
    posicion INTEGER DEFAULT 0,
    titulo VARCHAR(200) DEFAULT '',
    descripcion TEXT DEFAULT '',
    datos JSON DEFAULT '{}',
    modelo_usado VARCHAR(80) DEFAULT '',
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_network_insights_corrida ON network_insights(corrida_id);
CREATE INDEX IF NOT EXISTS ix_network_insights_tipo ON network_insights(tipo);
