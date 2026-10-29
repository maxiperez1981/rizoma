import json
import logging
import random
import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user
from database import get_db
from services.limites import limitar
from services import (claude_service, conjunto_service, embedding_service, privacy_notice, rizoma_service,
                      sugerencias_service, visibilidad)

router = APIRouter(prefix="/api/users", tags=["users"])

ANONYMIZED_AI_CACHE_AFTER = "2026-08-09 16:50:00-03"


def _terms(values):
    return [str(v).strip() for v in (values or []) if str(v).strip()]


def _norm(value):
    return str(value or "").lower().strip()


def _overlap(source, target):
    source_terms = _terms(source)
    target_terms = _terms(target)
    matches = []
    for s in source_terms:
        sn = _norm(s)
        if not sn:
            continue
        for t in target_terms:
            tn = _norm(t)
            if not tn:
                continue
            source_words = {w for w in sn.replace(",", " ").replace(";", " ").split() if len(w) > 3}
            target_words = {w for w in tn.replace(",", " ").replace(";", " ").split() if len(w) > 3}
            if sn in tn or tn in sn or (source_words and target_words and source_words & target_words):
                if s not in matches:
                    matches.append(s)
                break
    return matches[:5]


def _relationship_edges(user, other, learn_from_them, offer_them, shared):
    edges = []
    for item in learn_from_them[:3]:
        edges.append({
            "kind": "learn_from",
            "label": "aprendizaje",
            "from": other.name,
            "to": user.name,
            "source_node": item,
            "target_node": item,
            "text": f"Tu nodo de aprendizaje '{item}' conecta con algo que {other.name} puede aportar.",
        })
    for item in offer_them[:3]:
        edges.append({
            "kind": "offer_to",
            "label": "aporte",
            "from": user.name,
            "to": other.name,
            "source_node": item,
            "target_node": item,
            "text": f"Tu nodo de saber '{item}' conecta con algo que {other.name} quiere desarrollar.",
        })
    for item in shared[:2]:
        edges.append({
            "kind": "shared_interest",
            "label": "interés compartido",
            "from": user.name,
            "to": other.name,
            "source_node": item,
            "target_node": item,
            "text": f"Ambos grafos comparten interés en '{item}'.",
        })
    return edges



_ETIQUETA_RE = re.compile(r"\bPersona ([A-Z])\b")


def _personalizar_texto(texto, user, other, mapa_rizoma=None):
    """Devuelve los nombres reales a las etiquetas anonimas que usa el prompt.

    Al modelo no se le mandan identidades, pero escribe esas etiquetas en la
    explicacion y llegaban tal cual al usuario ("Persona A puede ofrecer...").
    Las etiquetas del contexto del rizoma que no se puedan resolver quedan
    como una mencion generica en vez de un codigo sin sentido.
    """
    mapa = {"Persona A": user.name, "Persona B": other.name}
    mapa.update(mapa_rizoma or {})
    return _ETIQUETA_RE.sub(
        lambda m: mapa.get(m.group(0), "otra persona de la red"), str(texto or "")
    )


def _personalize_ai_edges(edges, user, other, mapa_rizoma=None):
    out = []
    for edge in edges or []:
        if not isinstance(edge, dict):
            continue
        item = dict(edge)
        item["from"] = _personalizar_texto(item.get("from") or user.name, user, other, mapa_rizoma)
        item["to"] = _personalizar_texto(item.get("to") or other.name, user, other, mapa_rizoma)
        item["text"] = _personalizar_texto(item.get("text"), user, other, mapa_rizoma)
        out.append(item)
    return out

def _completeness(user: models.User, db: Session) -> int:
    score = 15
    if user.name: score += 10
    if user.institution: score += 8
    if user.bio: score += 10
    if user.can_offer: score += 18
    if user.wants_to_learn: score += 18
    if user.interests: score += 8
    if user.modality or user.availability: score += 6
    if user.ai_summary: score += 12
    apps = db.query(models.ProjectApplication).filter(models.ProjectApplication.user_id == user.id).count()
    if apps > 0: score += 5
    return min(score, 100)


