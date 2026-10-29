import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from services import privacy_notice, recursos_service
from services.limites import limitar

router = APIRouter(prefix="/api/recursos", tags=["recursos"])


class MisRecursos(BaseModel):
    recursos: list = Field(default_factory=list)


class Resultado(BaseModel):
    resultado: str = Field(default="", max_length=20)


class MeSirve(BaseModel):
    para_que: str = Field(default="", max_length=600)


@router.get("")
def catalogo(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return recursos_service.catalogo(db, user)


@router.get("/para-mi")
def para_mi(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return recursos_service.para_mi(db, user)


@router.get("/mios")
def mios(user: models.User = Depends(get_current_user)):
    return {"tipos": recursos_service.TIPOS, "recursos": user.recursos or []}


@router.put("/mios", dependencies=[Depends(privacy_notice.requiere_aviso_vigente), Depends(limitar("recursos", 30))])
def guardar(body: MisRecursos, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"tipos": recursos_service.TIPOS, "recursos": recursos_service.guardar(db, user, body.recursos)}


@router.post("/{owner_id}/{recurso_id}/me-sirve",
             dependencies=[Depends(privacy_notice.requiere_aviso_vigente), Depends(limitar("me_sirve", 20, 86400))])
def me_sirve(owner_id: uuid.UUID, recurso_id: str, body: MeSirve,
             user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return recursos_service.me_sirve(db, user, owner_id, recurso_id, body.para_que)


@router.get("/seguimiento")
def seguimiento(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return recursos_service.seguimiento(db, user)


@router.post("/usos/{uso_id}/resultado", dependencies=[Depends(limitar("resultado_recurso", 60))])
def resultado(uso_id: uuid.UUID, body: Resultado, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return recursos_service.registrar_resultado(db, user, uso_id, body.resultado)
