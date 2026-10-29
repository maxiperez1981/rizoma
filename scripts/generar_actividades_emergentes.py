"""Detecta actividades emergentes en el grafo y las guarda.

Uso (desde /home/alma-academica):
  PYTHONPATH=. python3 scripts/generar_actividades_emergentes.py
  PYTHONPATH=. python3 scripts/generar_actividades_emergentes.py --prefijo demo.unq. \
      --alcance "50 perfiles ficticios (demo.unq)"
  ... --sin-ia      no llama al modelo: usa el texto local
  ... --dry-run     muestra el resultado sin guardar

--prefijo recorta la red a los usuarios cuyo email empieza con ese texto (sirve
para analizar la red ficticia de la ponencia sin mezclar cuentas de prueba).
"""
import argparse
import collections

from sqlalchemy import text

from database import SessionLocal
from services import actividades_service, rizoma_service


def recortar(db, prefijo, unificar=False):
    completo = rizoma_service.cargar_grafo(db, unificar)
    ids = {r[0] for r in db.execute(
        text("select id from users where email like :p"), {"p": prefijo + "%"}).fetchall()}
    ppt, tpp = collections.defaultdict(set), collections.defaultdict(set)
    for tema, personas in completo.personas_por_tema.items():
        for p in personas & ids:
            ppt[tema].add(p)
            tpp[p].add(tema)
    return rizoma_service.Grafo(
        dict(ppt), dict(tpp), {i: completo.nombres[i] for i in ids}, completo.etiquetas,
        {k: v for k, v in completo.relacion_de.items() if k[0] in ids})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefijo")
    ap.add_argument("--alcance", default=actividades_service.ALCANCE_COMPLETO)
    ap.add_argument("--limite", type=int, default=8)
    ap.add_argument("--sin-ia", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--unificar", action="store_true", help="aplica la fusion semantica de temas")
    a = ap.parse_args()

    db = SessionLocal()
    try:
        grafo = recortar(db, a.prefijo, a.unificar) if a.prefijo else (rizoma_service.cargar_grafo(db, True) if a.unificar else None)
        res = actividades_service.generar(
            db, grafo=grafo, alcance=a.alcance, limite=a.limite,
            usar_ia=not a.sin_ia, guardar=not a.dry_run)
        for r in res:
            print(f"{r['posicion']}. {r['titulo']}  [{r['modelo_usado']}]")
            print(f"   temas: {' + '.join(r['temas'])} | areas: {r['areas'][0]}  <>  {r['areas'][1]}")
            print(f"   personas={r['n_personas']} demanda={r['demanda']} oferta={r['oferta']} score={r['score']} estabilidad={r['estabilidad']}")
            print(f"   {r['descripcion']}")
        print(f"\n{len(res)} actividades ({'sin guardar' if a.dry_run else 'guardadas'}, alcance: {a.alcance})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
