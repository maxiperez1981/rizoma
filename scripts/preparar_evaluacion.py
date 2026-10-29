"""Prepara los pares para la evaluacion humana a ciegas.

Uso (desde /home/alma-academica):
  PYTHONPATH=. python3 scripts/preparar_evaluacion.py --prefijo demo.unq. --usuarios 20
Crea, por usuario muestreado, un par de cada tipo (similitud, indirecto, control). Es idempotente por (a, b, alcance).
"""
import argparse
import importlib.util

from database import SessionLocal
from services import evaluacion_service

spec = importlib.util.spec_from_file_location("gen", "scripts/generar_actividades_emergentes.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

ap = argparse.ArgumentParser()
ap.add_argument("--prefijo", default="demo.unq.")
ap.add_argument("--usuarios", type=int, default=20)
ap.add_argument("--seed", type=int, default=11)
a = ap.parse_args()
db = SessionLocal()
try:
    g = gen.recortar(db, a.prefijo)
    n = evaluacion_service.preparar(db, g, a.prefijo, a.usuarios, f"{a.prefijo}*", a.seed)
    print(f"{n} pares nuevos")
finally:
    db.close()
