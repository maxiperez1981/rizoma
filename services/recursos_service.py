"""Recursos que cada persona pone a disposición de la red (traído de Rizoma Afadeco).

Además de lo que sabe, lo que quiere aprender y lo que le interesa, cada persona
puede ofrecer recursos sin saber de antemano para qué servirán: una persona que
quiere colaborar, datos, un laboratorio, un espacio, una convocatoria, tiempo.
Quien lo necesita lo reconoce y dice «me sirve, para…»: eso llega como mensaje a
quien lo ofreció y queda registrado. A las dos semanas, las dos partes cuentan si
hablaron y si sirvió.

Cada recurso se describe con temas, como el grafo, y se cruza con lo que cada
persona quiere aprender o le interesa (por el mismo tema o por el mismo subtema
del vocabulario controlado). Los textos pasan por el filtro de privacidad: sin
correos, teléfonos, documentos ni enlaces. Una persona ofrecida por otra se
describe sin su nombre hasta que acepte. Todo queda dentro del conjunto de quien
mira (prueba, demostración o red general).
"""
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models
from services import conjunto_service, visibilidad
from services.privacy_service import anonymize_text
from services.rizoma_service import slugify

TIPOS = {
    "persona": "Una persona que quiere colaborar",
    "datos": "Datos",
    "infraestructura": "Laboratorio o infraestructura",
    "software": "Software o materiales",
    "espacio": "Espacio o actividad",
    "oportunidad": "Convocatoria u oportunidad",
    "publicacion": "Revista o publicación",
    "estudiantes": "Estudiantes o un equipo",
    # Recursos que tiene cualquiera, para no premiar solo a quien ya tiene contactos.
    "tiempo": "Tiempo o una habilidad",
    # Se publica el tipo de acceso y su propósito, nunca el nombre del contacto.
    "acceso": "Acceso a medios o a espacios de gestión",
}
RESULTADOS = {"hablamos": "Hablamos", "sirvio": "Sirvió", "no_sirvio": "No sirvió"}
DIAS_SEGUIMIENTO = 14
MAX_RECURSOS, MAX_TEMAS = 8, 5


def _texto(valor, largo):
    return anonymize_text(valor, max_len=largo).strip()


def validar(lista) -> list:
    """Normaliza la lista que manda la persona; lo inválido se rechaza con un mensaje claro."""
    if not isinstance(lista, list):
        raise HTTPException(422, "Los recursos tienen que ser una lista.")
    if len(lista) > MAX_RECURSOS:
        raise HTTPException(422, f"Podés poner a disposición hasta {MAX_RECURSOS} recursos.")
    salida = []
    for r in lista:
        if not isinstance(r, dict):
            raise HTTPException(422, "Cada recurso tiene que ser un objeto.")
        tipo = r.get("tipo")
        if tipo not in TIPOS:
            raise HTTPException(422, "Tipo de recurso desconocido.")
        titulo = _texto(r.get("titulo"), 140)
        if len(titulo) < 4:
            raise HTTPException(422, "Cada recurso necesita un título de al menos 4 caracteres.")
        temas = [t for t in (_texto(x, 80) for x in (r.get("temas") or [])[:MAX_TEMAS]) if t]
        if tipo == "acceso" and len(_texto(r.get("detalle"), 500)) < 10:
            raise HTTPException(422, "Para un acceso a medios o espacios de gestión, contá en el detalle con qué propósito lo ofrecés.")
        salida.append({
            "id": str(r.get("id") or uuid.uuid4().hex[:10])[:12],
            "tipo": tipo,
            "titulo": titulo,
            "detalle": _texto(r.get("detalle"), 500),
            "condiciones": _texto(r.get("condiciones"), 140),
            "temas": temas,
            # Solo cuenta para una persona ofrecida por otra: sin aceptación, su nombre no se publica.
            "acepto": bool(r.get("acepto")) if tipo == "persona" else True,
        })
    return salida


def asegurar_temas(db: Session, recursos: list) -> None:
    """Crea los temas que falten, para que el clasificador los ubique en el vocabulario."""
    existentes = {t.slug for t in db.query(models.Topic).all()}
    alias = {a.alias_slug for a in db.query(models.TopicAlias).all()}
    for r in recursos:
        for tema in r["temas"]:
            slug = slugify(tema)
            if slug and slug not in existentes and slug not in alias:
                db.add(models.Topic(slug=slug, label=tema))
                existentes.add(slug)


def guardar(db: Session, user, lista) -> list:
    recursos = validar(lista)
    asegurar_temas(db, recursos)
    user.recursos = recursos
    db.commit()
    return recursos


class _Red:
    def __init__(self, db: Session, user):
        ids = conjunto_service.ids_del_conjunto(db, conjunto_service.conjunto_de_email(user.email))
        personas = db.query(models.User).filter(models.User.id.in_(list(ids))).all() if ids else []
        self.personas = {p.id: p for p in personas if p.id == user.id or visibilidad.aparece_en_sugerencias(p)}
        temas = db.query(models.Topic).all()
        self.por_slug = {t.slug: t for t in temas}
        por_id = {t.id: t for t in temas}
        for a in db.query(models.TopicAlias).all():
            if a.topic_id in por_id:
                self.por_slug.setdefault(a.alias_slug, por_id[a.topic_id])
        self.user, self.db = user, db

    def ficha(self, p):
        return {"id": str(p.id), "nombre": visibilidad.nombre_visible(p, self.user, como_puente=True),
                "institucion": visibilidad.institucion_visible(p, self.user)}

    def usos(self):
        filas = self.db.query(models.RecursoUso).filter(models.RecursoUso.owner_id.in_(list(self.personas))).all()
        cuenta, mios = {}, set()
        for u in filas:
            cuenta[(u.owner_id, u.recurso_id)] = cuenta.get((u.owner_id, u.recurso_id), 0) + 1
            if u.user_id == self.user.id:
                mios.add((u.owner_id, u.recurso_id))
        return cuenta, mios

    def tarjeta(self, p, r, cuenta, mios, motivo=None):
        return {**r, "tipo_nombre": TIPOS[r["tipo"]],
                "titulo": r["titulo"] if r.get("acepto", True) else "Una persona que quiere colaborar (nombre reservado hasta que acepte)",
                "de": self.ficha(p), "propio": p.id == self.user.id, "pedidos": cuenta.get((p.id, r["id"]), 0),
                "ya_lo_pediste": (p.id, r["id"]) in mios, "motivo": motivo}