def _user_out(user: models.User, db: Session) -> schemas.UserOut:
    creds_count = db.query(models.Credential).filter(models.Credential.user_id == user.id).count()
    projects_count = db.query(models.ProjectApplication).filter(
        models.ProjectApplication.user_id == user.id,
        models.ProjectApplication.status == "accepted"
    ).count()
    conns_count = db.query(models.Connection).filter(
        ((models.Connection.user_id_a == user.id) | (models.Connection.user_id_b == user.id)),
        models.Connection.status == "accepted"
    ).count()
    unread = db.query(models.Message).filter(
        models.Message.to_id == user.id,
        models.Message.read == False
    ).count()
    unread_notifs = db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.read == False
    ).count()

    return schemas.UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        institution=user.institution,
        bio=user.bio,
        ai_summary=user.ai_summary,
        ai_tags=user.ai_tags or [],
        can_offer=user.can_offer or [],
        wants_to_learn=user.wants_to_learn or [],
        interests=user.interests or [],
        availability=user.availability or "",
        modality=user.modality or "",
        participation_goal=user.participation_goal or "",
        commitment_level=user.commitment_level or "",
        profile_completeness=_completeness(user, db),
        credentials_count=creds_count,
        projects_count=projects_count,
        connections_count=conns_count,
        unread_messages=unread,
        unread_notifications=unread_notifs,
        created_at=user.created_at,
        conjunto=conjunto_service.conjunto_de_email(user.email),
        conjunto_etiqueta=conjunto_service.etiqueta(conjunto_service.conjunto_de_email(user.email)),
        visibilidad=visibilidad.preferencias(user),
        nombre_para_otros=visibilidad.nombre_visible(user, None),
    )


@router.get("/me", response_model=schemas.UserOut)
def get_me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_out(user, db)


