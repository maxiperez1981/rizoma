"""Seed de 50 perfiles ficticios UNQ para demo de Rizoma.

Idempotente por email. No toca usuarios reales y reconstruye aristas
persona-tema al final para que /me/rizoma-grafo y /me/rizoma-caminos muestren
las conexiones.
"""
import os
from database import SessionLocal
import models
from auth import hash_password
from services import rizoma_service
from services.embedding_service import update_user_embedding


PASSWORD_DEMO = os.environ["RIZOMA_DEMO_PASSWORD"]
INSTITUTION = "UNQ"


def perfil(n, name, carrera, can_offer, wants, interests, activity):
    return {
        "email": f"demo.unq.{n:02d}@rizoma.local",
        "name": name,
        "role": "student",
        "institution": f"{INSTITUTION} · {carrera}",
        "bio": (
            f"Perfil ficticio para demo de Rizoma. Estudiante de {carrera}. "
            f"Actividad emergente sugerida: {activity}."
        ),
        "ai_summary": f"Estudiante de {carrera}. Puede aportar {', '.join(can_offer[:2])}. Busca aprender {', '.join(wants[:2])}.",
        "ai_tags": interests[:],
        "can_offer": can_offer,
        "wants_to_learn": wants,
        "interests": interests,
        "availability": "6 h semanales",
        "modality": "hibrida",
        "participation_goal": activity,
        "commitment_level": "medio",
        "activity": activity,
    }


