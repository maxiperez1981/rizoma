"""Conjunto de demostracion para la exposicion: 16 perfiles ficticios (demo.vivo.*).

Uso (desde la carpeta del proyecto):
  RIZOMA_DEMO_PASSWORD=... PYTHONPATH=. python3 scripts/conjunto_demo.py cargar
  PYTHONPATH=. python3 scripts/conjunto_demo.py descargar
  PYTHONPATH=. python3 scripts/conjunto_demo.py estado

No toca el conjunto de prueba (demo.unq.*) ni a nadie mas: sincroniza solo las
aristas de estas personas (nunca rizoma_service.sincronizar, que reescribe la
tabla entera y cambia el orden de carga del que depende Louvain; ver
PENDIENTES.md). Cargar es idempotente por email; descargar borra estas personas
y todo lo que cuelga de ellas.

Tres historias armadas para contarse en vivo (a dos saltos, sin temas en comun):
  1. Carla (Enfermeria) -> Hospital Zonal Sur -> Diego (Informatica):
     historia clinica digital y desarrollo de software.
  2. Lucia (Comunicacion) -> Prof. Marta Quiroga -> Tomas (Bioinformatica):
     divulgacion cientifica y analisis genomico.
  3. Nahuel (Ambiente) -> Cooperativa Reciclar -> Sabrina (Economia):
     gestion de residuos y costos y precios.
"""
import os
import sys

from sqlalchemy import text

import models
from auth import hash_password
from database import SessionLocal
from services import rizoma_service
from services.embedding_service import update_user_embedding

PREFIJO = "demo.vivo."
BIO = "Perfil ficticio del conjunto de demostración de Rizoma."


def perfil(slug, nombre, rol, institucion, area, ofrece, quiere, intereses):
    return {"email": f"{PREFIJO}{slug}@rizoma.local", "name": nombre, "role": rol, "institution": institucion,
            "bio": f"{BIO} Área: {area}.", "can_offer": ofrece, "wants_to_learn": quiere, "interests": intereses,
            "ai_tags": intereses[:], "availability": "4 h semanales", "modality": "hibrida",
            "commitment_level": "medio"}


PERFILES = [
    # salud
    perfil("carla", "Carla Ibáñez", "student", "UNQ · Licenciatura en Enfermería", "salud",
           ["triage", "gestión de turnos", "atención primaria"], ["historia clínica digital"], ["salud comunitaria"]),
    perfil("valeria", "Valeria Romero", "student", "UNQ · Licenciatura en Terapia Ocupacional", "salud",
           ["accesibilidad", "rehabilitación"], ["interfaces sonoras"], ["autonomía"]),
    perfil("hospital", "Hospital Zonal Sur", "org", "Organización de salud", "salud",
           ["historia clínica digital", "residencias en salud"], ["desarrollo de software", "gestión de turnos"],
           ["salud comunitaria", "innovación en salud"]),
    # sistemas
    perfil("diego", "Diego Ferreyra", "student", "UNQ · Licenciatura en Informática", "sistemas",
           ["desarrollo de software", "bases de datos", "APIs"], ["usabilidad"], ["tecnología cívica"]),
    perfil("paula", "Paula Benítez", "student", "UNQ · Tecnicatura en Programación Informática", "sistemas",
           ["apps móviles", "usabilidad"], ["huella de carbono"], ["tecnología cívica"]),
    perfil("tomas", "Tomás Rivas", "student", "UNQ · Licenciatura en Bioinformática", "sistemas",
           ["análisis genómico", "Python"], ["comunicación de riesgo"], ["genómica"]),
    perfil("marta", "Prof. Marta Quiroga", "teacher", "UNQ · Departamento de Ciencia y Tecnología", "sistemas",
           ["análisis genómico", "visualización de datos"], ["divulgación científica"], ["ciencia pública", "genómica"]),
    # comunicacion
    perfil("lucia", "Lucía Paz", "student", "UNQ · Licenciatura en Comunicación Social", "comunicación",
           ["divulgación científica", "guion audiovisual"], ["visualización de datos"], ["ciencia pública"]),
    perfil("martin", "Martín Sosa", "student", "UNQ · Licenciatura en Comunicación Social", "comunicación",
           ["redes sociales", "campañas"], ["economía circular"], ["empleo local"]),
    # economia y gestion
    perfil("sabrina", "Sabrina Gómez", "student", "UNQ · Licenciatura en Economía del Desarrollo", "economía y gestión",
           ["costos y precios", "evaluación de proyectos"], ["economía social"], ["empleo local"]),
    perfil("rocio", "Rocío Álvarez", "student", "UNQ · Licenciatura en Administración", "economía y gestión",
           ["gestión de proyectos", "planificación"], ["innovación en salud"], ["organizaciones"]),
    perfil("gustavo", "Prof. Gustavo Herrera", "teacher", "UNQ · Departamento de Economía y Administración",
           "economía y gestión", ["economía social", "cooperativismo"], ["campañas"], ["empleo local", "economía circular"]),
    # ambiente y territorio
    perfil("nahuel", "Nahuel Ortiz", "student", "UNQ · Licenciatura en Ciencias Ambientales", "ambiente y territorio",
           ["gestión de residuos", "huella de carbono"], ["modelos de negocio"], ["economía circular"]),
    perfil("ezequiel", "Ezequiel Luna", "student", "UNQ · Tecnicatura en Gestión Ambiental", "ambiente y territorio",
           ["cartografía", "SIG"], ["apps móviles"], ["territorio"]),
    perfil("cooperativa", "Cooperativa Reciclar Quilmes", "org", "Organización de la economía social",
           "ambiente y territorio", ["clasificación de residuos", "trabajo cooperativo"],
           ["gestión de residuos", "costos y precios"], ["economía circular", "empleo local"]),
    # artes y tecnologia
    perfil("julian", "Julián Medina", "student", "UNQ · Licenciatura en Música y Tecnología", "artes y tecnología",
           ["diseño sonoro", "producción musical"], ["accesibilidad"], ["interfaces sonoras"]),
]

