"""Derechos de acceso y supresión: exportación para revisión y supresión con plan.

Exportar no entrega nada automáticamente: arma un paquete para que una persona
lo revise antes de enviarlo, porque incluye datos de terceros (mensajes
recibidos, sugerencias con nombres de otras personas). Las tablas y columnas son
explícitas: no hay exportación de la base completa ni SQL configurable.

Suprimir exige un plan con huella (qué se borra y cuánto), una copia de respaldo
reciente y la confirmación de quien opera. Deja un registro en
privacy_purge_audit con el seudónimo de la persona y las cantidades, sin datos
personales. Los proyectos creados por la persona no se borran (otras personas
pueden tener postulaciones o credenciales asociadas): se desvinculan.
"""
import hashlib
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from services import conjunto_service, seudonimos

# Tabla -> columnas que identifican a la persona. Lista cerrada a propósito.
SUJETO = {
    "users": ("id",),
    "user_topics": ("user_id",),
    "rizoma_snapshots": ("user_id",),
    "credentials": ("user_id",),
    "project_applications": ("user_id",),
    "projects": ("created_by",),
    "posts": ("user_id",),
    "messages": ("from_id", "to_id"),
    "connections": ("user_id_a", "user_id_b"),
    "match_candidates": ("user_id_a", "user_id_b"),
    "notifications": ("user_id", "other_user_id"),
    "match_outcomes": ("user_id",),
    "privacy_acknowledgments": ("user_id",),
    "privacy_requests": ("user_id",),
    "blind_pairs": ("a_id", "b_id"),
    "blind_ratings": ("rater_id",),
}
# Nunca salen en una exportación.
PROHIBIDOS = {"password_hash", "token", "secret", "api_key"}
# Se informan sin el valor (vector numérico derivado del perfil).
RESUMIDOS = {"embedding": "vector numérico de 1536 valores calculado a partir del perfil (se omite)"}
# Columnas con texto libre que pueden contener datos de terceros: revisar antes de entregar.
REVISAR = {"content", "body", "message", "explicacion", "notes", "detalle", "bio", "text_preview", "summary"}

# Supresión: orden de borrado de lo que no cae en cascada al borrar la persona.
BORRAR_ANTES = [
    ("notifications", "other_user_id"),
    ("match_outcomes", "user_id"),
    ("messages", "from_id"),
    ("messages", "to_id"),
    ("connections", "user_id_a"),
    ("connections", "user_id_b"),
    ("posts", "user_id"),
    ("project_applications", "user_id"),
    ("credentials", "user_id"),
    ("rizoma_snapshots", "user_id"),
]
# Caen en cascada con la persona (FK ON DELETE CASCADE): se cuentan para el plan.
EN_CASCADA = [
    ("user_topics", "user_id"),
    ("notifications", "user_id"),
    ("match_candidates", "user_id_a"),
    ("match_candidates", "user_id_b"),
    ("blind_pairs", "a_id"),
    ("blind_pairs", "b_id"),
    ("blind_ratings", "rater_id"),
    ("privacy_acknowledgments", "user_id"),
]


