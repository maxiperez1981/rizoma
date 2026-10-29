from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


@router.get("", response_model=list[schemas.CredentialOut])
def list_credentials(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    creds = db.query(models.Credential).filter(
        models.Credential.user_id == user.id
    ).order_by(models.Credential.created_at.desc()).all()
    return [schemas.CredentialOut(
        id=c.id, title=c.title, type=c.type, issuer_name=c.issuer_name,
        hours=c.hours, description=c.description, verified=c.verified,
        verified_at=c.verified_at, project_id=c.project_id,
        tags=c.tags or [], created_at=c.created_at,
    ) for c in creds]


@router.get("/public/{credential_id}")
def get_public_credential(credential_id: UUID, db: Session = Depends(get_db)):
    credential = (
        db.query(models.Credential)
        .options(joinedload(models.Credential.project))
        .filter(models.Credential.id == credential_id, models.Credential.verified == True)
        .first()
    )
    if not credential:
        raise HTTPException(404, "Credencial verificada no encontrada")

    project = credential.project
    return {
        "id": str(credential.id),
        "title": credential.title,
        "type": credential.type,
        "issuer_name": credential.issuer_name,
        "hours": credential.hours,
        "verified": credential.verified,
        "verified_at": credential.verified_at.isoformat() if credential.verified_at else None,
        "project_id": str(credential.project_id) if credential.project_id else None,
        "project_title": project.title if project else "",
        "tags": credential.tags or [],
        "verification_text": "Credencial emitida y validada institucionalmente en Rizoma.",
    }


@router.post("", response_model=schemas.CredentialOut)
def create_credential(
    body: schemas.CredentialCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cred = models.Credential(
        user_id=user.id,
        title=body.title,
        type=body.type,
        issuer_name=body.issuer_name,
        hours=body.hours,
        description=body.description,
        tags=body.tags,
        verified=False,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return schemas.CredentialOut(
        id=cred.id, title=cred.title, type=cred.type, issuer_name=cred.issuer_name,
        hours=cred.hours, description=cred.description, verified=cred.verified,
        verified_at=cred.verified_at, project_id=cred.project_id,
        tags=cred.tags or [], created_at=cred.created_at,
    )
