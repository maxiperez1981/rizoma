"""Supresión de una persona a pedido (derecho de supresión), en dos pasos.

Uso (desde la carpeta del proyecto):
  1) Plan, sin borrar nada:
     PYTHONPATH=. python3 scripts/privacidad_suprimir.py --email persona@ejemplo.org
  2) Aplicar, con la huella del plan revisado:
     PYTHONPATH=. python3 scripts/privacidad_suprimir.py --email persona@ejemplo.org \
        --confirmar <huella> --operador "Nombre" [--solicitud <id>]

Aplicar exige una copia de respaldo de menos de 26 horas en backups/db (si no la
hay, correr antes backup_db.sh). Queda registrado en privacy_purge_audit con el
seudónimo de la persona y las cantidades, sin datos personales. La supresión
llega a los respaldos cuando rotan (14 copias diarias): antes de restaurar una
copia hay que reaplicar las supresiones registradas.
"""
import argparse
from pathlib import Path

from sqlalchemy import text

import models
from database import SessionLocal
from services import privacy_export

RESPALDOS = Path(__file__).resolve().parent.parent / "backups" / "db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--confirmar", help="huella del plan revisado")
    ap.add_argument("--operador", default="")
    ap.add_argument("--solicitud", help="id del pedido en privacy_requests")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == a.email.strip().lower()).first()
        if not user:
            raise SystemExit("No hay una cuenta con ese correo")
        plan = privacy_export.plan_supresion(db, user)
        print("Persona:", plan["persona"])
        for k, v in plan["cantidades"].items():
            print(f"  {k}: {v}")
        print("Huella del plan:", plan["huella"])
        if not a.confirmar:
            print("\nNo se borró nada. Para aplicar: --confirmar <huella> --operador <nombre>")
            return
        if not a.operador.strip():
            raise SystemExit("Indicá --operador")
        respaldo = privacy_export.validar_respaldo(RESPALDOS)
        privacy_export.aplicar_supresion(db, user, a.confirmar, a.operador.strip(), str(respaldo))
        if a.solicitud:
            db.execute(text("""UPDATE privacy_requests SET estado = 'resuelta', resolved_at = now(),
                               resolucion = 'Cuenta suprimida' WHERE id = CAST(:i AS uuid)"""), {"i": a.solicitud})
            db.commit()
        print(f"Supresión aplicada. Respaldo previo: {respaldo.name}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
