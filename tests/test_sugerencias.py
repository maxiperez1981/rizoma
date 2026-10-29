"""Tests del orden estructural de las sugerencias y de los conjuntos de perfiles.

No tocan la base ni llaman a modelos: arman el grafo a mano.
"""
import uuid

import pytest

from services import conjunto_service, sugerencias_service as ss
from tests.test_rizoma import construir

# Red chica: A comparte "raro" con B y "comun" con C, D, E; F esta a dos saltos
# de A via B (tema "puente"); G no tiene temas (solo afin por similitud).
ARISTAS = [
    ("A", "raro", "offers"), ("B", "raro", "wants"),
    ("A", "comun", "interest"), ("C", "comun", "interest"), ("D", "comun", "interest"), ("E", "comun", "interest"),
    ("B", "puente", "offers"), ("F", "puente", "wants"),
    ("C", "otro", "offers"), ("H", "otro", "wants"),
]
AREAS = {"A": 0, "B": 0, "C": 1, "D": 1, "E": 1, "F": 2, "H": 3}


def red():
    g = construir(ARISTAS)
    g.nombres["G"] = "G"
    return g


def test_directos_e_indirectos_se_clasifican_bien():
    est = ss.estructuras(red(), "A", ["B", "C", "F", "G"], AREAS)
    assert est["B"].distancia == 2 and est["B"].compartidos == {"raro"}
    assert est["F"].distancia == 4 and est["F"].caminos == [("raro", "B", "puente")]
    assert est["G"].distancia == 0


def test_rareza_ordena_cada_bloque_y_deja_al_final_al_que_no_tiene_camino():
    g = red()
    est = ss.estructuras(g, "A", ["C", "B", "H", "F", "G"], AREAS)
    # bloque "comun": B (tema raro) antes que C (tema popular); bloque "puente": F antes que H
    assert ss.ordenar(est, g.nombres, "rareza") == ["B", "C", "F", "H", "G"]
    assert [ss.bloque(est[v]) for v in ("B", "F", "G")] == ["comun", "puente", "otros"]


def test_cruces_cuenta_areas_y_temas_de_los_caminos_mas_cortos():
    est = ss.estructuras(red(), "A", ["B", "F", "H"], AREAS)
    assert (est["B"].areas, est["B"].temas_puente) == (1, 1)
    assert (est["F"].areas, est["F"].temas_puente) == (2, 2)
    assert (est["H"].areas, est["H"].temas_puente) == (3, 2)  # A -comun- C -otro- H
    assert ss.ordenar(est, {}, "cruces") == ["B", "H", "F"]   # H cruza mas areas que F dentro de su bloque


def test_azar_mezcla_dentro_de_cada_bloque():
    g = red()
    est = ss.estructuras(g, "A", ["B", "C", "D", "E", "F", "H", "G"], AREAS)
    for semilla in range(1, 20):
        orden = ss.ordenar(est, g.nombres, "azar", semilla)
        assert [ss.bloque(est[v]) for v in orden] == ["comun"] * 4 + ["puente"] * 2 + ["otros"]


def test_azar_es_reproducible_con_la_misma_semilla():
    g = red()
    est = ss.estructuras(g, "A", ["B", "C", "D", "E", "F", "H"], AREAS)
    a = ss.ordenar(est, g.nombres, "azar", 1234)
    assert a == ss.ordenar(est, g.nombres, "azar", 1234)
    assert sorted(a) == sorted(["B", "C", "D", "E", "F", "H"])


def test_ningun_candidato_se_pierde_en_ningun_orden():
    g = red()
    candidatos = ["B", "C", "D", "E", "F", "G", "H"]
    est = ss.estructuras(g, "A", candidatos, AREAS)
    for orden in ss.ORDENES:
        assert sorted(ss.ordenar(est, g.nombres, orden, 7)) == sorted(candidatos)


def test_orden_desconocido_falla():
    with pytest.raises(ValueError):
        ss.ordenar({}, {}, "puntaje_del_modelo")


def test_el_dato_estructural_dice_cuantos_perfiles_declaran_cada_tema():
    g = red()
    est = ss.estructuras(g, "A", ["B", "F", "G"], AREAS)
    n = len(g.nombres)
    assert ss.dato_estructural(g, est["B"], "rareza") == f"Tema en común: raro (2 de {n} perfiles)"
    assert ss.dato_estructural(g, est["F"], "rareza") == \
        f"2 temas puente: raro (2 de {n} perfiles) y puente (2 de {n} perfiles) · vía B"
    assert ss.dato_estructural(g, est["F"], "cruces") == "Conecta 2 áreas a través de 2 temas puente"
    un_area = ss.estructuras(g, "A", ["F"], {"A": 0, "B": 0, "F": 0})["F"]
    assert ss.dato_estructural(g, un_area, "cruces") == "Conecta 1 área a través de 2 temas puente"
    assert ss.dato_estructural(g, est["F"], "azar", 99) == "Posición al azar · semilla 99"
    assert "Sin camino en el grafo" in ss.dato_estructural(g, est["G"], "rareza")


def test_recortar_deja_solo_al_conjunto():
    g = ss.recortar(red(), {"A", "B", "F"})
    assert set(g.temas_por_persona) == {"A", "B", "F"}
    assert g.personas_por_tema["comun"] == {"A"}


@pytest.mark.parametrize("email,conjunto", [
    ("demo.unq.07@rizoma.local", "prueba"),
    ("demo.vivo.carla@rizoma.local", "demostracion"),
    ("DEMO.VIVO.x@rizoma.local", "demostracion"),
    ("ej.ana.kuperman@rizoma.local", "general"),
    ("alguien@unq.edu.ar", "general"),
])
def test_conjunto_por_email(email, conjunto):
    assert conjunto_service.conjunto_de_email(email) == conjunto


def test_las_areas_no_dependen_del_orden_de_carga():
    from services import rizoma_service

    aristas = [(f"p{i}", f"t{(i * 7 + k) % 23}", "interest") for i in range(30) for k in range(4)]
    g = construir(aristas)
    for semilla in range(1, 6):
        base = rizoma_service.comunidades_personas(g, semilla)
        for orden in range(1, 6):
            assert rizoma_service.comunidades_personas(conjunto_service.reordenar(g, orden), semilla) == base


def test_el_orden_de_carga_guardado_se_respeta():
    p1, p2, t1, t2 = (str(uuid.UUID(int=i)) for i in (1, 2, 3, 4))
    datos = {
        "personas": [{"id": p1, "name": "Uno"}, {"id": p2, "name": "Dos"}],
        "temas": [{"id": t1, "label": "x"}, {"id": t2, "label": "y"}],
        "vinculos": [{"user_id": p1, "topic_id": t1, "relation": "offers"},
                     {"user_id": p2, "topic_id": t2, "relation": "wants"},
                     {"user_id": p2, "topic_id": t1, "relation": "wants"}],
        "fusiones_de_temas": [],
        "orden_de_carga": {"sin_unificar": {"personas": [p2, p1], "temas": [t2, t1]}},
    }
    g = conjunto_service.grafo_desde_archivo(datos)
    assert [str(p) for p in g.temas_por_persona] == [p2, p1]
    assert [str(t) for t in g.personas_por_tema] == [t2, t1]
