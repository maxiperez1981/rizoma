-- Actividades emergentes derivadas del grafo.
--
-- Combinaciones de temas de areas distintas (comunidades del grafo de
-- personas) que nadie reune todavia y que tienen oferta y demanda cruzadas.
-- Cada corrida guarda su conjunto; el alcance distingue la red completa de
-- recortes de prueba (ej. los 50 perfiles ficticios de la ponencia).

CREATE TABLE IF NOT EXISTS emerging_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    corrida_id UUID NOT NULL,
    alcance VARCHAR(80) NOT NULL DEFAULT 'red completa',
    posicion INTEGER DEFAULT 0,
    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT DEFAULT '',
    areas JSON DEFAULT '[]',
    temas JSON DEFAULT '[]',
    n_personas INTEGER DEFAULT 0,
    demanda INTEGER DEFAULT 0,
    oferta INTEGER DEFAULT 0,
    score DOUBLE PRECISION DEFAULT 0,
    modelo_usado VARCHAR(80) DEFAULT '',
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_emerging_activities_corrida ON emerging_activities(corrida_id);

-- Fraccion de corridas (con semillas distintas del algoritmo de areas) en que
-- reaparece la actividad. 1.0 = estable; cerca de 0.5 = depende de la particion.
ALTER TABLE emerging_activities ADD COLUMN IF NOT EXISTS estabilidad DOUBLE PRECISION DEFAULT 1;

-- Permite valorar una actividad emergente como resultado (util / no util).
ALTER TYPE match_target_type ADD VALUE IF NOT EXISTS 'activity';
