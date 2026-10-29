"""Tests de la deteccion de actividades emergentes (parte pura, sin base)."""
from collections import defaultdict

from services.rizoma_service import Grafo, actividades_emergentes


def construir(aristas):
    ppt, tpp, rel = defaultdict(set), defaultdict(set), {}
    for persona, tema, relacion in aristas:
        ppt[tema].add(persona)
        tpp[persona].add(tema)
        rel.setdefault((persona, tema), set()).add(relacion)
    personas = {p for p, _, _ in aristas}
    temas = {t for _, t, _ in aristas}
    return Grafo(ppt, tpp, {p: p for p in personas}, {t: t for t in temas}, rel)


def dos_areas(extra=()):
    """Area salud (s1..s6) y area datos (d1..d6), sin puentes entre ellas."""
    base = []
    for p in ("s1", "s2", "s3", "s4", "s5", "s6"):
        base += [(p, "cuidado", "offers"), (p, "salud", "interest")]
    for p in ("d1", "d2", "d3", "d4", "d5", "d6"):
        base += [(p, "grafos", "offers"), (p, "datos", "interest")]
    return construir(base + list(extra))


def pares(res):
    return {frozenset(t["label"] for t in r["temas"]) for r in res}


def test_detecta_cruce_con_oferta_y_demanda_cruzadas():
    g = dos_areas([("s1", "grafos", "wants"), ("d1", "cuidado", "wants")])
    res = actividades_emergentes(g)
    assert frozenset({"cuidado", "grafos"}) in pares(res)


def test_sin_demanda_no_hay_actividad():
    assert actividades_emergentes(dos_areas()) == []


def test_si_alguien_ya_aporta_ambos_temas_no_es_emergente():
    g = dos_areas([("s1", "grafos", "wants"), ("d1", "cuidado", "wants"),
                   ("x1", "cuidado", "offers"), ("x1", "grafos", "offers")])
    assert frozenset({"cuidado", "grafos"}) not in pares(actividades_emergentes(g))


def test_querer_aprender_un_tema_no_cuenta_como_consolidado():
    g = dos_areas([("s1", "grafos", "wants"), ("d1", "cuidado", "wants")])
    assert frozenset({"cuidado", "grafos"}) in pares(actividades_emergentes(g))


def test_no_repite_temas_y_respeta_el_limite():
    g = dos_areas([("s1", "grafos", "wants"), ("s2", "datos", "wants"),
                   ("d1", "cuidado", "wants"), ("d2", "salud", "wants")])
    res = actividades_emergentes(g, limite=1)
    assert len(res) == 1
    res = actividades_emergentes(g, limite=10)
    temas = [t["label"] for r in res for t in r["temas"]]
    assert len(temas) == len(set(temas))


def test_es_determinista():
    g = dos_areas([("s1", "grafos", "wants"), ("d1", "cuidado", "wants")])
    assert actividades_emergentes(g) == actividades_emergentes(g)


def test_consenso_informa_estabilidad_y_es_determinista():
    from services.rizoma_service import actividades_emergentes_consenso
    g = dos_areas([("s1", "grafos", "wants"), ("d1", "cuidado", "wants")])
    res = actividades_emergentes_consenso(g, semillas=range(1, 6))
    assert res and all(0.5 <= r["estabilidad"] <= 1.0 for r in res)
    assert res == actividades_emergentes_consenso(g, semillas=range(1, 6))


# ---------------------------------------------------------- demanda latente

def test_demanda_latente_exige_mas_deseo_que_oferta():
    from services.rizoma_service import demanda_latente
    g = construir([
        ("p1", "ia", "wants"), ("p2", "ia", "wants"), ("p3", "ia", "wants"),
        ("p4", "datos", "wants"), ("p5", "datos", "wants"), ("p6", "datos", "offers"), ("p7", "datos", "offers"),
        ("p8", "cocina", "wants"),
    ])
    res = demanda_latente(g)
    assert [r["tema"]["label"] for r in res] == ["ia"]
    assert res[0]["demanda"] == 3 and res[0]["oferta"] == 0


# ------------------------------------------------------------------ equipos

