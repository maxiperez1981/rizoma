"""Triangula el juicio de complementariedad con tres votantes y pares de control.

Uso (desde /home/alma-academica):
  PYTHONPATH=. python3 scripts/triangulacion.py --prefijo demo.unq. --usuarios 20 --guardar

Por cada usuario muestreado arma tres pares: el mas similar por embeddings,
el mejor camino indirecto y uno al azar sin temas en comun (control). Si un
votante dice "si" casi igual a los pares de control, su veredicto no discrimina.
"""
import argparse
import importlib.util
import json
import math
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import text

import models
from database import SessionLocal
from services import insights_service, rizoma_service as rs, triangulacion_service as tri

spec = importlib.util.spec_from_file_location("gen", "scripts/generar_actividades_emergentes.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def perfil(u):
    return {"name": u.name, "can_offer": u.can_offer or [], "wants_to_learn": u.wants_to_learn or [],
            "interests": u.interests or u.ai_tags or []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefijo", default="demo.unq.")
    ap.add_argument("--usuarios", type=int, default=20)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--guardar", action="store_true")
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    db = SessionLocal()
    try:
        g = gen.recortar(db, a.prefijo)
        usuarios = {u.id: u for u in db.query(models.User).filter(models.User.email.like(a.prefijo + "%")).all()}
        emb = {r[0]: [float(x) for x in r[1].strip("[]").split(",")] for r in db.execute(
            text("select id, embedding::text from users where email like :p and embedding is not null"),
            {"p": a.prefijo + "%"}).fetchall()}
        muestra = rnd.sample(sorted(usuarios, key=str), min(a.usuarios, len(usuarios)))
        pares = []
        for u in muestra:
            sim = sorted(((cos(emb[u], emb[o]), o) for o in emb if o != u), reverse=True)
            pares.append(("similitud", u, sim[0][1], sim[0][0]))
            cam = rs.caminos_desde(g, u, limite=1)
            if cam:
                d = cam[0]["persona_id"]
                pares.append(("indirecto", u, d, cos(emb[u], emb[d])))
            sin_tema = [o for o in emb if o != u and not (g.temas_por_persona[u] & g.temas_por_persona[o])]
            c = rnd.choice(sorted(sin_tema, key=str))
            pares.append(("control", u, c, cos(emb[u], emb[c])))

        def correr(p):
            tipo, u, o, s = p
            r = tri.triangular(perfil(usuarios[u]), perfil(usuarios[o]), s, "")
            return {"tipo": tipo, "a": usuarios[u].name, "b": usuarios[o].name, **r}

        with ThreadPoolExecutor(max_workers=4) as pool:
            items = list(pool.map(correr, pares))
        resumen = tri.resumir(items)
        print(json.dumps(resumen, ensure_ascii=False, indent=1))
        ruta = f"reports/triangulacion_{datetime.now():%Y%m%d_%H%M}.json"
        json.dump({"resumen": resumen, "items": items}, open(ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("detalle en", ruta)
        if a.guardar:
            insights_service.guardar(db, "triangulacion", f"{a.usuarios} usuarios de {a.prefijo}",
                                     [{"titulo": "Triangulacion de complementariedad",
                                       "descripcion": "Acuerdo entre gpt, claude y heuristica local, con pares de control.",
                                       "datos": resumen, "modelo_usado": "gpt+claude+heuristica"}])
            print("guardado en network_insights")
    finally:
        db.close()


if __name__ == "__main__":
    main()
