from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project_out(p: models.Project, db: Session, applications_count: Optional[int] = None) -> schemas.ProjectOut:
    apps_count = applications_count
    if apps_count is None:
        apps_count = db.query(models.ProjectApplication).filter(models.ProjectApplication.project_id == p.id).count()
    return schemas.ProjectOut(
        id=p.id,
        title=p.title,
        description=p.description,
        institution=p.institution,
        status=p.status,
        roles_available=p.roles_available or [],
        credential_title=p.credential_title,
        tags=p.tags or [],
        cover_url=p.cover_url,
        area=p.area or "",
        stage=p.stage or "",
        current_members=p.current_members or [],
        needs_skills=p.needs_skills or [],
        teaches_skills=p.teaches_skills or [],
        required_level=p.required_level or "",
        time_commitment=p.time_commitment or "",
        modality=p.modality or "",
        slots_available=p.slots_available or 0,
        accepts_learners=bool(p.accepts_learners),
        offers_mentorship=bool(p.offers_mentorship),
        applications_count=apps_count,
        created_at=p.created_at,
    )


@router.get("", response_model=list[schemas.ProjectOut])
def list_projects(
    status: str = "open",
    q: Optional[str] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Project)
    if status != "all":
        query = query.filter(models.Project.status == status)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            models.Project.title.ilike(like) | models.Project.description.ilike(like)
        )
    projects = query.order_by(models.Project.created_at.desc()).all()
    if tag:
        tag_norm = tag.strip().lower()
        projects = [p for p in projects if tag_norm in [str(t).lower() for t in (p.tags or [])]]

    if projects:
        counts_rows = (
            db.query(models.ProjectApplication.project_id, func.count(models.ProjectApplication.id))
            .filter(models.ProjectApplication.project_id.in_([p.id for p in projects]))
            .group_by(models.ProjectApplication.project_id)
            .all()
        )
        apps_counts = {pid: cnt for pid, cnt in counts_rows}
    else:
        apps_counts = {}

    return [_project_out(p, db, apps_counts.get(p.id, 0)) for p in projects]


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: UUID, db: Session = Depends(get_db)):
    p = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Proyecto no encontrado")
    return _project_out(p, db)


