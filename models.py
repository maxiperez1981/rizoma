import uuid
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Enum as SAEnum,
                        Float, ForeignKey, Integer, JSON, String, Text)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(120), nullable=False)
    role = Column(SAEnum("student", "teacher", "org", "admin", name="user_role"), default="student")
    institution = Column(String(120), default="")
    bio = Column(Text, default="")
    ai_summary = Column(Text, default="")
    ai_tags = Column(JSON, default=list)
    can_offer = Column(JSON, default=list)
    wants_to_learn = Column(JSON, default=list)
    interests = Column(JSON, default=list)
    availability = Column(String(120), default="")
    modality = Column(String(40), default="")
    participation_goal = Column(String(80), default="")
    commitment_level = Column(String(40), default="")
    profile_completeness = Column(Integer, default=20)
    embedding = Column(Vector(1536), nullable=True)
    embedding_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Qué ven los demás de la persona (services/visibilidad.py). sql/2026_10_18b_visibilidad.sql
    visibilidad = Column(JSON, default=dict, nullable=False)
    # Recursos que pone a disposición de la red (services/recursos_service.py). sql/2026_10_25_recursos.sql
    recursos = Column(JSON, default=list, nullable=False)

    credentials = relationship("Credential", back_populates="user", foreign_keys="Credential.user_id")
    projects_created = relationship("Project", back_populates="creator")
    applications = relationship("ProjectApplication", back_populates="user")
    posts = relationship("Post", back_populates="user")


class Topic(Base):
    """Tema canonico. Es el nodo compartido que conecta los grafos personales."""
    __tablename__ = "topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(160), unique=True, nullable=False, index=True)
    label = Column(String(160), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Clasificacion en el vocabulario controlado de dos niveles.
    macro = Column(String(80), nullable=True)
    subtema = Column(String(80), nullable=True)
    confianza = Column(Float, nullable=True)
    motivo = Column(Text, nullable=True)
    prompt_version = Column(String(80), nullable=True)
    clasificado_at = Column(DateTime, nullable=True)
    clasificacion_bloqueada = Column(Boolean, default=False, nullable=False)
    embedding = Column(Vector(1536), nullable=True)


class TopicVocabulary(Base):
    """Vocabulario controlado que se inyecta en el prompt de clasificacion."""
    __tablename__ = "topic_vocabulary"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    macro = Column(String(80), nullable=False)
    subtema = Column(String(80), nullable=False)


class TopicAlias(Base):
    """Sinonimo que apunta a un tema canonico."""
    __tablename__ = "topic_aliases"

    alias_slug = Column(String(160), primary_key=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)


class UserTopic(Base):
    """Arista persona-tema. relation: offers | wants | interest."""
    __tablename__ = "user_topics"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    relation = Column(String(16), primary_key=True)
    # Corregida a mano: la resincronizacion no la toca.
    bloqueado = Column(Boolean, default=False, nullable=False)
    bloqueado_at = Column(DateTime, nullable=True)


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    institution = Column(String(120), default="")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(SAEnum("open", "closed", "completed", name="project_status"), default="open")
    roles_available = Column(JSON, default=list)
    credential_title = Column(String(200), default="")
    tags = Column(JSON, default=list)
    cover_url = Column(String(500), default="")
    area = Column(String(120), default="")
    stage = Column(String(80), default="")
    current_members = Column(JSON, default=list)
    needs_skills = Column(JSON, default=list)
    teaches_skills = Column(JSON, default=list)
    required_level = Column(String(80), default="")
    time_commitment = Column(String(80), default="")
    modality = Column(String(40), default="")
    slots_available = Column(Integer, default=0)
    accepts_learners = Column(Boolean, default=True)
    offers_mentorship = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("User", back_populates="projects_created")
    credentials = relationship("Credential", back_populates="project")
    applications = relationship("ProjectApplication", back_populates="project")


class Credential(Base):
    __tablename__ = "credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    type = Column(SAEnum("extension", "portfolio", "mentorship", "course", "application", name="credential_type"), default="portfolio")
    issuer_name = Column(String(120), default="")
    hours = Column(Integer, default=0)
    description = Column(Text, default="")
    verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="credentials", foreign_keys=[user_id])
    project = relationship("Project", back_populates="credentials")


