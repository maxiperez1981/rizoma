import re
import zipfile
from io import BytesIO
from typing import Optional
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user
from database import get_db
from services import embedding_service, privacy_notice, rizoma_service
from services.limites import limitar
from services.privacy_service import anonymize_text, identificadores_de_usuario, minimizar_con_detalle
from services.claude_service import synthesize_profile, get_matches

router = APIRouter(prefix="/api/copilot", tags=["copilot"])

MAX_CV_BYTES = 2_500_000
MAX_TEXTO = 6000  # el mismo tope que CopilotRequest.text
ARCHIVOS_ADMITIDOS = ("txt", "md", "csv", "docx")


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]+", "-", str(value or "").strip().lower())
    return value.strip("-")[:70] or "nodo"


def _graph_from_profile(profile_data: dict, matches: list[schemas.MatchItem]) -> schemas.KnowledgeGraph:
    nodes = [schemas.GraphNode(id="cv", label="CV / trayectoria", kind="source")]
    edges = []
    seen = {"cv"}

    groups = [
        ("can_offer", "knowledge", "conocimiento"),
        ("wants_to_learn", "learning", "aprendizaje"),
        ("interests", "interest", "interés"),
    ]
    for field, kind, edge_label in groups:
        for item in (profile_data.get(field) or [])[:8]:
            node_id = f"{kind}-{_slug(item)}"
            if node_id not in seen:
                nodes.append(schemas.GraphNode(id=node_id, label=str(item), kind=kind))
                seen.add(node_id)
            edges.append(schemas.GraphEdge(source="cv", target=node_id, label=edge_label))

    for m in matches[:4]:
        if not m.project_id:
            continue
        node_id = f"project-{_slug(m.project_id)}"
        if node_id not in seen:
            nodes.append(schemas.GraphNode(id=node_id, label=m.title, kind="project"))
            seen.add(node_id)
        edges.append(schemas.GraphEdge(source="cv", target=node_id, label=m.match_level or "vínculo"))

    return schemas.KnowledgeGraph(nodes=nodes, edges=edges)


def _graph_payload(graph: schemas.KnowledgeGraph) -> dict:
    if hasattr(graph, "model_dump"):
        return graph.model_dump()
    return graph.dict()


def _save_snapshot(
    db: Session,
    user: models.User,
    profile_data: dict,
    graph: schemas.KnowledgeGraph,
    text: str,
    source_filename: str = "",
):
    # Del archivo solo se guarda el tipo: los nombres de archivo suelen llevar el
    # nombre de la persona ("CV_Nombre_Apellido.docx").
    extension = source_filename.rsplit(".", 1)[-1].lower()[:8] if "." in (source_filename or "") else ""
    db.add(models.RizomaSnapshot(
        user_id=user.id,
        source="cv_upload" if source_filename else "copilot_text",
        source_filename=f"archivo .{extension}" if extension else "",
        summary=profile_data.get("summary", ""),
        tags=profile_data.get("tags", []),
        can_offer=profile_data.get("can_offer", []),
        wants_to_learn=profile_data.get("wants_to_learn", []),
        interests=profile_data.get("interests", profile_data.get("tags", [])),
        graph=_graph_payload(graph),
        text_preview=anonymize_text(text, max_len=1000, identifiers=identificadores_de_usuario(user)),
    ))


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            xml = zf.read("word/document.xml")
    except Exception:
        raise HTTPException(400, "No pude leer el DOCX. Probá pegar el texto del CV.")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parts = []
    for p in root.findall(".//w:p", ns):
        texts = [t.text or "" for t in p.findall(".//w:t", ns)]
        line = "".join(texts).strip()
        if line:
            parts.append(line)
    return "\n".join(parts)


def _extract_cv_text(filename: str, data: bytes) -> str:
    name = (filename or "cv").lower()
    if len(data) > MAX_CV_BYTES:
        raise HTTPException(413, "El archivo es demasiado grande. Máximo 2.5 MB.")
    if name.endswith((".txt", ".md", ".csv")):
        return _decode_text(data)
    if name.endswith(".docx"):
        return _extract_docx(data)
    if name.endswith(".pdf"):
        raise HTTPException(415, "PDF todavía no está habilitado en el servidor. Pegá el texto del CV abajo o subí TXT/DOCX.")
    if name.endswith(".doc"):
        raise HTTPException(415, "DOC binario no está habilitado. Guardalo como DOCX o pegá el texto del CV.")
    raise HTTPException(415, "Formato no soportado. Usá TXT, MD, CSV o DOCX.")


