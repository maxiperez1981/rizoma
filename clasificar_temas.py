"""Clasifica los temas en un vocabulario controlado de dos niveles.

Sigue el patron de observatorio: el vocabulario vive en la base y se inyecta
en el prompt, asi la IA elige dentro de un conjunto conocido en vez de
inventar etiquetas. Cada clasificacion guarda confianza, motivo y la version
del prompt, para saber que reprocesar cuando el prompt cambie.

Uso:
  python3 clasificar_temas.py --vocabulario   # propone y guarda el vocabulario
  python3 clasificar_temas.py                 # clasifica los temas sin clasificar
  python3 clasificar_temas.py --todos         # reclasifica todo (salvo bloqueados)
"""
import json
import sys
from datetime import datetime, timezone

from database import SessionLocal
import models
from services.claude_service import _openai_json

PROMPT_VERSION = "temas_rizoma_v1_2_niveles"
LOTE = 40


def proponer_vocabulario(db) -> int:
    etiquetas = [t.label for t in db.query(models.Topic).order_by(models.Topic.label).all()]
    prompt = f"""Sos el clasificador de una red universitaria de extension que vincula
personas por lo que pueden ofrecer y lo que quieren aprender.

Te paso el vocabulario real de temas que usan las personas de la red:
{json.dumps(etiquetas, ensure_ascii=False)}

Proponé un vocabulario controlado de DOS niveles que los cubra:
- macro: entre 8 y 12 areas amplias
- subtema: entre 3 y 6 por macro

Reglas:
- Los subtemas tienen que ser lo bastante amplios como para que dos personas
  con habilidades distintas pero del mismo campo caigan en el mismo subtema.
- No uses nombres genericos como "Otros" salvo un unico cajon final.
- Escribilos en espanol, en singular o plural segun suene natural.

Devolvé SOLAMENTE este JSON:
{{"vocabulario": [{{"macro": "...", "subtemas": ["...", "..."]}}]}}"""

    data = _openai_json(prompt, 2000)
    if not data:
        print("la IA no devolvio vocabulario")
        return 0

    db.query(models.TopicVocabulary).delete()
    n = 0
    for bloque in data.get("vocabulario", []):
        macro = str(bloque.get("macro", "")).strip()[:80]
        for sub in bloque.get("subtemas", []):
            sub = str(sub).strip()[:80]
            if macro and sub:
                db.add(models.TopicVocabulary(macro=macro, subtema=sub))
                n += 1
    db.commit()
    return n


def _vocabulario_texto(db) -> str:
    por_macro = {}
    for v in db.query(models.TopicVocabulary).order_by(models.TopicVocabulary.macro).all():
        por_macro.setdefault(v.macro, []).append(v.subtema)
    return "\n".join(f"- {m}: {', '.join(s)}" for m, s in por_macro.items())


def clasificar(db, todos: bool) -> dict:
    vocab = _vocabulario_texto(db)
    if not vocab:
        print("no hay vocabulario: corré primero --vocabulario")
        return {}

    query = db.query(models.Topic).filter(models.Topic.clasificacion_bloqueada.is_(False))
    if not todos:
        query = query.filter(models.Topic.macro.is_(None))
    pendientes = query.all()
    print(f"temas a clasificar: {len(pendientes)}")

    ok = fallos = 0
    for i in range(0, len(pendientes), LOTE):
        lote = pendientes[i:i + LOTE]
        prompt = f"""Clasificá cada tema dentro de este vocabulario controlado.

VOCABULARIO:
{vocab}

TEMAS A CLASIFICAR:
{json.dumps([t.label for t in lote], ensure_ascii=False)}

Reglas:
- macro y subtema tienen que salir textuales del vocabulario de arriba.
- confianza entre 0 y 1.
- motivo: una frase corta explicando la eleccion.

Devolvé SOLAMENTE este JSON, en el mismo orden que los temas recibidos:
{{"clasificaciones": [{{"tema": "...", "macro": "...", "subtema": "...", "confianza": 0.0, "motivo": "..."}}]}}"""

        data = _openai_json(prompt, 3000)
        items = (data or {}).get("clasificaciones", [])
        por_label = {str(it.get("tema", "")).strip().lower(): it for it in items}

        for tema in lote:
            it = por_label.get(tema.label.strip().lower())
            if not it:
                fallos += 1
                continue
            tema.macro = str(it.get("macro", ""))[:80] or None
            tema.subtema = str(it.get("subtema", ""))[:80] or None
            try:
                tema.confianza = float(it.get("confianza") or 0)
            except (TypeError, ValueError):
                tema.confianza = 0.0
            tema.motivo = str(it.get("motivo", ""))[:400]
            tema.prompt_version = PROMPT_VERSION
            tema.clasificado_at = datetime.now(timezone.utc)
            ok += 1
        db.commit()
        print(f"  lote {i // LOTE + 1}: {len(lote)} temas")

    return {"clasificados": ok, "fallos": fallos}


def main() -> int:
    db = SessionLocal()
    try:
        if "--vocabulario" in sys.argv:
            n = proponer_vocabulario(db)
            print(f"vocabulario guardado: {n} subtemas")
            return 0
        print(clasificar(db, "--todos" in sys.argv))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
