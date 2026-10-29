"""Backfill de embeddings para usuarios sin vector.

Uso: python3 backfill_embeddings.py [--all]
Sin --all solo procesa usuarios con embedding NULL.
"""
import sys

from database import SessionLocal
import models
from services.embedding_service import build_embedding_text, update_user_embedding


def main() -> int:
    procesar_todos = '--all' in sys.argv
    db = SessionLocal()
    try:
        query = db.query(models.User)
        if not procesar_todos:
            query = query.filter(models.User.embedding.is_(None))
        usuarios = query.all()
        print(f'Usuarios a procesar: {len(usuarios)}')

        ok = vacios = fallos = 0
        for user in usuarios:
            if not build_embedding_text(user).strip():
                print(f'  - {user.email}: sin texto de perfil, se omite')
                vacios += 1
                continue
            if update_user_embedding(user, db):
                db.commit()
                print(f'  + {user.email}: embedding generado')
                ok += 1
            else:
                db.rollback()
                print(f'  ! {user.email}: fallo al generar')
                fallos += 1

        print(f'\nOK={ok}  sin_texto={vacios}  fallos={fallos}')
        return 1 if fallos else 0
    finally:
        db.close()


if __name__ == '__main__':
    raise SystemExit(main())
