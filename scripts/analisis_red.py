"""Metricas de la red para la ponencia, reproducibles.

Uso (desde /home/alma-academica):
  PYTHONPATH=. python3 scripts/analisis_red.py --prefijo demo.unq.
  PYTHONPATH=. python3 scripts/analisis_red.py --desde-archivo conjunto_prueba_ponencia/<archivo>.json

Solo lee la base (o un conjunto exportado con scripts/exportar_conjunto.py).
Calcula: estructura de la red, alcance por saltos, comparacion contra la
seleccion por similitud (embeddings), estabilidad de las actividades emergentes
frente a la semilla del algoritmo de areas, y las actividades, la demanda
latente y los puentes (Tablas 2 a 4 de la ponencia). La triangulacion de
modelos (Tabla 5) usa scripts/triangulacion.py, que llama a modelos de lenguaje
y puede variar entre corridas.
"""
import argparse
import collections
import importlib.util
import itertools
import math
import statistics

from sqlalchemy import text

from database import SessionLocal
from services import conjunto_service
from services import rizoma_service as rs

spec = importlib.util.spec_from_file_location("gen", "scripts/generar_actividades_emergentes.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def estructura(g):
    n = len(g.temas_por_persona)
    temas = g.personas_por_tema
    aristas = sum(len(v) for v in g.temas_por_persona.values())
    comp = sum(1 for p in temas.values() if len(p) >= 2)
    print(f"personas={n} temas={len(temas)} aristas={aristas} temas/persona={aristas / n:.1f}")
    print(f"temas compartidos (>=2 personas)={comp} ({100 * comp / len(temas):.1f}%), de una sola persona={len(temas) - comp} ({100 * (len(temas) - comp) / len(temas):.1f}%)")
    adj = {p: set() for p in g.temas_por_persona}
    for ps in temas.values():
        for a in ps:
            adj[a] |= ps - {a}
    dist = collections.Counter()
    for s in adj:
        vistos, frontera = {s: 0}, [s]
        while frontera:
            nuevo = []
            for a in frontera:
                for b in adj[a]:
                    if b not in vistos:
                        vistos[b] = vistos[a] + 1
                        nuevo.append(b)
            frontera = nuevo
        dist.update(d for b, d in vistos.items() if b != s)
    pares, acum = n * (n - 1), 0
    for d in sorted(dist):
        acum += dist[d]
        print(f"  a {d} saltos: {100 * dist[d] / pares:.1f}% de los pares (acumulado {100 * acum / pares:.1f}%)")


def embeddings_de_base(db, prefijo):
    return {r[0]: [float(x) for x in r[1].strip("[]").split(",")] for r in db.execute(
        text("select id, embedding::text from users where email like :p and embedding is not null"),
        {"p": prefijo + "%"}).fetchall()}


def comparacion(emb, g):
    peso = rs.rareza(g.personas_por_tema, len(g.nombres) or 1)
    r = collections.defaultdict(list)
    for u in g.temas_por_persona:
        sim = sorted(((cos(emb[u], emb[o]), o) for o in emb if o != u), reverse=True)
        top5, top10 = [o for _, o in sim[:5]], [o for _, o in sim[:10]]
        rango = {o: i + 1 for i, (_, o) in enumerate(sim)}
        cam = rs.caminos_desde(g, u, limite=1000)
        if not cam:
            continue
        dest = [c["persona_id"] for c in cam[:5]]
        rare = lambda c: (peso[c["tema_origen_id"]] + peso[c["tema_puente_id"]]) / 2
        r["candidatos"].append(len(cam))
        r["coincide5"].append(len(set(dest) & set(top5)) / len(dest))
        r["coincide10"].append(len(set(dest) & set(top10)) / len(dest))
        r["posicion"].append(statistics.mean(rango[d] for d in dest))
        r["rareza_top5"].append(statistics.mean(rare(c) for c in cam[:5]))
        r["rareza_todos"].append(statistics.mean(rare(c) for c in cam))
        r["sim_comparte"].append(sum(1 for o in top5 if g.temas_por_persona[u] & g.temas_por_persona[o]) / 5)
    m = {k: statistics.mean(v) for k, v in r.items()}
    print(f"candidatos indirectos por persona: media {m['candidatos']:.1f} (min {min(r['candidatos'])}, max {max(r['candidatos'])})")
    print(f"coincidencia indirectos top5 vs similitud top5: {100 * m['coincide5']:.1f}%; vs top10: {100 * m['coincide10']:.1f}%")
    print(f"posicion media de los indirectos en el ranking por similitud: {m['posicion']:.1f} de {len(emb) - 1}")
    print(f"rareza media del camino: top5 {m['rareza_top5']:.2f} vs todos {m['rareza_todos']:.2f}")
    print(f"los 5 mas similares comparten al menos un tema: {100 * m['sim_comparte']:.1f}%")


def estabilidad(g, corridas=30):
    clave = lambda r: frozenset(t["label"] for t in r["temas"])
    base = rs.actividades_emergentes_consenso(g)
    base_k = [clave(r) for r in base]
    n_areas, solapa, presencia = [], [], collections.Counter()
    for semilla in range(1, corridas + 1):
        n_areas.append(len(set(rs.comunidades_personas(g, semilla).values())))
        ks = {clave(r) for r in rs.actividades_emergentes(g, seed=semilla)}
        solapa.append(len(ks & set(base_k)) / len(base_k))
        presencia.update(ks & set(base_k))
    print(f"areas por semilla: {min(n_areas)}-{max(n_areas)} (mediana {statistics.median(n_areas)}), {corridas} semillas")
    print(f"solapamiento medio de una corrida simple con el consenso: {100 * statistics.mean(solapa):.0f}% (min {100 * min(solapa):.0f}%)")
    for r in base:
        k = clave(r)
        print(f"  {' + '.join(sorted(k))}: estabilidad en el sistema {r['estabilidad']:.2f}; aparece en {presencia[k]}/{corridas} semillas sueltas")


def hallazgos(g):
    """Actividades (consenso), demanda latente y puentes: sin base de escritura ni modelo de lenguaje."""
    print("actividades emergentes (consenso de 12 semillas):")
    for r in rs.actividades_emergentes_consenso(g):
        print(f"  {' + '.join(t['label'] for t in r['temas'])} | personas={r['n_personas']} demanda={r['demanda']} oferta={r['oferta']} estabilidad={r['estabilidad']:.2f}")
        print(f"    areas: {r['areas'][0]}  <>  {r['areas'][1]}")
    print("demanda formativa latente:")
    for r in rs.demanda_latente(g):
        print(f"  {r['tema']['label']} | quieren={r['demanda']} ofrecen={r['oferta']} areas={r['n_areas']}")
    pu = rs.puentes_estructurales(g)
    print(f"puentes estructurales (alcance base a {pu['saltos']} saltos: {100 * pu['alcance_base']:.1f}%):")
    for t in pu["temas"]:
        print(f"  tema {t['tema']} | perdida={100 * t['perdida_alcance']:.1f}% personas={t['personas']} areas={t['n_areas']}")
    for i, p in enumerate(pu["personas"], start=1):
        print(f"  persona {i} | perdida={100 * p['perdida_alcance']:.1f}% articulacion={p['punto_de_articulacion']} areas_que_conecta={len(p['areas_que_conecta'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefijo", default="demo.unq.")
    ap.add_argument("--corridas", type=int, default=30)
    ap.add_argument("--unificar", action="store_true", help="aplica la fusion semantica de temas")
    ap.add_argument("--desde-archivo", help="conjunto exportado; si se indica, no se lee la base")
    a = ap.parse_args()
    if a.desde_archivo:
        datos = conjunto_service.leer(a.desde_archivo)
        g = conjunto_service.grafo_desde_archivo(datos, a.unificar)
        emb = conjunto_service.embeddings_desde_archivo(datos)
    else:
        db = SessionLocal()
        try:
            g = gen.recortar(db, a.prefijo, a.unificar)
            emb = embeddings_de_base(db, a.prefijo)
        finally:
            db.close()
    print(f"(fusion semantica de temas: {'si' if a.unificar else 'no'})")
    print("== Estructura ==")
    estructura(g)
    print("\n== Comparacion con similitud semantica ==")
    comparacion(emb, g)
    print("\n== Estabilidad de las actividades emergentes ==")
    estabilidad(g, a.corridas)
    print("\n== Actividades, demanda latente y puentes ==")
    hallazgos(g)


if __name__ == "__main__":
    main()
