"""Aviso de privacidad, constancia de lectura y pedidos de derechos.

Los pedidos (copia de los datos, corrección, baja) quedan registrados para que
los atienda una persona: no se exporta ni se borra nada automáticamente desde la
interfaz. Ver scripts/privacidad_exportar.py y scripts/privacidad_suprimir.py.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from services import privacy_notice, seudonimos
from services.limites import limitar

router = APIRouter(prefix="/api/privacidad", tags=["privacidad"])


class LecturaIn(BaseModel):
    version: str = Field(min_length=1, max_length=40)


class SolicitudIn(BaseModel):
    tipo: Literal["acceso", "rectificacion", "supresion", "otra"]
    detalle: str = Field(default="", max_length=2000)


def _estado(db: Session, user: models.User) -> dict:
    lectura = privacy_notice.lectura_vigente(db, user.id)
    return {
        "version": privacy_notice.NOTICE_VERSION,
        "leida": bool(lectura),
        "leida_at": lectura.acknowledged_at.isoformat() if lectura else None,
        "url": "/privacidad",
    }


@router.get("/estado")
def estado(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _estado(db, user)


@router.post("/lectura")
def registrar_lectura(body: LecturaIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        privacy_notice.registrar_lectura(db, user.id, body.version)
    except ValueError:
        raise HTTPException(409, "El aviso cambió: volvé a leer la versión vigente.")
    return _estado(db, user)


@router.post("/solicitudes", dependencies=[Depends(limitar("privacidad_solicitud", 5, 86400))])
def crear_solicitud(body: SolicitudIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    pedido = models.PrivacyRequest(
        user_id=user.id,
        user_ref=seudonimos.seudonimo(str(user.id)),
        tipo=body.tipo,
        detalle=body.detalle.strip(),
    )
    db.add(pedido)
    db.commit()
    db.refresh(pedido)
    return {"id": str(pedido.id), "tipo": pedido.tipo, "estado": pedido.estado,
            "created_at": pedido.created_at.isoformat()}


@router.get("/solicitudes")
def mis_solicitudes(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    pedidos = (db.query(models.PrivacyRequest)
               .filter(models.PrivacyRequest.user_id == user.id)
               .order_by(models.PrivacyRequest.created_at.desc()).limit(20).all())
    return [{"id": str(p.id), "tipo": p.tipo, "estado": p.estado, "resolucion": p.resolucion,
             "created_at": p.created_at.isoformat(),
             "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None} for p in pedidos]
