"""Aviso de privacidad versionado y constancia de lectura. No es consentimiento para difusión.

Cada versión del aviso (static/privacidad.html) se guarda con su huella. Si
alguien cambia el texto sin subir NOTICE_VERSION, la aplicación no arranca: así
nunca hay dos textos distintos con la misma versión. La constancia registra qué
versión leyó cada persona y cuándo; no certifica su identidad ni autoriza usos
adicionales de sus datos.
"""
import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

NOTICE_VERSION = "2026-10-25.2"
NOTICE_PATH = Path(__file__).resolve().parent.parent / "static" / "privacidad.html"
CODIGO_PENDIENTE = "aviso_privacidad_pendiente"


def huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def leer_aviso() -> str:
    texto = NOTICE_PATH.read_text(encoding="utf-8")
    if NOTICE_VERSION not in texto:
        raise RuntimeError(f"static/privacidad.html no menciona la versión vigente {NOTICE_VERSION}")
    return texto


def verificar_publicacion(huella_guardada, huella_actual: str) -> None:
    """Falla si la versión ya estaba publicada con otro texto."""
    if huella_guardada is not None and huella_guardada != huella_actual:
        raise RuntimeError("El aviso de privacidad cambió sin actualizar NOTICE_VERSION")


def asegurar_publicacion(db: Session) -> None:
    """Registra la versión vigente (idempotente, segura con varios workers) y controla su texto."""
    texto = leer_aviso()
    actual = huella(texto)
    db.execute(
        text(
            """
            INSERT INTO privacy_notices (version, sha256, template_snapshot, published_at)
            VALUES (:v, :h, :t, now()) ON CONFLICT (version) DO NOTHING
            """
        ),
        {"v": NOTICE_VERSION, "h": actual, "t": texto},
    )
    db.commit()
    guardada = db.execute(text("SELECT sha256 FROM privacy_notices WHERE version = :v"),
                          {"v": NOTICE_VERSION}).scalar()
    verificar_publicacion(guardada, actual)


def lectura_vigente(db: Session, user_id):
    return (db.query(models.PrivacyAcknowledgment)
            .filter(models.PrivacyAcknowledgment.user_id == user_id,
                    models.PrivacyAcknowledgment.notice_version == NOTICE_VERSION)
            .first())


def registrar_lectura(db: Session, user_id, version: str) -> models.PrivacyAcknowledgment:
    if version != NOTICE_VERSION:
        raise ValueError("La versión leída no es la vigente")
    previa = lectura_vigente(db, user_id)
    if previa:
        return previa
    db.execute(
        text(
            """
            INSERT INTO privacy_acknowledgments (id, user_id, notice_version, acknowledged_at)
            VALUES (gen_random_uuid(), :u, :v, :t) ON CONFLICT (user_id, notice_version) DO NOTHING
            """
        ),
        {"u": str(user_id), "v": NOTICE_VERSION, "t": datetime.utcnow()},
    )
    db.commit()
    return lectura_vigente(db, user_id)


def requiere_aviso_vigente(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Dependencia para las funciones que tratan datos personales con IA o amplían el perfil."""
    if not lectura_vigente(db, user.id):
        raise HTTPException(428, {"code": CODIGO_PENDIENTE,
                                  "msg": "Antes de seguir, leé y confirmá el aviso de privacidad vigente."})
    return user
