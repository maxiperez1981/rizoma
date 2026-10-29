"""Conservación con plazos: revisión diaria que solo informa y depuración con plan.

Plazos propuestos (pendientes de decisión institucional, ver ops/PRIVACIDAD.md):
  - sugerencias y explicaciones (match_candidates y ai_match_suggestions): 12 meses;
  - notificaciones leídas: 6 meses; no leídas: 12 meses;
  - extractos de CV (rizoma_snapshots): 12 meses, salvo el más reciente de cada persona.
La cuenta y el perfil se conservan mientras la cuenta exista o hasta que la
persona pida la baja. Quedan fuera los perfiles del conjunto de prueba de la
ponencia (ficticios), para poder reproducir las cifras publicadas.

La revisión diaria no borra nada. Depurar exige el plan vigente (su huella),
una copia de respaldo reciente y la confirmación de quien opera; queda en
privacy_purge_audit con las cantidades, sin datos personales.
"""
import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.conjunto_service import CONJUNTOS

PLAZOS_MESES = {"sugerencias": 12, "notificaciones_leidas": 6, "notificaciones_no_leidas": 12, "extractos_cv": 12}
PREFIJO_EXCLUIDO = CONJUNTOS["prueba"]["prefijo"]


def corte(meses: int, ahora: datetime) -> datetime:
    return ahora - timedelta(days=round(meses * 30.44))


def _ids(db: Session, sql: str, **params) -> list[str]:
    return sorted(str(r[0]) for r in db.execute(text(sql), params).fetchall())


def plan(db: Session, ahora: datetime = None) -> dict:
    """Qué vencería hoy, por categoría, con una huella del plan."""
    ahora = ahora or datetime.utcnow()
    excl = "SELECT id FROM users WHERE email LIKE :pref"
    p = {"pref": PREFIJO_EXCLUIDO + "%"}
    c_sug = corte(PLAZOS_MESES["sugerencias"], ahora)
    c_leidas = corte(PLAZOS_MESES["notificaciones_leidas"], ahora)
    c_no_leidas = corte(PLAZOS_MESES["notificaciones_no_leidas"], ahora)
    c_cv = corte(PLAZOS_MESES["extractos_cv"], ahora)
    ids = {
        # Borrar el candidato arrastra sus sugerencias y las notificaciones asociadas (ON DELETE CASCADE).
        "match_candidates": _ids(db, f"""SELECT id FROM match_candidates WHERE created_at < :c
            AND user_id_a NOT IN ({excl}) AND user_id_b NOT IN ({excl})""", c=c_sug, **p),
        "ai_match_suggestions": _ids(db, f"""SELECT s.id FROM ai_match_suggestions s
            JOIN match_candidates m ON m.id = s.candidate_id WHERE s.created_at < :c
            AND m.user_id_a NOT IN ({excl}) AND m.user_id_b NOT IN ({excl})""", c=c_sug, **p),
        "notifications": _ids(db, f"""SELECT id FROM notifications WHERE user_id NOT IN ({excl})
            AND ((read AND created_at < :cl) OR (NOT read AND created_at < :cn))""", cl=c_leidas, cn=c_no_leidas, **p),
        "rizoma_snapshots": _ids(db, f"""SELECT id FROM rizoma_snapshots r WHERE created_at < :c
            AND user_id NOT IN ({excl})
            AND id <> (SELECT r2.id FROM rizoma_snapshots r2 WHERE r2.user_id = r.user_id
                       ORDER BY r2.created_at DESC LIMIT 1)""", c=c_cv, **p),
    }
    cuerpo = {"fecha": ahora.date().isoformat(), "plazos_meses": PLAZOS_MESES,
              "cantidades": {k: len(v) for k, v in ids.items()}}
    cuerpo["huella"] = hashlib.sha256(json.dumps({"ids": ids, "plazos": PLAZOS_MESES}, sort_keys=True).encode()).hexdigest()
    cuerpo["_ids"] = ids
    return cuerpo


def aplicar(db: Session, huella_esperada: str, operador: str, respaldo: str, ahora: datetime = None) -> dict:
    vigente = plan(db, ahora)
    if vigente["huella"] != huella_esperada:
        raise ValueError("El plan cambió desde que se revisó: volvé a generarlo")
    ids = vigente.pop("_ids")
    for tabla in ("ai_match_suggestions", "notifications", "match_candidates", "rizoma_snapshots"):
        if ids[tabla]:
            db.execute(text(f"DELETE FROM {tabla} WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": ids[tabla]})
    db.execute(
        text(
            """
            INSERT INTO privacy_purge_audit (id, tipo, sujeto, plan_sha256, counts_json, operator, backup_reference, purged_at)
            VALUES (gen_random_uuid(), 'conservacion', '', :h, CAST(:c AS json), :o, :b, now())
            """
        ),
        {"h": vigente["huella"], "c": json.dumps(vigente["cantidades"]), "o": operador, "b": respaldo},
    )
    db.commit()
    return vigente
