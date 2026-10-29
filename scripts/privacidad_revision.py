"""Revisión de conservación y pedidos de privacidad. Por defecto solo informa.

Uso (desde la carpeta del proyecto):
  PYTHONPATH=. python3 scripts/privacidad_revision.py
  PYTHONPATH=. python3 scripts/privacidad_revision.py --aplicar <huella> --operador "Nombre"

La revisión diaria (systemd/rizoma-privacy-review.timer) corre sin --aplicar:
informa qué venció según los plazos de services/privacy_retention.py y cuántos
pedidos de privacidad siguen pendientes. Aplicar exige la huella del plan y una
copia de respaldo de menos de 26 horas.
"""
import argparse
from pathlib import Path

from sqlalchemy import text

from database import SessionLocal
from services import privacy_export, privacy_retention

RESPALDOS = Path(__file__).resolve().parent.parent / "backups" / "db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", help="huella del plan revisado")
    ap.add_argument("--operador", default="")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        plan = privacy_retention.plan(db)
        plan.pop("_ids")
        print("Conservación al", plan["fecha"], "· plazos (meses):", plan["plazos_meses"])
        for k, v in plan["cantidades"].items():
            print(f"  vencidos en {k}: {v}")
        print("Huella del plan:", plan["huella"])
        pendientes = db.execute(text("""SELECT tipo, count(*), min(created_at) FROM privacy_requests
                                        WHERE estado IN ('pendiente', 'en_curso') GROUP BY tipo""")).fetchall()
        for tipo, n, desde in pendientes:
            print(f"  pedidos de privacidad abiertos ({tipo}): {n}, el más antiguo del {desde:%d/%m/%Y}")
        if not pendientes:
            print("  pedidos de privacidad abiertos: 0")
        if not a.aplicar:
            return
        if not a.operador.strip():
            raise SystemExit("Indicá --operador")
        respaldo = privacy_export.validar_respaldo(RESPALDOS)
        privacy_retention.aplicar(db, a.aplicar, a.operador.strip(), str(respaldo))
        print(f"Depuración aplicada. Respaldo previo: {respaldo.name}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
