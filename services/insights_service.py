import uuid
from datetime import datetime

from sqlalchemy.orm import Session

import models
from services import claude_service, rizoma_service

ALCANCE_COMPLETO = "red completa"


def _fila(i: models.Insight) -> dict:
    return {
        "id": str(i.id), "tipo": i.tipo, "posicion": i.posicion, "titulo": i.titulo,
        "descripcion": i.descripcion, "datos": i.datos or {}, "modelo_usado": i.modelo_usado,
        "alcance": i.alcance, "created_at": i.created_at.isoformat() if i.created_at else None,
    }


def ultima(db: Session, tipo: str, alcance: str = ALCANCE_COMPLETO) -> list:
    ultimo = (db.query(models.Insight)
              .filter(models.Insight.tipo == tipo, models.Insight.alcance == alcance)
              .order_by(models.Insight.created_at.desc()).first())
    if not ultimo:
        return []
    filas = (db.query(models.Insight).filter(models.Insight.corrida_id == ultimo.corrida_id)
             .order_by(models.Insight.posicion).all())
    return [_fila(f) for f in filas]


def guardar(db: Session, tipo: str, alcance: str, filas: list) -> list:
    corrida = uuid.uuid4()
    objetos = [models.Insight(
        corrida_id=corrida, alcance=alcance, tipo=tipo, posicion=i,
        titulo=f.get("titulo", ""), descripcion=f.get("descripcion", ""),
        datos=f.get("datos") or {}, modelo_usado=f.get("modelo_usado", ""),
        created_at=datetime.utcnow()) for i, f in enumerate(filas, start=1)]
    db.add_all(objetos)
    db.commit()
    return [_fila(o) for o in objetos]


def generar_demanda_latente(db: Session, grafo=None, alcance: str = ALCANCE_COMPLETO,
                            limite: int = 8, usar_ia: bool = True, persistir: bool = True) -> list:
    grafo = grafo or rizoma_service.cargar_grafo(db, unificar=True)
    filas = []
    for ev in rizoma_service.demanda_latente(grafo, limite=limite):
        texto = (claude_service.describir_demanda_latente(ev) if usar_ia else
                 {"titulo": f"Clinica de {ev['tema']['label']}",
                  "descripcion": f"{ev['demanda']} personas quieren aprender {ev['tema']['label']} y {ev['oferta']} lo ofrecen.",
                  "modelo_usado": "local-heuristic"})
        filas.append({**texto, "datos": {
            "tema": ev["tema"]["label"], "demanda": ev["demanda"], "oferta": ev["oferta"],
            "areas_demandantes": ev["areas_demandantes"], "n_areas": ev["n_areas"], "score": ev["score"]}})
    return guardar(db, "demanda_latente", alcance, filas) if persistir else filas


def equipo_de_actividad(db: Session, actividad_id: str, visibles=frozenset(), grafo=None) -> dict:
    """Equipo sugerido para una actividad. Solo se nombra a las personas cuyo id
    está en `visibles` (un conjunto de ids, o una función que recibe los ids del
    equipo y devuelve los visibles; ver services/cohortes.py). El resto aparece
    como «Persona N».
    """
    act = db.query(models.ActividadEmergente).filter(models.ActividadEmergente.id == actividad_id).first()
    if not act or len(act.temas or []) != 2:
        return {}
    grafo = grafo or rizoma_service.cargar_grafo(db)
    por_texto = {str(t): t for t in grafo.personas_por_tema}
    ids = [por_texto.get(t["id"]) for t in act.temas]
    if None in ids:
        return {}
    equipo = rizoma_service.equipo_para_actividad(grafo, ids[0], ids[1])
    if callable(visibles):
        visibles = visibles([str(m["persona_id"]) for m in equipo["miembros"]])
    miembros = []
    for n, m in enumerate(equipo["miembros"], start=1):
        visible = str(m["persona_id"]) in visibles
        miembros.append({
            "persona": m["persona"] if visible else f"Persona {n}",
            "persona_id": str(m["persona_id"]) if visible else None,
            "rol": m["rol"], "temas": m["temas"], "area": m["area"],
        })
    return {"actividad": act.titulo, **{k: v for k, v in equipo.items() if k != "miembros"}, "miembros": miembros}


def generar_puentes(db: Session, grafo=None, alcance: str = ALCANCE_COMPLETO, persistir: bool = True) -> dict:
    grafo = grafo or rizoma_service.cargar_grafo(db, unificar=True)
    res = rizoma_service.puentes_estructurales(grafo)
    datos = {
        "saltos": res["saltos"], "alcance_base": res["alcance_base"],
        "personas": [{**p, "persona_id": str(p["persona_id"])} for p in res["personas"]],
        "temas": [{**t, "tema_id": str(t["tema_id"])} for t in res["temas"]],
    }
    fila = {"titulo": "Puentes estructurales", "datos": datos, "modelo_usado": "grafo",
            "descripcion": "Personas y temas cuya ausencia desconectaria areas de la red (perdida de pares a pocos saltos)."}
    return guardar(db, "puentes", alcance, [fila])[0] if persistir else fila


def ocultar_nombres(insight: dict, visibles=frozenset(), nombres=None) -> dict:
    """Personas que no están en `visibles` (ids como texto) pasan a 'Persona N', sin id.

    `nombres` ({id texto: nombre}) reemplaza el nombre guardado en la corrida por
    el que cada persona eligió mostrar (services/visibilidad.py).
    """
    nombres = nombres or {}
    out = {**insight, "datos": {**insight["datos"]}}
    out["datos"]["personas"] = [
        {**p, "persona": nombres.get(str(p.get("persona_id")), p.get("persona"))}
        if str(p.get("persona_id")) in visibles else {**p, "persona": f"Persona {i}", "persona_id": None}
        for i, p in enumerate(insight["datos"].get("personas", []), start=1)
    ]
    return out
