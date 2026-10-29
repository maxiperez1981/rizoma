"""Recalcula la triangulacion de la Tabla 5 con umbrales fijos sobre los puntajes guardados.
Umbrales fijados antes de ver resultados: 30 (actual), 50 y 70 para los modelos; heuristica solo en 30.
No llama a modelos ni escribe en la base: lee el informe guardado de la corrida.
Uso: python3 scripts/umbrales_triangulacion.py [ruta/al/informe.json]"""
import itertools, json, os, sys
UMBRALES = (30, 50, 70)
MODELOS = ("gpt-4o-mini", "gpt-4.1", "o4-mini")
TIPOS = ("similitud", "indirecto", "control")
RUTA = sys.argv[1] if len(sys.argv) > 1 else "reports/triangulacion_20261002_1420.json"
rep = json.load(open(RUTA, encoding="utf-8"))
items = rep["items"]

def kappa(x, y):  # copiado de services/triangulacion_service.py
    n = len(x)
    if n == 0:
        return float("nan")
    po = sum(a == b for a, b in zip(x, y)) / n
    px, py = sum(x) / n, sum(y) / n
    pe = px * py + (1 - px) * (1 - py)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)

def auc(pos, neg):
    return sum(1 if a > b else 0.5 if a == b else 0 for a in pos for b in neg) / (len(pos) * len(neg))

def voto(i, v, u):
    s = i["scores"][v]
    return None if s is None else s >= u

def tasas(v, u):
    out = {}
    for t in TIPOS:
        vals = [voto(i, v, u) for i in items if i["tipo"] == t]
        vals = [x for x in vals if x is not None]
        out[t] = (sum(vals) / len(vals), sum(vals), len(vals))
    return out

def aucs(v):
    g = lambda t: [i["scores"][v] for i in items if i["tipo"] == t and i["scores"][v] is not None]
    return {"ind": (auc(g("indirecto"), g("control")), len(g("indirecto")), len(g("control"))),
            "sim": (auc(g("similitud"), g("control")), len(g("similitud")), len(g("control")))}

def kappas(u, votantes):
    out = {}
    for a, b in itertools.combinations(votantes, 2):
        ua = 30 if a == "heuristica" else u
        ub = 30 if b == "heuristica" else u
        par = [(voto(i, a, ua), voto(i, b, ub)) for i in items]
        par = [p for p in par if None not in p]
        xs, ys = [p[0] for p in par], [p[1] for p in par]
        out[(a, b)] = (kappa(xs, ys), sum(p == q for p, q in par) / len(par), len(par))
    return out

# ---- Control 1: el umbral 30 reproduce la corrida publicada
errores = []
for i in items:
    for v in MODELOS + ("heuristica",):
        if i["votos"][v] is not None and voto(i, v, 30) != i["votos"][v]:
            errores.append((i["a"], i["b"], v))
pub = rep["resumen"]
for v in MODELOS + ("heuristica",):
    for t in TIPOS:
        mio, ref = round(tasas(v, 30)[t][0], 3), pub["tasa_de_si_por_tipo"][t][v]
        if mio != ref: errores.append(("tasa", v, t, mio, ref))
for (a, b), (k, ac, n) in kappas(30, MODELOS + ("heuristica",)).items():
    key = f"{a} / {b}" if f"{a} / {b}" in pub["acuerdo_entre_votantes"] else f"{b} / {a}"
    ref = pub["acuerdo_entre_votantes"][key]
    if (round(k, 3), round(ac, 3), n) != (ref["kappa"], ref["acuerdo"], ref["n"]):
        errores.append(("kappa", key, round(k, 3), ref))
tabla5_auc = {"gpt-4o-mini": (0.56, 0.92), "gpt-4.1": (0.58, 0.97), "o4-mini": (0.59, 0.88), "heuristica": (0.54, 0.99)}
for v, (ai, asim) in tabla5_auc.items():
    a = aucs(v)
    if (round(a["ind"][0], 2), round(a["sim"][0], 2)) != (ai, asim): errores.append(("auc", v, a))
print("CONTROL 1 (umbral 30 = Tabla 5):", "OK, coincide todo" if not errores else errores)
if errores: sys.exit(1)

# ---- Resultados
json.dump({"umbrales": UMBRALES,
           "tasas": {f"{v}@{u}": tasas(v, u) for v in MODELOS for u in UMBRALES} | {"heuristica@30": tasas("heuristica", 30)},
           "auc": {v: aucs(v) for v in MODELOS + ("heuristica",)},
           "kappa": {f"{u}": {f"{a} / {b}": r for (a, b), r in kappas(u, MODELOS).items()} for u in UMBRALES}},
          open(os.path.join(os.path.dirname(RUTA) or ".", "resultados_umbrales.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for u in UMBRALES:
    print(f"\n== umbral {u}")
    for v in MODELOS:
        t = tasas(v, u); a = aucs(v)
        print(f"{v:12} " + "  ".join(f"{k}={r[0]*100:5.1f}% ({r[1]}/{r[2]})" for k, r in t.items())
              + f"  AUCind={a['ind'][0]:.2f} AUCsim={a['sim'][0]:.2f}")
    for (a, b), (k, ac, n) in kappas(u, MODELOS).items():
        print(f"   kappa {a} / {b}: {k:.3f}  acuerdo {ac*100:.1f}%  n={n}")
t = tasas("heuristica", 30); a = aucs("heuristica")
print("\nheuristica@30 " + "  ".join(f"{k}={r[0]*100:5.1f}% ({r[1]}/{r[2]})" for k, r in t.items()) + f"  AUCind={a['ind'][0]:.2f} AUCsim={a['sim'][0]:.2f}")
print("n de AUC o4-mini:", aucs("o4-mini"))
