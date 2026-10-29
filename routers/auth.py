from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
from auth import hash_password, verify_password, create_access_token
from database import get_db
from routers.users import _completeness
from services import privacy_notice

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenResponse)
def register(body: schemas.RegisterRequest, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    if body.role not in ("student", "teacher", "org"):
        body.role = "student"

    user = models.User(
        email=email,
        password_hash=hash_password(body.password),
        name=body.name,
        role=body.role,
        institution=body.institution,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user.profile_completeness = _completeness(user, db)
    db.commit()
    if body.aviso_version == privacy_notice.NOTICE_VERSION:
        privacy_notice.registrar_lectura(db, user.id, body.aviso_version)
    return {"access_token": create_access_token(str(user.id))}


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email o contraseña incorrectos")
    return {"access_token": create_access_token(str(user.id))}
