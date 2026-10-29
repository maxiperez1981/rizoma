"""Tests de la logica del rizoma.

No tocan la base: arman el grafo a mano y ejercitan la parte pura. Lo que se
prueba es el criterio de recomendacion, que es donde vive la decision de
producto y donde una regresion pasaria inadvertida.
"""
from collections import defaultdict

import pytest

from services.rizoma_service import (
    Grafo,
    caminos_desde,
    contexto_rizoma_con_mapa,
    rareza,
    slugify,
)


def construir(aristas, nombres=None, etiquetas=None):
    """aristas: lista de (persona, tema, relacion)."""
    personas_por_tema = defaultdict(set)
    temas_por_persona = defaultdict(set)
    relacion_de = {}
    for persona, tema, relacion in aristas:
        personas_por_tema[tema].add(persona)
        temas_por_persona[persona].add(tema)
        relacion_de.setdefault((persona, tema), set()).add(relacion)
    personas = {p for p, _, _ in aristas}
    temas = {t for _, t, _ in aristas}
    return Grafo(
        personas_por_tema,
        temas_por_persona,
        nombres or {p: p for p in personas},
        etiquetas or {t: t for t in temas},
        relacion_de,
    )


# --------------------------- normalizacion ---------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("PostgreSQL", "postgresql"),
    ("  Economía   Social  ", "economia social"),
    ("Agroecología Urbana", "agroecologia urbana"),
    ("visualización\tde datos", "visualizacion de datos"),
])
def test_slugify_normaliza(entrada, esperado):
    assert slugify(entrada) == esperado


def test_slugify_unifica_variantes_de_acento_y_espacio():
    assert slugify("Economía Social") == slugify("economia  social")


# ------------------------------ rareza -------------------------------

def test_rareza_penaliza_temas_populares():
    personas_por_tema = {"popular": {1, 2, 3, 4, 5}, "raro": {1, 2}}
    peso = rareza(personas_por_tema, total_personas=10)
    assert peso["raro"] > peso["popular"]


def test_rareza_es_cero_si_lo_tiene_todo_el_mundo():
    peso = rareza({"todos": set(range(10))}, total_personas=10)
    assert peso["todos"] == pytest.approx(0.0)


# ------------------------------ caminos ------------------------------

def test_no_sugiere_a_quien_ya_comparte_un_tema():
    """Si A y B comparten tema, B es un vinculo directo: no debe aparecer aca."""
    g = construir([
        ("A", "t1", "wants"),
        ("B", "t1", "offers"),
        ("B", "t2", "offers"),
        ("C", "t2", "wants"),
    ])
    destinos = [c["persona_id"] for c in caminos_desde(g, "A")]
    assert "B" not in destinos
    assert "C" in destinos


def test_no_sugiere_al_propio_usuario():
    g = construir([("A", "t1", "offers"), ("B", "t1", "wants"), ("B", "t2", "offers"),
                   ("C", "t2", "wants")])
    assert "A" not in [c["persona_id"] for c in caminos_desde(g, "A")]


def test_sin_segundo_orden_no_hay_caminos():
    g = construir([("A", "t1", "offers"), ("B", "t1", "wants")])
    assert caminos_desde(g, "A") == []


def test_prefiere_el_camino_por_temas_raros():
    """Dos destinos alcanzables; gana el que pasa por el tema menos compartido."""
    aristas = [("A", "puente", "offers"), ("M", "puente", "wants")]
    # tema popular: lo tocan cuatro personas ademas del destino
    aristas += [("M", "popular", "offers")]
    aristas += [(f"R{i}", "popular", "wants") for i in range(4)]
    aristas += [("destino_popular", "popular", "wants")]
    # tema raro: solo el intermediario y el destino
    aristas += [("M", "raro", "offers"), ("destino_raro", "raro", "wants")]
    g = construir(aristas)

    orden = [c["persona_id"] for c in caminos_desde(g, "A")]
    assert orden.index("destino_raro") < orden.index("destino_popular")