# Tablas que apuntan a users sin borrado en cascada (lo demas cae con el usuario).
SIN_CASCADA = [
    ("notifications", "other_user_id"), ("connections", "user_id_a"), ("connections", "user_id_b"),
    ("credentials", "user_id"), ("match_outcomes", "user_id"), ("messages", "from_id"), ("messages", "to_id"),
    ("posts", "user_id"), ("project_applications", "user_id"), ("projects", "created_by"),
    ("rizoma_snapshots", "user_id"),
]


def cargar(db):
    clave = os.environ.get("RIZOMA_DEMO_PASSWORD")
    if not clave:
        raise SystemExit("Falta RIZOMA_DEMO_PASSWORD (la misma de los perfiles de ejemplo).")
    creados = 0
    for datos in PERFILES:
        user = db.query(models.User).filter(models.User.email == datos["email"]).first()
        if user is None:
            user = models.User(email=datos["email"], password_hash=hash_password(clave))
            db.add(user)
            creados += 1
        for campo, valor in datos.items():
            if campo != "email":
                setattr(user, campo, valor)
        db.flush()
        update_user_embedding(user, db)
        rizoma_service.sincronizar_usuario(db, user)
    db.commit()
    print(f"cargados {len(PERFILES)} perfiles ({creados} nuevos)")


def descargar(db):
    ids = [r[0] for r in db.execute(text("select id from users where email like :p"), {"p": PREFIJO + "%"})]
    if not ids:
        print("no hay perfiles de demostración cargados")
        return
    for tabla, columna in SIN_CASCADA:
        db.execute(text(f"delete from {tabla} where {columna} = any(:ids)"), {"ids": ids})
    db.execute(text("delete from users where id = any(:ids)"), {"ids": ids})
    db.commit()
    print(f"descargados {len(ids)} perfiles de demostración")


def estado(db):
    n = db.execute(text("select count(*) from users where email like :p"), {"p": PREFIJO + "%"}).scalar()
    prueba = db.execute(text("select count(*) from users where email like 'demo.unq.%'")).scalar()
    print(f"demostración: {n} perfiles · prueba: {prueba} perfiles")


def main():
    accion = sys.argv[1] if len(sys.argv) > 1 else "estado"
    db = SessionLocal()
    try:
        {"cargar": cargar, "descargar": descargar, "estado": estado}[accion](db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
