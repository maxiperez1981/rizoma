-- Notificacion in-app cuando la IA encuentra un match nuevo con complementariedad.
-- Cierra el hueco entre "se genero la sugerencia" y "el usuario se entera":
-- hoy el matching es pull (solo aparece si el usuario vuelve a entrar a ver
-- sus matches), asi que las 118 sugerencias generadas no le llegan a nadie
-- si no vuelven a la pestania de matches por su cuenta.
--
-- No manda email ni push: solo queda disponible via GET /api/users/notifications.

DO $$ BEGIN
    CREATE TYPE notification_type AS ENUM ('match');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type notification_type NOT NULL DEFAULT 'match',
    candidate_id UUID REFERENCES match_candidates(id) ON DELETE CASCADE,
    other_user_id UUID REFERENCES users(id),
    title VARCHAR(200) NOT NULL,
    body TEXT DEFAULT '',
    read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_notifications_user_unread
    ON notifications(user_id) WHERE NOT read;
