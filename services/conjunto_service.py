"""Conjuntos de perfiles: a cual pertenece cada persona y lectura de conjuntos exportados.

Un conjunto se reconoce por el prefijo del email. Las sugerencias de una
persona se calculan solo dentro de su conjunto, asi la red ficticia de la
ponencia, la de demostracion y los perfiles generales no se mezclan.
"""
import collections
import json
import uuid

CONJUNTOS = {
    "prueba": {"prefijo": "demo.unq.", "etiqueta": "Conjunto de prueba (ponencia)"},
    "demostracion": {"prefijo": "demo.vivo.", "etiqueta": "Conjunto de demostración"},
}
GENERAL = "general"


def conjunto_de_email(email: str) -> str:
    email = (email or "").lower()
    for nombre, c in CONJUNTOS.items():
        if email.startswith(c["prefijo"]):
            return nombre
    return GENERAL


def etiqueta(nombre: str) -> str:
    return CONJUNTOS.get(nombre, {}).get("etiqueta", "Red general")


def ids_del_conjunto(db, nombre: str) -> set:
    """Ids de las personas de un conjunto (prueba, demostracion o general)."""
    from sqlalchemy import text

    filas = db.execute(text("select id, email from users")).fetchall()
    return {i for i, email in filas if conjunto_de_email(email) == nombre}


def grafo_del_conjunto(db, user):
    """Grafo bipartito restringido al conjunto de la persona, con el orden de carga de siempre.

    Los nombres vienen como los puede ver `user` (services/visibilidad.py): así
    caminos, puentes, red y equipos no muestran más de lo que cada persona eligió.
    Los análisis de la ponencia usan rizoma_service.cargar_grafo, no esta función.
    """
    from services import rizoma_service, sugerencias_service, visibilidad

    ids = ids_del_conjunto(db, conjunto_de_email(user.email))
    g = sugerencias_service.recortar(rizoma_service.cargar_grafo(db), ids)
    return g._replace(nombres=visibilidad.nombres_para(db, user, g.nombres)), ids


def leer(ruta: str) -> dict:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def grafo_desde_archivo(datos: dict, unificar: bool = False):
    """Arma el mismo Grafo que generar_actividades_emergentes.recortar(), desde un archivo.

    Si el archivo trae `orden_de_carga`, personas y temas se cargan en ese orden:
    la deteccion de areas (Louvain) depende de el, no solo de la semilla.
    """
    from services.rizoma_service import Grafo

    u = uuid.UUID
    fusion = {u(f["topic_id"]): u(f["canonical_id"]) for f in datos["fusiones_de_temas"]} if unificar else {}
    ppt, tpp, relacion_de = collections.defaultdict(set), collections.defaultdict(set), {}
    for v in datos["vinculos"]:
        persona, tema = u(v["user_id"]), u(v["topic_id"])
        tema = fusion.get(tema, tema)
        ppt[tema].add(persona)
        tpp[persona].add(tema)
        relacion_de.setdefault((persona, tema), set()).add(v["relation"])
    orden = (datos.get("orden_de_carga") or {}).get("unificado" if unificar else "sin_unificar")
    if orden:
        ppt = {u(t): ppt[u(t)] for t in orden["temas"]}
        tpp = {u(p): tpp[u(p)] for p in orden["personas"]}
    nombres = {u(p["id"]): p["name"] for p in datos["personas"]}
    etiquetas = {u(t["id"]): t["label"] for t in datos["temas"]}
    return Grafo(dict(ppt), dict(tpp), nombres, etiquetas, relacion_de)


def reordenar(g, semilla: int):
    """Mismo grafo con personas y temas cargados en otro orden (permutacion con semilla)."""
    import random

    from services.rizoma_service import Grafo

    rnd = random.Random(semilla)
    temas, personas = list(g.personas_por_tema), list(g.temas_por_persona)
    rnd.shuffle(temas)
    rnd.shuffle(personas)
    return Grafo({t: g.personas_por_tema[t] for t in temas}, {p: g.temas_por_persona[p] for p in personas},
                 g.nombres, g.etiquetas, g.relacion_de)


def embeddings_desde_archivo(datos: dict) -> dict:
    return {uuid.UUID(p["id"]): p["embedding"] for p in datos["personas"] if p.get("embedding")}
