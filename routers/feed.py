from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from auth import get_current_user
from database import get_db
from services import conjunto_service, visibilidad

router = APIRouter(prefix="/api/feed", tags=["feed"])

_VALID_POST_TYPES = {"advance", "project", "credential", "mentorship", "opportunity"}
_FILTER_MAP = {
    "extension": "opportunity",
    "aprendizaje": "advance",
    "pasantia": "portfolio",
    "mentoria": "mentorship",
}


@router.get("")
def get_feed(filter_type: str = "all", user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Requiere sesión: cada publicación lleva nombre, rol e institución de su autor.
    # Como las sugerencias, solo muestra publicaciones del propio conjunto y las institucionales.
    ids_conjunto = conjunto_service.ids_del_conjunto(db, conjunto_service.conjunto_de_email(user.email))
    q = (db.query(models.Post).options(joinedload(models.Post.user))
         .filter(or_(models.Post.user_id.in_(ids_conjunto), models.Post.is_institutional.is_(True)))
         .order_by(models.Post.created_at.desc()))
    if filter_type != "all":
        mapped = _FILTER_MAP.get(filter_type, filter_type)
        if mapped not in _VALID_POST_TYPES:
            raise HTTPException(400, f"Tipo de filtro inválido: '{filter_type}'")
        q = q.filter(models.Post.type == mapped)

    posts = q.limit(20).all()
    result = []
    for p in posts:
        result.append({
            "id": str(p.id),
            "user_name": visibilidad.nombre_visible(p.user, user) if p.user else "Sistema",
            "user_role": p.user.role if p.user else "org",
            "user_institution": visibilidad.institucion_visible(p.user, user) if p.user else "Rizoma",
            "type": p.type,
            "content": p.content,
            "credential_generated": p.credential_generated,
            "tags": p.tags or [],
            "is_institutional": p.is_institutional,
            "created_at": p.created_at.isoformat(),
        })
    return result


@router.post("")
def create_post(
    body: schemas.PostCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    valid_types = ("advance", "project", "credential", "mentorship", "opportunity")
    if body.type not in valid_types:
        raise HTTPException(400, "Tipo de señal inválido")
    post = models.Post(
        user_id=user.id,
        type=body.type,
        content=body.content,
        credential_generated=body.credential_generated,
        tags=body.tags,
    )
    db.add(post)
    db.commit()
    return {"ok": True, "message": "Señal enviada para revisión institucional"}


@router.get("/search")
def search(q: str = "", user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Requiere sesión y busca personas solo dentro del conjunto de quien consulta:
    # sin esto cualquiera podía listar nombres, roles e instituciones desde internet.
    if not q:
        return {"projects": [], "users": [], "credentials": []}

    term = f"%{q.lower()}%"

    projects = db.query(models.Project).filter(
        (models.Project.title.ilike(term)) | (models.Project.description.ilike(term))
    ).limit(5).all()

    # Se busca sobre lo que cada persona deja ver (nombre visible, institución
    # visible) y solo entre quienes aceptan aparecer en búsquedas.
    ids_conjunto = conjunto_service.ids_del_conjunto(db, conjunto_service.conjunto_de_email(user.email))
    candidatos = (db.query(models.User).filter(models.User.id.in_(ids_conjunto))
                  .order_by(models.User.name, models.User.id).all())
    users = []
    for u in candidatos:
        if u.id != user.id and not visibilidad.aparece_en_busqueda(u):
            continue
        nombre, institucion = visibilidad.nombre_visible(u, user), visibilidad.institucion_visible(u, user)
        if visibilidad.coincide(q, nombre, institucion):
            users.append((u, nombre, institucion))
        if len(users) == 5:
            break

    credentials = (
        db.query(models.Credential)
        .options(joinedload(models.Credential.project))
        .filter(
            models.Credential.verified == True,
            or_(
                models.Credential.title.ilike(term),
                models.Credential.issuer_name.ilike(term),
                models.Credential.description.ilike(term),
            ),
        )
        .limit(5)
        .all()
    )

    return {
        "projects": [{"id": str(p.id), "title": p.title, "detail": p.institution, "type": "Proyecto"} for p in projects],
        "users": [{"id": str(u.id), "title": nombre, "detail": " · ".join(x for x in (u.role, institucion) if x), "type": "Persona"}
                  for u, nombre, institucion in users],
        "credentials": [
            {
                "id": str(c.id),
                "title": c.title,
                "detail": f"{c.issuer_name or 'Rizoma'} · {c.project.title if c.project else 'Proyecto no asociado'}",
                "type": "Credencial verificada",
                "url": f"/credenciales/{c.id}",
            }
            for c in credentials
        ],
    }
