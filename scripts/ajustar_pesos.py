"""Ajusta (informativamente) los pesos del camino indirecto con las calificaciones humanas.

Uso: PYTHONPATH=. python3 scripts/ajustar_pesos.py
Requiere al menos 20 pares indirectos con calificacion; si no, lo avisa.
"""
import json

from database import SessionLocal
from services import pesos_service

db = SessionLocal()
try:
    print(json.dumps(pesos_service.desde_calificaciones(db), ensure_ascii=False, indent=1))
finally:
    db.close()
