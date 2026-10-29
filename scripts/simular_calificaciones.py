"""Simula evaluadores para probar la herramienta de evaluacion a ciegas.

Uso (desde /home/alma-academica, con el servicio andando):
  PYTHONPATH=. python3 scripts/simular_calificaciones.py            # simula 3 evaluadores sobre todos los pares
  PYTHONPATH=. python3 scripts/simular_calificaciones.py --borrar   # borra TODO lo simulado

Requiere la variable de entorno RIZOMA_DEMO_PASSWORD (clave de las cuentas demo).
Usa la API real (siguiente -> calificar -> resumen -> pesos). Las notas son
sinteticas: dependen del tipo del par con ruido, solo para ejercitar el flujo.
Todo queda marcado con comentario 'SIMULADO'. NO usar estos resultados como evidencia.
"""
import os
import argparse
import json
import random
import urllib.request

from sqlalchemy import text

from database import SessionLocal

BASE = "http://127.0.0.1:6162"
EVALUADORES = ["ej.ana.kuperman@rizoma.local", "ej.nestor.aguirre@rizoma.local", "ej.paula.roldan@rizoma.local"]
MEDIA = {"similitud": 4.2, "indirecto": 3.0, "control": 2.0}


def http(metodo, ruta, token=None, cuerpo=None):
    req = urllib.request.Request(BASE + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--borrar", action="store_true")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        if a.borrar:
            n = db.execute(text("delete from blind_ratings where comentario = 'SIMULADO'")).rowcount
            db.commit()
            print(f"{n} calificaciones simuladas borradas")
            return
        tipo_de = {str(r[0]): r[1] for r in db.execute(text("select id, tipo from blind_pairs")).fetchall()}
        rnd = random.Random(5)
        tokens = {e: http("POST", "/auth/login", cuerpo={"email": e, "password": os.environ["RIZOMA_DEMO_PASSWORD"]})["access_token"] for e in EVALUADORES}
        hechas = 0
        for email, tok in tokens.items():
            while True:
                par = http("GET", "/api/red/evaluacion/siguiente", tok)
                if not par:
                    break
                tipo = tipo_de[par["pair_id"]]
                nota = max(1, min(5, round(rnd.gauss(MEDIA[tipo], 0.9))))
                http("POST", "/api/red/evaluacion", tok, {"pair_id": par["pair_id"], "rating": nota, "comentario": "SIMULADO"})
                hechas += 1
        db.execute(text("update blind_ratings set simulada = true where comentario = 'SIMULADO'"))
        db.commit()
        print(f"{hechas} calificaciones simuladas por {len(tokens)} evaluadores (marcadas como simuladas)")
        print("\n== resumen ==")
        print(json.dumps(http("GET", "/api/red/evaluacion/resumen?incluir_simuladas=true", tokens[EVALUADORES[0]]), ensure_ascii=False, indent=1))
        print("\n== ajuste de pesos ==")
        print(json.dumps(http("GET", "/api/red/pesos", tokens[EVALUADORES[0]]), ensure_ascii=False, indent=1))
    finally:
        db.close()


if __name__ == "__main__":
    main()
