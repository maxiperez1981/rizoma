import logging
import os
from html import escape
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session, joinedload

from config import settings
from database import Base, engine, SessionLocal
import models
from routers import auth, users, projects, credentials, copilot, messages, feed, notifications, actividades, red, privacidad, recursos
from services import privacy_notice

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Rizoma API",
    version="2.1.0",
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None if settings.environment == "production" else "/redoc",
    openapi_url=None if settings.environment == "production" else "/openapi.json",
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # Las respuestas de la API y de autenticación traen datos personales: que no
    # queden en la caché del navegador ni de intermediarios.
    if (request.url.path == "/" or response.headers.get("content-type", "").startswith("text/html")
            or request.url.path.startswith(("/api/", "/auth/"))):
        response.headers["Cache-Control"] = "no-store, private, max-age=0"
        response.headers["Pragma"] = "no-cache"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(credentials.router)
app.include_router(copilot.router)
app.include_router(messages.router)
app.include_router(feed.router)
app.include_router(notifications.router)
app.include_router(actividades.router)
app.include_router(red.router)
app.include_router(privacidad.router)
app.include_router(recursos.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": "rizoma", "version": "2.1.0"}


@app.head("/health")
def health_head():
    return Response(status_code=200)


# ── Seed data ──────────────────────────────────────────────────────────────────

SEED_PROJECTS = [
    {
        "title": "Laboratorio de IA responsable",
        "description": "Auditoría social de sistemas automatizados usados en políticas públicas, educación y servicios. El equipo produce fichas de riesgo, entrevistas, tableros y recomendaciones de gobernanza.",
        "institution": "UNQ",
        "roles_available": ["Relevamiento", "Análisis de datos", "Entrevistas", "Visualización", "Comunicación pública"],
        "credential_title": "Competencia en auditoría social de IA",
        "tags": ["IA", "ética", "política pública", "datos"],
        "cover_url": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=900&q=75",
    },
    {
        "title": "Relevamiento territorial barrial",
        "description": "Buscamos estudiantes para relevar, ordenar y visualizar datos de acceso a servicios en barrios del conurbano. La participación acredita rol, horas, entregables y evaluación docente.",
        "institution": "Programa de Extensión UNQ",
        "roles_available": ["Relevamiento de campo", "Procesamiento de datos", "Cartografía digital"],
        "credential_title": "Asistente de relevamiento territorial",
        "tags": ["datos", "territorio", "visualización", "impacto social"],
        "cover_url": "https://images.unsplash.com/photo-1524178232363-1fb2b075b655?auto=format&fit=crop&w=1200&q=75",
    },
    {
        "title": "Mentoría: primer antecedente académico",
        "description": "Mentoría para estudiantes que quieran iniciar su primer proyecto verificable. Máximo 3 estudiantes por semestre. Sin CV previo requerido — sí actitud crítica y disposición a trabajar.",
        "institution": "UNQ",
        "roles_available": ["Mentoreado activo", "Bitácora semanal", "Entrega final"],
        "credential_title": "Bitácora de mentoría firmada",
        "tags": ["mentoría", "portfolio", "primer antecedente", "tutoría 1:1"],
        "cover_url": "",
    },
    {
        "title": "Archivo oral comunitario",
        "description": "Entrevistas, edición, preservación y devolución pública con consentimiento informado. Proyecto de extensión con impacto directo en la comunidad.",
        "institution": "UNQ",
        "roles_available": ["Entrevistador/a", "Editor/a de audio", "Comunicador/a"],
        "credential_title": "Participación en proyecto de memoria comunitaria",
        "tags": ["historia", "comunidad", "comunicación", "extensión"],
        "cover_url": "https://images.unsplash.com/photo-1517048676732-d65bc937f952?auto=format&fit=crop&w=1200&q=75",
    },
]

SEED_POSTS = [
    {
        "user_name": "Programa de Extensión UNQ",
        "type": "opportunity",
        "content": "Buscamos estudiantes para relevar, ordenar y visualizar datos de acceso a servicios en barrios del conurbano. La participación acredita rol, horas, entregables y evaluación docente.",
        "credential_generated": "Asistente de relevamiento territorial + tablero de datos publicado.",
        "tags": ["datos", "territorio", "visualización", "impacto social"],
        "is_institutional": True,
    },
    {
        "user_name": "Laboratorio IA UNQ",
        "type": "opportunity",
        "content": "Abrimos convocatoria para el ciclo 2026 del Lab IA responsable. Buscamos estudiantes de cualquier carrera con ganas de aprender auditoría de sistemas automatizados.",
        "credential_generated": "Competencia verificada en auditoría social de IA.",
        "tags": ["IA", "ética", "política pública"],
        "is_institutional": True,
    },
]


def _seed(db: Session):
    if not db.query(models.User).filter(models.User.email == "admin").first():
        if settings.initial_admin_password:
            from auth import hash_password
            admin = models.User(
                email="admin",
                password_hash=hash_password(settings.initial_admin_password),
                name="Administrador",
                role="admin",
                institution="Rizoma",
            )
            db.add(admin)
            db.commit()
            logging.info("Usuario admin inicial creado desde INITIAL_ADMIN_PASSWORD")
        else:
            logging.info("No se creó admin inicial: INITIAL_ADMIN_PASSWORD no está configurado")

    if db.query(models.Project).count() > 0:
        return

    system_user = models.User(
        email="sistema@rizoma.entornodepruebas.com.ar",
        password_hash="$2b$12$disabled",
        name="Sistema Rizoma",
        role="org",
        institution="Rizoma",
    )
    db.add(system_user)
    db.flush()

    for data in SEED_PROJECTS:
        project = models.Project(
            title=data["title"],
            description=data["description"],
            institution=data["institution"],
            created_by=system_user.id,
            status="open",
            roles_available=data["roles_available"],
            credential_title=data["credential_title"],
            tags=data["tags"],
            cover_url=data["cover_url"],
        )
        db.add(project)

    for data in SEED_POSTS:
        post = models.Post(
            user_id=system_user.id,
            type=data["type"],
            content=data["content"],
            credential_generated=data["credential_generated"],
            tags=data["tags"],
            is_institutional=data["is_institutional"],
        )
        db.add(post)

    db.commit()
    logging.info("Seed completado: %d proyectos, %d posts", len(SEED_PROJECTS), len(SEED_POSTS))


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed(db)
        # Publica la versión vigente del aviso; si su texto cambió sin subir la
        # versión, la aplicación no arranca (services/privacy_notice.py).
        privacy_notice.asegurar_publicacion(db)
    finally:
        db.close()


# ── SPA fallback ───────────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/credenciales/{credential_id}", response_class=HTMLResponse, include_in_schema=False)
    def public_credential_page(credential_id: UUID):
        db = SessionLocal()
        try:
            credential = (
                db.query(models.Credential)
                .options(joinedload(models.Credential.project))
                .filter(models.Credential.id == credential_id, models.Credential.verified == True)
                .first()
            )
            if not credential:
                raise HTTPException(status_code=404, detail="Credencial verificada no encontrada")

            title = escape(credential.title)
            issuer = escape(credential.issuer_name or "Rizoma")
            project_title = escape(credential.project.title if credential.project else "Proyecto no asociado")
            verified_at = credential.verified_at.strftime("%d/%m/%Y") if credential.verified_at else "validacion institucional"
            hours = f"{credential.hours} horas" if credential.hours else "Horas no informadas"
            tags = "".join(f"<span>{escape(str(tag))}</span>" for tag in (credential.tags or []))

            return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} - Credencial verificada - Rizoma</title>
  <style>
    :root {{ --ink:#181818; --muted:#666; --line:#e5e1dc; --primary:#c8102e; --soft:#faf7f4; }}
    body {{ margin:0; font-family:Arial,sans-serif; color:var(--ink); background:var(--soft); }}
    main {{ max-width:760px; margin:0 auto; padding:42px 20px; }}
    .card {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:26px; box-shadow:0 14px 40px rgba(20,20,20,.08); }}
    .brand {{ color:var(--primary); font-weight:800; letter-spacing:.08em; text-transform:uppercase; font-size:12px; }}
    h1 {{ margin:12px 0 8px; font-size:32px; line-height:1.1; }}
    p {{ line-height:1.55; }}
    .verified {{ display:inline-flex; color:#0f6b3d; background:#ecf8f1; border:1px solid #bfe8cf; border-radius:999px; padding:7px 11px; font-weight:700; font-size:13px; }}
    .meta {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:22px 0; }}
    .meta div {{ border:1px solid var(--line); border-radius:6px; padding:12px; background:#fff; }}
    .meta span {{ display:block; color:var(--muted); font-size:12px; margin-bottom:4px; }}
    .tags {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }}
    .tags span {{ border:1px solid var(--line); border-radius:999px; padding:5px 9px; font-size:12px; color:var(--muted); }}
    a {{ color:var(--primary); font-weight:700; }}
  </style>
</head>
<body>
  <main>
    <article class="card">
      <div class="brand">Rizoma</div>
      <h1>{title}</h1>
      <div class="verified">Credencial verificada</div>
      <section class="meta">
        <div><span>Emisor</span><strong>{issuer}</strong></div>
        <div><span>Proyecto</span><strong>{project_title}</strong></div>
        <div><span>Validacion</span><strong>{verified_at}</strong><br>{hours}</div>
      </section>
      <p>Esta credencial fue emitida y validada institucionalmente en Rizoma. La vista publica muestra informacion minima para verificar el respaldo sin exponer datos personales del titular.</p>
      <div class="tags">{tags}</div>
      <p style="margin-top:24px"><a href="/">Volver a Rizoma</a></p>
    </article>
  </main>
</body>
</html>"""
        finally:
            db.close()

    @app.get("/privacidad", include_in_schema=False)
    def privacy_page():
        response = FileResponse(str(privacy_notice.NOTICE_PATH), media_type="text/html; charset=utf-8")
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/presentacion", include_in_schema=False)
    def presentation_page():
        response = FileResponse(str(STATIC_DIR / "presentacion.html"), media_type="text/html; charset=utf-8")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/openapi.json", include_in_schema=False)
    @app.get("/docs", include_in_schema=False)
    @app.get("/redoc", include_in_schema=False)
    def disabled_docs():
        if settings.environment == "production":
            raise HTTPException(status_code=404, detail="No encontrado")
        raise HTTPException(status_code=404, detail="No encontrado")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        index = STATIC_DIR / "index.html"
        response = FileResponse(str(index))
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response
