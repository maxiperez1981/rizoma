import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

import models
from config import settings
from services.privacy_service import anonymize_list, anonymize_text, identificadores_de_usuario

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"

# Fecha de la ultima vez que cambio la "receta" del embedding: el modelo de
# arriba o build_embedding_text(). Los vectores generados antes de esta fecha
# quedan desactualizados y check_embeddings.py los marca para regenerar.
# Al tocar el modelo o la construccion del texto, subir esta fecha.
RECIPE_UPDATED_AT = datetime(2026, 8, 9, tzinfo=timezone.utc)


def _join_items(label: str, values: list, identifiers=()) -> str:
    cleaned = anonymize_list(values or [], identifiers=identifiers)
    return f"{label}: " + ", ".join(cleaned) if cleaned else ""


def build_embedding_text(user: models.User) -> str:
    # Sin el nombre ni el correo de la persona. No se sube RECIPE_UPDATED_AT:
    # los perfiles sin esos datos en el texto dan el mismo texto que antes, y
    # los vectores se rehacen solos cuando la persona actualiza su perfil.
    propios = identificadores_de_usuario(user)
    parts = [
        _join_items("Puede aportar", user.can_offer or [], propios),
        _join_items("Quiere aprender", user.wants_to_learn or [], propios),
        _join_items("Intereses", user.interests or user.ai_tags or [], propios),
    ]
    if user.ai_summary:
        parts.append("Resumen: " + anonymize_text(user.ai_summary, max_len=1200, identifiers=propios))
    elif user.bio:
        parts.append("Bio: " + anonymize_text(user.bio, max_len=1200, identifiers=propios))
    return "\n".join(p for p in parts if p.strip())


def generate_embedding(source_text: str) -> Optional[list[float]]:
    source_text = anonymize_text(source_text, max_len=8000)
    if not source_text or not settings.openai_api_key:
        return None

    payload = {"model": EMBEDDING_MODEL, "input": source_text[:8000]}
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        embedding = data["data"][0]["embedding"]
        return [float(v) for v in embedding]
    except urllib.error.HTTPError as exc:
        logger.error("Error HTTP generando embedding: status=%s", exc.code)
    except Exception as exc:
        logger.error("Error generando embedding: %s", type(exc).__name__)
    return None


def update_user_embedding(user: models.User, db: Session) -> bool:
    embedding = generate_embedding(build_embedding_text(user))
    if embedding is None:
        return False
    user.embedding = embedding
    user.embedding_updated_at = datetime.now(timezone.utc)
    db.add(user)
    return True


def nearest_profiles(user: models.User, db: Session, limit: int = 25) -> list[tuple[models.User, float]]:
    if user.embedding is None:
        return []

    emb_literal = (
        user.embedding
        if isinstance(user.embedding, str)
        else "[" + ",".join(str(float(v)) for v in user.embedding) + "]"
    )

    rows = db.execute(
        text(
            """
            SELECT id, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM users
            WHERE id != CAST(:user_id AS uuid) AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        ),
        {"embedding": emb_literal, "user_id": str(user.id), "limit": limit},
    ).fetchall()

    if not rows:
        return []

    ids = [row[0] for row in rows]
    similarity_by_id = {str(row[0]): float(row[1] or 0.0) for row in rows}
    users_by_id = {
        str(item.id): item
        for item in db.query(models.User).filter(models.User.id.in_(ids)).all()
    }
    return [
        (users_by_id[str(row_id)], similarity_by_id[str(row_id)])
        for row_id in ids
        if str(row_id) in users_by_id
    ]


