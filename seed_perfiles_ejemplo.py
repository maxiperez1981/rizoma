"""Crea perfiles de ejemplo con estructura de vinculacion deliberada.

El objetivo es que el grafo se lea: en vez de perfiles homogeneos que
matchean todos contra todos, arma cinco dominios semanticamente distantes
(datos, agroecologia, salud, cooperativismo, comunicacion) mas dos perfiles
puente que los cosen.

La complementariedad se detecta por palabras compartidas entre wants_to_learn
y can_offer, asi que cada termino que alguien quiere aprender aparece textual
en el can_offer de otro. Los terminos son multipalabra y distintivos para no
generar aristas espurias por palabras genericas.

Uso: python3 seed_perfiles_ejemplo.py
Es idempotente: actualiza por email si el perfil ya existe.
"""
import os
from database import SessionLocal
import models
from auth import hash_password
from services.embedding_service import update_user_embedding

PASSWORD_DEMO = os.environ["RIZOMA_DEMO_PASSWORD"]

PERFILES = [
    # --- Dominio: datos e IA ---
    {
        "email": "ej.lucia.ferrari@rizoma.local",
        "name": "Lucia Ferrari",
        "institution": "Universidad Nacional de Quilmes",
        "role": "student",
        "bio": "Estudiante avanzada de ingenieria en informatica. Vengo de dos anios "
               "sosteniendo la infraestructura de datos de un proyecto de extension: "
               "armo los esquemas, escribo las migraciones y mantengo las APIs que "
               "consumen los equipos. Me falta el otro lado: nunca coordine un taller "
               "ni sistematice lo que pasa en el territorio.",
        "can_offer": ["PostgreSQL", "modelado de embeddings", "APIs con FastAPI", "limpieza de datasets"],
        "wants_to_learn": ["facilitacion de talleres comunitarios", "economia social y solidaria",
                           "escritura de informes publicos"],
        "interests": ["infraestructura de datos", "software libre", "extension universitaria"],
        "availability": "10 h semanales",
        "modality": "hibrida",
        "participation_goal": "sumar practica territorial",
        "commitment_level": "alto",
    },
    {
        "email": "ej.ramiro.otero@rizoma.local",
        "name": "Ramiro Otero",
        "institution": "Universidad de Buenos Aires",
        "role": "student",
        "bio": "Disenio y programo visualizaciones interactivas. Trabaje en piezas de "
               "periodismo de datos donde el desafio no era el calculo sino que se "
               "entendiera de un vistazo. Quiero entender la capa de abajo, el modelo "
               "de datos, y meterme en un dominio con los pies en la tierra.",
        "can_offer": ["visualizacion de grafos con D3", "analisis de redes sociales", "tableros interactivos"],
        "wants_to_learn": ["PostgreSQL", "agroecologia urbana", "entrevistas en profundidad"],
        "interests": ["periodismo de datos", "software libre", "diseno de interfaces"],
        "availability": "6 h semanales",
        "modality": "remota",
        "participation_goal": "aplicar visualizacion a un caso real",
        "commitment_level": "medio",
    },
    # --- Dominio: agroecologia y ambiente ---
    {
        "email": "ej.mariana.quispe@rizoma.local",
        "name": "Mariana Quispe",
        "institution": "INTA - Agencia Florencio Varela",
        "role": "teacher",
        "bio": "Tecnica agronoma. Acompanio huertas periurbanas desde hace ocho anios: "
               "transicion de suelos degradados, armado de compost a escala de barrio, "
               "formacion de promotores. Tengo cuadernos llenos de registros que nunca "
               "logre convertir en algo que se pueda mostrar ni defender ante un municipio.",
        "can_offer": ["agroecologia urbana", "compostaje comunitario", "manejo de suelos degradados"],
        "wants_to_learn": ["tableros interactivos", "trazabilidad con codigos QR"],
        "interests": ["soberania alimentaria", "huertas periurbanas", "extension universitaria"],
        "availability": "8 h semanales",
        "modality": "presencial",
        "participation_goal": "mostrar resultados de campo",
        "commitment_level": "alto",
    },
    {
        "email": "ej.tomas.beltran@rizoma.local",
        "name": "Tomas Beltran",
        "institution": "Cooperativa La Yunta",
        "role": "org",
        "bio": "Coordino la logistica de una feria de productores que mueve 40 familias. "
               "Armamos un sistema de etiquetas para que el comprador sepa de que quinta "
               "salio cada cajon. Funciona, pero es artesanal y no escala. Necesito "
               "entender mejor la produccion misma, no solo moverla.",
        "can_offer": ["trazabilidad con codigos QR", "logistica de ferias francas", "certificacion participativa"],
        "wants_to_learn": ["agroecologia urbana", "analisis de redes sociales"],
        "interests": ["soberania alimentaria", "comercio justo", "cooperativismo"],
        "availability": "5 h semanales",
        "modality": "presencial",
        "participation_goal": "profesionalizar la trazabilidad",
        "commitment_level": "medio",
    },
    # --- Dominio: salud comunitaria ---
    {
        "email": "ej.paula.roldan@rizoma.local",
        "name": "Paula Roldan",
        "institution": "Hospital El Cruce",
        "role": "teacher",
        "bio": "Medica generalista con formacion en epidemiologia. Hice relevamientos "
               "casa por casa en barrios sin cloacas y aprendi que el dato mas dificil "
               "no es el que falta sino el que esta mal cargado. Vivo peleando con "
               "planillas inconsistentes y sin nadie que me ayude a ordenarlas.",
        "can_offer": ["epidemiologia de campo", "entrevistas en profundidad", "promocion de salud barrial"],
        "wants_to_learn": ["limpieza de datasets", "tableros interactivos"],
        "interests": ["determinantes sociales de la salud", "salud publica", "huertas periurbanas"],
        "availability": "4 h semanales",
        "modality": "hibrida",
        "participation_goal": "ordenar datos de relevamientos",
        "commitment_level": "medio",
    },
    {
        "email": "ej.nestor.aguirre@rizoma.local",
        "name": "Nestor Aguirre",
        "institution": "Centro de Salud N 12",
        "role": "student",
        "bio": "Enfermero y estudiante de la licenciatura. Estoy en la primera linea de "
               "un centro de salud barrial y me toca contener situaciones para las que "
               "nadie te forma. Quiero pasar de la intuicion al metodo y poder escribir "
               "lo que hacemos de un modo que sirva para pedir recursos.",
        "can_offer": ["enfermeria comunitaria", "primeros auxilios psicologicos"],
        "wants_to_learn": ["epidemiologia de campo", "escritura de informes publicos"],
        "interests": ["determinantes sociales de la salud", "salud publica", "formacion de promotores"],
        "availability": "6 h semanales",
        "modality": "presencial",
        "participation_goal": "formalizar la practica",
        "commitment_level": "alto",
    },
    # --- Dominio: economia social y cooperativismo ---
    {
        "email": "ej.sofia.iglesias@rizoma.local",
        "name": "Sofia Iglesias",
        "institution": "Federacion de Cooperativas de Trabajo",
        "role": "org",
        "bio": "Administro cooperativas hace doce anios y armo balances sociales, que es "
               "la parte que nadie quiere hacer y la unica que despues te permite "
               "demostrar algo. Me interesa entender como las herramientas de IA podrian "
               "ayudarnos a encontrar complementariedades entre cooperativas.",
        "can_offer": ["economia social y solidaria", "administracion de cooperativas", "balance social"],
        "wants_to_learn": ["modelado de embeddings", "trazabilidad con codigos QR"],
        "interests": ["cooperativismo", "comercio justo", "autogestion"],
        "availability": "6 h semanales",
        "modality": "hibrida",
        "participation_goal": "vincular cooperativas entre si",
        "commitment_level": "alto",
    },
    {
        "email": "ej.julian.ferreyra@rizoma.local",
        "name": "Julian Ferreyra",
        "institution": "Universidad Nacional de Quilmes",
        "role": "teacher",
        "bio": "Trabajador social. Coordino asambleas y talleres donde suele haber mas "
               "conflicto que acuerdo, y ese es el trabajo. Me interesa el cruce entre "
               "organizacion comunitaria y salud: son la misma conversacion con dos "
               "vocabularios distintos.",
        "can_offer": ["facilitacion de talleres comunitarios", "mediacion de conflictos"],
        "wants_to_learn": ["administracion de cooperativas", "epidemiologia de campo"],
        "interests": ["autogestion", "organizacion comunitaria", "formacion de promotores"],
        "availability": "8 h semanales",
        "modality": "presencial",
        "participation_goal": "articular salud y organizacion",
        "commitment_level": "alto",
    },
    # --- Dominio: comunicacion y narrativa ---
    {
        "email": "ej.carla.bentivegna@rizoma.local",
        "name": "Carla Bentivegna",
        "institution": "Universidad Nacional de Quilmes",
        "role": "student",
        "bio": "Comunicadora. Produzco un podcast sobre experiencias barriales y escribo "
               "los informes que despues se presentan en el municipio. Se contar una "
               "historia; lo que no se es leer la trama de relaciones que hay detras de "
               "las historias que cuento.",
        "can_offer": ["escritura de informes publicos", "produccion de podcast", "guion documental"],
        "wants_to_learn": ["analisis de redes sociales", "promocion de salud barrial"],
        "interests": ["comunicacion publica", "narrativas territoriales", "organizacion comunitaria"],
        "availability": "5 h semanales",
        "modality": "hibrida",
        "participation_goal": "dar visibilidad a proyectos",
        "commitment_level": "medio",
    },
    {
        "email": "ej.diego.sarli@rizoma.local",
        "name": "Diego Sarli",
        "institution": "Cooperativa Audiovisual Sur",
        "role": "org",
        "bio": "Fotografo documental. Tengo un archivo de veinte anios de imagenes de "
               "organizaciones del conurbano sur, en cajas y discos que nadie catalogo. "
               "Quiero aprender a estructurar ese archivo y meterme en produccion "
               "audiovisual mas larga.",
        "can_offer": ["fotografia documental", "archivo audiovisual"],
        "wants_to_learn": ["guion documental", "compostaje comunitario"],
        "interests": ["narrativas territoriales", "memoria colectiva", "comunicacion publica"],
        "availability": "4 h semanales",
        "modality": "presencial",
        "participation_goal": "poner en valor el archivo",
        "commitment_level": "bajo",
    },
    # --- Puentes: cosen dominios distantes ---
    {
        "email": "ej.ana.kuperman@rizoma.local",
        "name": "Ana Kuperman",
        "institution": "Universidad Nacional de Quilmes",
        "role": "teacher",
        "bio": "Bioestadistica. Mi trabajo es exactamente el puente entre el equipo de "
               "salud que releva y el equipo tecnico que modela: traduzco preguntas "
               "clinicas a consultas y devuelvo tableros que un residente pueda leer sin "
               "capacitacion previa. Ahora me toca coordinar equipos y ahi si estoy floja.",
        "can_offer": ["epidemiologia de campo", "PostgreSQL", "tableros interactivos"],
        "wants_to_learn": ["mediacion de conflictos", "certificacion participativa"],
        "interests": ["salud publica", "infraestructura de datos", "determinantes sociales de la salud"],
        "availability": "10 h semanales",
        "modality": "hibrida",
        "participation_goal": "coordinar equipos mixtos",
        "commitment_level": "alto",
    },
    {
        "email": "ej.marcos.villalba@rizoma.local",
        "name": "Marcos Villalba",
        "institution": "Cooperativa La Yunta",
        "role": "org",
        "bio": "Empece cargando cajones en la feria y termine administrando la "
               "cooperativa y produciendo el programa de radio con el que nos damos a "
               "conocer. Toco muchas teclas y ninguna a fondo. Me interesa entender que "
               "puede hacer la IA con la informacion que ya generamos sin darnos cuenta.",
        "can_offer": ["administracion de cooperativas", "logistica de ferias francas", "produccion de podcast"],
        "wants_to_learn": ["modelado de embeddings", "enfermeria comunitaria"],
        "interests": ["cooperativismo", "narrativas territoriales", "soberania alimentaria"],
        "availability": "7 h semanales",
        "modality": "presencial",
        "participation_goal": "articular la cooperativa con la universidad",
        "commitment_level": "medio",
    },
]


def main() -> int:
    db = SessionLocal()
    try:
        creados = actualizados = 0
        for datos in PERFILES:
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
            user.profile_completeness = 90

            update_user_embedding(user, db)
            db.commit()
            print(f"  {user.name}: listo")

        print(f"\ncreados={creados}  actualizados={actualizados}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
