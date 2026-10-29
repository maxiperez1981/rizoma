"""Aprende de las calificaciones humanas que pesa en un camino indirecto.

El puntaje actual de un camino es peso[t1] * peso[t2] / log(2 + grado del
intermediario). Con las calificaciones a ciegas de los pares `indirecto` se
ajusta una regresion ridge sobre esas mismas piezas (mas la similitud
semantica) y se valida con leave-one-out. No cambia el ranking en produccion:
informa si el puntaje actual predice lo que los evaluadores consideran util y
que pieza deberia pesar mas. Por debajo de MINIMO_PARES no da resultados.
"""
import math
from collections import defaultdict

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

import models
from services import rizoma_service as rs

MINIMO_PARES = 20
NOMBRES = ["rareza_tema_origen", "rareza_tema_puente", "inversa_grado_intermediario", "similitud_semantica"]


def _rangos(v):
    orden = np.argsort(v, kind="stable")
    r = np.empty(len(v))
    r[orden] = np.arange(len(v))
    for x in set(v):
        idx = np.where(np.array(v) == x)[0]
        r[idx] = r[idx].mean()
    return r


def spearman(x, y) -> float:
    rx, ry = _rangos(list(x)), _rangos(list(y))
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def ridge(X: np.ndarray, y: np.ndarray, lam: float = 1.0):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    ym = y.mean()
    beta = np.linalg.solve(Z.T @ Z + lam * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return beta, mu, sd, ym


def predecir(X, modelo):
    beta, mu, sd, ym = modelo
    return ((X - mu) / sd) @ beta + ym


def ajustar(X: np.ndarray, y: np.ndarray, puntaje_actual: np.ndarray, lam: float = 1.0) -> dict:
    """Ajuste ridge con validacion leave-one-out. X: n x 4 en el orden de NOMBRES."""
    n = len(y)
    if n < MINIMO_PARES:
        return {"estado": "datos_insuficientes", "pares": n, "minimo": MINIMO_PARES}
    modelo = ridge(X, y, lam)
    loo = np.array([predecir(X[i:i + 1], ridge(np.delete(X, i, 0), np.delete(y, i), lam))[0] for i in range(n)])
    ajuste = predecir(X, modelo)
    ss_res, ss_tot = float(((y - ajuste) ** 2).sum()), float(((y - y.mean()) ** 2).sum())
    return {
        "estado": "ok", "pares": n,
        "correlacion_puntaje_actual_vs_calificacion": round(spearman(puntaje_actual, y), 3),
        "correlacion_modelo_ajustado_loo": round(spearman(loo, y), 3),
        "r2_en_muestra": round(1 - ss_res / ss_tot, 3) if ss_tot else None,
        "coeficientes_estandarizados": {k: round(float(b), 3) for k, b in zip(NOMBRES, modelo[0])},
        "lectura": "Si la correlacion del modelo ajustado (loo) no supera a la del puntaje actual, "
                   "los pesos actuales ya capturan lo que los evaluadores valoran.",
    }


def desde_calificaciones(db: Session, lam: float = 1.0) -> dict:
    filas = db.query(models.BlindRating, models.BlindPair).join(
        models.BlindPair, models.BlindPair.id == models.BlindRating.pair_id).filter(
        models.BlindPair.tipo == "indirecto", models.BlindRating.simulada.is_(False)).all()
    notas = defaultdict(list)
    par = {}
    for r, p in filas:
        notas[p.id].append(r.rating)
        par[p.id] = p
    if len(notas) < MINIMO_PARES:
        return {"estado": "datos_insuficientes", "pares": len(notas), "minimo": MINIMO_PARES}

    grafo_completo = rs.cargar_grafo(db)
    emb = {r[0]: [float(x) for x in r[1].strip("[]").split(",")]
           for r in db.execute(text("select id, embedding::text from users where embedding is not null")).fetchall()}
    por_alcance = {}
    X, y, actual = [], [], []
    for pid, valores in notas.items():
        p = par[pid]
        if p.alcance not in por_alcance:
            prefijo = p.alcance.rstrip("*")
            ids = {r[0] for r in db.execute(text("select id from users where email like :p"), {"p": prefijo + "%"}).fetchall()}
            g = rs.recortar_por_ids(grafo_completo, ids)
            por_alcance[p.alcance] = (g, rs.rareza(g.personas_por_tema, len(g.nombres) or 1))
        g, peso = por_alcance[p.alcance]
        camino = next((c for c in rs.caminos_desde(g, p.a_id, limite=1000) if c["persona_id"] == p.b_id), None)
        if camino is None or p.a_id not in emb or p.b_id not in emb:
            continue
        va, vb = np.array(emb[p.a_id]), np.array(emb[p.b_id])
        grado = len(g.temas_por_persona.get(camino["intermedio_id"], ()))
        X.append([peso[camino["tema_origen_id"]], peso[camino["tema_puente_id"]], 1 / math.log(2 + grado),
                  float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb)))])
        y.append(float(np.mean(valores)))
        actual.append(camino["score"])
    return ajustar(np.array(X), np.array(y), np.array(actual), lam)
