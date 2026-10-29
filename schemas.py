from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


def _clean_text(value: str, max_len: int) -> str:
    return (value or "").strip()[:max_len]


def _clean_list(values: list, max_items: int = 12, max_len: int = 60) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for item in values[:max_items]:
        text = _clean_text(str(item), max_len)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _clean_optional_list(values: Optional[list]) -> Optional[list[str]]:
    if values is None:
        return None
    return _clean_list(values)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(min_length=2, max_length=120)
    role: Literal["student", "teacher", "org"] = "student"
    institution: str = Field(default="", max_length=120)
    # Versión del aviso de privacidad que la persona confirmó haber leído al registrarse.
    aviso_version: str = Field(default="", max_length=40)

    @field_validator("name", "institution")
    @classmethod
    def trim_profile_fields(cls, value: str) -> str:
        return _clean_text(value, 120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str
    role: str
    institution: str
    bio: str
    ai_summary: str
    ai_tags: list
    can_offer: list = []
    wants_to_learn: list = []
    interests: list = []
    availability: str = ""
    modality: str = ""
    participation_goal: str = ""
    commitment_level: str = ""
    profile_completeness: int
    credentials_count: int = 0
    projects_count: int = 0
    connections_count: int = 0
    unread_messages: int = 0
    unread_notifications: int = 0
    created_at: datetime
    # Conjunto de perfiles con el que trabaja la persona: prueba, demostracion o general.
    conjunto: str = "general"
    conjunto_etiqueta: str = "Red general"
    # Qué ven los demás de la persona (services/visibilidad.py) y cómo se ve su nombre.
    visibilidad: dict = {}
    nombre_para_otros: str = ""

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    institution: Optional[str] = Field(default=None, max_length=120)
    bio: Optional[str] = Field(default=None, max_length=1200)
    can_offer: Optional[list] = None
    wants_to_learn: Optional[list] = None
    interests: Optional[list] = None
    availability: Optional[str] = Field(default=None, max_length=120)
    modality: Optional[str] = Field(default=None, max_length=40)
    participation_goal: Optional[str] = Field(default=None, max_length=80)
    commitment_level: Optional[str] = Field(default=None, max_length=40)

    @field_validator("name", "institution", "bio", "availability", "modality", "participation_goal", "commitment_level")
    @classmethod
    def trim_optional_fields(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None

    @field_validator("can_offer", "wants_to_learn", "interests")
    @classmethod
    def clean_profile_lists(cls, values: Optional[list]) -> Optional[list[str]]:
        return _clean_optional_list(values)


class UserPublic(BaseModel):
    id: UUID
    name: str
    role: str
    institution: str
    bio: str
    ai_summary: str
    ai_tags: list
    can_offer: list = []
    wants_to_learn: list = []
    interests: list = []

    class Config:
        from_attributes = True


class PersonComplementarity(BaseModel):
    id: UUID
    name: str
    role: str
    institution: str
    ai_summary: str = ""
    can_offer: list = []
    wants_to_learn: list = []
    interests: list = []
    you_can_learn_from_them: list = []
    you_can_offer_them: list = []
    shared_interests: list = []
    connection_type: str = "Complementariedad posible"
    connection_reason: str = ""
    relationship_edges: list = Field(default_factory=list)


class ComplementarySuggestion(PersonComplementarity):
    # El veredicto y el puntaje del modelo no viajan: no intervienen en el orden
    # ni se muestran. La explicacion se pide aparte (ExplicacionSugerencia).
    similarity_score: float = 0.0
    explicacion: str = ""
    # Sugerencia ya redactada, si existe: es el objeto sobre el que se registran resultados.
    ai_suggestion_id: Optional[UUID] = None
    # Camino indirecto que justifica la sugerencia, vacio si el vinculo es directo.
    camino: list = []
    # Dato del grafo que ubica a la sugerencia en su lugar segun el orden elegido.
    dato_estructural: str = ""
    orden: str = "rareza"
    semilla: Optional[int] = None
    # Posicion dentro de su bloque: "comun" (tema en comun), "puente" (camino
    # indirecto) u "otros" (sin camino en el grafo, solo afinidad de perfiles).
    posicion: int = 0
    bloque: str = "comun"
    conjunto: str = "general"


class ExplicacionSugerencia(BaseModel):
    id: UUID
    explicacion: str = ""
    relationship_edges: list = Field(default_factory=list)
    ai_suggestion_id: Optional[UUID] = None
    # True cuando no hubo modelo disponible y respondio el respaldo local.
    degradado: bool = False

class ProjectOut(BaseModel):
    id: UUID
    title: str
    description: str
    institution: str
    status: str
    roles_available: list
    credential_title: str
    tags: list
    cover_url: str
    area: str = ""
    stage: str = ""
    current_members: list = []
    needs_skills: list = []
    teaches_skills: list = []
    required_level: str = ""
    time_commitment: str = ""
    modality: str = ""
    slots_available: int = 0
    accepts_learners: bool = True
    offers_mentorship: bool = False
    applications_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20, max_length=3000)
    institution: str = Field(default="", max_length=120)
    roles_available: list = []
    credential_title: str = Field(default="", max_length=200)
    tags: list = []
    cover_url: str = Field(default="", max_length=500)
    area: str = Field(default="", max_length=120)
    stage: str = Field(default="", max_length=80)
    current_members: list = []
    needs_skills: list = []
    teaches_skills: list = []
    required_level: str = Field(default="", max_length=80)
    time_commitment: str = Field(default="", max_length=80)
    modality: str = Field(default="", max_length=40)
    slots_available: int = Field(default=0, ge=0, le=500)
    accepts_learners: bool = True
    offers_mentorship: bool = False

    @field_validator("title", "description", "institution", "credential_title", "cover_url", "area", "stage", "required_level", "time_commitment", "modality")
    @classmethod
    def trim_project_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("roles_available", "tags", "current_members", "needs_skills", "teaches_skills")
    @classmethod
    def clean_project_lists(cls, values: list) -> list[str]:
        return _clean_list(values)


class CredentialOut(BaseModel):
    id: UUID
    title: str
    type: str
    issuer_name: str
    hours: int
    description: str
    verified: bool
    verified_at: Optional[datetime]
    project_id: Optional[UUID]
    tags: list
    created_at: datetime

    class Config:
        from_attributes = True


class CredentialCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    type: Literal["extension", "portfolio", "mentorship", "course", "application"] = "portfolio"
    issuer_name: str = Field(default="", max_length=120)
    hours: int = Field(default=0, ge=0, le=5000)
    description: str = Field(default="", max_length=1200)
    tags: list = []

    @field_validator("title", "issuer_name", "description")
    @classmethod
    def trim_credential_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("tags")
    @classmethod
    def clean_credential_tags(cls, values: list) -> list[str]:
        return _clean_list(values)


class ApplicationRequest(BaseModel):
    message: str = Field(default="", max_length=1200)
    intent: str = Field(default="explore", max_length=40)

    @field_validator("message", "intent")
    @classmethod
    def trim_message(cls, value: str) -> str:
        return value.strip()


class ApplicationOut(BaseModel):
    id: UUID
    status: str
    project_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class CopilotRequest(BaseModel):
    text: str = Field(min_length=10, max_length=6000)
    # Tipo del archivo de origen si el texto salió de la vista previa de un CV ("docx", "txt"...).
    archivo: str = Field(default="", max_length=8)

    @field_validator("text")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()


class MatchItem(BaseModel):
    project_id: Optional[str] = None
    title: str
    score: int = 70
    match_level: str = "Exploratorio"
    text: str
    why: str = ""
    you_contribute: str = ""
    you_can_learn: str = ""
    project_needs: str = ""
    why_connect: str = ""
    suggested_action: str = "Quiero explorar esta oportunidad"


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str = ""


class KnowledgeGraph(BaseModel):
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []


class CopilotResponse(BaseModel):
    summary: str
    tags: list
    gaps: list
    path_step: int
    top_area: str
    can_offer: list = []
    wants_to_learn: list = []
    interests: list = []
    graph: KnowledgeGraph = Field(default_factory=KnowledgeGraph)
    source_filename: str = ""
    matches: list[MatchItem]


class RizomaSnapshotOut(BaseModel):
    id: UUID
    source: str = "copilot"
    source_filename: str = ""
    summary: str = ""
    tags: list = []
    can_offer: list = []
    wants_to_learn: list = []
    interests: list = []
    graph: dict = {}
    created_at: datetime

    class Config:
        from_attributes = True


class MatchOutcomeCreate(BaseModel):
    target_type: str = Field(pattern="^(person|project|ai_suggestion|activity)$")
    target_id: str = Field(min_length=1, max_length=80)
    outcome: str = Field(pattern="^(started|useful|not_useful|collaboration)$")
    source: str = Field(default="rizoma", max_length=40)
    notes: str = Field(default="", max_length=600)

    @field_validator("target_id", "source", "notes")
    @classmethod
    def trim_outcome_fields(cls, value: str) -> str:
        return value.strip()


class MatchOutcomeOut(BaseModel):
    id: UUID
    target_type: str
    target_id: str
    outcome: str
    source: str = "rizoma"
    notes: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


class DashboardMetricsRow(BaseModel):
    mes: datetime
    sugerencias_totales: int
    vinculos_utiles: int
    vinculos_no_utiles: int
    colaboraciones_generadas: int

    class Config:
        from_attributes = True

class MessageSend(BaseModel):
    to_id: UUID
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def trim_body(cls, value: str) -> str:
        return value.strip()


class MessageThread(BaseModel):
    id: UUID
    from_user_id: UUID
    from_user_name: str
    last_message: str
    unread: bool
    created_at: datetime

    class Config:
        from_attributes = True


class FeedItem(BaseModel):
    id: UUID
    user_name: str
    user_role: str
    user_institution: str
    type: str
    content: str
    credential_generated: str
    tags: list
    is_institutional: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PostCreate(BaseModel):
    type: Literal["advance", "project", "credential", "mentorship", "opportunity"] = "advance"
    content: str = Field(min_length=2, max_length=3000)
    credential_generated: str = Field(default="", max_length=200)
    tags: list = []

    @field_validator("content", "credential_generated")
    @classmethod
    def trim_post_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("tags")
    @classmethod
    def clean_post_tags(cls, values: list) -> list[str]:
        return _clean_list(values)


class SearchResult(BaseModel):
    projects: list
    users: list
    credentials: list


class ApplicationReviewOut(BaseModel):
    id: UUID
    status: str
    project_id: UUID
    user_id: UUID
    user_name: str
    user_email: str
    user_institution: str
    message: str
    credential_id: Optional[UUID]
    credential_title: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


class ApplicationDecision(BaseModel):
    evidence_note: Optional[str] = Field(default=None, max_length=1200)
    hours: int = Field(default=0, ge=0, le=5000)
    tags: list = []

    @field_validator("evidence_note")
    @classmethod
    def trim_evidence_note(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None

    @field_validator("tags")
    @classmethod
    def clean_decision_tags(cls, values: list) -> list[str]:
        return _clean_list(values)

