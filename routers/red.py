import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from services.limites import limitar
from services import (cohortes, conjunto_service, evaluacion_service, insights_service, pesos_service,
                      pregunta_service, privacy_notice, rizoma_service, visibilidad)

router = APIRouter(prefix="/api/red", tags=["red"])
ROLES_INSTITUCIONALES = ("teacher", "org", "admin")


class PreguntaIn(BaseModel):
    pregunta: str = Field(min_length=3, max_length=400)


class SimulacionIn(BaseModel):
    nombre: str = Field(default="Persona simulada", max_length=80)
    can_offer: List[str] = Field(default_factory=list, max_length=12)
    wants_to_learn: List[str] = Field(default_factory=list, max_length=12)
    interests: List[str] = Field(default_factory=list, max_length=12)


@router.get("/demanda-latente")
def demanda_latente(alcance: str = insights_service.ALCANCE_COMPLETO,
                    user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return insights_service.ultima(db, "demanda_latente", alcance)


@router.post("/demanda-latente/recalcular", dependencies=[Depends(limitar("recalcular", 6))])
def recalcular_demanda(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ROLES_INSTITUCIONALES:
        raise HTTPException(403, "Solo docentes, organizaciones o administracion pueden recalcular")
    return insights_service.generar_demanda_latente(db)


@router.get("/equipo/{actividad_id}", dependencies=[Depends(limitar("equipo", 60))])
def equipo(actividad_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Equipo armado dentro del conjunto de quien consulta; nombres solo de su cohorte.
    grafo, _ = conjunto_service.grafo_del_conjunto(db, user)
    res = insights_service.equipo_de_actividad(
        db, actividad_id, visibles=lambda ids: cohortes.ids_visibles(db, user, ids), grafo=grafo)
    if not res:
        raise HTTPException(404, "Actividad no encontrada o sin datos suficientes")
    return res


@router.post("/preguntar", dependencies=[Depends(privacy_notice.requiere_aviso_vigente), Depends(limitar("preguntar", 20))])
def preguntar(body: PreguntaIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return pregunta_service.preguntar(db, user, body.pregunta)


@router.post("/simular", dependencies=[Depends(limitar("simular", 30))])
def simular(body: SimulacionIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Solo contra el conjunto de quien simula, con los nombres que cada persona deja ver.
    g, _ = conjunto_service.grafo_del_conjunto(db, user)
    return rizoma_service.simular_persona(g, body.model_dump())


@router.get("/triangulacion")
def triangulacion(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    ultimo = (db.query(models.Insight).filter(models.Insight.tipo == "triangulacion")
              .order_by(models.Insight.created_at.desc()).first())
    return insights_service._fila(ultimo) if ultimo else {}


class CalificacionIn(BaseModel):
    pair_id: str = Field(min_length=36, max_length=36)
    rating: int = Field(ge=1, le=5)
    comentario: str = Field(default="", max_length=500)


@router.get("/evaluacion/siguiente")
def evaluacion_siguiente(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return evaluacion_service.siguiente(db, user) or {}


@router.post("/evaluacion")
def evaluacion_calificar(body: CalificacionIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not evaluacion_service.calificar(db, user, body.pair_id, body.rating, body.comentario):
        raise HTTPException(400, "No se pudo registrar la calificacion (par inexistente, propio o ya calificado)")
    return {"ok": True}


@router.get("/evaluacion/resumen")
def evaluacion_resumen(incluir_simuladas: bool = False, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ROLES_INSTITUCIONALES:
        raise HTTPException(403, "Solo docentes, organizaciones o administracion")
    return evaluacion_service.resumen(db, incluir_simuladas)


@router.get("/puentes")
def puentes(alcance: str = insights_service.ALCANCE_COMPLETO,
            user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    filas = insights_service.ultima(db, "puentes", alcance)
    if not filas:
        return {}
    # Nombres solo de la cohorte de quien consulta (administración ve todos),
    # y como cada persona eligió mostrarse.
    ids = [p.get("persona_id") for p in filas[0].get("datos", {}).get("personas", [])]
    visibles = cohortes.ids_visibles(db, user, ids)
    nombres = visibilidad.nombres_para(db, user, [uuid.UUID(i) for i in visibles])
    return insights_service.ocultar_nombres(filas[0], visibles, {str(k): v for k, v in nombres.items()})


@router.post("/puentes/recalcular", dependencies=[Depends(limitar("recalcular", 6))])
def recalcular_puentes(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ROLES_INSTITUCIONALES:
        raise HTTPException(403, "Solo docentes, organizaciones o administracion pueden recalcular")
    return insights_service.generar_puentes(db)


@router.get("/pesos", dependencies=[Depends(limitar("pesos", 30))])
def pesos(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ROLES_INSTITUCIONALES:
        raise HTTPException(403, "Solo docentes, organizaciones o administracion")
    return pesos_service.desde_calificaciones(db)
