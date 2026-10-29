-- Privacidad (18/10/2026): aviso versionado con constancia de lectura,
-- solicitudes de derechos y auditoría de supresiones y depuraciones.
-- Aplicar ANTES de reiniciar el servicio: con 2 workers, create_all en paralelo
-- puede chocar al crear tablas nuevas.

CREATE TABLE IF NOT EXISTS privacy_notices (
    id SERIAL PRIMARY KEY,
    version VARCHAR(40) NOT NULL UNIQUE,
    sha256 CHAR(64) NOT NULL,
    template_snapshot TEXT NOT NULL,
    published_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS privacy_acknowledgments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notice_version VARCHAR(40) NOT NULL,
    acknowledged_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (user_id, notice_version)
);

-- user_ref: seudónimo estable de la persona, para que el registro sobreviva a una supresión.
CREATE TABLE IF NOT EXISTS privacy_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    user_ref VARCHAR(24) NOT NULL DEFAULT '',
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('acceso', 'rectificacion', 'supresion', 'otra')),
    detalle TEXT NOT NULL DEFAULT '',
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'en_curso', 'resuelta', 'rechazada')),
    resolucion TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    resolved_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS privacy_requests_estado_idx ON privacy_requests (estado, created_at);

-- Sin datos personales: seudónimo, cantidades por tabla, huella del plan y copia de respaldo usada.
CREATE TABLE IF NOT EXISTS privacy_purge_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('supresion', 'conservacion')),
    sujeto VARCHAR(24) NOT NULL DEFAULT '',
    plan_sha256 CHAR(64) NOT NULL,
    counts_json JSON NOT NULL,
    operator VARCHAR(80) NOT NULL,
    backup_reference TEXT NOT NULL,
    purged_at TIMESTAMP NOT NULL DEFAULT now()
);
