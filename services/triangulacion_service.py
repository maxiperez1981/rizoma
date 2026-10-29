"""Triangulacion: varios modelos juzgan la misma sugerencia de complementariedad.

Votantes: un modelo de OpenAI, un modelo de Anthropic y la heuristica local
(solapamiento de terminos). El acuerdo entre votantes y la tasa de "si" frente
a pares de control (al azar) permiten ver si un veredicto discrimina o aprueba
todo.
"""
import itertools
import json
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from config import settings
from services import claude_service

logger = logging.getLogger(__name__)
MODELOS_OPENAI = ("gpt-4o-mini", "gpt-4.1", "o4-mini")


def _voto_openai(modelo):
    def votar(a, b, sim, ctx):
        if not settings.openai_api_key:
            return None
        razonador = modelo.startswith(("o1", "o3", "o4", "gpt-5"))
        payload = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": "Respondé solamente JSON válido, sin markdown ni texto extra."},
                {"role": "user", "content": claude_service._complementarity_prompt(a, b, sim, ctx)},
            ],
            "response_format": {"type": "json_object"},
            # Sin almacenamiento opcional en OpenAI. No activa retención cero ni
            # elimina los registros de seguridad del proveedor.
            "store": False,
        }
        payload["max_completion_tokens" if razonador else "max_tokens"] = 2500 if razonador else 800
        if not razonador:
            payload["temperature"] = 0.2
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions", data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return claude_service._normalize_complementarity(json.loads(data["choices"][0]["message"]["content"].strip()), modelo)
        except Exception as e:
            logger.error("Voto %s fallo: %s", modelo, type(e).__name__)
            return None
    return votar


def _voto_claude(a, b, sim, ctx):
    client = claude_service._anthropic_client()
    if not client:
        return None
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=800,
            messages=[{"role": "user", "content": claude_service._complementarity_prompt(a, b, sim, ctx) + "\nSolo JSON, nada mas."}])
        return claude_service._normalize_complementarity(json.loads(resp.content[0].text.strip()), "claude-sonnet-4-6")
    except Exception as e:
        logger.error("Voto claude fallo: %s", type(e).__name__)
        return None


def _voto_heuristica(a, b, sim, ctx):
    return claude_service._normalize_complementarity(claude_service._local_complementarity(a, b, sim), "local-heuristic")


def votantes() -> dict:
    v = {m: _voto_openai(m) for m in MODELOS_OPENAI}
    if settings.anthropic_api_key:
        v["claude"] = _voto_claude
    v["heuristica"] = _voto_heuristica
    return v


def triangular(person_a: dict, person_b: dict, similitud: float = 0.0, contexto: str = "") -> dict:
    fns = votantes()
    with ThreadPoolExecutor(max_workers=len(fns)) as pool:
        futuros = {k: pool.submit(f, person_a, person_b, similitud, contexto) for k, f in fns.items()}
        res = {k: f.result() for k, f in futuros.items()}
    votos = {k: (None if r is None else bool(r["hay_complementariedad"])) for k, r in res.items()}
    validos = [v for v in votos.values() if v is not None]
    return {
        "votos": votos,
        "scores": {k: (None if r is None else r["score_final"]) for k, r in res.items()},
        "consenso": sum(validos) * 2 > len(validos) if validos else False,
        "unanime": len(set(validos)) == 1 and len(validos) >= 2,
        "n_votos": len(validos),
    }


def kappa(x: list, y: list) -> float:
    """Kappa de Cohen entre dos listas de votos booleanos."""
    n = len(x)
    if n == 0:
        return float("nan")
    po = sum(a == b for a, b in zip(x, y)) / n
    px, py = sum(x) / n, sum(y) / n
    pe = px * py + (1 - px) * (1 - py)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def resumir(items: list) -> dict:
    """items: [{"tipo": "similitud|indirecto|control", "votos": {...}, "consenso": bool, ...}]."""
    nombres = sorted({v for i in items for v in i["votos"]})
    tipos = sorted({i["tipo"] for i in items})
    tasas = {}
    for t in tipos:
        grupo = [i for i in items if i["tipo"] == t]
        fila = {"n": len(grupo)}
        for v in nombres:
            vals = [i["votos"][v] for i in grupo if i["votos"].get(v) is not None]
            fila[v] = round(sum(vals) / len(vals), 3) if vals else None
        fila["consenso"] = round(sum(i["consenso"] for i in grupo) / len(grupo), 3)
        tasas[t] = fila
    acuerdo = {}
    for a, b in itertools.combinations(nombres, 2):
        par = [(i["votos"][a], i["votos"][b]) for i in items
               if i["votos"].get(a) is not None and i["votos"].get(b) is not None]
        if par:
            xs, ys = [p[0] for p in par], [p[1] for p in par]
            acuerdo[f"{a} / {b}"] = {"acuerdo": round(sum(p == q for p, q in par) / len(par), 3),
                                      "kappa": round(kappa(xs, ys), 3), "n": len(par)}
    return {"votantes": nombres, "tasa_de_si_por_tipo": tasas, "acuerdo_entre_votantes": acuerdo,
            "unanimes": round(sum(i["unanime"] for i in items) / len(items), 3), "n_total": len(items)}