def test_penaliza_al_intermediario_muy_conectado():
    """Mismo tema puente y mismo destino, pero un intermediario toca todo."""
    comun = [("A", "t1", "offers"), ("A", "t2", "offers")]
    # M1 es especifico: solo t1 y el tema puente
    v1 = [("M1", "t1", "wants"), ("M1", "pa", "offers"), ("D1", "pa", "wants")]
    # M2 toca t2 y ademas ocho temas mas: es un hub
    v2 = [("M2", "t2", "wants"), ("M2", "pb", "offers"), ("D2", "pb", "wants")]
    v2 += [("M2", f"extra{i}", "interest") for i in range(8)]
    g = construir(comun + v1 + v2)

    puntajes = {c["persona_id"]: c["score"] for c in caminos_desde(g, "A")}
    assert puntajes["D1"] > puntajes["D2"]


def test_respeta_el_limite():
    aristas = [("A", "t1", "offers"), ("M", "t1", "wants")]
    for i in range(10):
        aristas += [("M", f"p{i}", "offers"), (f"D{i}", f"p{i}", "wants")]
    g = construir(aristas)
    assert len(caminos_desde(g, "A", limite=3)) == 3


def test_el_camino_tiene_la_forma_esperada():
    g = construir([("A", "t1", "wants"), ("M", "t1", "offers"),
                   ("M", "t2", "wants"), ("D", "t2", "offers")],
                  nombres={"A": "Ana", "M": "Marta", "D": "Diego"},
                  etiquetas={"t1": "grafos", "t2": "compostaje"})
    (c,) = caminos_desde(g, "A")
    tipos = [paso["tipo"] for paso in c["camino"]]
    assert tipos == ["persona", "tema", "persona", "tema", "persona"]
    assert [paso["label"] for paso in c["camino"]] == [
        "Ana", "grafos", "Marta", "compostaje", "Diego"]
    assert c["intermedio_id"] == "M"
    assert c["tema_puente_id"] == "t2"


def test_el_orden_es_estable_ante_empates():
    """Dos caminos identicos en puntaje no pueden alternar entre llamadas."""
    g = construir([("A", "t1", "offers"), ("M", "t1", "wants"),
                   ("M", "pa", "offers"), ("D1", "pa", "wants"),
                   ("M", "pb", "offers"), ("D2", "pb", "wants")])
    primero = [c["persona_id"] for c in caminos_desde(g, "A")]
    for _ in range(5):
        assert [c["persona_id"] for c in caminos_desde(g, "A")] == primero


# ---------------------- contexto para el modelo ----------------------

def test_el_contexto_no_filtra_nombres_reales():
    """Al modelo se le manda la estructura, no las identidades."""
    g = construir([("A", "t1", "wants"), ("M", "t1", "offers"),
                   ("M", "t2", "wants"), ("D", "t2", "offers")],
                  nombres={"A": "Ana Kuperman", "M": "Marta Diaz", "D": "Diego Sarli"},
                  etiquetas={"t1": "grafos", "t2": "compostaje"})

    class UsuarioFalso:
        id = "A"
        name = "Ana Kuperman"

    texto, mapa = contexto_rizoma_con_mapa(None, UsuarioFalso(), grafo=g)

    assert "Marta Diaz" not in texto
    assert "Diego Sarli" not in texto
    assert "Ana Kuperman" not in texto
    # los temas si viajan: son lo que le da sentido al camino
    assert "grafos" in texto and "compostaje" in texto
    # y el mapa permite devolver los nombres al mostrar el resultado
    assert set(mapa.values()) >= {"Marta Diaz", "Diego Sarli"}


def test_contexto_vacio_si_no_hay_caminos():
    g = construir([("A", "t1", "offers"), ("B", "t1", "wants")])

    class UsuarioFalso:
        id = "A"
        name = "Ana"

    texto, mapa = contexto_rizoma_con_mapa(None, UsuarioFalso(), grafo=g)
    assert texto == ""
    assert mapa == {}
