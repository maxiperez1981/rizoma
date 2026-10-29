from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

import models
from auth import get_current_user
from database import get_db
from services import visibilidad

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    notifs = db.query(models.Notification).filter(
        models.Notification.user_id == user.id
    ).options(joinedload(models.Notification.other_user)).order_by(
        models.Notification.created_at.desc()
    ).all()

    result = []
    for n in notifs:
        result.append({
            "id": str(n.id),
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "other_user_id": str(n.other_user_id) if n.other_user_id else None,
            "other_user_name": visibilidad.nombre_visible(n.other_user, user) if n.other_user else None,
            "candidate_id": str(n.candidate_id) if n.candidate_id else None,
            "read": n.read,
            "created_at": n.created_at.isoformat(),
        })
    return result


@router.get("/unread_count")
def unread_count(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.read.is_(False),
    ).count()
    return {"unread": count}


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    notif = db.query(models.Notification).filter(
        models.Notification.id == notification_id,
        models.Notification.user_id == user.id,
    ).first()
    if not notif:
        raise HTTPException(404, "Notificacion no encontrada")
    notif.read = True
    db.commit()
    return {"ok": True}
