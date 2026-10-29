-- Marca las calificaciones de prueba (generadas por IA o por scripts) para que el
-- resumen y el ajuste de pesos las excluyan por defecto sin borrarlas.
ALTER TABLE blind_ratings ADD COLUMN IF NOT EXISTS simulada BOOLEAN NOT NULL DEFAULT false;
