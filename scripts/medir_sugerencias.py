"""Cuenta las sugerencias de personas que devuelve el endpoint para cada perfil de un conjunto.

Llama a la funcion del endpoint directamente, con la base configurada en .env:
usar SOLO contra la base de desarrollo. Con el codigo anterior al cambio puede
llamar al modelo de lenguaje (para las sugerencias que no esten en cache).

Uso: PYTHONPATH=. python3 scripts/medir_sugerencias.py --prefijo demo.unq. --salida antes.json
     PYTHONPATH=. python3 scripts/medir_sugerencias.py --prefijo demo.unq. --salida despues.json --orden rareza
"""
import argparse
import inspect
import json
import statistics

from config import settings
from database import SessionLocal
import models
from routers import users


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefijo", default="demo.unq.")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--orden", default=None)
    ap.add_argument("--semilla", type=int, default=None)
    a = ap.parse_args()
    if "_dev" not in (settings.database_url or ""):
        raise SystemExit("Este script solo corre contra la base de desarrollo (alma_academica_dev).")

    params = inspect.signature(users.complementary_people).parameters
    extra = {}
    if "orden" in params and a.orden:
        extra["orden"] = a.orden
    if "semilla" in params and a.semilla is not None:
        extra["semilla"] = a.semilla

    db = SessionLocal()
    salida = {}
    try:
        personas = db.query(models.User).filter(models.User.email.like(a.prefijo + "%")).order_by(models.User.email).all()
        for u in personas:
            res = users.complementary_people(user=u, db=db, **extra)
            salida[u.email] = [{"id": str(s.id), "nombre": s.name,
                                **{k: getattr(s, a) for k, a in (("dato", "dato_estructural"), ("bloque", "bloque"),
                                                                 ("posicion", "posicion")) if hasattr(s, a)}}
                               for s in res]
            print(u.email, len(res), flush=True)
    finally:
        db.close()
    n = [len(v) for v in salida.values()]
    resumen = {"personas": len(n), "media": round(statistics.mean(n), 2), "min": min(n), "max": max(n)}
    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump({"resumen": resumen, "parametros": extra, "por_persona": salida}, f, ensure_ascii=False, indent=1)
    print(resumen)


if __name__ == "__main__":
    main()
