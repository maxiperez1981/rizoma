"""Unificacion semantica de temas (no destructiva).

El 69 % de los temas de la red de prueba pertenece a una sola persona, en parte
porque "visualizacion" y "visualizacion de datos" son nodos distintos. Se
embebe cada etiqueta, se agrupa por similitud con enlace completo (todos los
pares del grupo superan el umbral, para no encadenar temas lejanos) y se guarda
un mapa tema -> canonico. No se borra ningun tema ni arista.
"""
import json
import urllib.request
from datetime import datetime

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

import models
from config import settings
from services import claude_service
from services.embedding_service import EMBEDDING_MODEL

LOTE = 100


def _embeber(textos: list) -> list:
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps({"model": EMBEDDING_MODEL, "input": textos}).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))["data"]
    return [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]


def embeber_temas(db: Session, forzar: bool = False) -> int:
    temas = db.query(models.Topic).filter(True if forzar else models.Topic.embedding.is_(None)).all()
    for i in range(0, len(temas), LOTE):
        lote = temas[i:i + LOTE]
        for t, v in zip(lote, _embeber([t.label for t in lote])):
            t.embedding = v
    db.commit()
    return len(temas)


def _matriz(db: Session):
    filas = db.execute(text("select id, label, embedding::text from topics where embedding is not null order by id")).fetchall()
    ids = [f[0] for f in filas]
    m = np.array([[float(x) for x in f[2].strip("[]").split(",")] for f in filas])
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    return ids, {f[0]: f[1] for f in filas}, m @ m.T


def agrupar(sim: np.ndarray, umbral: float) -> list:
    """Enlace completo: devuelve grupos de indices (de tamano >= 2)."""
    n = len(sim)
    grupo = list(range(n))
    miembros = {i: [i] for i in range(n)}
    pares = np.argwhere(np.triu(sim >= umbral, k=1))
    for a, b in sorted(pares.tolist(), key=lambda p: -sim[p[0], p[1]]):
        ga, gb = grupo[a], grupo[b]
        if ga == gb:
            continue
        if all(sim[x, y] >= umbral for x in miembros[ga] for y in miembros[gb]):
            for x in miembros[gb]:
                grupo[x] = ga
            miembros[ga] += miembros.pop(gb)
    return [sorted(m) for m in miembros.values() if len(m) >= 2]


def verificar(grupos: list, lote: int = 15) -> list:
    """Confirma con el modelo que cada grupo sean variantes del mismo tema.

    Los embeddings proponen; el modelo descarta falsos amigos como
    "bioprocesos | procesos". Si el modelo no responde, el grupo se descarta
    (conviene perder una fusion antes que unir dos temas distintos).
    """
    confirmados = []
    for i in range(0, len(grupos), lote):
        parte = grupos[i:i + lote]
        listado = "\n".join(f"{n}. " + " | ".join(g["etiquetas"]) for n, g in enumerate(parte, start=1))
        prompt = f"""Cada linea es un grupo de etiquetas de temas de trayectorias universitarias y laborales. Para cada grupo decidi si las etiquetas son variantes del MISMO tema, a los fines de vincular a personas que trabajan en el.

Responde SI cuando:
- son sinonimos o variantes de escritura o numero ("laboratorio | laboratorios", "IA y empleo | IA y trabajo");
- una es la otra con un calificador menor que no cambia el campo de trabajo ("visualizacion | visualizacion de datos", "accesibilidad | accesibilidad web", "entrevistas | entrevistas en profundidad", "permanencia | permanencia estudiantil", "visualizacion de grafos | visualizacion de grafos con D3").

Responde NO cuando son temas vecinos pero distintos, o una es un campo mucho mas amplio que la otra ("bioprocesos | procesos", "salud | salud publica", "estrategia | estrategia digital", "mediacion de conflictos | mediacion pedagogica", "comunicacion institucional | articulacion institucional", "tecnologia social | tecnologia").

{listado}

Solo JSON: {{"grupos": [{{"n": 1, "mismo_tema": true}}]}}"""
        data, _ = claude_service.llm_json(prompt, 1200, modelo="gpt-4.1")
        decisiones = {d.get("n"): bool(d.get("mismo_tema")) for d in (data or {}).get("grupos", []) if isinstance(d, dict)}
        confirmados += [g for n, g in enumerate(parte, start=1) if decisiones.get(n)]
    return confirmados


def proponer(db: Session, umbral: float, con_verificacion: bool = False) -> list:
    ids, etiquetas, sim = _matriz(db)
    frecuencia = dict(db.execute(text("select topic_id, count(distinct user_id) from user_topics group by 1")).fetchall())
    salida = []
    for g in agrupar(sim, umbral):
        miembros = [ids[i] for i in g]
        canonico = sorted(miembros, key=lambda t: (-frecuencia.get(t, 0), len(etiquetas[t]), etiquetas[t]))[0]
        minimo = min(sim[x, y] for x in g for y in g if x < y)
        salida.append({"canonico": canonico, "etiquetas": [etiquetas[t] for t in miembros],
                       "miembros": miembros, "similitud_minima": round(float(minimo), 3)})
    salida = sorted(salida, key=lambda s: -s["similitud_minima"])
    return verificar(salida) if con_verificacion else salida


def aplicar(db: Session, umbral: float, con_verificacion: bool = True) -> dict:
    grupos = proponer(db, umbral, con_verificacion)
    ids, etiquetas, sim = _matriz(db)
    pos = {t: i for i, t in enumerate(ids)}
    db.query(models.TopicMerge).delete()
    for g in grupos:
        for t in g["miembros"]:
            if t != g["canonico"]:
                db.add(models.TopicMerge(topic_id=t, canonical_id=g["canonico"],
                                         similitud=float(sim[pos[t], pos[g["canonico"]]]), umbral=umbral,
                                         created_at=datetime.utcnow()))
    db.commit()
    return {"grupos": len(grupos), "temas_fusionados": sum(len(g["miembros"]) - 1 for g in grupos)}


def mapa(db: Session) -> dict:
    return {m.topic_id: m.canonical_id for m in db.query(models.TopicMerge).all()}
