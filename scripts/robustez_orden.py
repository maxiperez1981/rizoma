"""Robustez de las actividades emergentes frente al orden de carga del grafo.

Louvain depende de la semilla y tambien del orden en que se cargan personas y
temas. La ponencia midio solo la semilla (30 semillas, un unico orden: el de la
base). Aca se combinan 30 ordenes de carga (permutaciones con semilla fija) con
las mismas 30 semillas de Louvain, sobre la red unificada, y se informa:
  - por cada actividad de la Tabla 4, en que porcentaje de las 900 corridas
    sueltas (orden x semilla) aparece entre las 8 principales;
  - en cuantos de los 30 ordenes la reconoce el consenso del sistema (12 semillas);
  - toda otra actividad que aparezca, con su frecuencia (no se descarta ninguna).

Solo lee un conjunto exportado; no usa la base ni modelos.
Uso: PYTHONPATH=. python3 scripts/robustez_orden.py conjunto_prueba_ponencia/<archivo_con_orden>.json [salida.json]
"""
import collections
import json
import os
import sys
from multiprocessing import Pool

from services import conjunto_service as cs
from services import rizoma_service as rs

ORDENES = range(1, 31)
SEMILLAS = range(1, 31)


def clave(r):
    return frozenset(t["label"] for t in r["temas"])


def correr_orden(args):
    ruta, orden = args
    g = cs.reordenar(cs.grafo_desde_archivo(cs.leer(ruta), unificar=True), orden)
    sueltas = [sorted(map(sorted, map(clave, rs.actividades_emergentes(g, seed=s)))) for s in SEMILLAS]
    consenso = sorted(sorted(clave(r)) for r in rs.actividades_emergentes_consenso(g))
    return orden, sueltas, consenso


def main():
    ruta = sys.argv[1]
    g0 = cs.grafo_desde_archivo(cs.leer(ruta), unificar=True)
    tabla4 = [clave(r) for r in rs.actividades_emergentes_consenso(g0)]
    base_sueltas = collections.Counter(k for s in SEMILLAS for k in map(clave, rs.actividades_emergentes(g0, seed=s)))

    with Pool(min(8, os.cpu_count() or 1)) as pool:
        resultados = pool.map(correr_orden, [(ruta, o) for o in ORDENES])

    sueltas, consenso = collections.Counter(), collections.Counter()
    for _, por_semilla, cons in resultados:
        for acts in por_semilla:
            sueltas.update(frozenset(a) for a in acts)
        consenso.update(frozenset(a) for a in cons)
    total, n_ord = len(ORDENES) * len(SEMILLAS), len(ORDENES)

    filas = []
    for k in tabla4:
        filas.append({"actividad": " + ".join(sorted(k)), "en_tabla_4": True,
                      "orden_base_30_semillas": base_sueltas[k] / len(SEMILLAS),
                      "corridas_sueltas_900": sueltas[k] / total, "consenso_30_ordenes": consenso[k] / n_ord})
    for k in sorted(set(sueltas) | set(consenso), key=lambda k: (-sueltas[k], sorted(k))):
        if k in tabla4:
            continue
        filas.append({"actividad": " + ".join(sorted(k)), "en_tabla_4": False,
                      "orden_base_30_semillas": base_sueltas[k] / len(SEMILLAS),
                      "corridas_sueltas_900": sueltas[k] / total, "consenso_30_ordenes": consenso[k] / n_ord})

    salida = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(ruta), "robustez_orden.json")
    if os.path.exists(salida):
        raise SystemExit(f"{salida} ya existe: no se pisa un resultado anterior")
    with open(salida, "w", encoding="utf-8") as f:
        json.dump({"ordenes": list(ORDENES), "semillas": list(SEMILLAS), "red": "unificada", "filas": filas},
                  f, ensure_ascii=False, indent=1)
    print(f"{'actividad':45} {'T4':3} {'base 30 sem':>11} {'900 sueltas':>11} {'consenso 30 ord':>15}")
    for r in filas:
        print(f"{r['actividad'][:45]:45} {'si' if r['en_tabla_4'] else 'no':3} "
              f"{100 * r['orden_base_30_semillas']:10.0f}% {100 * r['corridas_sueltas_900']:10.1f}% "
              f"{100 * r['consenso_30_ordenes']:14.0f}%")
    print("guardado en", salida)


if __name__ == "__main__":
    main()
