"""Paso 2 del rizoma: relaciona los grafos personales entre si.

Modelo: grafo bipartito persona-tema. Cada persona se cuelga de temas
canonicos compartidos, asi que los grafos individuales pasan a ser uno solo.

Sobre ese grafo:
  - distancia 2 (persona-tema-persona) = comparten un tema, vinculo directo
  - distancia 4 (persona-tema-persona-tema-persona) = relacion de relaciones

Lo interesante para recomendar es la distancia 4 entre personas que NO
comparten ningun tema: no se pueden encontrar solas. Se puntua por rareza,
no por cercania. Un camino que pasa por un tema que tienen cinco personas no
dice nada; uno que pasa por un tema de dos, si.
"""
import itertools
import math
import unicodedata
from collections import Counter, defaultdict, namedtuple

from sqlalchemy.orm import Session

import models

RELACIONES = (("can_offer", "offers"), ("wants_to_learn", "wants"), ("interests", "interest"))


def slugify(texto: str) -> str:
    """Normaliza un texto libre a slug canonico."""
    s = unicodedata.normalize("NFD", str(texto).lower().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def sincronizar(db: Session) -> dict:
    """Reconstruye temas y aristas persona-tema desde los perfiles.

    Idempotente: se puede correr cuantas veces se quiera.
    """
    alias = {a.alias_slug: a.topic_id for a in db.query(models.TopicAlias).all()}
    temas = {t.slug: t for t in db.query(models.Topic).all()}

    # Las aristas corregidas a mano sobreviven a la reconstruccion.
    db.query(models.UserTopic).filter(models.UserTopic.bloqueado.is_(False)).delete()
    protegidas = {
        (ut.user_id, ut.topic_id, ut.relation)
        for ut in db.query(models.UserTopic).filter(models.UserTopic.bloqueado.is_(True)).all()
    }

    aristas = set()
    for user in db.query(models.User).all():
        for campo, relacion in RELACIONES:
            for item in (getattr(user, campo) or []):
                slug = slugify(item)
                if not slug:
                    continue
                if slug in alias:
                    topic_id = alias[slug]
                else:
                    tema = temas.get(slug)
                    if tema is None:
                        tema = models.Topic(slug=slug, label=str(item).strip())
                        db.add(tema)
                        db.flush()
                        temas[slug] = tema
                    topic_id = tema.id
                aristas.add((user.id, topic_id, relacion))

    for user_id, topic_id, relacion in aristas:
        if (user_id, topic_id, relacion) in protegidas:
            continue
        db.add(models.UserTopic(user_id=user_id, topic_id=topic_id, relation=relacion))
    db.commit()
    return {"temas": len(temas), "aristas": len(aristas)}


def sincronizar_usuario(db: Session, user: models.User) -> int:
    """Reconstruye solo las aristas de una persona. Barato, para usar al guardar."""
    alias = {a.alias_slug: a.topic_id for a in db.query(models.TopicAlias).all()}
    temas = {t.slug: t for t in db.query(models.Topic).all()}

    db.query(models.UserTopic).filter(
        models.UserTopic.user_id == user.id,
        models.UserTopic.bloqueado.is_(False),
    ).delete()
    protegidas = {
        (ut.topic_id, ut.relation)
        for ut in db.query(models.UserTopic).filter(
            models.UserTopic.user_id == user.id,
            models.UserTopic.bloqueado.is_(True),
        ).all()
    }

    aristas = set()
    for campo, relacion in RELACIONES:
        for item in (getattr(user, campo) or []):
            slug = slugify(item)
            if not slug:
                continue
            if slug in alias:
                topic_id = alias[slug]
            else:
                tema = temas.get(slug)
                if tema is None:
                    tema = models.Topic(slug=slug, label=str(item).strip())
                    db.add(tema)
                    db.flush()
                    temas[slug] = tema
                topic_id = tema.id
            aristas.add((topic_id, relacion))

    for topic_id, relacion in aristas:
        if (topic_id, relacion) in protegidas:
            continue
        db.add(models.UserTopic(user_id=user.id, topic_id=topic_id, relation=relacion))
    return len(aristas)


Grafo = namedtuple(
    "Grafo",
    "personas_por_tema temas_por_persona nombres etiquetas relacion_de",
)


def cargar_grafo(db: Session, unificar: bool = False):
    """Carga publica del grafo, para reutilizarlo entre llamadas de un request.

    Con `unificar=True` se aplica el mapa de fusiones semanticas de temas
    (topic_merges) sin modificar la base: cada tema fusionado se lee como su canonico.
    """
    return _cargar_grafo(db, unificar)


def _cargar_grafo(db: Session, unificar: bool = False):
    """Carga el grafo bipartito completo desde la base."""
    personas_por_tema = defaultdict(set)
    temas_por_persona = defaultdict(set)
    relacion_de = {}
    fusion = {m.topic_id: m.canonical_id for m in db.query(models.TopicMerge).all()} if unificar else {}

    # Orden fijo: sin ORDER BY la base devuelve las filas en su orden fisico,
    # que cambia al insertar o borrar perfiles ajenos (ver PENDIENTES.md).
    filas = db.query(models.UserTopic).order_by(
        models.UserTopic.user_id, models.UserTopic.topic_id, models.UserTopic.relation)
    for ut in filas.all():
        tema = fusion.get(ut.topic_id, ut.topic_id)
        personas_por_tema[tema].add(ut.user_id)
        temas_por_persona[ut.user_id].add(tema)
        relacion_de.setdefault((ut.user_id, tema), set()).add(ut.relation)

    nombres = {u.id: u.name for u in db.query(models.User).all()}
    etiquetas = {t.id: t.label for t in db.query(models.Topic).all()}
    return Grafo(personas_por_tema, temas_por_persona, nombres, etiquetas, relacion_de)


def rareza(personas_por_tema: dict, total_personas: int) -> dict:
    """Peso IDF por tema: cuanta menos gente lo toca, mas informativo es."""
    return {
        topic_id: math.log(total_personas / max(len(personas), 1))
        for topic_id, personas in personas_por_tema.items()
    }


def caminos_desde(g, user_id, limite: int = 10) -> list:
    """Parte pura: personas a distancia 4 que no comparten ningun tema.

    Recibe el grafo ya cargado, asi puede probarse sin base de datos.
    """
    peso = rareza(g.personas_por_tema, len(g.nombres) or 1)
    mis_temas = g.temas_por_persona.get(user_id, set())
    directos = {p for t in mis_temas for p in g.personas_por_tema[t]} | {user_id}
    mi_nombre = g.nombres.get(user_id, "?")

    mejores = {}
    for t1 in mis_temas:
        for intermedio in g.personas_por_tema[t1]:
            if intermedio == user_id:
                continue
            grado_intermedio = len(g.temas_por_persona.get(intermedio, ()))
            for t2 in g.temas_por_persona.get(intermedio, ()):
                if t2 in mis_temas:
                    continue
                for destino in g.personas_por_tema[t2]:
                    if destino in directos:
                        continue
                    # rareza de los dos temas del camino, penalizando
                    # intermediarios que se conectan con todo el mundo
                    score = peso[t1] * peso[t2] / math.log(2 + grado_intermedio)
                    actual = mejores.get(destino)
                    if actual is None or score > actual[0]:
                        mejores[destino] = (score, t1, intermedio, t2)

    salida = []
    for destino, (score, t1, intermedio, t2) in sorted(
        mejores.items(), key=lambda x: (-x[1][0], str(x[0]))
    )[:limite]:
        salida.append({
            "persona_id": destino,
            "persona": g.nombres.get(destino, "?"),
            "tema_origen_id": t1,
            "tema_puente_id": t2,
            "intermedio_id": intermedio,
            "score": round(score, 3),
            "camino": [
                {"tipo": "persona", "label": mi_nombre},
                {"tipo": "tema", "label": g.etiquetas.get(t1, "?"),
                 "relacion": sorted(g.relacion_de.get((user_id, t1), []))},
                {"tipo": "persona", "label": g.nombres.get(intermedio, "?")},
                {"tipo": "tema", "label": g.etiquetas.get(t2, "?"),
                 "relacion": sorted(g.relacion_de.get((destino, t2), []))},
                {"tipo": "persona", "label": g.nombres.get(destino, "?")},
            ],
        })
    return salida


def caminos_sugeridos(db: Session, user: models.User, limite: int = 10, grafo=None) -> list:
    """Personas a distancia 4 que no comparten ningun tema con el usuario.

    Son las que la seleccion directa nunca alcanza: no hay overlap lexico ni
    tema en comun. El camino explica por que tendrian que conocerse.

    Se puede pasar un grafo ya cargado para no releerlo de la base.
    """
    return caminos_desde(grafo or _cargar_grafo(db), user.id, limite)


def contexto_rizoma(db: Session, user: models.User, limite: int = 6, grafo=None) -> str:
    return contexto_rizoma_con_mapa(db, user, limite, grafo)[0]


def contexto_rizoma_con_mapa(db: Session, user: models.User, limite: int = 6, grafo=None) -> tuple:
    """Serializa el vecindario como texto compacto para pasarle al modelo.

    Las personas van seudonimizadas (Persona C, D, ...) igual que en el resto
    del prompt: el modelo necesita la estructura del camino para razonar, no
    las identidades. Los temas si van textuales, que es lo que le da sentido.
    """
    caminos = caminos_sugeridos(db, user, limite, grafo)
    if not caminos:
        return "", {}

    seudonimo = {user.name: "Persona A"}
    letras = iter("CDEFGHIJKLMNOPQRSTUVWXYZ")

    def etiqueta(nombre: str) -> str:
        if nombre not in seudonimo:
            seudonimo[nombre] = f"Persona {next(letras, 'X')}"
        return seudonimo[nombre]

    lineas = []
    for c in caminos:
        p = c["camino"]
        lineas.append(
            f"- {etiqueta(p[0]['label'])} --[{p[1]['label']}]--> {etiqueta(p[2]['label'])} "
            f"--[{p[3]['label']}]--> {etiqueta(p[4]['label'])}"
        )
    texto = (
        "CAMINOS INDIRECTOS EN LA RED (la persona del medio conecta dos mundos "
        "que no se tocan):\n" + "\n".join(lineas)
    )
    # invertido: la etiqueta que ve el modelo -> el nombre real, para poder
    # devolver los nombres cuando el modelo los escriba en la explicacion
    return texto, {etiqueta: nombre for nombre, etiqueta in seudonimo.items()}


def grafo_vecindario(db: Session, user: models.User, max_personas: int = 14, grafo=None) -> dict:
    """Vecindario del usuario como nodos y aristas, listo para dibujar.

    Anillo 1: personas que comparten algun tema. Anillo 2: personas
    alcanzables solo por camino indirecto, con el tema puente que las trae.
    Se puede pasar el grafo ya recortado al conjunto de la persona.
    """
    g = grafo or _cargar_grafo(db)
    personas_por_tema, temas_por_persona = g.personas_por_tema, g.temas_por_persona
    nombres, etiquetas, relacion_de = g.nombres, g.etiquetas, g.relacion_de
    peso = rareza(personas_por_tema, len(nombres) or 1)
    # el macro del vocabulario controlado agrupa el grafo espacialmente
    macros = {t.id: (t.macro or "Sin clasificar") for t in db.query(models.Topic).all()}

    def macro_dominante(persona_id):
        cuenta = Counter(macros.get(t, "Sin clasificar")
                         for t in temas_por_persona.get(persona_id, ()))
        return cuenta.most_common(1)[0][0] if cuenta else "Sin clasificar"
    mis_temas = temas_por_persona.get(user.id, set())

    nodes, edges, vistos = [], [], set()

    def nodo(nid, label, kind, **extra):
        if nid not in vistos:
            vistos.add(nid)
            nodes.append({"id": nid, "label": label, "kind": kind, **extra})

    def arista(a, b, relacion, anillo):
        edges.append({"source": a, "target": b, "relacion": relacion, "anillo": anillo})

    yo = f"p:{user.id}"
    nodo(yo, user.name, "yo", macro=macro_dominante(user.id))

    for t in mis_temas:
        nodo(f"t:{t}", etiquetas.get(t, "?"), "tema",
             rareza=round(peso.get(t, 0), 2),
             personas=len(personas_por_tema.get(t, ())),
             macro=macros.get(t, "Sin clasificar"))
        for rel in sorted(relacion_de.get((user.id, t), ["interest"])):
            arista(yo, f"t:{t}", rel, 0)

    vecinos = {}
    for t in mis_temas:
        for p in personas_por_tema.get(t, ()):
            if p != user.id:
                vecinos.setdefault(p, set()).add(t)

    ordenados = sorted(vecinos.items(), key=lambda kv: -sum(peso.get(t, 0) for t in kv[1]))
    for p, compartidos in ordenados[:max_personas]:
        nodo(f"p:{p}", nombres.get(p, "?"), "persona", macro=macro_dominante(p))
        for t in compartidos:
            for rel in sorted(relacion_de.get((p, t), ["interest"])):
                arista(f"p:{p}", f"t:{t}", rel, 1)

    for c in caminos_desde(g, user.id, 5):
        t2, destino, intermedio = c["tema_puente_id"], c["persona_id"], c["intermedio_id"]
        nodo(f"p:{intermedio}", nombres.get(intermedio, "?"), "persona",
             macro=macro_dominante(intermedio))
        nodo(f"t:{t2}", etiquetas.get(t2, "?"), "tema",
             rareza=round(peso.get(t2, 0), 2),
             personas=len(personas_por_tema.get(t2, ())),
             macro=macros.get(t2, "Sin clasificar"))
        nodo(f"p:{destino}", nombres.get(destino, "?"), "indirecto",
             macro=macro_dominante(destino))
        for rel in sorted(relacion_de.get((intermedio, t2), ["interest"])):
            arista(f"p:{intermedio}", f"t:{t2}", rel, 2)
        for rel in sorted(relacion_de.get((destino, t2), ["interest"])):
            arista(f"p:{destino}", f"t:{t2}", rel, 2)

    return {"nodes": nodes, "edges": edges}


def red_completa(db: Session, user: models.User = None, grafo=None) -> dict:
    """Toda la red: cada persona con todos sus temas, no solo los compartidos.

    Es la vista de conjunto, complementaria del vecindario: sirve para leer la
    forma general de la red, no para decidir con quien hablar. Se puede pasar
    el grafo ya recortado al conjunto de la persona.
    """
    g = grafo or _cargar_grafo(db)
    peso = rareza(g.personas_por_tema, len(g.nombres) or 1)
    macros = {t.id: (t.macro or "Sin clasificar") for t in db.query(models.Topic).all()}

    def macro_dominante(persona_id):
        cuenta = Counter(macros.get(t, "Sin clasificar")
                         for t in g.temas_por_persona.get(persona_id, ()))
        return cuenta.most_common(1)[0][0] if cuenta else "Sin clasificar"

    yo = user.id if user is not None else None
    nodes, edges = [], []
    for persona_id, temas in g.temas_por_persona.items():
        if not temas:
            continue
        nodes.append({
            "id": f"p:{persona_id}",
            "label": g.nombres.get(persona_id, "?"),
            "kind": "yo" if persona_id == yo else "persona",
            "macro": macro_dominante(persona_id),
            "temas": len(temas),
        })
    for topic_id, personas in g.personas_por_tema.items():
        if not personas:
            continue
        nodes.append({
            "id": f"t:{topic_id}",
            "label": g.etiquetas.get(topic_id, "?"),
            "kind": "tema",
            "macro": macros.get(topic_id, "Sin clasificar"),
            "rareza": round(peso.get(topic_id, 0), 2),
            "personas": len(personas),
        })
    for (persona_id, topic_id), relaciones in g.relacion_de.items():
        for rel in sorted(relaciones):
            edges.append({"source": f"p:{persona_id}", "target": f"t:{topic_id}", "relacion": rel})

    return {"nodes": nodes, "edges": edges,
            "resumen": {"personas": len(g.temas_por_persona), "temas": len(g.personas_por_tema),
                        "aristas": len(edges)}}


def crear_notificacion_match(db: Session, user: "models.User", other: "models.User",
                              candidate_id, explicacion: str) -> None:
    """Avisa in-app a ambos lados de un match nuevo con evidencia en el grafo.

    Se dispara la primera vez que el par aparece entre las primeras sugerencias
    con un tema en comun o un camino indirecto, no por el veredicto del modelo
    (que aprueba casi cualquier par). Sin esto el matching es puramente pull.
    No dispara email ni push todavia.
    """
    from services.visibilidad import nombre_visible

    explicacion = (explicacion or "").strip()
    db.add(models.Notification(
        user_id=user.id,
        other_user_id=other.id,
        candidate_id=candidate_id,
        title=f"Nuevo match con {nombre_visible(other, user)}",
        body=explicacion,
    ))
    db.add(models.Notification(
        user_id=other.id,
        other_user_id=user.id,
        candidate_id=candidate_id,
        title=f"Nuevo match con {nombre_visible(user, other)}",
        body=explicacion,
    ))


def comunidades_personas(g, seed: int = 7) -> dict:
    """Areas emergentes del propio grafo: comunidades de personas.

    Las personas se unen por los temas que comparten, ponderados por rareza, y
    se agrupan con Louvain. No depende de ninguna clasificacion de temas, que
    en la practica esta incompleta. Devuelve {persona_id: indice_de_comunidad}
    con las comunidades ordenadas de mayor a menor.
    """
    import networkx as nx

    peso = rareza(g.personas_por_tema, len(g.nombres) or 1)
    grafo = nx.Graph()
    # Personas y temas se cargan ordenados por id: Louvain depende del orden de
    # carga ademas de la semilla, y asi el resultado no depende de como llego el grafo.
    grafo.add_nodes_from(sorted(g.temas_por_persona, key=str))
    for tema in sorted(g.personas_por_tema, key=str):
        personas = g.personas_por_tema[tema]
        if len(personas) < 2:
            continue
        for a, b in itertools.combinations(sorted(personas, key=str), 2):
            if grafo.has_edge(a, b):
                grafo[a][b]["weight"] += peso[tema]
            else:
                grafo.add_edge(a, b, weight=peso[tema])
    comunidades = nx.community.louvain_communities(grafo, weight="weight", seed=seed)
    ordenadas = sorted(comunidades, key=lambda c: (-len(c), min(str(p) for p in c)))
    return {p: i for i, c in enumerate(ordenadas) for p in c}


def _etiqueta_area(g, comunidad: dict, indice: int, peso: dict, n: int = 3) -> str:
    """Nombre descriptivo de un area: sus temas compartidos mas frecuentes."""
    conteo = Counter()
    for persona, c in comunidad.items():
        if c != indice:
            continue
        for tema in g.temas_por_persona.get(persona, ()):
            if len(g.personas_por_tema[tema]) >= 2:
                conteo[tema] += 1
    top = sorted(conteo, key=lambda t: (-conteo[t], -peso[t], str(t)))[:n]
    return " / ".join(g.etiquetas.get(t, "?") for t in top) or f"area {indice + 1}"


def actividades_emergentes(g, limite: int = 8, soporte_min: int = 2,
                           dominancia_min: float = 0.6, seed: int = 7) -> list:
    """Combinaciones de temas de areas distintas que nadie reune todavia.

    Un par de temas (a, b) es candidato cuando:
      - cada tema lo tocan al menos `soporte_min` personas (no es ruido);
      - cada uno pertenece sobre todo a un area distinta del grafo;
      - ninguna persona aporta los dos como capacidad o interes (querer
        aprender uno no cuenta: la combinacion no esta consolidada);
      - hay oferta de uno y demanda del otro (alguien quiere aprender un tema
        y alguien ofrece el otro).
    Se ordenan por rareza media de los temas, por la cantidad de personas
    involucradas y por la oferta/demanda cruzada. La seleccion final evita
    repetir temas y limita los cruces entre el mismo par de areas.

    Es una funcion pura sobre el grafo: sin base de datos ni modelo de lenguaje.
    """
    comunidad = comunidades_personas(g, seed)
    peso = rareza(g.personas_por_tema, len(g.nombres) or 1)

    def dominante(tema):
        conteo = Counter(comunidad[p] for p in g.personas_por_tema[tema] if p in comunidad)
        indice, n = sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        return indice, n / sum(conteo.values())

    def con_relacion(tema, relacion):
        return {p for p in g.personas_por_tema[tema]
                if relacion in g.relacion_de.get((p, tema), ())}

    def aportan(tema):
        """Quienes ya traen el tema como capacidad o interes (no solo como deseo)."""
        return {p for p in g.personas_por_tema[tema]
                if g.relacion_de.get((p, tema), set()) - {"wants"}}

    temas = sorted((t for t, ps in g.personas_por_tema.items() if len(ps) >= soporte_min), key=str)
    area = {t: dominante(t) for t in temas}

    candidatos = []
    for a, b in itertools.combinations(temas, 2):
        (ca, fa), (cb, fb) = area[a], area[b]
        if ca == cb or fa < dominancia_min or fb < dominancia_min:
            continue
        pa, pb = g.personas_por_tema[a], g.personas_por_tema[b]
        if aportan(a) & aportan(b):
            continue
        quieren_a, quieren_b = con_relacion(a, "wants"), con_relacion(b, "wants")
        ofrecen_a, ofrecen_b = con_relacion(a, "offers"), con_relacion(b, "offers")
        if not ((quieren_a and ofrecen_b) or (quieren_b and ofrecen_a)):
            continue
        demanda = len(quieren_a) + len(quieren_b)
        oferta = len(ofrecen_a) + len(ofrecen_b)
        n_personas = len(pa | pb)
        score = ((peso[a] + peso[b]) / 2) * math.sqrt(n_personas) * (1 + math.log(1 + min(demanda, oferta)))
        candidatos.append((score, a, b, ca, cb, demanda, oferta, n_personas))

    candidatos.sort(key=lambda c: (-c[0], str(c[1]), str(c[2])))
    usados, cruces, salida = set(), Counter(), []
    for score, a, b, ca, cb, demanda, oferta, n_personas in candidatos:
        par = tuple(sorted((ca, cb)))
        if a in usados or b in usados or cruces[par] >= 2:
            continue
        usados.update((a, b))
        cruces[par] += 1
        salida.append({
            "temas": [{"id": a, "label": g.etiquetas.get(a, "?")},
                      {"id": b, "label": g.etiquetas.get(b, "?")}],
            "areas": [_etiqueta_area(g, comunidad, ca, peso), _etiqueta_area(g, comunidad, cb, peso)],
            "n_personas": n_personas,
            "demanda": demanda,
            "oferta": oferta,
            "score": round(score, 3),
        })
        if len(salida) >= limite:
            break
    return salida


def actividades_emergentes_consenso(g, limite: int = 8, semillas=range(1, 13),
                                    estabilidad_min: float = 0.5, **kwargs) -> list:
    """Actividades emergentes que sobreviven a distintas particiones en areas.

    Louvain depende de la semilla, asi que una sola corrida puede proponer
    cruces que son artefacto de esa particion. Se repite la deteccion con varias
    semillas y se conservan los pares de temas que aparecen en al menos
    `estabilidad_min` de las corridas, ordenados por estabilidad y puntaje.
    Cada resultado lleva su `estabilidad`: fraccion de corridas en que aparecio
    entre las `limite` principales (la misma ventana que ve el usuario).
    """
    semillas = list(semillas)
    apariciones, mejores = Counter(), {}
    for semilla in semillas:
        for r in actividades_emergentes(g, limite=limite, seed=semilla, **kwargs):
            clave = frozenset(t["id"] for t in r["temas"])
            apariciones[clave] += 1
            if clave not in mejores or r["score"] > mejores[clave]["score"]:
                mejores[clave] = r

    ordenadas = sorted(
        ((apariciones[k] / len(semillas), mejores[k]["score"], k) for k in mejores
         if apariciones[k] / len(semillas) >= estabilidad_min),
        key=lambda x: (-x[0], -x[1], sorted(str(i) for i in x[2])))

    usados, salida = set(), []
    for estabilidad, _, clave in ordenadas:
        if clave & usados:
            continue
        usados |= clave
        salida.append(dict(mejores[clave], estabilidad=round(estabilidad, 2)))
        if len(salida) >= limite:
            break
    return salida


# ---------------------------------------------------------------- demanda latente

def demanda_latente(g, limite: int = 8, demanda_min: int = 2, seed: int = 7) -> list:
    """Temas que mucha gente quiere aprender y pocas personas ofrecen.

    Es la senal de "demanda formativa latente": donde hay mas deseo de aprender
    que capacidad disponible, una clinica o un curso corto tendria publico.
    Funcion pura sobre el grafo.
    """
    comunidad = comunidades_personas(g, seed)
    peso = rareza(g.personas_por_tema, len(g.nombres) or 1)

    def con_relacion(tema, relacion):
        return {p for p in g.personas_por_tema[tema]
                if relacion in g.relacion_de.get((p, tema), ())}

    salida = []
    for tema, personas in g.personas_por_tema.items():
        quieren, ofrecen = con_relacion(tema, "wants"), con_relacion(tema, "offers")
        if len(quieren) < demanda_min or len(quieren) <= len(ofrecen):
            continue
        areas = Counter(comunidad[p] for p in quieren if p in comunidad)
        salida.append({
            "tema": {"id": tema, "label": g.etiquetas.get(tema, "?")},
            "demanda": len(quieren),
            "oferta": len(ofrecen),
            "areas_demandantes": [_etiqueta_area(g, comunidad, i, peso) for i, _ in areas.most_common(3)],
            "n_areas": len(areas),
            "score": round((len(quieren) / (1 + len(ofrecen))) * math.sqrt(len(quieren)), 3),
        })
    salida.sort(key=lambda r: (-r["score"], str(r["tema"]["id"])))
    return salida[:limite]


# -------------------------------------------------------------------- equipos

def equipo_para_actividad(g, tema_a, tema_b, tamano: int = 4, seed: int = 7) -> dict:
    """Arma un equipo que cubra una actividad emergente (dos temas).

    Roles: quien aporta cada tema, quien quiere aprender alguno (idealmente de
    otra area) y una persona puente que toque las dos areas. Es greedy y
    determinista; devuelve tambien que queda sin cubrir.
    """
    comunidad = comunidades_personas(g, seed)
    peso = rareza(g.personas_por_tema, len(g.nombres) or 1)

    def rel(p, t):
        return g.relacion_de.get((p, t), set())

    def amplitud(p):
        return (len(g.temas_por_persona.get(p, ())), str(p))

    def mejor(candidatos, usados):
        pool = [p for p in candidatos if p not in usados]
        return sorted(pool, key=lambda p: (-amplitud(p)[0], amplitud(p)[1]))[0] if pool else None

    miembros, usados = [], set()

    def agregar(persona, rol, temas):
        usados.add(persona)
        miembros.append({
            "persona_id": persona,
            "persona": g.nombres.get(persona, "?"),
            "rol": rol,
            "temas": [g.etiquetas.get(t, "?") for t in temas],
            "area": comunidad.get(persona),
        })

    for tema in (tema_a, tema_b):
        ofrecen = [p for p in g.personas_por_tema.get(tema, ()) if "offers" in rel(p, tema)]
        interesados = [p for p in g.personas_por_tema.get(tema, ()) if rel(p, tema) - {"wants"}]
        elegido = mejor(ofrecen, usados) or mejor(interesados, usados)
        if elegido:
            agregar(elegido, f"aporta {g.etiquetas.get(tema, '?')}", [tema])

    areas_equipo = {m["area"] for m in miembros}
    quieren = [p for t in (tema_a, tema_b) for p in g.personas_por_tema.get(t, ())
               if "wants" in rel(p, t)]
    nuevos_areas = [p for p in quieren if comunidad.get(p) not in areas_equipo]
    aprendiz = mejor(nuevos_areas, usados) or mejor(quieren, usados)
    if aprendiz:
        temas = [t for t in (tema_a, tema_b) if "wants" in rel(aprendiz, t)]
        agregar(aprendiz, "quiere aprender " + " y ".join(g.etiquetas.get(t, "?") for t in temas), temas)

    if tamano >= 4 and miembros:
        areas_objetivo = {m["area"] for m in miembros}

        def alcance(p):
            return len({comunidad.get(q) for t in g.temas_por_persona.get(p, ())
                        for q in g.personas_por_tema[t] if q != p} & areas_objetivo)
        pool = [p for p in g.temas_por_persona if p not in usados]
        if pool:
            puente = sorted(pool, key=lambda p: (-alcance(p), -len(g.temas_por_persona[p]), str(p)))[0]
            agregar(puente, "puente entre areas", list(g.temas_por_persona[puente])[:2])

    cubiertos = {t for m in miembros for t in (tema_a, tema_b)
                 if m["rol"].startswith("aporta ") and m["rol"].endswith(g.etiquetas.get(t, "?"))}
    return {
        "miembros": miembros,
        "temas_cubiertos": [g.etiquetas.get(t, "?") for t in (tema_a, tema_b) if t in cubiertos],
        "temas_sin_cubrir": [g.etiquetas.get(t, "?") for t in (tema_a, tema_b) if t not in cubiertos],
        "areas_distintas": len({m["area"] for m in miembros}),
    }


# ----------------------------------------------------------------- simulacion

def simular_persona(g, persona: dict, semillas=range(1, 9), limite: int = 8) -> dict:
    """Que pasaria si se sumara esta persona a la red (sin tocar la base).

    `persona`: {"nombre", "can_offer", "wants_to_learn", "interests"}. Los
    terminos se vinculan a temas existentes por slug; los que no existen se
    crean como temas nuevos solo en la simulacion.
    """
    por_slug = {slugify(label): t for t, label in g.etiquetas.items()}
    virtual = "__virtual__"
    ppt = {t: set(ps) for t, ps in g.personas_por_tema.items()}
    tpp = {p: set(ts) for p, ts in g.temas_por_persona.items()}
    rel = {k: set(v) for k, v in g.relacion_de.items()}
    etiquetas = dict(g.etiquetas)
    nuevos, vinculados = [], []

    for relacion, clave in (("offers", "can_offer"), ("wants", "wants_to_learn"), ("interest", "interests")):
        for termino in persona.get(clave) or []:
            slug = slugify(str(termino))
            if not slug:
                continue
            tema = por_slug.get(slug)
            if tema is None:
                tema = f"nuevo:{slug}"
                por_slug[slug] = tema
                etiquetas[tema] = str(termino).strip()
                nuevos.append(etiquetas[tema])
            else:
                vinculados.append(etiquetas[tema])
            ppt.setdefault(tema, set()).add(virtual)
            tpp.setdefault(virtual, set()).add(tema)
            rel.setdefault((virtual, tema), set()).add(relacion)

    nombres = dict(g.nombres)
    nombres[virtual] = persona.get("nombre") or "Persona simulada"
    g2 = Grafo(ppt, tpp, nombres, etiquetas, rel)

    def clave(r):
        return frozenset(etiquetas.get(t["id"], t["label"]) for t in r["temas"])

    antes = {clave(r): r for r in actividades_emergentes_consenso(g, limite=limite, semillas=semillas)}
    despues = {clave(r): r for r in actividades_emergentes_consenso(g2, limite=limite, semillas=semillas)}

    com1, com2 = comunidades_personas(g, 7), comunidades_personas(g2, 7)
    n1, n2 = len(set(com1.values())), len(set(com2.values()))
    peso2 = rareza(g2.personas_por_tema, len(g2.nombres) or 1)
    area = _etiqueta_area(g2, com2, com2[virtual], peso2) if virtual in com2 else None

    mis_temas = tpp.get(virtual, set())
    directos = Counter()
    for t in mis_temas:
        for p in ppt[t]:
            if p != virtual:
                directos[p] += 1
    top_directos = [{"persona": nombres.get(p, "?"),
                     "temas_compartidos": sorted(etiquetas[t] for t in mis_temas if p in ppt[t])}
                    for p, _ in sorted(directos.items(), key=lambda kv: (-kv[1], str(kv[0])))[:5]]
    indirectos = [{"persona": c["persona"], "camino": " -> ".join(x["label"] for x in c["camino"])}
                  for c in caminos_desde(g2, virtual, limite=5)]

    return {
        "temas_vinculados": sorted(set(vinculados)),
        "temas_nuevos": sorted(set(nuevos)),
        "area_asignada": area,
        "areas_antes": n1, "areas_despues": n2,
        "conexiones_directas": len(directos),
        "directos": top_directos,
        "indirectos": indirectos,
        "actividades_nuevas": [sorted(k) for k in despues if k not in antes],
        "actividades_perdidas": [sorted(k) for k in antes if k not in despues],
        "actividades_estables": len(set(antes) & set(despues)),
    }


# ------------------------------------------------------- puentes estructurales

def _adyacencia(g, sin_persona=None, sin_tema=None) -> dict:
    """Proyeccion persona-persona: unidas si comparten algun tema."""
    adj = {p: set() for p in g.temas_por_persona if p != sin_persona}
    for tema, personas in g.personas_por_tema.items():
        if tema == sin_tema:
            continue
        validas = [p for p in personas if p in adj]
        for p in validas:
            adj[p].update(q for q in validas if q != p)
    return adj


def _pares_a_saltos(adj: dict, saltos: int, universo: set) -> set:
    """Pares ordenados (u, v), ambos en `universo`, con distancia <= saltos."""
    alcanzables = set()
    for origen in universo:
        visto, frontera = {origen}, [origen]
        for _ in range(saltos):
            siguiente = []
            for a in frontera:
                for b in adj.get(a, ()):
                    if b not in visto:
                        visto.add(b)
                        siguiente.append(b)
            frontera = siguiente
        alcanzables.update((origen, v) for v in visto if v != origen and v in universo)
    return alcanzables


def puentes_estructurales(g, limite: int = 6, saltos: int = 3, seed: int = 7) -> dict:
    """Personas y temas cuya ausencia desconectaria areas de la red.

    Para cada persona y cada tema se mide la `perdida_alcance`: que fraccion de
    los pares de personas a `saltos` o menos dejaria de estarlo si ese nodo
    faltara (hueco estructural en el sentido de Burt, hecho contrafactual). Se
    informan ademas la restriccion de Burt, si es punto de articulacion y que
    areas conecta. Funcion pura sobre el grafo.
    """
    import networkx as nx

    comunidad = comunidades_personas(g, seed)
    peso = rareza(g.personas_por_tema, len(g.nombres) or 1)
    adj = _adyacencia(g)
    universo = set(adj)
    base = _pares_a_saltos(adj, saltos, universo)

    proy = nx.Graph()
    proy.add_nodes_from(adj)
    for tema, personas in g.personas_por_tema.items():
        for a, b in itertools.combinations(sorted(personas, key=str), 2):
            if proy.has_edge(a, b):
                proy[a][b]["weight"] += peso[tema]
            else:
                proy.add_edge(a, b, weight=peso[tema])
    restriccion = nx.constraint(proy, weight="weight")
    articulacion = set(nx.articulation_points(proy))

    def etiqueta(i):
        return _etiqueta_area(g, comunidad, i, peso)

    personas = []
    for p in universo:
        resto = universo - {p}
        antes = {(u, v) for (u, v) in base if u != p and v != p}
        despues = _pares_a_saltos(_adyacencia(g, sin_persona=p), saltos, resto)
        perdida = (len(antes) - len(antes & despues)) / len(antes) if antes else 0.0
        vecinos_areas = Counter(comunidad[q] for q in adj[p] if q in comunidad and comunidad[q] != comunidad.get(p))
        r = restriccion.get(p)
        personas.append({
            "persona_id": p, "persona": g.nombres.get(p, "?"),
            "perdida_alcance": round(perdida, 4),
            "restriccion_burt": None if r is None or r != r else round(float(r), 3),
            "punto_de_articulacion": p in articulacion,
            "area_propia": etiqueta(comunidad[p]) if p in comunidad else None,
            "areas_que_conecta": [etiqueta(i) for i, _ in vecinos_areas.most_common(3)],
        })
    personas.sort(key=lambda r: (-r["perdida_alcance"], str(r["persona_id"])))

    temas = []
    for tema, ps in g.personas_por_tema.items():
        if len(ps) < 2:
            continue
        despues = _pares_a_saltos(_adyacencia(g, sin_tema=tema), saltos, universo)
        perdida = (len(base) - len(base & despues)) / len(base) if base else 0.0
        por_area = Counter(comunidad[p] for p in ps if p in comunidad)
        temas.append({
            "tema_id": tema, "tema": g.etiquetas.get(tema, "?"),
            "perdida_alcance": round(perdida, 4), "personas": len(ps),
            "areas_que_une": [etiqueta(i) for i, _ in por_area.most_common(3)],
            "n_areas": len(por_area),
        })
    temas.sort(key=lambda r: (-r["perdida_alcance"], -r["n_areas"], str(r["tema_id"])))
    return {"personas": personas[:limite], "temas": temas[:limite],
            "alcance_base": round(len(base) / (len(universo) * (len(universo) - 1)), 4) if len(universo) > 1 else 0.0,
            "saltos": saltos}


def recortar_por_ids(g, ids: set):
    """Subgrafo con solo las personas de `ids` (los temas quedan si los toca alguna)."""
    ppt, tpp = defaultdict(set), defaultdict(set)
    for tema, personas in g.personas_por_tema.items():
        for p in personas & ids:
            ppt[tema].add(p)
            tpp[p].add(tema)
    return Grafo(dict(ppt), dict(tpp), {i: g.nombres[i] for i in ids if i in g.nombres}, g.etiquetas,
                 {k: v for k, v in g.relacion_de.items() if k[0] in ids})
