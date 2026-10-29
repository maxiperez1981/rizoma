"""Preguntarle a la red: respuesta con el grafo como evidencia.

La pregunta se vuelve un embedding, se recuperan las personas mas cercanas, se
calcula para cada una su relacion con quien pregunta (temas compartidos o
camino indirecto) y el modelo redacta una respuesta usando solo esa evidencia.
Los perfiles viajan anonimizados al modelo (Persona 1..k) y los caminos le
llegan sin nombres de personas. Solo se buscan personas del conjunto de quien
pregunta que aceptan aparecer en sugerencias; los nombres se devuelven como
cada una eligió mostrarse (services/visibilidad.py).
"""
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

import models
from services import claude_service, conjunto_service, embedding_service, rizoma_service, visibilidad
from services.privacy_service import anonymize_list, anonymize_text


def _persona_sin_nombre(i: int, total: int) -> str:
    if i == 0:
        return "quien pregunta"
    return "esta persona" if i == total - 1 else "otra persona"


def _relacion(g, user_id, otro_id, caminos):
    """Vinculo con quien pregunta. `detalle` se muestra; `detalle_modelo` va al prompt, sin nombres."""
    mios, suyos = g.temas_por_persona.get(user_id, set()), g.temas_por_persona.get(otro_id, set())
    comunes = sorted(g.etiquetas.get(t, "?") for t in mios & suyos)
    if comunes:
        detalle = "temas compartidos: " + ", ".join(comunes)
        return {"tipo": "directa", "detalle": detalle, "detalle_modelo": detalle}
    c = caminos.get(str(otro_id))
    if c:
        pasos = c["camino"]
        return {"tipo": "indirecta",
                "detalle": "camino: " + " -> ".join(p["label"] for p in pasos),
                "detalle_modelo": "camino: " + " -> ".join(
                    _persona_sin_nombre(i, len(pasos)) if p["tipo"] == "persona" else p["label"]
                    for i, p in enumerate(pasos))}
    return {"tipo": "ninguna", "detalle": "sin vinculo en el grafo", "detalle_modelo": "sin vinculo en el grafo"}


def _salida(c, user, motivo=""):
    u = c["user"]
    return {"id": str(u.id), "nombre": c["nombre"], "institucion": visibilidad.institucion_visible(u, user),
            "motivo": motivo, "vinculo": c["rel"]["tipo"], "detalle": c["rel"]["detalle"]}


def preguntar(db: Session, user: models.User, pregunta: str, k: int = 6) -> dict:
    pregunta = anonymize_text(pregunta, max_len=400)
    vector = embedding_service.generate_embedding(pregunta)
    if vector is None:
        return {"respuesta": "No pude interpretar la pregunta ahora (falta el servicio de embeddings).", "personas": [], "modelo_usado": "ninguno"}

    g, ids = conjunto_service.grafo_del_conjunto(db, user)
    literal = "[" + ",".join(str(v) for v in vector) + "]"
    filas = db.execute(text("""
        SELECT id, 1 - (embedding <=> CAST(:v AS vector)) AS sim FROM users
        WHERE embedding IS NOT NULL AND id != CAST(:me AS uuid) AND id = ANY(CAST(:ids AS uuid[]))
        ORDER BY embedding <=> CAST(:v AS vector), id LIMIT :lim"""),
        {"v": literal, "me": str(user.id), "ids": [str(i) for i in ids], "lim": k + 20}).fetchall()
    usuarios = {str(u.id): u for u in db.query(models.User).filter(models.User.id.in_([f[0] for f in filas])).all()} if filas else {}
    filas = [f for f in filas if visibilidad.aparece_en_sugerencias(usuarios[str(f[0])])][:k]
    if not filas:
        return {"respuesta": "La red todavia no tiene perfiles para responder esa pregunta.", "personas": [], "modelo_usado": "ninguno"}

    caminos = {str(c["persona_id"]): c for c in rizoma_service.caminos_desde(g, user.id, limite=500)}

    candidatos = []
    for n, (uid, sim) in enumerate(filas, start=1):
        u = usuarios[str(uid)]
        candidatos.append({"n": n, "user": u, "nombre": visibilidad.nombre_visible(u, user),
                           "sim": float(sim or 0.0), "rel": _relacion(g, user.id, uid, caminos)})

    bloque = "\n".join(
        f"Persona {c['n']}: ofrece {anonymize_list(c['user'].can_offer or [])}; quiere aprender {anonymize_list(c['user'].wants_to_learn or [])}; "
        f"intereses {anonymize_list(c['user'].interests or [])}. Relacion con quien pregunta: {c['rel']['detalle_modelo']}."
        for c in candidatos)
    prompt = f"""Una persona de una red universitaria pregunta: "{pregunta}"

Perfil de quien pregunta: ofrece {anonymize_list(user.can_offer or [])}; quiere aprender {anonymize_list(user.wants_to_learn or [])}.

Personas de la red que podrian tener que ver con la pregunta:
{bloque}

Responde en espanol rioplatense neutro usando SOLO estos datos: no inventes capacidades ni personas, no afirmes que alguien sabe algo que no figura. Si ninguna persona sirve, deci que la red no tiene evidencia suficiente. Cita el vinculo (tema compartido o camino) cuando exista.

Solo JSON: {{"respuesta": "3 o 4 frases", "recomendadas": [{{"numero": 1, "motivo": "una frase"}}]}}"""
    data, modelo = claude_service.llm_json(prompt, 700)

    por_n = {c["n"]: c for c in candidatos}
    personas, vistos = [], set()
    for rec in (data or {}).get("recomendadas", []) or []:
        c = por_n.get(rec.get("numero")) if isinstance(rec, dict) else None
        if c and c["n"] not in vistos:
            vistos.add(c["n"])
            personas.append(_salida(c, user, str(rec.get("motivo") or "")[:300]))
    if data and data.get("respuesta"):
        texto = str(data["respuesta"])[:1200]
        for c in sorted(candidatos, key=lambda c: -c["n"]):
            texto = re.sub(rf"\b(?:[Ll]a|[Ee]l)\s+Persona\s+{c['n']}\b", c["nombre"], texto)
            texto = texto.replace(f"Persona {c['n']}", c["nombre"])
        return {"respuesta": texto, "personas": personas, "modelo_usado": modelo}
    return {
        "respuesta": "No pude redactar una respuesta con el modelo. Estas son las personas mas cercanas a tu pregunta.",
        "personas": [_salida(c, user) for c in candidatos[:3]],
        "modelo_usado": "local-heuristic",
    }
