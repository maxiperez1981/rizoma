-- Retira el indice ivfflat sobre users.embedding.
--
-- Con 12 perfiles y lists=100 el indice quedaba practicamente vacio por lista:
-- el planner lo ignoraba (Seq Scan) y ocupaba 1656 kB. Peor aun, si el planner
-- llegara a usarlo, con probes=1 leeria una sola lista y devolveria resultados
-- incompletos.
--
-- El scan secuencial sobre esta cantidad de filas es exacto y mas rapido.
-- Recrear el indice cuando la tabla supere ~1000 perfiles, eligiendo
-- lists = sqrt(cantidad_de_filas) y subiendo ivfflat.probes segun la precision
-- que se necesite. Para ~10k perfiles seria:
--
--   CREATE INDEX ix_users_embedding ON users
--       USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
--   SET ivfflat.probes = 10;

DROP INDEX IF EXISTS ix_users_embedding;