def test_equipo_cubre_ambos_temas_y_no_repite_personas():
    from services.rizoma_service import equipo_para_actividad
    g = dos_areas([("s1", "grafos", "wants"), ("d1", "cuidado", "wants")])
    eq = equipo_para_actividad(g, "cuidado", "grafos")
    ids = [m["persona_id"] for m in eq["miembros"]]
    assert len(ids) == len(set(ids)) and 3 <= len(ids) <= 4
    assert set(eq["temas_cubiertos"]) == {"cuidado", "grafos"} and eq["temas_sin_cubrir"] == []
    assert eq == equipo_para_actividad(g, "cuidado", "grafos")


def test_equipo_informa_lo_que_no_puede_cubrir():
    from services.rizoma_service import equipo_para_actividad
    g = construir([("a1", "x", "offers"), ("a2", "x", "interest"), ("b1", "y", "wants")])
    eq = equipo_para_actividad(g, "x", "y")
    assert "y" in eq["temas_sin_cubrir"]


# --------------------------------------------------------------- simulacion

def test_simulacion_no_modifica_el_grafo_y_reporta_temas_nuevos():
    from services.rizoma_service import simular_persona
    g = dos_areas()
    antes = {t: set(p) for t, p in g.personas_por_tema.items()}
    res = simular_persona(g, {"nombre": "Test", "can_offer": ["cuidado", "tema inedito"],
                              "wants_to_learn": ["grafos"], "interests": []}, semillas=range(1, 4))
    assert {t: set(p) for t, p in g.personas_por_tema.items()} == antes
    assert res["temas_nuevos"] == ["tema inedito"] and "cuidado" in res["temas_vinculados"]
    assert res["conexiones_directas"] >= 6


# ------------------------------------------------------------- triangulacion

def test_kappa_y_resumen():
    from services.triangulacion_service import kappa, resumir
    assert kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert kappa([True, True, False, False], [True, False, True, False]) == 0.0
    items = [{"tipo": "control", "votos": {"gpt": True, "claude": False, "heuristica": False}, "consenso": False, "unanime": False},
             {"tipo": "similitud", "votos": {"gpt": True, "claude": True, "heuristica": True}, "consenso": True, "unanime": True}]
    r = resumir(items)
    assert r["tasa_de_si_por_tipo"]["control"]["gpt"] == 1.0 and r["tasa_de_si_por_tipo"]["control"]["claude"] == 0.0
    assert r["unanimes"] == 0.5


def test_auc_de_evaluacion():
    from services.evaluacion_service import _auc
    assert _auc([5, 4], [1, 2]) == 1.0
    assert _auc([3], [3]) == 0.5
    assert _auc([], [1]) is None


def test_puentes_detecta_a_la_persona_que_une_dos_areas():
    from services.rizoma_service import puentes_estructurales
    base = []
    for p in ("s1", "s2", "s3", "s4"):
        base += [(p, "salud", "interest"), (p, "cuidado", "offers")]
    for p in ("d1", "d2", "d3", "d4"):
        base += [(p, "datos", "interest"), (p, "grafos", "offers")]
    base += [("puente", "salud", "interest"), ("puente", "datos", "interest")]
    res = puentes_estructurales(construir(base), saltos=2)
    top = res["personas"][0]
    assert top["persona_id"] == "puente" and top["punto_de_articulacion"] is True
    assert top["perdida_alcance"] > 0
    assert {t["tema"] for t in res["temas"][:2]} == {"salud", "datos"}


def test_ajuste_de_pesos_recupera_la_senal_y_exige_minimo():
    import numpy as np
    from services.pesos_service import MINIMO_PARES, ajustar
    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, 4))
    y = 3 * X[:, 1] + rng.normal(scale=0.3, size=40)
    r = ajustar(X, y, puntaje_actual=X[:, 0])
    assert r["estado"] == "ok"
    assert r["coeficientes_estandarizados"]["rareza_tema_puente"] > 1.5
    assert r["correlacion_modelo_ajustado_loo"] > 0.9 > abs(r["correlacion_puntaje_actual_vs_calificacion"])
    assert ajustar(X[:5], y[:5], X[:5, 0])["estado"] == "datos_insuficientes"
    assert MINIMO_PARES == 20


def test_limite_de_uso_bloquea_y_se_libera():
    from services.limites import consumir
    k = ("t", "u1")
    assert [consumir(k, 3, 100, ahora=t) for t in (0, 1, 2)] == [0, 0, 0]
    espera = consumir(k, 3, 100, ahora=3)
    assert espera > 0
    assert consumir(("t", "u2"), 3, 100, ahora=3) == 0
    assert consumir(k, 3, 100, ahora=101) == 0
