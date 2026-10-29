-- Correccion humana que la IA no puede pisar.
--
-- Tomado de observatorio, que usa noticias.clasificacion_bloqueada para
-- congelar las filas corregidas a mano (hoy tiene 55). Sin esto, cada
-- resincronizacion de temas borra y reconstruye todas las aristas, asi que
-- cualquier correccion se pierde en el proximo guardado de perfil.

ALTER TABLE user_topics ADD COLUMN IF NOT EXISTS bloqueado BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE user_topics ADD COLUMN IF NOT EXISTS bloqueado_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_user_topics_bloqueado
    ON user_topics(user_id) WHERE bloqueado;