@router.post("/{project_id}/apply")
def apply_to_project(
    project_id: UUID,
    body: schemas.ApplicationRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")
    if project.status != "open":
        raise HTTPException(400, "El proyecto no está abierto")

    existing = db.query(models.ProjectApplication).filter(
        models.ProjectApplication.user_id == user.id,
        models.ProjectApplication.project_id == project.id,
    ).first()
    if existing:
        raise HTTPException(400, "Ya manifestaste interés en este proyecto")

    credential = models.Credential(
        user_id=user.id,
        title=f"Interés registrado: {project.title}",
        type="application",
        issuer_name=project.institution or "Rizoma",
        description=f"Interés inicial para explorar participación en el proyecto '{project.title}'. La credencial verificable se emite solo si la experiencia ocurre y es revisada institucionalmente.",
        verified=False,
        project_id=project.id,
        tags=project.tags or [],
    )
    db.add(credential)
    db.flush()

    application = models.ProjectApplication(
        user_id=user.id,
        project_id=project.id,
        message=body.message,
        status="pending",
        credential_id=credential.id,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    db.refresh(credential)

    return {
        "application": {"id": str(application.id), "status": application.status},
        "credential": {
            "id": str(credential.id),
            "title": credential.title,
            "type": credential.type,
            "verified": credential.verified,
        },
        "message": "Interés enviado. Si ambas partes avanzan, podrán conversar y luego validar la experiencia.",
    }


@router.post("", response_model=schemas.ProjectOut)
def create_project(
    body: schemas.ProjectCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in ("teacher", "org", "admin"):
        raise HTTPException(403, "Solo docentes y organizaciones pueden crear proyectos")
    project = models.Project(
        title=body.title,
        description=body.description,
        institution=body.institution or user.institution,
        created_by=user.id,
        roles_available=body.roles_available,
        credential_title=body.credential_title,
        tags=body.tags,
        cover_url=body.cover_url,
        area=body.area,
        stage=body.stage,
        current_members=body.current_members,
        needs_skills=body.needs_skills,
        teaches_skills=body.teaches_skills,
        required_level=body.required_level,
        time_commitment=body.time_commitment,
        modality=body.modality,
        slots_available=body.slots_available,
        accepts_learners=body.accepts_learners,
        offers_mentorship=body.offers_mentorship,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_out(project, db, 0)


def _can_review_project(project: models.Project, user: models.User) -> bool:
    if user.role == "admin":
        return True
    if project.created_by and project.created_by == user.id:
        return True
    same_institution = (project.institution or "").strip().lower() == (user.institution or "").strip().lower()
    return user.role in ("teacher", "org") and bool(project.institution) and same_institution


def _application_review_out(application: models.ProjectApplication) -> schemas.ApplicationReviewOut:
    credential = getattr(application, "credential", None)
    return schemas.ApplicationReviewOut(
        id=application.id,
        status=application.status,
        project_id=application.project_id,
        user_id=application.user.id,
        user_name=application.user.name,
        user_email=application.user.email,
        user_institution=application.user.institution or "",
        message=application.message or "",
        credential_id=application.credential_id,
        credential_title=credential.title if credential else "",
        created_at=application.created_at,
    )


@router.get("/{project_id}/applications", response_model=list[schemas.ApplicationReviewOut])
def list_project_applications(
    project_id: str,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")
    if not _can_review_project(project, user):
        raise HTTPException(403, "No tenés permisos para revisar interesados de este proyecto")
    applications = (
        db.query(models.ProjectApplication)
        .filter(models.ProjectApplication.project_id == project.id)
        .order_by(models.ProjectApplication.created_at.desc())
        .all()
    )
    return [_application_review_out(a) for a in applications]


@router.post("/applications/{application_id}/accept")
def accept_application(
    application_id: UUID,
    body: schemas.ApplicationDecision,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    application = db.query(models.ProjectApplication).filter(
        models.ProjectApplication.id == application_id
    ).first()
    if not application:
        raise HTTPException(404, "Interés no encontrado")
    project = application.project
    if not _can_review_project(project, user):
        raise HTTPException(403, "No tenés permisos para validar esta participación")
    credential = db.query(models.Credential).filter(
        models.Credential.id == application.credential_id
    ).first()
    if credential is None:
        credential = models.Credential(user_id=application.user_id, project_id=project.id)
        db.add(credential)
        db.flush()
        application.credential_id = credential.id
    application.status = "accepted"
    credential.title = project.credential_title or f"Participación verificada: {project.title}"
    credential.type = "extension"
    credential.issuer_name = project.institution or user.institution or "Rizoma"
    credential.hours = body.hours
    credential.description = body.evidence_note or (
        f"Participación validada institucionalmente en el proyecto {project.title}."
    )
    credential.verified = True
    credential.verified_at = datetime.utcnow()
    credential.project_id = project.id
    credential.tags = list(dict.fromkeys((project.tags or []) + (project.needs_skills or []) + (body.tags or [])))[:8]
    db.add(models.Message(
        from_id=user.id,
        to_id=application.user_id,
        body=f"Tu participación en \"{project.title}\" fue validada. Ya tenés la credencial verificada en tu perfil.",
    ))
    db.commit()
    db.refresh(application)
    db.refresh(credential)
    return {
        "application": {"id": str(application.id), "status": application.status},
        "credential": {
            "id": str(credential.id),
            "title": credential.title,
            "verified": credential.verified,
            "verified_at": credential.verified_at.isoformat() if credential.verified_at else None,
        },
        "message": "Participación validada y credencial verificada.",
    }


@router.post("/applications/{application_id}/reject")
def reject_application(
    application_id: UUID,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    application = db.query(models.ProjectApplication).filter(
        models.ProjectApplication.id == application_id
    ).first()
    if not application:
        raise HTTPException(404, "Interés no encontrado")
    if not _can_review_project(application.project, user):
        raise HTTPException(403, "No tenés permisos para revisar este interés")
    application.status = "rejected"
    credential = db.query(models.Credential).filter(
        models.Credential.id == application.credential_id
    ).first()
    if credential:
        credential.verified = False
        credential.description = credential.description or "Interés revisado sin validación institucional."
    db.add(models.Message(
        from_id=user.id,
        to_id=application.user_id,
        body=f"Tu interés en \"{application.project.title}\" fue revisado y no se incorporó en esta instancia.",
    ))
    db.commit()
    return {
        "application": {"id": str(application.id), "status": application.status},
        "message": "Interés marcado como no incorporado.",
    }
