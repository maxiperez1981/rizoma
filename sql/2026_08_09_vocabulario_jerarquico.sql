-- Vocabulario controlado de dos niveles para los temas.
--
-- Tomado de observatorio (temas_nivel2_controlados + noticia_temas_jerarquicos):
-- el vocabulario vive en la base y se inyecta en el prompt, asi la IA clasifica
-- DENTRO de un conjunto conocido en vez de inventar etiquetas nuevas.
--
-- Resuelve el problema de granularidad: "visualizacion de datos" y
-- "visualizacion de grafos con D3" no tienen que fusionarse ni quedar
-- inconexos; son hermanos bajo el mismo subtema y conectan por ahi.

BEGIN;

CREATE TABLE IF NOT EXISTS topic_vocabulary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    macro VARCHAR(80) NOT NULL,
    subtema VARCHAR(80) NOT NULL,
    UNIQUE (macro, subtema)
);

ALTER TABLE topics ADD COLUMN IF NOT EXISTS macro VARCHAR(80);
ALTER TABLE topics ADD COLUMN IF NOT EXISTS subtema VARCHAR(80);
ALTER TABLE topics ADD COLUMN IF NOT EXISTS confianza REAL;
ALTER TABLE topics ADD COLUMN IF NOT EXISTS motivo TEXT;
ALTER TABLE topics ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(80);
ALTER TABLE topics ADD COLUMN IF NOT EXISTS clasificado_at TIMESTAMPTZ;
-- Clasificacion corregida a mano: la IA no la vuelve a tocar.
ALTER TABLE topics ADD COLUMN IF NOT EXISTS clasificacion_bloqueada BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS ix_topics_macro ON topics(macro);
CREATE INDEX IF NOT EXISTS ix_topics_subtema ON topics(subtema);

ALTER TABLE topic_vocabulary OWNER TO alma;

COMMIT;
