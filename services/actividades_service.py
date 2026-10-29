import uuid
from datetime import datetime

from sqlalchemy.orm import Session

import models
from services import claude_service, rizoma_service

ALCANCE_COMPLETO = "red completa"


def _serializar(a: models.ActividadEmergente) -> dict:
    return {
        "id": str(a.id),
        "posicion": a.posicion,
        "titulo": a.titulo,
        "descripcion": a.descripcion,
        "areas": a.areas or [],
        "temas": [t.get("label") for t in (a.temas or [])],
        "n_personas": a.n_personas,
        "demanda": a.demanda,
        "oferta": a.oferta,
        "score": a.score,
        "estabilidad": a.estabilidad,
        "modelo_usado": a.modelo_usado,
        "alcance": a.alcance,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def ultima_corrida(db: Session, alcance: str = ALCANCE_COMPLETO) -> list:
    ultima = (db.query(models.ActividadEmergente)
              .filter(models.ActividadEmergente.alcance == alcance)
              .order_by(models.ActividadEmergente.created_at.desc()).first())
    if not ultima:
        return []
    filas = (db.query(models.ActividadEmergente)
             .filter(models.ActividadEmergente.corrida_id == ultima.corrida_id)
             .order_by(models.ActividadEmergente.posicion).all())
    return [_serializar(f) for f in filas]


def generar(db: Session, grafo=None, alcance: str = ALCANCE_COMPLETO, limite: int = 8,
            usar_ia: bool = True, guardar: bool = True) -> list:
    """Detecta en el grafo, nombra con el modelo y (opcional) guarda la corrida."""
    grafo = grafo or rizoma_service.cargar_grafo(db, unificar=True)
    detectadas = rizoma_service.actividades_emergentes_consenso(grafo, limite=limite)

    corrida = uuid.uuid4()
    resultado = []
    for i, ev in enumerate(detectadas, start=1):
        if usar_ia:
            texto = claude_service.describir_actividad_emergente(ev)
        else:
            texto = claude_service._normalize_actividad(claude_service._local_actividad(ev), "local-heuristic")
        fila = models.ActividadEmergente(
            corrida_id=corrida, alcance=alcance, posicion=i,
            titulo=texto["titulo"], descripcion=texto["descripcion"],
            areas=ev["areas"],
            temas=[{"id": str(t["id"]), "label": t["label"]} for t in ev["temas"]],
            n_personas=ev["n_personas"], demanda=ev["demanda"], oferta=ev["oferta"],
            score=ev["score"], estabilidad=ev["estabilidad"], modelo_usado=texto["modelo_usado"],
            created_at=datetime.utcnow(),
        )
        if guardar:
            db.add(fila)
        resultado.append(_serializar(fila) | {"posicion": i})
    if guardar:
        db.commit()
    return resultado
