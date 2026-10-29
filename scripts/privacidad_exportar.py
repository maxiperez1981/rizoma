"""Prepara la copia de los datos de una persona (derecho de acceso) para revisión humana.

Uso (desde la carpeta del proyecto):
  PYTHONPATH=. python3 scripts/privacidad_exportar.py --email persona@ejemplo.org [--solicitud <id>]

No envía nada: deja un JSON con permisos 600 en /var/lib/rizoma-privacy/exportaciones/
para que una persona lo revise (incluye datos de terceros) y lo envíe por un canal
adecuado. Con --solicitud marca el pedido como "en_curso".
"""
import argparse

from sqlalchemy import text

import models
from database import SessionLocal
from services import privacy_export

CARPETA = "/var/lib/rizoma-privacy/exportaciones"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--solicitud", help="id del pedido en privacy_requests")
    ap.add_argument("--carpeta", default=CARPETA)
    a = ap.parse_args()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == a.email.strip().lower()).first()
        if not user:
            raise SystemExit("No hay una cuenta con ese correo")
        resultado = privacy_export.exportar(db, user)
        ruta = privacy_export.guardar_paquete(resultado, a.carpeta)
        if a.solicitud:
            db.execute(text("UPDATE privacy_requests SET estado = 'en_curso' WHERE id = CAST(:i AS uuid)"),
                       {"i": a.solicitud})
            db.commit()
        print(f"Paquete para revisar: {ruta}")
        print("Cantidades:", resultado["cantidades"])
        print("Revisar antes de enviar: incluye datos de otras personas.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
