"""Revisa embeddings desactualizados y opcionalmente los regenera.

Un embedding queda desactualizado si el perfil tiene texto y ademas: no tiene
vector, no tiene fecha de generacion, o se genero antes de la ultima vez que
cambio la receta (services.embedding_service.RECIPE_UPDATED_AT).

Uso:
  python3 check_embeddings.py          # solo informa; exit 1 si hay pendientes
  python3 check_embeddings.py --fix    # regenera los pendientes
"""
import sys
from datetime import timezone

from database import SessionLocal
import models
from services.embedding_service import (
    RECIPE_UPDATED_AT,
    build_embedding_text,
    update_user_embedding,
)


def motivo_desactualizado(user) -> str:
    """Motivo por el que hay que regenerar, o cadena vacia si esta al dia."""
    if not build_embedding_text(user).strip():
        return ""  # perfil vacio: no hay nada que vectorizar
    if user.embedding is None:
        return "sin embedding"
    if user.embedding_updated_at is None:
        return "sin fecha de generacion"

    generado = user.embedding_updated_at
    if generado.tzinfo is None:
        generado = generado.replace(tzinfo=timezone.utc)
    if generado < RECIPE_UPDATED_AT:
        return f"receta vieja (generado {generado:%Y-%m-%d})"
    return ""


def main() -> int:
    regenerar = "--fix" in sys.argv
    db = SessionLocal()
    try:
        pendientes = []
        for user in db.query(models.User).all():
            motivo = motivo_desactualizado(user)
            if motivo:
                pendientes.append((user, motivo))

        if not pendientes:
            print("Todos los embeddings estan al dia.")
            return 0

        print(f"Embeddings desactualizados: {len(pendientes)}")
        for user, motivo in pendientes:
            print(f"  {user.email}: {motivo}")

        if not regenerar:
            print("\nCorrer con --fix para regenerarlos.")
            return 1

        print()
        fallos = 0
        for user, _ in pendientes:
            if update_user_embedding(user, db):
                db.commit()
                print(f"  + {user.email}: regenerado")
            else:
                db.rollback()
                print(f"  ! {user.email}: fallo al regenerar")
                fallos += 1

        print(f"\nRegenerados={len(pendientes) - fallos}  fallos={fallos}")
        return 1 if fallos else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