def catalogo(db: Session, user) -> list:
    red = _Red(db, user)
    cuenta, mios = red.usos()
    salida = [red.tarjeta(p, r, cuenta, mios) for p in red.personas.values() for r in (p.recursos or [])]
    return sorted(salida, key=lambda x: (x["propio"], -x["pedidos"], x["tipo"], x["titulo"]))


def para_mi(db: Session, user, limite: int = 6) -> list:
    """Recursos de otras personas que tocan lo que quiero aprender (primero) o lo que me interesa."""
    red = _Red(db, user)
    cuenta, mios = red.usos()
    busco = {}
    for t in (user.interests or []):
        busco[slugify(t)] = "te interesa"
    for t in (user.wants_to_learn or []):
        busco[slugify(t)] = "querés aprender"
    sub_mio = {}
    for slug, por in busco.items():
        t = red.por_slug.get(slug)
        if t and t.subtema:
            sub_mio.setdefault(t.subtema, (t.label, por))
    salida = []
    for p in red.personas.values():
        if p.id == user.id:
            continue
        for r in (p.recursos or []):
            motivo, puntaje = None, 0
            for tema in r["temas"]:
                s = slugify(tema)
                if s in busco:
                    motivo, puntaje = f"Toca «{tema}», que {busco[s]}", (3 if busco[s] == "querés aprender" else 2)
                    break
            if not motivo:
                for tema in r["temas"]:
                    t = red.por_slug.get(slugify(tema))
                    if t and t.subtema in sub_mio:
                        motivo, puntaje = f"Mismo subtema ({t.subtema}) que «{sub_mio[t.subtema][0]}», que {sub_mio[t.subtema][1]}", 1
                        break
            if motivo:
                salida.append((puntaje, red.tarjeta(p, r, cuenta, mios, motivo)))
    salida.sort(key=lambda x: (-x[0], -x[1]["pedidos"], x[1]["titulo"]))
    return [t for _, t in salida[:limite]]


def me_sirve(db: Session, user, owner_id, recurso_id: str, para_que: str) -> dict:
    red = _Red(db, user)
    duenio = red.personas.get(owner_id)
    recurso = next((r for r in ((duenio.recursos or []) if duenio else []) if r["id"] == recurso_id), None)
    if not recurso:
        raise HTTPException(404, "Ese recurso no está disponible.")
    if owner_id == user.id:
        raise HTTPException(400, "Es un recurso tuyo.")
    para_que = _texto(para_que, 400)
    if len(para_que) < 8:
        raise HTTPException(422, "Contá en una línea para qué te sirve.")
    if db.query(models.RecursoUso).filter_by(owner_id=owner_id, recurso_id=recurso_id, user_id=user.id).first():
        raise HTTPException(409, "Ya le avisaste que este recurso te sirve.")
    titulo = recurso["titulo"] if recurso.get("acepto", True) else TIPOS["persona"]
    db.add(models.RecursoUso(owner_id=owner_id, recurso_id=recurso_id, user_id=user.id, para_que=para_que))
    db.add(models.Message(from_id=user.id, to_id=owner_id, body=f"Me sirve tu recurso «{titulo}», para: {para_que}"))
    db.commit()
    return {"ok": True}


def seguimiento(db: Session, user) -> list:
    """Avisos «me sirve» de hace DIAS_SEGUIMIENTO días o más, sin resultado: ¿hablaron? ¿sirvió?"""
    limite = datetime.utcnow() - timedelta(days=DIAS_SEGUIMIENTO)
    filas = (db.query(models.RecursoUso)
             .filter(models.RecursoUso.resultado.is_(None), models.RecursoUso.created_at <= limite,
                     (models.RecursoUso.user_id == user.id) | (models.RecursoUso.owner_id == user.id))
             .order_by(models.RecursoUso.created_at).all())
    salida = []
    for u in filas:
        duenio, quien = db.get(models.User, u.owner_id), db.get(models.User, u.user_id)
        r = next((x for x in (duenio.recursos or []) if x["id"] == u.recurso_id), None) if duenio else None
        if not r or not quien:
            continue
        otro = duenio if u.user_id == user.id else quien
        salida.append({"id": str(u.id), "titulo": r["titulo"] if r.get("acepto", True) else TIPOS["persona"],
                       "dias": (datetime.utcnow() - u.created_at).days, "para_que": u.para_que,
                       "pediste": u.user_id == user.id, "con": visibilidad.nombre_visible(otro, user, como_puente=True)})
    return salida


def registrar_resultado(db: Session, user, uso_id, resultado: str) -> dict:
    if resultado not in RESULTADOS:
        raise HTTPException(422, "Resultado desconocido.")
    u = db.get(models.RecursoUso, uso_id)
    if not u or user.id not in (u.user_id, u.owner_id):
        raise HTTPException(404, "Ese aviso no existe.")
    u.resultado, u.resultado_at = resultado, datetime.utcnow()
    db.commit()
    return {"ok": True}
