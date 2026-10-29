from pathlib import Path

p = Path("routers/users.py")
s = p.read_text(encoding="utf-8")

old = """    for _, other, similarity_score, learn_from_them, offer_them, shared in stage:
        other_offers = other.can_offer or []
"""
new = """    for _, other, similarity_score, learn_from_them, offer_them, shared in stage:
        other_id = str(other.id)
        camino_indirecto = caminos.get(other_id)
        other_offers = other.can_offer or []
"""
if old not in s:
    raise SystemExit("loop marker not found")
s = s.replace(old, new)

old = """        if not ai_result["hay_complementariedad"]:
            continue

        if learn_from_them and offer_them:
            ctype = "Complementariedad recíproca"
        elif learn_from_them:
            ctype = "Puede ayudarte a aprender"
        elif offer_them:
            ctype = "Podés aportar a su recorrido"
        elif shared:
            ctype = "Interés compartido"
        elif str(other.id) in caminos:
            ctype = "Vínculo indirecto en la red"
        else:
            ctype = "Complementariedad sugerida por IA"
"""
new = """        if not ai_result["hay_complementariedad"] and camino_indirecto:
            pasos = " -> ".join(paso.get("label", "?") for paso in camino_indirecto.get("camino", []))
            ai_result = {
                "hay_complementariedad": True,
                "score_final": max(45, int(ai_result.get("score_final") or 0)),
                "explicacion": (
                    "Hay un vínculo indirecto para explorar: no aparece por similitud directa, "
                    f"sino por este camino de la red: {pasos}."
                ),
                "relationship_edges": ai_result.get("relationship_edges") or [],
                "modelo_usado": (str(ai_result.get("modelo_usado") or "local-heuristic") + "+camino-indirecto"),
            }

        if not ai_result["hay_complementariedad"]:
            continue

        if learn_from_them and offer_them:
            ctype = "Complementariedad recíproca"
        elif learn_from_them:
            ctype = "Puede ayudarte a aprender"
        elif offer_them:
            ctype = "Podés aportar a su recorrido"
        elif shared:
            ctype = "Interés compartido"
        elif camino_indirecto:
            ctype = "Vínculo indirecto en la red"
        else:
            ctype = "Complementariedad sugerida por IA"
"""
if old not in s:
    raise SystemExit("fallback marker not found")
s = s.replace(old, new)

s = s.replace('camino=caminos.get(str(other.id), {}).get("camino", []),', 'camino=(camino_indirecto or {}).get("camino", []),')

p.write_text(s, encoding="utf-8")
print("patched indirect fallback")