def _run_from_text(text: str, user: models.User, db: Session, source_filename: str = "") -> schemas.CopilotResponse:
    if len(text.strip()) < 10:
        raise HTTPException(400, "Subí un CV o pegá al menos 10 caracteres de tu trayectoria")

    credential_titles = [
        c.title for c in db.query(models.Credential).filter(
            models.Credential.user_id == user.id
        ).all()
    ]

    # El nombre y el correo de la persona se retiran de la copia que va al modelo.
    profile_data = synthesize_profile(text, credential_titles, identificadores_de_usuario(user))

    user.ai_summary = profile_data.get("summary", "")
    user.ai_tags = profile_data.get("tags", [])
    user.can_offer = profile_data.get("can_offer", [])
    user.wants_to_learn = profile_data.get("wants_to_learn", [])
    user.interests = profile_data.get("interests", profile_data.get("tags", []))
    db.flush()

    open_projects = db.query(models.Project).filter(models.Project.status == "open").all()
    projects_for_match = [
        {
            "id": str(p.id),
            "title": p.title,
            "description": p.description,
            "tags": p.tags or [],
            "roles_available": p.roles_available or [],
            "area": p.area or "",
            "stage": p.stage or "",
            "needs_skills": p.needs_skills or [],
            "teaches_skills": p.teaches_skills or [],
            "required_level": p.required_level or "",
            "time_commitment": p.time_commitment or "",
            "modality": p.modality or "",
            "accepts_learners": bool(p.accepts_learners),
            "offers_mentorship": bool(p.offers_mentorship),
            "status": p.status,
        }
        for p in open_projects
    ]

    raw_matches = get_matches(
        user_summary=profile_data.get("summary", ""),
        user_tags=profile_data.get("tags", []),
        projects=projects_for_match,
        can_offer=profile_data.get("can_offer", []),
        wants_to_learn=profile_data.get("wants_to_learn", []),
        interests=profile_data.get("interests", []),
    )

    matches = []
    for m in raw_matches[:4]:
        project = next((p for p in open_projects if str(p.id) == str(m.get("project_id", ""))), None)
        matches.append(schemas.MatchItem(
            project_id=m.get("project_id"),
            title=project.title if project else m.get("title", "Proyecto"),
            score=m.get("score", 70),
            match_level=m.get("match_level", "Exploratorio"),
            text=m.get("text", ""),
            why=m.get("why", m.get("why_connect", "")),
            you_contribute=m.get("you_contribute", ""),
            you_can_learn=m.get("you_can_learn", ""),
            project_needs=m.get("project_needs", ""),
            why_connect=m.get("why_connect", ""),
            suggested_action=m.get("suggested_action", "Abrir conversación"),
        ))

    graph = _graph_from_profile(profile_data, matches)
    _save_snapshot(db, user, profile_data, graph, text, source_filename)
    embedding_service.update_user_embedding(user, db)
    rizoma_service.sincronizar_usuario(db, user)
    db.commit()
    return schemas.CopilotResponse(
        summary=profile_data.get("summary", ""),
        tags=profile_data.get("tags", []),
        gaps=profile_data.get("gaps", []),
        path_step=profile_data.get("path_step", 0),
        top_area=profile_data.get("top_area", ""),
        can_offer=profile_data.get("can_offer", []),
        wants_to_learn=profile_data.get("wants_to_learn", []),
        interests=profile_data.get("interests", []),
        graph=graph,
        source_filename=source_filename,
        matches=matches,
    )


@router.post("/vista-previa", dependencies=[Depends(limitar("vista_previa", 40))])
async def vista_previa(
    file: Optional[UploadFile] = File(None),
    texto: str = Form(""),
    user: models.User = Depends(get_current_user),
):
    """Copia seudonimizada del CV para revisar antes de enviarla al modelo.

    No llama a ningún modelo ni guarda nada (ni el archivo ni el texto): lee el
    archivo o el texto, retira nombre, correo, teléfonos, documentos,
    direcciones, enlaces y usuarios, y devuelve la copia con lo que se retiró.
    Por eso no exige el aviso leído: el envío al modelo es el paso siguiente.
    """
    archivo = ""
    if file is not None and (file.filename or "").strip():
        data = await file.read()
        texto = _extract_cv_text(file.filename, data)
        archivo = file.filename.rsplit(".", 1)[-1].lower()[:8] if "." in file.filename else ""
    copia, retirado = minimizar_con_detalle(texto, identificadores_de_usuario(user))
    if len(copia) < 10:
        raise HTTPException(400, "Subí un CV o pegá al menos 10 caracteres de tu trayectoria")
    return {"texto": copia[:MAX_TEXTO], "retirado": retirado, "archivo": archivo,
            "recortado": len(copia) > MAX_TEXTO}


@router.post("", response_model=schemas.CopilotResponse, dependencies=[Depends(privacy_notice.requiere_aviso_vigente)])
def run_copilot(
    body: schemas.CopilotRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Si el texto viene de la vista previa de un archivo, se registra solo su tipo.
    archivo = body.archivo.lower() if body.archivo.lower() in ARCHIVOS_ADMITIDOS else ""
    return _run_from_text(body.text, user, db, source_filename=f"cv.{archivo}" if archivo else "")


@router.post("/cv", response_model=schemas.CopilotResponse, dependencies=[Depends(privacy_notice.requiere_aviso_vigente)])
async def run_copilot_from_cv(
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = await file.read()
    text = _extract_cv_text(file.filename or "cv", data).strip()
    return _run_from_text(text, user, db, source_filename=file.filename or "cv")



