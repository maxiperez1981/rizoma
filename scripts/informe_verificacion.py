"""Informe de verificacion del cambio de orden (Parte 4): antes vs ahora y ejemplos por orden.

Lee los archivos de verificacion/ que generan medir_sugerencias.py (antes y
despues) y, de la base de desarrollo, los veredictos que el modelo emitio
durante la medicion del antes. No llama a modelos ni escribe en la base.
Uso: PYTHONPATH=. python3 scripts/informe_verificacion.py [semilla]
"""
import collections
import json
import random
import sys

from sqlalchemy import text

from database import SessionLocal
from services import rizoma_service as rs

SEMILLA = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
ORDENES = ("rareza", "cruces", "azar")


def veredictos_del_antes():
    db = SessionLocal()
    try:
        g = rs.cargar_grafo(db)
        filas = db.execute(text(
            """select c.user_id_a, c.user_id_b, s.hay_complementariedad
               from ai_match_suggestions s join match_candidates c on c.id = s.candidate_id
               where s.created_at > now() - interval '3 hours'""")).fetchall()
    finally:
        db.close()
    cuenta = collections.Counter()
    for a, b, hay in filas:
        comparten = bool(g.temas_por_persona.get(a, set()) & g.temas_por_persona.get(b, set()))
        cuenta[("si" if hay else "no", "comparten tema" if comparten else "sin tema en comun")] += 1
    return cuenta


def main():
    print("== Veredictos del modelo durante la medicion del antes")
    for (hay, tipo), n in sorted(veredictos_del_antes().items()):
        print(f"  modelo dijo {hay:2} | {tipo:18} | {n}")

    antes = json.load(open("verificacion/sugerencias_antes.json", encoding="utf-8"))
    despues = {o: json.load(open(f"verificacion/sugerencias_despues_{o}.json", encoding="utf-8")) for o in ORDENES}
    print("\n== Sugerencias por persona")
    print("  antes :", antes["resumen"])
    print("  ahora :", despues["rareza"]["resumen"])
    perdidas = sum(len({s["id"] for s in antes["por_persona"][e]} - {s["id"] for s in despues["rareza"]["por_persona"][e]})
                   for e in antes["por_persona"])
    print("  sugerencias de antes que ya no aparecen ahora:", perdidas)

    elegidas = random.Random(SEMILLA).sample(sorted(despues["rareza"]["por_persona"]), 3)
    for e in elegidas:
        print(f"\n### {e} | antes: {len(antes['por_persona'][e])} | ahora: {len(despues['rareza']['por_persona'][e])}")
        for o in ORDENES:
            print(f"  [{o}{' semilla ' + str(despues[o]['parametros'].get('semilla')) if o == 'azar' else ''}]")
            for i, s in enumerate(despues[o]["por_persona"][e][:5], 1):
                print(f"    {i}. {s['nombre']} -- {s['dato']}")


if __name__ == "__main__":
    main()