PERFILES = [
    perfil(1, "Lucia Medina", "Licenciatura en Informatica", ["Python", "bases de datos", "scraping", "visualizacion de datos"], ["comunicacion publica de datos", "periodismo cientifico"], ["IA y empleo", "datos abiertos", "visualizacion"], "Observatorio de empleos IA en el conurbano"),
    perfil(2, "Tomas Pereyra", "Licenciatura en Comunicacion Social", ["redaccion", "entrevistas", "narrativas transmedia", "comunicacion publica de datos"], ["analisis de datos", "visualizacion de datos"], ["IA y empleo", "ciencia publica", "desigualdad"], "Historias de reconversion laboral con evidencia"),
    perfil(3, "Camila Rios", "Licenciatura en Bioinformatica", ["secuencias biologicas", "mineria de datos", "analisis genomico"], ["visualizacion inmersiva", "diseno de interfaces"], ["genomica", "salud", "IA cientifica"], "Visualizacion de datos biomedicos para publicos no expertos"),
    perfil(4, "Mateo Silva", "Licenciatura en Artes Digitales", ["visualizacion inmersiva", "UX", "prototipado interactivo"], ["datos cientificos", "analisis genomico"], ["interaccion", "accesibilidad", "arte y ciencia"], "Interfaces para explorar redes de conocimiento"),
    perfil(5, "Sofia Acosta", "Ingenieria en Automatizacion y Control Industrial", ["sensores", "PLC", "control de procesos", "automatizacion liviana"], ["economia cooperativa", "gestion pyme"], ["industria 4.0", "seguridad laboral"], "Sensores de bajo costo para pymes y cooperativas"),
    perfil(6, "Bruno Cejas", "Tecnicatura Universitaria en Economia Social y Solidaria", ["economia cooperativa", "mapeo de actores", "gestion asociativa"], ["automatizacion liviana", "sensores"], ["cooperativas", "territorio", "trabajo"], "Transformacion digital situada en unidades productivas"),
    perfil(7, "Valentina Nunez", "Ingenieria en Alimentos", ["calidad alimentaria", "inocuidad", "procesos industriales"], ["comercio exterior", "trazabilidad digital"], ["alimentos regionales", "certificaciones"], "Trazabilidad exportable para alimentos locales"),
    perfil(8, "Agustin Torres", "Licenciatura en Comercio Internacional", ["comercio exterior", "logistica", "normativa internacional"], ["calidad alimentaria", "inocuidad"], ["exportacion", "cadenas productivas"], "Puente entre laboratorio, calidad y mercado externo"),
    perfil(9, "Martina Lopez", "Licenciatura en Ciencias Sociales", ["entrevistas", "analisis territorial", "metodologia cualitativa"], ["programacion", "bases de datos"], ["politicas publicas", "empleo", "territorio"], "Mapa cuali-cuantitativo de demandas laborales emergentes"),
    perfil(10, "Nicolas Vera", "Tecnicatura Universitaria en Programacion Informatica", ["programacion", "APIs", "frontend", "bases de datos"], ["metodologia cualitativa", "analisis territorial"], ["datos abiertos", "educacion", "territorio"], "Herramientas para investigacion social aplicada"),
    perfil(11, "Florencia Cabrera", "Licenciatura en Educacion", ["didactica", "evaluacion", "diseno curricular"], ["IA generativa", "programacion"], ["tutorias", "inclusion educativa"], "Tutor IA con corpus validado por catedras"),
    perfil(12, "Joaquin Molina", "Licenciatura en Musica y Tecnologia", ["diseno sonoro", "composicion digital", "produccion musical"], ["accesibilidad", "terapia ocupacional"], ["interfaces sonoras", "salud", "cuidado"], "Experiencias auditivas para orientacion y cuidado"),
    perfil(13, "Ailen Duarte", "Licenciatura en Terapia Ocupacional", ["accesibilidad", "evaluacion funcional", "cuidado"], ["diseno sonoro", "interfaces sonoras"], ["autonomia", "persona mayor", "salud"], "Interfaces sonoras accesibles para personas mayores"),
    perfil(14, "Federico Sosa", "Licenciatura en Turismo y Hoteleria", ["gestion turistica", "diseno de experiencias", "patrimonio local"], ["realidad aumentada", "produccion digital"], ["turismo inteligente", "territorio"], "Recorridos aumentados para patrimonio local"),
    perfil(15, "Rocio Benitez", "Tecnicatura Universitaria en Produccion Digital", ["produccion digital", "edicion multimedia", "realidad aumentada"], ["historia local", "archivo"], ["museos", "memoria", "patrimonio local"], "Archivo interactivo de memorias laborales"),
    perfil(16, "Ivan Arce", "Licenciatura en Gestion de Recursos Humanos y Relaciones Laborales", ["seleccion laboral", "capacitacion", "clima laboral"], ["auditoria algoritmica", "sesgos"], ["IA justa", "empleo", "organizaciones"], "Protocolos de IA responsable en seleccion"),
    perfil(17, "Paula Mansilla", "Profesorado de Ciencias Sociales", ["planificacion didactica", "ciudadania", "talleres"], ["datos laborales", "IA y empleo"], ["educacion", "trabajo", "juventudes"], "Secuencias para alfabetizacion laboral e IA"),
    perfil(18, "Ezequiel Herrera", "Licenciatura en Biotecnologia", ["bioprocesos", "cultivos", "laboratorio"], ["comunicacion cientifica", "periodismo cientifico"], ["bioeconomia", "salud", "ciencia publica"], "Comunicacion publica de desarrollos biotecnologicos"),
    perfil(19, "Milagros Paz", "Tecnicatura Universitaria en Quimica", ["ensayos quimicos", "laboratorio", "materiales"], ["monitoreo ambiental", "comunicacion de riesgo"], ["agua", "suelo", "calidad"], "Red comunitaria de medicion ambiental"),
    perfil(20, "Damian Castro", "Tecnicatura Universitaria en Tecnologia Ambiental y Petroquimica", ["monitoreo ambiental", "muestreo", "gestion ambiental"], ["comunicacion de riesgo", "ensayos quimicos"], ["ambiente", "industria", "territorio"], "Reportes territoriales de contaminacion y prevencion"),
    perfil(21, "Julieta Farias", "Licenciatura en Economia del Desarrollo", ["indicadores", "politica economica", "evaluacion de politicas"], ["modelos predictivos", "machine learning"], ["desarrollo", "empleo", "IA y empleo"], "Indice local de transicion laboral por IA"),
    perfil(22, "Santiago Ibarra", "Licenciatura en Historia", ["archivo", "memoria", "analisis documental"], ["produccion multimedia", "visualizacion"], ["trabajo", "movimientos sociales", "historia local"], "Narrativas digitales sobre cambios laborales"),
    perfil(23, "Candela Quiroga", "Arquitectura Naval", ["diseno naval", "materiales", "planos tecnicos"], ["sensorica", "mantenimiento predictivo"], ["movilidad", "energia", "seguridad"], "Mantenimiento predictivo para embarcaciones"),
    perfil(24, "Lautaro Gimenez", "Licenciatura en Administracion Hotelera", ["operaciones hoteleras", "calidad de servicio", "experiencia de usuario"], ["ciencia de datos", "modelos predictivos"], ["turismo inteligente", "servicios"], "Prediccion de demanda turistica responsable"),
    perfil(25, "Micaela Robledo", "Tecnicatura en Gestion de Medios Comunitarios", ["produccion radial", "redes barriales", "comunicacion comunitaria"], ["economia social", "marketplace cooperativo"], ["comunicacion popular", "cooperativas"], "Marketplace cooperativo con narrativa territorial"),
    perfil(26, "Gonzalo Paredes", "Tecnicatura Universitaria en Seguridad e Higiene en el Trabajo", ["matrices de riesgo", "prevencion", "seguridad laboral"], ["automatizacion", "alertas predictivas"], ["IA y trabajo", "industria"], "Alertas predictivas en entornos de trabajo"),
    perfil(27, "Abril Dominguez", "Contador Publico", ["costos", "auditoria", "reportes contables"], ["datos productivos", "visualizacion de datos"], ["pymes", "gestion", "reconversion tecnologica"], "Tableros financieros para reconversion tecnologica"),
    perfil(28, "Matias Ferreyra", "Licenciatura en Administracion", ["procesos", "estrategia", "gestion de equipos"], ["IA aplicada", "automatizacion de tareas"], ["innovacion organizacional", "gestion"], "Mapa de automatizacion de tareas administrativas"),
    perfil(29, "Josefina Salas", "Licenciatura en Gestion del Comercio Internacional", ["cadenas globales", "documentacion comercial", "logistica"], ["trazabilidad digital", "blockchain"], ["comercio exterior", "evidencia digital"], "Evidencia digital para cadenas productivas regionales"),
    perfil(30, "Ramiro Aguirre", "Tecnicatura Universitaria en Ciencias Empresariales", ["modelo de negocio", "ventas", "operaciones"], ["prototipado tecnologico", "IA aplicada"], ["emprendimientos", "pymes"], "Laboratorio de microemprendimientos con IA"),
    perfil(31, "Nadia Peralta", "Licenciatura en Enfermeria", ["cuidado", "educacion sanitaria", "salud comunitaria"], ["analitica de datos", "tableros interactivos"], ["salud publica", "persona mayor"], "Deteccion temprana de necesidades de cuidado"),
    perfil(32, "Leandro Roldan", "Tecnicatura Universitaria en Acompanamiento y Cuidado de la Persona Mayor", ["acompanamiento", "rutinas de cuidado", "escucha activa"], ["tecnologias accesibles", "agenda inteligente"], ["envejecimiento", "autonomia", "cuidado"], "Agenda inteligente de cuidados comunitarios"),
    perfil(33, "Carolina Vega", "Profesorado de Educacion", ["evaluacion formativa", "planificacion", "tutorias"], ["herramientas IA", "analitica de aprendizaje"], ["inclusion educativa", "permanencia"], "Asistente para seguimiento de trayectorias escolares"),
    perfil(34, "Pablo Fernandez", "Profesorado de Historia", ["narrativa historica", "archivos", "didactica"], ["diseno interactivo", "produccion digital"], ["memoria", "educacion", "trabajo"], "Museo digital de trayectorias laborales locales"),
    perfil(35, "Marina Godoy", "Profesorado de Comunicacion Social", ["produccion audiovisual", "talleres", "comunicacion educativa"], ["datos abiertos", "auditoria algoritmica"], ["juventudes", "medios", "IA"], "Campanas de alfabetizacion algoritmica"),
    perfil(36, "Lucas Campos", "Licenciatura en Geografia", ["SIG", "cartografia", "analisis territorial"], ["mercado laboral", "datos laborales"], ["movilidad", "ambiente", "empleo"], "Mapa de accesibilidad a oportunidades de empleo"),
    perfil(37, "Elena Suarez", "Licenciatura en Ciencias Sociales y Humanidades", ["analisis cultural", "escritura academica", "lectura institucional"], ["IA documental", "mineria de textos"], ["educacion superior", "trabajo"], "Monitor de cambios en perfiles profesionales"),
    perfil(38, "Ignacio Navarro", "Licenciatura en Educacion", ["gestion educativa", "mediacion pedagogica", "campus virtual"], ["UX", "visualizacion de grafos"], ["permanencia", "trayectorias"], "Rizoma de tutorias y alertas de abandono"),
    perfil(39, "Malena Ortiz", "Licenciatura en Artes y Tecnologias", ["instalaciones interactivas", "sensores", "arte publico"], ["datos sociales", "analisis territorial"], ["comunidad", "trabajo", "arte"], "Instalacion sobre transformacion del trabajo"),
    perfil(40, "Sebastian Luna", "Licenciatura en Composicion con Medios Electroacusticos", ["sintesis sonora", "composicion", "archivo sonoro"], ["IA creativa responsable", "derechos digitales"], ["sonido", "memoria", "cultura"], "Archivo sonoro generado con consentimiento"),
    perfil(41, "Victoria Arias", "Tecnicatura Universitaria en Creacion Musical", ["composicion musical", "produccion cultural", "gestion de repertorio"], ["distribucion digital", "derechos digitales"], ["industrias culturales", "cooperativas"], "Cooperativa de musica y derechos digitales"),
    perfil(42, "Alan Mendez", "Tecnicatura Universitaria en Produccion Musical y Nuevas Tecnologias", ["grabacion", "mezcla", "podcast"], ["comunicacion institucional", "periodismo cientifico"], ["educacion", "sonido", "IA"], "Podcast de ciencia y mercado laboral"),
    perfil(43, "Bianca Costa", "Licenciatura en Informatica", ["machine learning", "backend", "auditoria tecnica"], ["etica de IA", "sesgos"], ["datos", "recomendadores", "IA justa"], "Auditoria tecnica de algoritmos de recomendacion"),
    perfil(44, "Franco Villalba", "Licenciatura en Bioinformatica", ["modelado biologico", "bases omicas", "analisis genomico"], ["negocios biotecnologicos", "modelo de negocio"], ["bioeconomia", "emprendimientos"], "Vinculacion entre laboratorio y emprendimientos biotech"),
    perfil(45, "Renata Esposito", "Ingenieria en Alimentos", ["formulacion", "vida util", "calidad alimentaria"], ["diseno de marca", "comunicacion visual"], ["alimentos saludables", "territorio"], "Marca territorial con evidencia nutricional"),
    perfil(46, "Hernan Bravo", "Tecnicatura Universitaria en Biotecnologia", ["tecnicas de laboratorio", "cultivos", "bioprocesos"], ["gestion de proyectos", "vinculacion tecnologica"], ["laboratorios", "biotech"], "Banco de capacidades tecnicas para laboratorios"),
    perfil(47, "Selene Morales", "Licenciatura en Comunicacion Social", ["estrategia digital", "edicion", "divulgacion"], ["bioinformatica basica", "IA cientifica"], ["ciencia abierta", "salud"], "Divulgacion de IA aplicada a ciencias naturales"),
    perfil(48, "Diego Ledesma", "Licenciatura en Administracion Hotelera", ["gestion de servicios", "experiencia de usuario", "turismo"], ["accesibilidad", "tecnologias accesibles"], ["turismo inclusivo", "territorio"], "Circuitos turisticos accesibles con soporte digital"),
    perfil(49, "Noelia Fuentes", "Tecnicatura Universitaria en Gestion de Pequenas y Medianas Empresas", ["diagnostico pyme", "procesos", "gestion"], ["automatizacion liviana", "IA aplicada"], ["productividad", "empleo", "pymes"], "Clinica de IA para pymes locales"),
    perfil(50, "Emiliano Rivas", "Licenciatura en Economia del Desarrollo", ["indicadores sociales", "evaluacion de politicas", "analisis de desigualdad"], ["comunicacion visual", "visualizacion de datos"], ["IA", "brechas digitales", "empleo"], "Informe publico sobre reconversion y brechas digitales"),
]


