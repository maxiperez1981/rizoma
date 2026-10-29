-- Paso 2 del rizoma: el tema como entidad unica y compartida.
--
-- Hasta ahora cada CV generaba un grafo con nodos propios: el "PostgreSQL" de
-- una persona y el de otra eran dos nodos distintos colgando de cada CV, asi
-- que dos grafos nunca compartian un nodo y no podian relacionarse.
--
-- Estas tablas hacen que el tema exista una sola vez y que las personas se
-- cuelguen de el. Recien ahi los grafos individuales pasan a ser un solo grafo.

BEGIN;

CREATE TABLE IF NOT EXISTS topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(160) UNIQUE NOT NULL,
    label VARCHAR(160) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sinonimos que apuntan a un tema canonico. Editable a mano: la decision de
-- que dos textos son el mismo tema es de producto, no automatizable.
CREATE TABLE IF NOT EXISTS topic_aliases (
    alias_slug VARCHAR(160) PRIMARY KEY,
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_topics (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    relation VARCHAR(16) NOT NULL CHECK (relation IN ('offers', 'wants', 'interest')),
    PRIMARY KEY (user_id, topic_id, relation)
);

CREATE INDEX IF NOT EXISTS ix_user_topics_topic ON user_topics(topic_id);
CREATE INDEX IF NOT EXISTS ix_user_topics_user ON user_topics(user_id);
CREATE INDEX IF NOT EXISTS ix_topic_aliases_topic ON topic_aliases(topic_id);

ALTER TABLE topics OWNER TO alma;
ALTER TABLE topic_aliases OWNER TO alma;
ALTER TABLE user_topics OWNER TO alma;

COMMIT;
