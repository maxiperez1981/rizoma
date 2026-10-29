"""Evaluacion humana a ciegas: el unico juez independiente de lo que propone el grafo."""
import math
import random
import statistics
from collections import defaultdict

from sqlalchemy import func, text
from sqlalchemy.orm import Session

import models
from services import rizoma_service as rs
from services.privacy_service import anonymized_profile


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def muestrear_pares(db: Session, g, prefijo: str, usuarios: int, seed: int = 11) -> list:
    """Por usuario: el mas similar, el mejor camino indirecto y un control al azar sin temas comunes."""
    rnd = random.Random(seed)
    ids = sorted({r[0] for r in db.execute(text("select id from users where email like :p"), {"p": prefijo + "%"}).fetchall()}, key=str)
    emb = {r[0]: [float(x) for x in r[1].strip("[]").split(",")] for r in db.execute(
        text("select id, embedding::text from users where email like :p and embedding is not null"), {"p": prefijo + "%"}).fetchall()}
    pares = []
    for u in rnd.sample(ids, min(usuarios, len(ids))):
        sim = sorted(((_cos(emb[u], emb[o]), o) for o in emb if o != u), reverse=True)
        pares.append(("similitud", u, sim[0][1], sim[0][0]))
        cam = rs.caminos_desde(g, u, limite=1)
        if cam:
            pares.append(("indirecto", u, cam[0]["persona_id"], _cos(emb[u], emb[cam[0]["persona_id"]])))
        sin_tema = [o for o in emb if o != u and not (g.temas_por_persona[u] & g.temas_por_persona[o])]
        c = rnd.choice(sorted(sin_tema, key=str))
        pares.append(("control", u, c, _cos(emb[u], emb[c])))
    return pares


def preparar(db: Session, g, prefijo: str, usuarios: int, alcance: str, seed: int = 11) -> int:
    nuevos = 0
    for tipo, a, b, _ in muestrear_pares(db, g, prefijo, usuarios, seed):
        existe = db.query(models.BlindPair).filter(
            models.BlindPair.a_id == a, models.BlindPair.b_id == b, models.BlindPair.alcance == alcance).first()
        if not existe:
            db.add(models.BlindPair(a_id=a, b_id=b, tipo=tipo, alcance=alcance))
            nuevos += 1
    db.commit()
    return nuevos


def _perfil(u: models.User, etiqueta: str) -> dict:
    p = anonymized_profile({"can_offer": u.can_offer or [], "wants_to_learn": u.wants_to_learn or [],
                            "interests": u.interests or u.ai_tags or []}, etiqueta)
    return {k: v for k, v in p.items() if k != "name"} | {"etiqueta": etiqueta}


def siguiente(db: Session, rater: models.User):
    """Un par que este evaluador no calificó, priorizando los menos calificados; orden A/B al azar."""
    ya = db.query(models.BlindRating.pair_id).filter(models.BlindRating.rater_id == rater.id)
    cuenta = dict(db.query(models.BlindRating.pair_id, func.count()).filter(models.BlindRating.simulada.is_(False))
                  .group_by(models.BlindRating.pair_id).all())
    pool = [p for p in db.query(models.BlindPair).filter(~models.BlindPair.id.in_(ya)).all()
            if rater.id not in (p.a_id, p.b_id)]
    if not pool:
        return None
    rnd = random.Random()
    menor = min(cuenta.get(p.id, 0) for p in pool)
    par = rnd.choice([p for p in pool if cuenta.get(p.id, 0) == menor])
    a, b = db.get(models.User, par.a_id), db.get(models.User, par.b_id)
    if rnd.random() < 0.5:
        a, b = b, a
    restantes = len(pool)
    return {"pair_id": str(par.id), "persona_a": _perfil(a, "Persona A"), "persona_b": _perfil(b, "Persona B"),
            "pendientes": restantes}


def calificar(db: Session, rater: models.User, pair_id: str, rating: int, comentario: str) -> bool:
    par = db.get(models.BlindPair, pair_id)
    if not par or rater.id in (par.a_id, par.b_id):
        return False
    if db.query(models.BlindRating).filter_by(pair_id=par.id, rater_id=rater.id).first():
        return False
    db.add(models.BlindRating(pair_id=par.id, rater_id=rater.id, rating=rating, comentario=(comentario or "")[:500]))
    db.commit()
    return True


def _auc(pos, neg):
    if not pos or not neg:
        return None
    return round(sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg)), 3)


def resumen(db: Session, incluir_simuladas: bool = False) -> dict:
    """Por defecto excluye las calificaciones marcadas como simuladas (generadas por IA o por scripts)."""
    consulta = db.query(models.BlindRating, models.BlindPair).join(
        models.BlindPair, models.BlindPair.id == models.BlindRating.pair_id)
    if not incluir_simuladas:
        consulta = consulta.filter(models.BlindRating.simulada.is_(False))
    filas = consulta.all()
    excluidas = 0 if incluir_simuladas else db.query(models.BlindRating).filter(models.BlindRating.simulada.is_(True)).count()
    por_tipo, por_par, evaluadores = defaultdict(list), defaultdict(list), defaultdict(int)
    for r, p in filas:
        por_tipo[p.tipo].append(r.rating)
        por_par[(p.id, p.tipo)].append(r.rating)
        evaluadores[r.rater_id] += 1
    medias = defaultdict(list)
    for (_, tipo), vals in por_par.items():
        medias[tipo].append(statistics.mean(vals))
    dobles = [vals for vals in por_par.values() if len(vals) >= 2]
    return {
        "calificaciones": len(filas),
        "simuladas_excluidas": excluidas,
        "evaluadores": len(evaluadores),
        "pares_totales": db.query(models.BlindPair).count(),
        "media_por_tipo": {t: {"media": round(statistics.mean(v), 2), "n": len(v)} for t, v in por_tipo.items()},
        "auc": {"indirecto_vs_control": _auc(medias["indirecto"], medias["control"]),
                "similitud_vs_control": _auc(medias["similitud"], medias["control"])},
        "pares_con_2_o_mas_evaluadores": len(dobles),
        "diferencia_media_entre_evaluadores": round(statistics.mean(max(v) - min(v) for v in dobles), 2) if dobles else None,
    }
