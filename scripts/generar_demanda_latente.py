"""Calcula y guarda la demanda formativa latente.

Uso (desde /home/alma-academica):
  PYTHONPATH=. python3 scripts/generar_demanda_latente.py
  PYTHONPATH=. python3 scripts/generar_demanda_latente.py --prefijo demo.unq. --alcance "50 perfiles ficticios (demo.unq)"
"""
import argparse
import importlib.util

from database import SessionLocal
from services import insights_service

spec = importlib.util.spec_from_file_location("gen", "scripts/generar_actividades_emergentes.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

ap = argparse.ArgumentParser()
ap.add_argument("--prefijo")
ap.add_argument("--alcance", default=insights_service.ALCANCE_COMPLETO)
ap.add_argument("--sin-ia", action="store_true")
a = ap.parse_args()
db = SessionLocal()
try:
    g = gen.recortar(db, a.prefijo) if a.prefijo else None
    for r in insights_service.generar_demanda_latente(db, grafo=g, alcance=a.alcance, usar_ia=not a.sin_ia):
        d = r["datos"]
        print(f"{r['posicion']}. {r['titulo']} [{r['modelo_usado']}] tema={d['tema']} quieren={d['demanda']} ofrecen={d['oferta']}")
finally:
    db.close()
