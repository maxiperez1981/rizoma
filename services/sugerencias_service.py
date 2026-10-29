"""Orden de las sugerencias entre personas calculado solo con el grafo.

El modelo de lenguaje no interviene en que personas se sugieren ni en que
orden: la triangulacion mostro que aprueba incluso pares al azar (AUC ~0,56
frente a controles). Aca se ordena con tres criterios elegibles:

  rareza  (por defecto) rareza de los temas del mejor camino, con la funcion
          rareza() de siempre: el tema compartido mas raro, o el promedio de
          los dos temas de un camino indirecto. Desempata el puntaje de
          caminos_desde (que penaliza intermediarios muy conectados).

Las sugerencias se agrupan en dos bloques, temas en comun y caminos puente, y
cada criterio ordena dentro de cada bloque.
  cruces  orden en escalones: mas areas distintas (A), despues mas temas
          puente distintos (T), despues la rareza y por ultimo el id. A y T se
          cuentan solo sobre los caminos mas cortos del par.
  azar    permutacion con una semilla visible: la misma semilla da el mismo orden.

Las personas sin ningun camino en el grafo (afines solo por embeddings) van
aparte, al final y por nombre, en los tres ordenes: el grafo no dice nada sobre ellas.
Todo es puro (recibe el grafo), asi se prueba sin base.
"""
import math
import random
from dataclasses import dataclass, field

from services import rizoma_service

ORDENES = ("rareza", "cruces", "azar")
SEMILLA_AREAS = 7  # la misma de las actividades emergentes


@dataclass
class Estructura:
    persona_id: object
    distancia: int  # 2 = comparten tema, 4 = camino indirecto, 0 = sin camino en el grafo
    compartidos: set = field(default_factory=set)
    caminos: list = field(default_factory=list)  # (t1, intermedio, t2)
    rareza: float = 0.0
    desempate: float = 0.0
    areas: int = 0
    temas_puente: int = 0
    mejor: tuple = None


def recortar(g, ids):
    """El grafo restringido a un conjunto de personas, conservando el orden de carga."""
    ids = set(ids)
    ppt, tpp = {}, {}
    for tema, personas in g.personas_por_tema.items():
        dentro = personas & ids
        if dentro:
            ppt[tema] = set(dentro)
    for persona, temas in g.temas_por_persona.items():
        if persona in ids:
            tpp[persona] = set(temas)
    return rizoma_service.Grafo(ppt, tpp, {i: n for i, n in g.nombres.items() if i in ids}, g.etiquetas,
                                {k: v for k, v in g.relacion_de.items() if k[0] in ids})


def estructuras(g, user_id, candidatos, areas=None) -> dict:
    """Datos estructurales de cada candidato frente a la persona."""
    peso = rizoma_service.rareza(g.personas_por_tema, len(g.nombres) or 1)
    if areas is None:
        areas = rizoma_service.comunidades_personas(g, SEMILLA_AREAS) if g.temas_por_persona else {}
    mios = g.temas_por_persona.get(user_id, set())
    salida = {}
    for v in candidatos:
        suyos = g.temas_por_persona.get(v, set())
        e = Estructura(persona_id=v, distancia=0)
        compartidos = mios & suyos
        if compartidos:
            e.distancia, e.compartidos = 2, compartidos
            mejor = max(compartidos, key=lambda t: (peso[t], str(t)))
            e.rareza = peso[mejor]
            e.desempate = sum(peso[t] for t in compartidos)
            e.mejor = (mejor,)
            e.areas = len({areas.get(user_id), areas.get(v)} - {None})
            e.temas_puente = len(compartidos)
        else:
            for t1 in mios:
                for w in g.personas_por_tema.get(t1, ()):
                    if w in (user_id, v):
                        continue
                    for t2 in g.temas_por_persona.get(w, ()) & suyos:
                        e.caminos.append((t1, w, t2))
            if e.caminos:
                e.distancia = 4
                grado = lambda w: len(g.temas_por_persona.get(w, ()))
                medio = lambda c: (peso[c[0]] + peso[c[2]]) / 2
                puntaje = lambda c: peso[c[0]] * peso[c[2]] / math.log(2 + grado(c[1]))
                e.mejor = max(e.caminos, key=lambda c: (medio(c), puntaje(c), str(c[1]), str(c[0]), str(c[2])))
                e.rareza = medio(e.mejor)
                e.desempate = max(puntaje(c) for c in e.caminos)
                e.areas = len(({areas.get(user_id), areas.get(v)} | {areas.get(c[1]) for c in e.caminos}) - {None})
                e.temas_puente = len({c[0] for c in e.caminos} | {c[2] for c in e.caminos})
        salida[v] = e
    return salida


