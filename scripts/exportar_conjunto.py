"""Exporta un conjunto de perfiles a un archivo con fecha, sin modificar la base.

Uso (desde la carpeta del proyecto):
  PYTHONPATH=. python3 scripts/exportar_conjunto.py --prefijo demo.unq. \
      --carpeta conjunto_prueba_ponencia

Guarda personas (con su embedding), temas, vinculos persona-tema, el mapa de
unificacion de temas y los alias. Los ids se conservan tal cual porque los
desempates del analisis dependen de ellos. Solo lee la base.

Tambien guarda el orden de carga de personas y temas tal como lo arma hoy la
base, con y sin unificacion: Louvain depende de ese orden y la base lo da por
el orden fisico de las filas (consulta sin ORDER BY). Con el orden guardado,
el archivo reproduce las cifras aunque la base cambie de orden. Ver PENDIENTES.md.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import subprocess

from sqlalchemy import text

from database import SessionLocal

_spec = importlib.util.spec_from_file_location("gen", "scripts/generar_actividades_emergentes.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def orden_de_carga(db, prefijo: str) -> dict:
    """Orden de personas y de temas del grafo recortado, en cada variante."""
    salida = {}
    for nombre, unificar in (("sin_unificar", False), ("unificado", True)):
        g = gen.recortar(db, prefijo, unificar)
        salida[nombre] = {"personas": [str(p) for p in g.temas_por_persona],
                          "temas": [str(t) for t in g.personas_por_tema]}
    return salida


def _filas(db, sql, **params):
    return [dict(r) for r in db.execute(text(sql), params).mappings().all()]


def _plano(valor):
    if isinstance(valor, (datetime.date, datetime.datetime)):
        return valor.isoformat()
    if valor is None or isinstance(valor, (str, int, float, bool, list, dict)):
        return valor
    return str(valor)


def exportar(db, prefijo: str) -> dict:
    personas = _filas(db, """
        select id, email, name, role, institution, bio, can_offer, wants_to_learn, interests,
               embedding::text as embedding
        from users where email like :p order by id""", p=prefijo + "%")
    for p in personas:
        p["embedding"] = [float(x) for x in p["embedding"].strip("[]").split(",")] if p["embedding"] else None
    ids = [p["id"] for p in personas]
    vinculos = _filas(db, """
        select user_id, topic_id, relation, bloqueado from user_topics
        where user_id = any(:ids) order by user_id, topic_id, relation""", ids=ids)
    fusiones = _filas(db, "select topic_id, canonical_id, similitud, umbral from topic_merges order by topic_id")
    usados = {v["topic_id"] for v in vinculos} | {f["topic_id"] for f in fusiones} | {f["canonical_id"] for f in fusiones}
    temas = _filas(db, "select id, slug, label, macro, subtema from topics where id = any(:ids) order by id",
                   ids=list(usados))
    alias = _filas(db, "select alias_slug, topic_id from topic_aliases where topic_id = any(:ids) order by alias_slug",
                   ids=list(usados))
    plano = lambda filas: [{k: _plano(v) for k, v in f.items()} for f in filas]
    return {"personas": plano(personas), "temas": plano(temas), "vinculos": plano(vinculos),
            "fusiones_de_temas": plano(fusiones), "alias_de_temas": plano(alias),
            "orden_de_carga": orden_de_carga(db, prefijo)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefijo", default="demo.unq.")
    ap.add_argument("--carpeta", default="conjunto_prueba_ponencia")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        datos = exportar(db, a.prefijo)
    finally:
        db.close()
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    ahora = datetime.datetime.now()
    datos = {"meta": {"prefijo": a.prefijo, "exportado": ahora.isoformat(timespec="seconds"), "commit": commit,
                      "personas": len(datos["personas"]), "temas": len(datos["temas"]),
                      "vinculos": len(datos["vinculos"]), "fusiones": len(datos["fusiones_de_temas"])},
             **datos}
    os.makedirs(a.carpeta, exist_ok=True)
    ruta = os.path.join(a.carpeta, f"conjunto_{a.prefijo.strip('.').replace('.', '_')}_{ahora:%Y%m%d}_con_orden.json")
    if os.path.exists(ruta):
        raise SystemExit(f"{ruta} ya existe: no se sobrescribe un conjunto exportado")
    contenido = json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)
    print(ruta, datos["meta"], "sha256", hashlib.sha256(contenido.encode()).hexdigest()[:16])


if __name__ == "__main__":
    main()
