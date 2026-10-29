from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from services.limites import limitar
from services import actividades_service

router = APIRouter(prefix="/api/actividades-emergentes", tags=["actividades"])


@router.get("")
def listar(alcance: str = actividades_service.ALCANCE_COMPLETO,
           user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ultima corrida guardada. Son agregados de la red: no expone personas."""
    return actividades_service.ultima_corrida(db, alcance)


@router.post("/recalcular", dependencies=[Depends(limitar("recalcular", 6))])
def recalcular(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ("teacher", "org", "admin"):
        raise HTTPException(403, "Solo docentes, organizaciones o administracion pueden recalcular")
    return actividades_service.generar(db)