@router.put("/me/visibilidad", response_model=schemas.UserOut)
def update_visibilidad(
    body: dict,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Qué ven los demás de mí. No usa IA: no exige el aviso leído."""
    cambios = visibilidad.validar(body)
    if not cambios:
        raise HTTPException(400, "No hay preferencias válidas para guardar")
    user.visibilidad = {**(user.visibilidad or {}), **cambios}
    db.commit()
    db.refresh(user)
    return _user_out(user, db)


@router.put("/me", response_model=schemas.UserOut, dependencies=[Depends(privacy_notice.requiere_aviso_vigente)])
def update_me(
    body: schemas.UserUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    embedding_dirty = False
    embedding_fields = {"bio", "can_offer", "wants_to_learn", "interests"}
    for field in ("name", "institution", "bio", "can_offer", "wants_to_learn", "interests", "availability", "modality", "participation_goal", "commitment_level"):
        value = getattr(body, field)
        if value is not None:
            setattr(user, field, value)
            embedding_dirty = embedding_dirty or field in embedding_fields
    if embedding_dirty:
        embedding_service.update_user_embedding(user, db)
        rizoma_service.sincronizar_usuario(db, user)
    db.commit()
    db.refresh(user)
    return _user_out(user, db)


@router.get("/people/complementary", response_model=list[schemas.ComplementarySuggestion], dependencies=[Depends(limitar("complementary", 60))])
def complementary_people(
    orden: str = "rareza",
    semilla: Optional[int] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sugerencias de personas ordenadas solo con el grafo, sin llamar a ningun modelo.

    Los candidatos son los mismos que antes entraban a la preseleccion (similitud
    de perfiles y oferta/demanda cruzada) mas todas las personas alcanzables en
    el grafo, siempre dentro del conjunto de la persona. Ya no hay recorte a 8
    antes del modelo ni filtro por su veredicto: no se pierde ninguna. El orden
    lo elige quien consulta (ver services/sugerencias_service.py) y cada
    sugerencia trae el dato estructural que la ubica en su lugar. La explicacion
    redactada por el modelo se pide aparte, al abrir la sugerencia.
    """
    if orden not in sugerencias_service.ORDENES:
        raise HTTPException(400, f"orden debe ser uno de {', '.join(sugerencias_service.ORDENES)}")
    if orden == "azar" and semilla is None:
        semilla = random.randint(1, 9999)
    if orden != "azar":
        semilla = None

    conjunto = conjunto_service.conjunto_de_email(user.email)
    g, ids = conjunto_service.grafo_del_conjunto(db, user)

    my_offers = user.can_offer or []
    my_learns = user.wants_to_learn or []
    my_interests = user.interests or user.ai_tags or []

    def lexical_signal(other):
        other_offers = other.can_offer or []
        other_learns = other.wants_to_learn or []
        other_interests = other.interests or other.ai_tags or []
        learn_from_them = _overlap(my_learns, other_offers)
        offer_them = _overlap(other_learns, my_offers)
        shared = _overlap(my_interests, other_interests)
        signal = len(learn_from_them) * 3 + len(offer_them) * 3 + len(shared)
        return signal, learn_from_them, offer_them, shared

    # Preseleccion de siempre, sin el recorte a 8: los 25 perfiles mas similares
    # del conjunto, quienes tienen oferta/demanda o intereses cruzados, y todas
    # las personas que el grafo alcanza (directas y por camino indirecto).
    similitud = {}
    for other, sim in embedding_service.nearest_profiles(user, db, limit=len(ids) + 1):
        if other.id in ids and len(similitud) < 25:
            similitud[other.id] = sim
    alcanzables = {p for t in g.temas_por_persona.get(user.id, ()) for w in g.personas_por_tema.get(t, ())
                   for t2 in g.temas_por_persona.get(w, ()) for p in g.personas_por_tema.get(t2, ())}
    otros = {o.id: o for o in db.query(models.User).filter(models.User.id.in_(ids), models.User.id != user.id).all()}
    pool = {}
    for oid, other in otros.items():
        # Quien eligió no aparecer en sugerencias no se sugiere (sigue en la red).
        if not visibilidad.aparece_en_sugerencias(other):
            continue
        signal, learn_from_them, offer_them, shared = lexical_signal(other)
        if oid in similitud or oid in alcanzables or signal > 0:
            pool[oid] = (other, learn_from_them, offer_them, shared)
    if not pool:
        return []

    est = sugerencias_service.estructuras(g, user.id, list(pool))
    nombres = {oid: visibilidad.nombre_visible(item[0], user) for oid, item in pool.items()}
    orden_ids = sugerencias_service.ordenar(est, nombres, orden, semilla)

    # Sugerencia ya redactada (si existe) solo para registrar el resultado sobre
    # el mismo objeto que antes; no se llama al modelo ni se usa su veredicto.
    previas = {str(r.user_id_b): r.suggestion_id for r in db.execute(
        text(
            """
            SELECT DISTINCT ON (c.user_id_b) c.user_id_b, s.id AS suggestion_id
            FROM match_candidates c JOIN ai_match_suggestions s ON s.candidate_id = c.id
            WHERE c.user_id_a = :a AND s.created_at >= CAST(:cache_after AS timestamptz)
            ORDER BY c.user_id_b, s.created_at DESC
            """
        ),
        {"a": str(user.id), "cache_after": ANONYMIZED_AI_CACHE_AFTER},
    )}

    salida = []
    por_bloque = {}
    for oid in orden_ids:
        other, learn_from_them, offer_them, shared = pool[oid]
        e = est[oid]
        bloque = sugerencias_service.bloque(e)
        por_bloque[bloque] = posicion = por_bloque.get(bloque, 0) + 1
        dato = sugerencias_service.dato_estructural(g, e, orden, semilla)
        # Aviso la primera vez que el par aparece entre las 4 primeras de su
        # bloque (8 en total, como antes) con evidencia en el grafo.
        if posicion <= 4 and bloque != "otros":
            _registrar_y_notificar(db, user, other, float(similitud.get(oid, 0.0)), dato)
        if learn_from_them and offer_them:
            ctype = "Complementariedad recíproca"
        elif learn_from_them:
            ctype = "Puede ayudarte a aprender"
        elif offer_them:
            ctype = "Podés aportar a su recorrido"
        elif shared:
            ctype = "Interés compartido"
        elif e.distancia == 4:
            ctype = "Vínculo indirecto en la red"
        elif e.distancia == 2:
            ctype = "Tema en común"
        else:
            ctype = "Perfil afín por similitud"
        visto = visibilidad.como_se_ve(other, user)
        salida.append(schemas.ComplementarySuggestion(
            id=other.id,
            name=visto.name,
            role=other.role,
            institution=visibilidad.institucion_visible(other, user),
            ai_summary=visibilidad.bio_visible(other, user, other.ai_summary or other.bio or ""),
            can_offer=(other.can_offer or [])[:5],
            wants_to_learn=(other.wants_to_learn or [])[:5],
            interests=(other.interests or other.ai_tags or [])[:5],
            you_can_learn_from_them=learn_from_them,
            you_can_offer_them=offer_them,
            shared_interests=shared,
            connection_type=ctype,
            connection_reason=dato,
            relationship_edges=_relationship_edges(user, visto, learn_from_them, offer_them, shared),
            similarity_score=float(similitud.get(oid, 0.0)),
            ai_suggestion_id=previas.get(str(oid)),
            camino=sugerencias_service.camino_para_mostrar(g, user.id, e),
            dato_estructural=dato,
            orden=orden,
            semilla=semilla,
            posicion=posicion,
            bloque=bloque,
            conjunto=conjunto,
        ))
    db.commit()
    return salida


def _registrar_y_notificar(db: Session, user: models.User, other: models.User, similitud: float, dato: str):
    """Registra el par como candidato y avisa la primera vez que aparece con evidencia en el grafo."""
    fila = db.execute(
        text(
            """
            INSERT INTO match_candidates (id, user_id_a, user_id_b, similarity_score, created_at)
            VALUES (gen_random_uuid(), :a, :b, :score, now())
            ON CONFLICT (user_id_a, user_id_b) DO NOTHING
            RETURNING id
            """
        ),
        {"a": str(user.id), "b": str(other.id), "score": similitud},
    ).fetchone()
    if fila is not None:
        rizoma_service.crear_notificacion_match(db, user, other, fila[0], dato)


def _candidato(db: Session, user: models.User, other: models.User) -> tuple:
    """Id del par en match_candidates (lo crea si hace falta) y su similitud de perfiles."""
    sim = db.execute(
        text("SELECT 1 - (a.embedding <=> b.embedding) FROM users a, users b WHERE a.id = :a AND b.id = :b"),
        {"a": str(user.id), "b": str(other.id)},
    ).scalar()
    sim = float(sim or 0.0)
    fila = db.execute(
        text(
            """
            INSERT INTO match_candidates (id, user_id_a, user_id_b, similarity_score, created_at)
            VALUES (gen_random_uuid(), :a, :b, :score, now())
            ON CONFLICT (user_id_a, user_id_b) DO UPDATE SET similarity_score = EXCLUDED.similarity_score
            RETURNING id
            """
        ),
        {"a": str(user.id), "b": str(other.id), "score": sim},
    ).fetchone()
    return fila[0], sim


@router.get("/people/{other_id}/explicacion", response_model=schemas.ExplicacionSugerencia, dependencies=[Depends(privacy_notice.requiere_aviso_vigente), Depends(limitar("explicacion", 120))])
def explicacion_sugerencia(
    other_id: UUID,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Explicacion redactada por el modelo para una sugerencia, a pedido.

    Es el unico punto del flujo de sugerencias que llama al modelo. Reutiliza la
    explicacion guardada si es reciente. El veredicto y el puntaje del modelo se
    guardan (para investigacion) pero no se devuelven.
    """
    other = db.query(models.User).filter(models.User.id == other_id).first()
    if other is None or other.id == user.id or (
        conjunto_service.conjunto_de_email(other.email) != conjunto_service.conjunto_de_email(user.email)
    ):
        raise HTTPException(404, "Sugerencia no encontrada")
    candidate_id, sim = _candidato(db, user, other)

    cached = db.execute(
        text(
            """
            SELECT id, explicacion, relationship_edges, modelo_usado
            FROM ai_match_suggestions
            WHERE candidate_id = :candidate_id
              AND created_at > now() - interval '7 days'
              AND created_at >= CAST(:cache_after AS timestamptz)
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"candidate_id": str(candidate_id), "cache_after": ANONYMIZED_AI_CACHE_AFTER},
    ).mappings().first()

    g, _ = conjunto_service.grafo_del_conjunto(db, user)
    contexto_rizoma, mapa_rizoma = rizoma_service.contexto_rizoma_con_mapa(db, user, grafo=g)
    if cached:
        suggestion_id, explicacion = cached["id"], cached["explicacion"] or ""
        edges, modelo = cached["relationship_edges"] or [], cached["modelo_usado"] or "cache"
    else:
        person = lambda u: {"name": u.name, "can_offer": u.can_offer or [], "wants_to_learn": u.wants_to_learn or [],
                            "interests": u.interests or u.ai_tags or []}
        try:
            ai_result = claude_service.evaluate_complementarity(person(user), person(other), sim, contexto_rizoma)
        except Exception:
            logging.exception("Fallo evaluate_complementarity para %s", other.id)
            raise HTTPException(503, "No se pudo redactar la explicación ahora; probá de nuevo en un rato.")
        explicacion, edges = ai_result["explicacion"], ai_result.get("relationship_edges") or []
        modelo = ai_result.get("modelo_usado", "unknown")
        suggestion_id = db.execute(
            text(
                """
                INSERT INTO ai_match_suggestions
                    (id, candidate_id, hay_complementariedad, score_final, explicacion, relationship_edges, modelo_usado, created_at)
                VALUES (gen_random_uuid(), :candidate_id, :hay, :score, :explicacion, CAST(:edges AS jsonb), :modelo, now())
                RETURNING id
                """
            ),
            {
                "candidate_id": str(candidate_id),
                "hay": bool(ai_result["hay_complementariedad"]),
                "score": int(ai_result["score_final"]),
                "explicacion": explicacion,
                "edges": json.dumps(edges, ensure_ascii=False),
                "modelo": modelo,
            },
        ).fetchone()[0]
    db.commit()
    visto = visibilidad.como_se_ve(other, user)
    return schemas.ExplicacionSugerencia(
        id=other.id,
        explicacion=_personalizar_texto(explicacion, user, visto, mapa_rizoma),
        relationship_edges=_personalize_ai_edges(edges, user, visto, mapa_rizoma),
        ai_suggestion_id=suggestion_id,
        degradado=str(modelo).startswith("local-"),
    )