def _plano(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    if valor is None or isinstance(valor, (str, int, float, bool, list, dict)):
        return valor
    return str(valor)


def _limpiar(fila: dict) -> dict:
    salida = {}
    for k, v in fila.items():
        if k in PROHIBIDOS or any(p in k for p in ("password", "secret")):
            continue
        salida[k] = RESUMIDOS[k] if k in RESUMIDOS and v is not None else _plano(v)
    return salida


def exportar(db: Session, user) -> dict:
    """Todo lo que Rizoma guarda de una persona, para revisión humana antes de entregar."""
    uid = str(user.id)
    resultado = {
        "persona": seudonimos.seudonimo(uid),
        "generado": datetime.utcnow().isoformat(timespec="seconds"),
        "requiere_revision_humana": True,
        "nota": ("Incluye datos de otras personas (mensajes recibidos, sugerencias que las mencionan). "
                 "Revisar y recortar lo que no corresponda antes de entregar."),
        "columnas_a_revisar": sorted(REVISAR),
        "registros": {},
    }
    for tabla, columnas in SUJETO.items():
        condicion = " OR ".join(f"{c} = CAST(:u AS uuid)" for c in columnas)
        filas = db.execute(text(f"SELECT * FROM {tabla} WHERE {condicion}"), {"u": uid}).mappings().all()
        resultado["registros"][tabla] = [_limpiar(dict(f)) for f in filas]
    sugerencias = db.execute(
        text(
            """
            SELECT s.* FROM ai_match_suggestions s JOIN match_candidates c ON c.id = s.candidate_id
            WHERE c.user_id_a = CAST(:u AS uuid) OR c.user_id_b = CAST(:u AS uuid)
            """
        ),
        {"u": uid},
    ).mappings().all()
    resultado["registros"]["ai_match_suggestions"] = [_limpiar(dict(f)) for f in sugerencias]
    resultado["cantidades"] = {t: len(v) for t, v in resultado["registros"].items()}
    return resultado


def guardar_paquete(resultado: dict, carpeta) -> Path:
    """Escribe el paquete con permisos 600 en una carpeta 700."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    os.chmod(carpeta, 0o700)
    ruta = carpeta / f"exportacion_{resultado['persona']}_{datetime.utcnow():%Y%m%d_%H%M%S}.json"
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)
    return ruta


def _contar(db: Session, tabla: str, columna: str, uid: str) -> int:
    return db.execute(text(f"SELECT count(*) FROM {tabla} WHERE {columna} = CAST(:u AS uuid)"), {"u": uid}).scalar()


def plan_supresion(db: Session, user) -> dict:
    """Qué se borraría al suprimir a la persona, con una huella para confirmar."""
    if user.role == "admin" or str(user.email or "").startswith("sistema@"):
        raise ValueError("No se suprimen cuentas de administración ni del sistema por esta vía")
    if conjunto_service.conjunto_de_email(user.email) == "prueba":
        raise ValueError("El conjunto de prueba de la ponencia es ficticio y se conserva para reproducir las cifras")
    uid = str(user.id)
    cantidades = {}
    for tabla, columna in BORRAR_ANTES + EN_CASCADA:
        cantidades[f"{tabla}.{columna}"] = _contar(db, tabla, columna, uid)
    cantidades["ai_match_suggestions (en cascada)"] = db.execute(
        text("""SELECT count(*) FROM ai_match_suggestions s JOIN match_candidates c ON c.id = s.candidate_id
                WHERE c.user_id_a = CAST(:u AS uuid) OR c.user_id_b = CAST(:u AS uuid)"""), {"u": uid}).scalar()
    cantidades["projects.created_by (se desvincula)"] = _contar(db, "projects", "created_by", uid)
    cantidades["privacy_requests.user_id (se desvincula)"] = _contar(db, "privacy_requests", "user_id", uid)
    cuerpo = {"persona": seudonimos.seudonimo(uid), "cantidades": cantidades}
    cuerpo["huella"] = hashlib.sha256(json.dumps(cuerpo, sort_keys=True).encode()).hexdigest()
    return cuerpo


def aplicar_supresion(db: Session, user, huella_esperada: str, operador: str, respaldo: str) -> dict:
    """Borra a la persona si el plan sigue siendo el confirmado. Deja auditoría sin datos personales."""
    plan = plan_supresion(db, user)
    if plan["huella"] != huella_esperada:
        raise ValueError("El plan cambió desde que se confirmó: volvé a generarlo y revisalo")
    uid = str(user.id)
    db.execute(text("UPDATE privacy_requests SET user_id = NULL, user_ref = :r WHERE user_id = CAST(:u AS uuid)"),
               {"u": uid, "r": plan["persona"]})
    db.execute(text("UPDATE projects SET created_by = NULL WHERE created_by = CAST(:u AS uuid)"), {"u": uid})
    for tabla, columna in BORRAR_ANTES:
        db.execute(text(f"DELETE FROM {tabla} WHERE {columna} = CAST(:u AS uuid)"), {"u": uid})
    db.execute(text("DELETE FROM users WHERE id = CAST(:u AS uuid)"), {"u": uid})
    db.execute(
        text(
            """
            INSERT INTO privacy_purge_audit (id, tipo, sujeto, plan_sha256, counts_json, operator, backup_reference, purged_at)
            VALUES (gen_random_uuid(), 'supresion', :s, :h, CAST(:c AS json), :o, :b, now())
            """
        ),
        {"s": plan["persona"], "h": plan["huella"], "c": json.dumps(plan["cantidades"]), "o": operador, "b": respaldo},
    )
    db.commit()
    return plan


def validar_respaldo(carpeta, horas_max: int = 26) -> Path:
    """La copia diaria más reciente, si existe, no está vacía y tiene menos de `horas_max` horas."""
    copias = sorted(Path(carpeta).glob("alma_academica_*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not copias:
        raise ValueError(f"No hay copias de respaldo en {carpeta}")
    ultima = copias[0]
    edad = datetime.now() - datetime.fromtimestamp(ultima.stat().st_mtime)
    if ultima.stat().st_size == 0 or edad > timedelta(hours=horas_max):
        raise ValueError(f"La copia más reciente ({ultima.name}) está vacía o tiene más de {horas_max} horas")
    return ultima