class ProjectApplication(Base):
    __tablename__ = "project_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    message = Column(Text, default="")
    status = Column(SAEnum("pending", "accepted", "rejected", name="application_status"), default="pending")
    credential_id = Column(UUID(as_uuid=True), ForeignKey("credentials.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="applications")
    project = relationship("Project", back_populates="applications")


class Connection(Base):
    __tablename__ = "connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id_a = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    user_id_b = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(SAEnum("pending", "accepted", name="connection_status"), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class RizomaSnapshot(Base):
    __tablename__ = "rizoma_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String(40), default="copilot")
    source_filename = Column(String(255), default="")
    summary = Column(Text, default="")
    tags = Column(JSON, default=list)
    can_offer = Column(JSON, default=list)
    wants_to_learn = Column(JSON, default=list)
    interests = Column(JSON, default=list)
    graph = Column(JSON, default=dict)
    text_preview = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class MatchOutcome(Base):
    __tablename__ = "match_outcomes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    target_type = Column(String(20), nullable=False)
    target_id = Column(String(80), nullable=False)
    outcome = Column(String(24), nullable=False)
    source = Column(String(40), default="rizoma")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class MatchCandidate(Base):
    __tablename__ = "match_candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id_a = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    user_id_b = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    similarity_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class AIMatchSuggestion(Base):
    __tablename__ = "ai_match_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("match_candidates.id"), nullable=False, index=True)
    hay_complementariedad = Column(Boolean, default=False)
    score_final = Column(Integer, default=0)
    explicacion = Column(Text, default="")
    relationship_edges = Column(JSON, default=list)
    modelo_usado = Column(String(80), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

class RecursoUso(Base):
    """Aviso «me sirve, para…» sobre un recurso que otra persona puso a disposición."""
    __tablename__ = "recurso_usos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recurso_id = Column(String(12), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    para_que = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Seguimiento a las dos semanas: hablamos | sirvio | no_sirvio.
    resultado = Column(String(20), nullable=True)
    resultado_at = Column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    to_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sender = relationship("User", foreign_keys=[from_id])


class Post(Base):
    __tablename__ = "posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type = Column(SAEnum("advance", "project", "credential", "mentorship", "opportunity", name="post_type"), default="advance")
    content = Column(Text, nullable=False)
    credential_generated = Column(String(200), default="")
    tags = Column(JSON, default=list)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    is_institutional = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="posts")


class Notification(Base):
    """Aviso in-app de que hay un match nuevo. No dispara envio externo (email/push);
    eso se evalua aparte una vez que se decida activarlo con usuarios reales."""
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(SAEnum("match", name="notification_type"), default="match")
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("match_candidates.id", ondelete="CASCADE"), nullable=True)
    other_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, default="")
    read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    other_user = relationship("User", foreign_keys=[other_user_id])



class ActividadEmergente(Base):
    """Combinacion de temas de areas distintas que nadie reune todavia en la red.

    La deriva el grafo (ver rizoma_service.actividades_emergentes); el modelo de
    lenguaje solo la nombra y la explica. Es una hipotesis, no un hecho. Cada
    corrida guarda su propio conjunto: GET devuelve la ultima de cada alcance.
    """
    __tablename__ = "emerging_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    corrida_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    alcance = Column(String(80), default="red completa", nullable=False)
    posicion = Column(Integer, default=0)
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, default="")
    areas = Column(JSON, default=list)
    temas = Column(JSON, default=list)
    n_personas = Column(Integer, default=0)
    demanda = Column(Integer, default=0)
    oferta = Column(Integer, default=0)
    score = Column(Float, default=0.0)
    estabilidad = Column(Float, default=1.0)
    modelo_usado = Column(String(80), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Insight(Base):
    """Hallazgo derivado del grafo y guardado por corrida (demanda latente, triangulacion, ...)."""
    __tablename__ = "network_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    corrida_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    alcance = Column(String(80), default="red completa", nullable=False)
    tipo = Column(String(40), nullable=False, index=True)
    posicion = Column(Integer, default=0)
    titulo = Column(String(200), default="")
    descripcion = Column(Text, default="")
    datos = Column(JSON, default=dict)
    modelo_usado = Column(String(80), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class BlindPair(Base):
    """Par de personas para evaluar a ciegas. `tipo` (similitud|indirecto|control) nunca se expone al evaluador."""
    __tablename__ = "blind_pairs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    a_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    b_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(String(20), nullable=False)
    alcance = Column(String(80), default="", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class BlindRating(Base):
    __tablename__ = "blind_ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pair_id = Column(UUID(as_uuid=True), ForeignKey("blind_pairs.id", ondelete="CASCADE"), nullable=False, index=True)
    rater_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)
    comentario = Column(Text, default="")
    simulada = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TopicMerge(Base):
    """Fusion semantica no destructiva: `topic_id` se lee como `canonical_id` al unificar el grafo."""
    __tablename__ = "topic_merges"

    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    canonical_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    similitud = Column(Float)
    umbral = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Privacidad (sql/2026_10_18_privacidad.sql) ─────────────────────────────────

class PrivacyNotice(Base):
    """Cada versión publicada del aviso, con su huella y una copia del texto."""
    __tablename__ = "privacy_notices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(40), unique=True, nullable=False)
    sha256 = Column(String(64), nullable=False)
    template_snapshot = Column(Text, nullable=False)
    published_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PrivacyAcknowledgment(Base):
    """Constancia de lectura de una versión del aviso. No es consentimiento para difusión."""
    __tablename__ = "privacy_acknowledgments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    notice_version = Column(String(40), nullable=False)
    acknowledged_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PrivacyRequest(Base):
    """Pedido de acceso, rectificación o supresión. Lo atiende una persona, no se resuelve solo."""
    __tablename__ = "privacy_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_ref = Column(String(24), nullable=False, default="")
    tipo = Column(String(20), nullable=False)
    detalle = Column(Text, nullable=False, default="")
    estado = Column(String(20), nullable=False, default="pendiente")
    resolucion = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)


class PrivacyPurgeAudit(Base):
    """Registro de supresiones y depuraciones aplicadas, sin datos personales."""
    __tablename__ = "privacy_purge_audit"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(String(20), nullable=False)
    sujeto = Column(String(24), nullable=False, default="")
    plan_sha256 = Column(String(64), nullable=False)
    counts_json = Column(JSON, nullable=False)
    operator = Column(String(80), nullable=False)
    backup_reference = Column(Text, nullable=False)
    purged_at = Column(DateTime, default=datetime.utcnow, nullable=False)
