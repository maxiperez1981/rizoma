-- Preferencias de visibilidad por persona (18/10/2026): cómo se muestra el
-- nombre, si se ve la bio, si aparece en sugerencias y búsquedas, si se ve la
-- institución. Vacío = valores por defecto (services/visibilidad.py).
-- Aplicar ANTES de reiniciar: el modelo ya lee esta columna.
ALTER TABLE users ADD COLUMN IF NOT EXISTS visibilidad JSON NOT NULL DEFAULT '{}'::json;
