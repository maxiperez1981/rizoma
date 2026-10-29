"""Regenera y guarda todos los hallazgos derivados del grafo.

Uso (desde /home/alma-academica):
  PYTHONPATH=. python3 scripts/regenerar_hallazgos.py                       # red completa
  PYTHONPATH=. python3 scripts/regenerar_hallazgos.py --prefijo demo.unq. --alcance "50 perfiles ficticios (demo.unq)"
  ... --sin-unificar   no aplica la fusion semantica de temas
  ... --sin-ia         no llama al modelo para redactar

Antes, si se agregaron temas nuevos: calcular embeddings y fusiones con
services.temas_service (embeber_temas / aplicar).
"""
import argparse
import importlib.util

from database import SessionLocal
from services import actividades_service, insights_service, rizoma_service

spec = importlib.util.spec_from_file_location("gen", "scripts/generar_actividades_emergentes.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

ap = argparse.ArgumentParser()
ap.add_argument("--prefijo")
ap.add_argument("--alcance", default=insights_service.ALCANCE_COMPLETO)
ap.add_argument("--sin-unificar", action="store_true")
ap.add_argument("--sin-ia", action="store_true")
a = ap.parse_args()
db = SessionLocal()
try:
    unificar = not a.sin_unificar
    g = gen.recortar(db, a.prefijo, unificar) if a.prefijo else rizoma_service.cargar_grafo(db, unificar)
    act = actividades_service.generar(db, grafo=g, alcance=a.alcance, usar_ia=not a.sin_ia)
    dem = insights_service.generar_demanda_latente(db, grafo=g, alcance=a.alcance, usar_ia=not a.sin_ia)
    pue = insights_service.generar_puentes(db, grafo=g, alcance=a.alcance)
    print(f"alcance={a.alcance} unificar={unificar}: {len(act)} actividades, {len(dem)} demandas latentes, "
          f"{len(pue['datos']['personas'])} personas puente, {len(pue['datos']['temas'])} temas puente")
finally:
    db.close()