def main():
    db = SessionLocal()
    try:
        creados = 0
        actualizados = 0
        embeddings = 0
        for datos in PERFILES:
            activity = datos.pop("activity")
            user = db.query(models.User).filter(models.User.email == datos["email"]).first()
            if user is None:
                user = models.User(email=datos["email"], password_hash=hash_password(PASSWORD_DEMO))
                db.add(user)
                creados += 1
            else:
                actualizados += 1

            for campo, valor in datos.items():
                if campo != "email":
                    setattr(user, campo, valor)
            user.profile_completeness = 95
            db.flush()
            if update_user_embedding(user, db):
                embeddings += 1
            snap = db.query(models.RizomaSnapshot).filter(
                models.RizomaSnapshot.user_id == user.id,
                models.RizomaSnapshot.source == "demo_unq_50",
            ).order_by(models.RizomaSnapshot.created_at.desc()).first()
            if snap is None:
                snap = models.RizomaSnapshot(user_id=user.id, source="demo_unq_50")
                db.add(snap)
            snap.source_filename = "seed_unq_50.py"
            snap.summary = user.ai_summary
            snap.tags = user.ai_tags or []
            snap.can_offer = user.can_offer or []
            snap.wants_to_learn = user.wants_to_learn or []
            snap.interests = user.interests or []
            snap.graph = {
                "nodes": [{"id": "cv", "label": "Trayectoria demo", "kind": "source"}],
                "edges": [],
                "activity": activity,
            }
            snap.text_preview = user.bio
            db.commit()
            print(f"{datos['email']} {user.name}: listo")

        sync = rizoma_service.sincronizar(db)
        print(f"creados={creados} actualizados={actualizados} embeddings={embeddings}")
        print(f"sincronizacion={sync}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