BLOQUES = {2: "comun", 4: "puente", 0: "otros"}


def bloque(e: Estructura) -> str:
    """Temas en comun, caminos puente u otros perfiles (sin camino en el grafo)."""
    return BLOQUES[e.distancia]


def ordenar(est: dict, nombres: dict, orden: str = "rareza", semilla: int = None) -> list:
    """Ids de los candidatos: primero los de tema en comun, despues los de camino
    puente, cada bloque ordenado con el criterio pedido; al final los que no
    tienen camino, por nombre. Los bloques se ordenan por separado porque un
    tema compartido cuenta solo y un camino promedia dos: juntos, los directos
    quedarian siempre arriba."""
    if orden not in ORDENES:
        raise ValueError(f"orden desconocido: {orden}")
    rnd = random.Random(semilla)
    salida = []
    for distancia in (2, 4):
        grupo = [v for v, e in est.items() if e.distancia == distancia]
        if orden == "rareza":
            grupo.sort(key=lambda v: (-est[v].rareza, -est[v].desempate, str(v)))
        elif orden == "cruces":
            grupo.sort(key=lambda v: (-est[v].areas, -est[v].temas_puente, -est[v].rareza, str(v)))
        else:
            grupo.sort(key=str)
            rnd.shuffle(grupo)
        salida += grupo
    return salida + sorted((v for v, e in est.items() if not e.distancia), key=lambda v: (nombres.get(v, ""), str(v)))


def dato_estructural(g, e: Estructura, orden: str, semilla: int = None) -> str:
    """Una linea con el dato que ubica a la sugerencia en su lugar."""
    n = len(g.nombres)
    cuantos = lambda t: f"{len(g.personas_por_tema.get(t, ()))} de {n} perfiles"
    tema = lambda t: g.etiquetas.get(t, "?")
    if not e.distancia:
        return "Sin camino en el grafo: aparece solo por afinidad de perfiles"
    if orden == "azar":
        return f"Posición al azar · semilla {semilla}"
    if orden == "cruces":
        areas = f"{e.areas} {'área' if e.areas == 1 else 'áreas'}"
        if e.distancia == 2:
            return (f"Conecta {areas} a través de "
                    f"{e.temas_puente} {'tema en común' if e.temas_puente == 1 else 'temas en común'}")
        return f"Conecta {areas} a través de {e.temas_puente} temas puente"
    if e.distancia == 2:
        (t,) = e.mejor
        if len(e.compartidos) == 1:
            return f"Tema en común: {tema(t)} ({cuantos(t)})"
        return f"{len(e.compartidos)} temas en común; el más raro: {tema(t)} ({cuantos(t)})"
    t1, w, t2 = e.mejor
    return (f"2 temas puente: {tema(t1)} ({cuantos(t1)}) y {tema(t2)} ({cuantos(t2)}) "
            f"· vía {g.nombres.get(w, 'otra persona')}")


def camino_para_mostrar(g, user_id, e: Estructura) -> list:
    """El mejor camino indirecto con la forma que ya dibuja la interfaz."""
    if e.distancia != 4:
        return []
    t1, w, t2 = e.mejor
    return [
        {"tipo": "persona", "label": g.nombres.get(user_id, "?")},
        {"tipo": "tema", "label": g.etiquetas.get(t1, "?"), "relacion": sorted(g.relacion_de.get((user_id, t1), []))},
        {"tipo": "persona", "label": g.nombres.get(w, "?")},
        {"tipo": "tema", "label": g.etiquetas.get(t2, "?"), "relacion": sorted(g.relacion_de.get((e.persona_id, t2), []))},
        {"tipo": "persona", "label": g.nombres.get(e.persona_id, "?")},
    ]
