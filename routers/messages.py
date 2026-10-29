from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from auth import get_current_user
from database import get_db
from services import conjunto_service, visibilidad

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("")
def list_messages(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    msgs = db.query(models.Message).filter(
        models.Message.to_id == user.id
    ).options(joinedload(models.Message.sender)).order_by(models.Message.created_at.desc()).all()

    result = []
    for m in msgs:
        result.append({
            "id": str(m.id),
            "from_user_id": str(m.from_id),
            "from_user_name": visibilidad.nombre_visible(m.sender, user) if m.sender else "Desconocido",
            "from_user_institution": visibilidad.institucion_visible(m.sender, user) if m.sender else "",
            "last_message": m.body[:120],
            "unread": not m.read,
            "created_at": m.created_at.isoformat(),
        })
    return result


@router.post("/{message_id}/read")
def mark_read(message_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg = db.query(models.Message).filter(
        models.Message.id == message_id,
        models.Message.to_id == user.id
    ).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    msg.read = True
    db.commit()
    return {"ok": True}


@router.post("")
def send_message(
    body: schemas.MessageSend,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    to_user = db.query(models.User).filter(models.User.id == body.to_id).first()
    # Solo dentro del propio conjunto, como las sugerencias y la búsqueda.
    if not to_user or (user.role != "admin" and (
        conjunto_service.conjunto_de_email(to_user.email) != conjunto_service.conjunto_de_email(user.email)
    )):
        raise HTTPException(404, "Usuario destinatario no encontrado")
    msg = models.Message(from_id=user.id, to_id=body.to_id, body=body.body)
    db.add(msg)
    db.commit()
    return {"ok": True, "message": "Mensaje enviado"}