@router.get("/red-completa")
def red_completa(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """La red entera: todas las personas con todos sus temas."""
    g, _ = conjunto_service.grafo_del_conjunto(db, user)
    return rizoma_service.red_completa(db, user, grafo=g)


@router.get("/me/rizoma-grafo")
def rizoma_grafo(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vecindario del usuario como nodos y aristas, para dibujar el grafo."""
    g, _ = conjunto_service.grafo_del_conjunto(db, user)
    return rizoma_service.grafo_vecindario(db, user, grafo=g)


@router.get("/me/rizoma-caminos")
def rizoma_caminos(
    limite: int = 10,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Personas alcanzables solo por camino indirecto en el grafo de temas.

    Complementa a /people/complementary: aquel devuelve vinculos directos,
    este devuelve los que no comparten ningun tema con el usuario y por lo
    tanto no pueden encontrarse solos.
    """
    g, _ = conjunto_service.grafo_del_conjunto(db, user)
    return rizoma_service.caminos_sugeridos(db, user, min(limite, 25), grafo=g)


@router.get("/me/rizoma-snapshots", response_model=list[schemas.RizomaSnapshotOut])
def rizoma_snapshots(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.RizomaSnapshot).filter(
        models.RizomaSnapshot.user_id == user.id
    ).order_by(models.RizomaSnapshot.created_at.desc()).limit(12).all()


@router.post("/match-outcomes", response_model=schemas.MatchOutcomeOut)
def create_match_outcome(
    body: schemas.MatchOutcomeCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = models.MatchOutcome(
        user_id=user.id,
        target_type=body.target_type,
        target_id=body.target_id,
        outcome=body.outcome,
        source=body.source or "rizoma",
        notes=body.notes or "",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/match-outcomes", response_model=list[schemas.MatchOutcomeOut])
def list_match_outcomes(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.MatchOutcome).filter(
        models.MatchOutcome.user_id == user.id
    ).order_by(models.MatchOutcome.created_at.desc()).limit(50).all()



@router.get("/admin/dashboard/metricas", response_model=list[schemas.DashboardMetricsRow])
def dashboard_metricas(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in ("teacher", "org", "admin"):
        raise HTTPException(403, "No autorizado para ver el tablero institucional")
    rows = db.execute(text("SELECT * FROM dashboard_metricas")).fetchall()
    return [
        schemas.DashboardMetricsRow(
            mes=row.mes,
            sugerencias_totales=row.sugerencias_totales,
            vinculos_utiles=row.vinculos_utiles,
            vinculos_no_utiles=row.vinculos_no_utiles,
            colaboraciones_generadas=row.colaboraciones_generadas,
        )
        for row in rows
    ]

@router.get("/{user_id}", response_model=schemas.UserPublic)
def get_user(user_id: UUID, viewer: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    # Fuera del propio conjunto el perfil no existe (salvo para administración).
    if not user or (viewer.role != "admin" and (
        conjunto_service.conjunto_de_email(user.email) != conjunto_service.conjunto_de_email(viewer.email)
    )):
        raise HTTPException(404, "Usuario no encontrado")
    return schemas.UserPublic(
        id=user.id,
        name=visibilidad.nombre_visible(user, viewer),
        role=user.role,
        institution=visibilidad.institucion_visible(user, viewer),
        bio=visibilidad.bio_visible(user, viewer, user.bio),
        ai_summary=visibilidad.bio_visible(user, viewer, user.ai_summary),
        ai_tags=user.ai_tags or [],
        can_offer=user.can_offer or [],
        wants_to_learn=user.wants_to_learn or [],
        interests=user.interests or [],
    )




