"""Recursos ficticios del conjunto de demostración (demo.vivo.*) y algunos avisos «me sirve».

Uso: PYTHONPATH=. python3 scripts/recursos_demo.py cargar | descargar
Idempotente: reemplaza los recursos de los perfiles demo.vivo.* y sus avisos.
Solo toca cuentas demo.vivo.*: nunca perfiles reales ni del conjunto de prueba.
"""
import sys
from datetime import datetime, timedelta

from sqlalchemy import text

import models
from database import SessionLocal
from services import recursos_service

P = "demo.vivo."


def r(tipo, titulo, temas, detalle="", condiciones="", acepto=True, rid=None):
    return {"id": rid, "tipo": tipo, "titulo": titulo, "temas": temas, "detalle": detalle,
            "condiciones": condiciones, "acepto": acepto}


RECURSOS = {
    "gustavo": [r("persona", "Un colega que trabaja inteligencia artificial y quiere colaborar con la economía social",
                  ["inteligencia artificial", "economía social"],
                  "Quiere sumarse a proyectos, talleres o asesorías. Todavía no sabemos para qué: proponelo vos.",
                  "Virtual, sin costo", rid="ia-colega")],
    "hospital": [r("datos", "Registros anonimizados de demoras en los turnos de atención primaria",
                   ["gestión de turnos", "innovación en salud"],
                   "Series de 2023 a 2025, sin datos de pacientes, para trabajos finales o prototipos.", "Con convenio de uso", rid="turnos"),
                 r("espacio", "Rotaciones en las residencias de salud", ["residencias en salud", "historia clínica digital"],
                   "Cupos para que estudiantes de otras carreras conozcan cómo se organiza un servicio.", "Dos por cuatrimestre", rid="rotaciones")],
    "cooperativa": [r("espacio", "Planta de clasificación abierta para visitas y prácticas", ["clasificación de residuos", "economía circular"],
                      "Se puede observar el proceso completo y medir lo que se recupera.", "Martes y jueves a la mañana", rid="planta"),
                    r("datos", "Toneladas recuperadas por material, 2020–2025", ["gestión de residuos"], rid="toneladas")],
    "marta": [r("infraestructura", "Servidores del laboratorio de bioinformática para análisis de datos", ["análisis genómico", "Python"],
                "Horas de cómputo para proyectos de estudiantes, con acompañamiento.", "Remoto", rid="servidores")],
    "julian": [r("infraestructura", "Estudio de grabación de la carrera, en los horarios libres", ["producción musical", "diseño sonoro"],
                 rid="estudio")],
    "ezequiel": [r("software", "Capas SIG del distrito de Quilmes", ["SIG", "cartografía"],
                   "Calles, barrios, centros de salud y puntos verdes, listos para usar.", "Licencia abierta", rid="capas")],
    "sabrina": [r("software", "Planilla de costos para emprendimientos de la economía social", ["costos y precios", "economía social"],
                  "Con una guía corta para calcular el precio de venta.", "Licencia abierta", rid="planilla")],
    # Recursos que tiene cualquiera: tiempo y habilidades, no solo contactos.
    "diego": [r("tiempo", "Dos horas por semana para armar una base de datos o una API", ["bases de datos", "APIs"],
                "Para proyectos de extensión o de otras carreras que necesiten ordenar sus datos.", "Virtual", rid="api")],
    "lucia": [r("tiempo", "Guiones para contar un proyecto en video", ["divulgación científica", "guion audiovisual"],
                "Ayudo a convertir un trabajo técnico en una pieza corta para redes.", rid="guiones")],
    "rocio": [r("tiempo", "Ayuda para planificar un proyecto y su cronograma", ["gestión de proyectos", "planificación"], rid="plan")],
    "tomas": [r("estudiantes", "Grupo de estudio de Python que suma gente de otras carreras", ["Python"],
                "Nos juntamos una vez por semana; no hace falta saber programar.", "Viernes a la tarde", rid="grupo-py")],
    # Acceso con propósito declarado, sin el nombre del contacto.
    "martin": [r("acceso", "Llegada a una radio comunitaria de la zona", ["comunicación comunitaria", "campañas"],
                 "Para difundir proyectos de extensión y de la economía social. Presento el trabajo si las dos partes aceptan.",
                 "Entrevistas de divulgación, no publicidad", rid="radio")],
}

# (quien pide, de quién es, recurso, para qué)
USOS = [
    ("cooperativa", "gustavo", "ia-colega", "Para clasificar con IA las fotos de los materiales que llegan a la planta."),
    ("diego", "hospital", "turnos", "Para probar una app que reordene los turnos con datos reales anonimizados."),
    ("nahuel", "cooperativa", "planta", "Para medir la huella de carbono de la clasificación en mi trabajo final."),
    ("valeria", "julian", "estudio", "Para grabar interfaces sonoras accesibles para rehabilitación."),
    ("tomas", "lucia", "guiones", "Para contar en video un análisis genómico sin jerga."),
]


def _user(db, slug):
    return db.query(models.User).filter(models.User.email == f"{P}{slug}@rizoma.local").first()


def cargar(db):
    for slug, lista in RECURSOS.items():
        u = _user(db, slug)
        if u is None:
            raise SystemExit(f"falta el perfil {P}{slug}")
        recursos = recursos_service.validar(lista)
        recursos_service.asegurar_temas(db, recursos)
        u.recursos = recursos
    db.flush()
    descargar_usos(db)
    # Avisos de hace tres semanas, para que se vea el seguimiento «¿hablaron? ¿sirvió?».
    hace = datetime.utcnow() - timedelta(days=21)
    for quien, de, rid, para in USOS:
        a, b = _user(db, quien), _user(db, de)
        titulo = next(x["titulo"] for x in RECURSOS[de] if x["id"] == rid)
        db.add(models.RecursoUso(owner_id=b.id, recurso_id=rid, user_id=a.id, para_que=para, created_at=hace))
        db.add(models.Message(from_id=a.id, to_id=b.id, body=f"Me sirve tu recurso «{titulo}», para: {para}", created_at=hace))
    db.commit()
    print(f"recursos en {len(RECURSOS)} perfiles, {sum(len(v) for v in RECURSOS.values())} recursos, {len(USOS)} avisos")


def descargar_usos(db):
    ids = [x[0] for x in db.execute(text("select id from users where email like :p"), {"p": P + "%"})]
    db.execute(text("delete from recurso_usos where owner_id = any(:ids)"), {"ids": ids})
    db.execute(text("delete from messages where body like 'Me sirve tu recurso%' and to_id = any(:ids) and from_id = any(:ids)"),
               {"ids": ids})


def descargar(db):
    descargar_usos(db)
    db.execute(text("update users set recursos = '[]'::json where email like :p"), {"p": P + "%"})
    db.commit()
    print("recursos de la demostración retirados")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        {"cargar": cargar, "descargar": descargar}[sys.argv[1] if len(sys.argv) > 1 else "cargar"](db)
    finally:
        db.close()
