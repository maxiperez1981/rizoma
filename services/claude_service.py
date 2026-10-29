import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from config import settings
from services.privacy_service import anonymize_list, anonymize_text, anonymized_profile

logger = logging.getLogger(__name__)


def _anthropic_client():
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except Exception as e:
        logger.warning("No se pudo inicializar Anthropic client: %s", type(e).__name__)
        return None


def _as_list(value, max_items=8):
    if isinstance(value, list):
        return [str(v).strip()[:60] for v in value if str(v).strip()][:max_items]
    return []


def _normalize_profile(data: dict) -> dict:
    data = data if isinstance(data, dict) else {}
    tags = _as_list(data.get("tags"))
    can_offer = _as_list(data.get("can_offer"))
    wants = _as_list(data.get("wants_to_learn"))
    interests = _as_list(data.get("interests")) or tags
    gaps = _as_list(data.get("gaps")) or wants[:3]
    return {
        "summary": str(data.get("summary") or "Grafo en construcción: conocimientos, aprendizajes buscados e intereses extraídos de una trayectoria para vincular con otros.")[:900],
        "tags": tags[:5],
        "gaps": gaps[:4],
        "path_step": int(data.get("path_step") or 0),
        "top_area": str(data.get("top_area") or (interests[0] if interests else "proyectos académicos"))[:80],
        "can_offer": can_offer[:8],
        "wants_to_learn": wants[:8],
        "interests": interests[:8],
    }


def _normalize_matches(items: object) -> list:
    if isinstance(items, dict):
        items = items.get("matches", [])
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append({
            "project_id": str(item.get("project_id", "")),
            "score": int(item.get("score") or 70),
            "match_level": str(item.get("match_level") or "Exploratorio")[:40],
            "text": str(item.get("text") or "Hay una complementariedad posible para explorar.")[:300],
            "why": str(item.get("why") or item.get("why_connect") or "")[:700],
            "you_contribute": str(item.get("you_contribute") or "")[:450],
            "you_can_learn": str(item.get("you_can_learn") or "")[:450],
            "project_needs": str(item.get("project_needs") or "")[:450],
            "why_connect": str(item.get("why_connect") or item.get("why") or "")[:700],
            "suggested_action": str(item.get("suggested_action") or "Quiero explorar esta oportunidad")[:80],
        })
    return out


def synthesize_profile(text: str, credential_titles: list[str] = None, identifiers=()) -> dict:
    """Arma el perfil desde un CV o texto. `identifiers`: nombre y correo de la
    persona, para retirarlos de la copia que se envía al modelo."""
    safe_text = anonymize_text(text, max_len=6000, identifiers=identifiers)
    safe_credentials = anonymize_list(credential_titles or [], max_items=12, max_len=120, identifiers=identifiers)
    if settings.openai_api_key:
        result = _openai_synthesize(safe_text, safe_credentials)
        if result:
            return _normalize_profile(result)
    client = _anthropic_client()
    if client:
        return _normalize_profile(_claude_synthesize(client, safe_text, safe_credentials))
    return _local_synthesize(safe_text)


def get_matches(user_summary: str, user_tags: list, projects: list, can_offer=None, wants_to_learn=None, interests=None) -> list:
    user_summary = anonymize_text(user_summary, max_len=1200)
    user_tags = anonymize_list(user_tags or [], max_items=12, max_len=80)
    can_offer = anonymize_list(can_offer or [], max_items=12, max_len=80)
    wants_to_learn = anonymize_list(wants_to_learn or [], max_items=12, max_len=80)
    interests = anonymize_list(interests or [], max_items=12, max_len=80)
    if settings.openai_api_key:
        result = _openai_matches(user_summary, user_tags, projects, can_offer, wants_to_learn, interests)
        if result is not None:
            return _normalize_matches(result)
    client = _anthropic_client()
    if client:
        return _normalize_matches(_claude_matches(client, user_summary, user_tags, projects, can_offer, wants_to_learn, interests))
    return _local_matches(user_tags, projects, can_offer, wants_to_learn, interests)


def _openai_json(prompt: str, max_tokens: int, modelo: Optional[str] = None) -> Optional[object]:
    payload = {
        "model": modelo or settings.openai_model,
        "messages": [
            {"role": "system", "content": "Respondé solamente JSON válido, sin markdown ni texto extra."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        # Sin almacenamiento opcional en OpenAI. No activa retención cero ni
        # elimina los registros de seguridad del proveedor.
        "store": False,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return json.loads(data["choices"][0]["message"]["content"].strip())
    except urllib.error.HTTPError as e:
        logger.error("Error HTTP en OpenAI: status=%s", e.code)
    except Exception as e:
        logger.error("Error en OpenAI: %s", type(e).__name__)
    return None


def _profile_prompt(text: str, credential_titles: list) -> str:
    creds_str = "\n".join(f"- {c}" for c in credential_titles) if credential_titles else "Ninguna aún."
    return f"""Sos el copiloto de Rizoma, un motor de complementariedad académica orientado a la acción.

Objetivo del producto: conectar personas con proyectos donde puedan aportar lo que ya saben y aprender aquello que quieren desarrollar. No funciona como vidriera profesional, bolsa de empleo ni ranking de candidatos.

Analizá el texto del usuario y separá con cuidado:
- lo que sabe o puede aportar;
- lo que quiere aprender o explorar;
- temas de interés;
- brechas o próximos aprendizajes.

Texto del usuario:
{text}

Credenciales existentes, si sirven como contexto posterior y no como eje principal:
{creds_str}

Devolvé SOLAMENTE un objeto JSON válido:
{{
  "summary": "2-3 oraciones sobrias: qué podría aportar y qué busca aprender haciendo proyectos reales",
  "can_offer": ["capacidad o experiencia concreta"],
  "wants_to_learn": ["aprendizaje o exploración concreta"],
  "interests": ["tema de interés"],
  "tags": ["tag sintético"],
  "gaps": ["próximo aprendizaje concreto"],
  "path_step": 0,
  "top_area": "área principal"
}}

Reglas:
- No inventes capacidades no declaradas.
- No infieras datos sensibles.
- No prometas empleo.
- Priorizá verbos de acción: aportar, aprender, explorar, colaborar, construir.
- tags, can_offer, wants_to_learn e interests: máximo 6 ítems cada uno.
"""


def _openai_synthesize(text: str, credential_titles: list) -> Optional[dict]:
    result = _openai_json(_profile_prompt(text, credential_titles), 900)
    return result if isinstance(result, dict) else None


def _matches_prompt(user_summary: str, user_tags: list, projects: list, can_offer: list, wants_to_learn: list, interests: list) -> str:
    projects_json = json.dumps(projects, ensure_ascii=False, indent=2)
    return f"""Sos el motor de complementariedad de Rizoma.

No busques solo tags iguales. Buscá intercambios posibles entre:
- lo que la persona sabe o puede aportar;
- lo que quiere aprender;
- lo que cada proyecto necesita;
- lo que cada proyecto puede enseñar u ofrecer.

CV, trayectoria o grafo inicial de la persona:
- Resumen: {user_summary}
- Puede aportar: {', '.join(can_offer) if can_offer else 'sin definir'}
- Quiere aprender: {', '.join(wants_to_learn) if wants_to_learn else 'sin definir'}
- Intereses: {', '.join(interests or user_tags) if (interests or user_tags) else 'sin definir'}

Proyectos abiertos:
{projects_json}

Devolvé SOLAMENTE este objeto JSON:
{{
  "matches": [
    {{
      "project_id": "...",
      "score": 82,
      "match_level": "Alta|Media|Exploratoria",
      "text": "síntesis breve del intercambio posible",
      "you_contribute": "qué puede aportar la persona al proyecto",
      "you_can_learn": "qué podría aprender o desarrollar",
      "project_needs": "qué necesidad concreta del proyecto se cubre",
      "why_connect": "por qué tiene sentido conectarlos ahora",
      "suggested_action": "Abrir conversación|Explorar conexión|Contactar al equipo"
    }}
  ]
}}

Reglas:
- La IA recomienda conexiones, no decide incorporaciones.
- No ordenes personas por valor personal.
- No prometas resultados.
- Preferí proyectos que aceptan personas en aprendizaje cuando el usuario quiere aprender algo.
- Si no hay complementariedad real, marcá match_level como Exploratoria y explicá la incertidumbre.
"""


def _openai_matches(user_summary: str, user_tags: list, projects: list, can_offer: list, wants_to_learn: list, interests: list) -> Optional[list]:
    if not projects:
        return []
    result = _openai_json(_matches_prompt(user_summary, user_tags, projects, can_offer, wants_to_learn, interests), 1600)
    if isinstance(result, dict) and isinstance(result.get("matches"), list):
        return result["matches"]
    return None


def _claude_synthesize(client, text: str, credential_titles: list) -> dict:
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=900,
            messages=[{"role": "user", "content": _profile_prompt(text, credential_titles) + "\nSolo JSON, nada más."}],
        )
        return json.loads(resp.content[0].text.strip())
    except Exception as e:
        logger.error("Error en claude synthesize: %s", type(e).__name__)
        return _local_synthesize(text)


def _claude_matches(client, user_summary: str, user_tags: list, projects: list, can_offer: list, wants_to_learn: list, interests: list) -> list:
    if not projects:
        return []
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1400,
            messages=[{"role": "user", "content": _matches_prompt(user_summary, user_tags, projects, can_offer, wants_to_learn, interests) + "\nSolo JSON, nada más."}],
        )
        raw = json.loads(resp.content[0].text.strip())
        return raw.get("matches", raw) if isinstance(raw, dict) else raw
    except Exception as e:
        logger.error("Error en claude matches: %s", type(e).__name__)
        return _local_matches(user_tags, projects, can_offer, wants_to_learn, interests)


_KW = [
    {"k": ["ia", "inteligencia artificial", "machine learning", "datos", "data", "python", "estadística"], "tag": "datos e IA", "need": ["Python", "análisis de datos"]},
    {"k": ["territ", "barr", "comunit", "social"], "tag": "trabajo territorial", "need": ["cartografía digital", "sistematización"]},
    {"k": ["comun", "periodis", "audiovisual"], "tag": "comunicación pública", "need": ["diseño de contenidos", "edición"]},
    {"k": ["educ", "tutor", "docen", "pedagog"], "tag": "educación", "need": ["investigación educativa", "evaluación"]},
    {"k": ["diseño", "ux", "visual", "video"], "tag": "diseño y producción", "need": ["UX", "portfolio"]},
]


def _local_synthesize(text: str) -> dict:
    lo = text.lower()
    matched = [e for e in _KW if any(k in lo for k in e["k"])]
    tags = [e["tag"] for e in matched][:5] or ["proyectos académicos"]
    can_offer = []
    wants = []
    for e in matched:
        if any(word in lo for word in ["sé", "saber", "manejo", "experiencia", "trabajo", "docencia", "gestión"]):
            can_offer.append(e["tag"])
        wants.extend(e["need"][:1])
    if not can_offer:
        can_offer = tags[:2]
    wants = list(dict.fromkeys(wants))[:4] or ["metodología de trabajo", "producción colaborativa"]
    return {
        "summary": f"Grafo orientado a aportar en {', '.join(can_offer[:2])} y aprender {', '.join(wants[:2])} mediante proyectos reales.",
        "tags": tags,
        "gaps": wants[:3],
        "path_step": 1,
        "top_area": tags[0],
        "can_offer": can_offer[:6],
        "wants_to_learn": wants[:6],
        "interests": tags[:6],
    }


def _overlap(a: list, b: list) -> int:
    aa = {str(x).lower() for x in a}
    bb = {str(x).lower() for x in b}
    return len(aa & bb)


def _local_matches(user_tags: list, projects: list, can_offer=None, wants_to_learn=None, interests=None) -> list:
    can_offer = can_offer or []
    wants_to_learn = wants_to_learn or []
    interests = interests or user_tags or []
    results = []
    for p in projects:
        needs = p.get("needs_skills", []) or p.get("roles_available", []) or p.get("tags", [])
        teaches = p.get("teaches_skills", []) or p.get("tags", [])
        contribution = _overlap(can_offer + interests, needs + p.get("tags", []))
        learning = _overlap(wants_to_learn + interests, teaches + p.get("tags", []))
        learner_bonus = 1 if p.get("accepts_learners") and wants_to_learn else 0
        score = min(95, 55 + contribution * 12 + learning * 12 + learner_bonus * 8)
        level = "Alta" if score >= 82 else "Media" if score >= 68 else "Exploratoria"
        offer = ", ".join((can_offer or interests or ["tu experiencia"])[0:2])
        learn = ", ".join((wants_to_learn or teaches or ["nuevas capacidades"])[0:2])
        need = ", ".join((needs or ["colaboradores con interés real"])[0:2])
        results.append({
            "project_id": str(p["id"]),
            "score": score,
            "match_level": level,
            "text": f"Puede haber intercambio: aportás {offer} y podrías desarrollar {learn}.",
            "you_contribute": f"Tu grafo puede aportar {offer} al proyecto.",
            "you_can_learn": f"El proyecto puede ayudarte a desarrollar {learn}.",
            "project_needs": f"El proyecto necesita o valora {need}.",
            "why_connect": "La conexión tiene sentido si ambas partes quieren explorar una colaboración concreta antes de hablar de credenciales.",
            "suggested_action": "Quiero explorar esta oportunidad",
        })
    return sorted(results, key=lambda x: x["score"], reverse=True)

def _as_edges(value) -> list:
    if not isinstance(value, list):
        return []
    edges = []
    for item in value[:6]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("razon") or "").strip()[:260]
        source_node = str(item.get("source_node") or item.get("origen") or "").strip()[:80]
        target_node = str(item.get("target_node") or item.get("destino") or "").strip()[:80]
        if not text and not (source_node and target_node):
            continue
        edges.append({
            "kind": str(item.get("kind") or "ai_complementarity")[:40],
            "label": str(item.get("label") or "complementariedad")[:60],
            "from": str(item.get("from") or item.get("desde") or "Persona A")[:120],
            "to": str(item.get("to") or item.get("hacia") or "Persona B")[:120],
            "source_node": source_node,
            "target_node": target_node,
            "text": text or f"{source_node} puede conectarse con {target_node}.",
        })
    return edges


def _normalize_complementarity(data: dict, modelo_usado: str) -> dict:
    data = data if isinstance(data, dict) else {}
    score = int(data.get("score_final") or 0)
    score = max(0, min(100, score))
    return {
        "hay_complementariedad": bool(data.get("hay_complementariedad", score >= 30)),
        "score_final": score,
        "explicacion": str(data.get("explicacion") or "")[:700],
        "relationship_edges": _as_edges(data.get("relationship_edges")),
        "modelo_usado": modelo_usado,
    }


def _complementarity_prompt(person_a: dict, person_b: dict, similarity_score: float, rizoma_context: str = "") -> str:
    person_a = anonymized_profile(person_a, "Persona A")
    person_b = anonymized_profile(person_b, "Persona B")
    rizoma_context = f"\n{rizoma_context}\n" if rizoma_context else ""
    return f"""Sos el motor de complementariedad de Rizoma, una red universitaria basada en grafos de trayectorias verificables.

No estás buscando al mejor candidato. Estás buscando dónde puede producirse una complementariedad útil para ambas partes: qué puede aportar una persona, qué quiere aprender, qué puede recibir de otra y qué podrían construir juntas.

PERSONA A ({person_a.get('name', 'Persona A')}):
puede_ofrecer: {person_a.get('can_offer', [])}
quiere_aprender: {person_a.get('wants_to_learn', [])}
intereses: {person_a.get('interests', [])}

PERSONA B ({person_b.get('name', 'Persona B')}):
puede_ofrecer: {person_b.get('can_offer', [])}
quiere_aprender: {person_b.get('wants_to_learn', [])}
intereses: {person_b.get('interests', [])}

Similaridad vectorial preliminar entre ambos perfiles (0 a 1): {similarity_score:.3f}
{rizoma_context}
Tarea:
1. Evaluá si existe complementariedad real, no solo parecido temático.
2. Asigná un score final de 0 a 100.
3. Redactá una explicación breve, máximo 3 oraciones, dirigida a ambas personas.
4. Devolvé relaciones explícitas entre nodos para dibujar el grafo: qué nodo de A se conecta con qué nodo de B y por qué.
5. Si no hay complementariedad real, asigná score menor a 30.
6. Si hay caminos indirectos listados arriba que involucren a estas dos personas, usalos: el vínculo más valioso suele ser el que pasa por un tema que ninguna de las dos nombra directamente. Mencioná ese puente en la explicación.

Devolvé SOLAMENTE este objeto JSON:
{{
  "hay_complementariedad": true,
  "score_final": 0,
  "explicacion": "texto breve",
  "relationship_edges": [
    {{
      "kind": "learn_from|offer_to|shared_interest|collaboration",
      "label": "aprendizaje|aporte|interés compartido|colaboración",
      "from": "{person_a.get('name', 'Persona A')}",
      "to": "{person_b.get('name', 'Persona B')}",
      "source_node": "nodo de A",
      "target_node": "nodo de B",
      "text": "por qué se conectan esos dos nodos"
    }}
  ]
}}
"""


def _openai_complementarity(person_a: dict, person_b: dict, similarity_score: float, rizoma_context: str = "") -> Optional[dict]:
    result = _openai_json(_complementarity_prompt(person_a, person_b, similarity_score, rizoma_context), 800)
    return result if isinstance(result, dict) else None


def _claude_complementarity(client, person_a: dict, person_b: dict, similarity_score: float, rizoma_context: str = "") -> dict:
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{
                "role": "user",
                "content": _complementarity_prompt(person_a, person_b, similarity_score, rizoma_context) + "\nSolo JSON, nada más.",
            }],
        )
        return json.loads(resp.content[0].text.strip())
    except Exception as e:
        logger.error("Error en claude complementarity: %s", type(e).__name__)
        return _local_complementarity(person_a, person_b, similarity_score)


def _local_complementarity(person_a: dict, person_b: dict, similarity_score: float) -> dict:
    a_learn = {str(v).lower() for v in (person_a.get("wants_to_learn") or [])}
    b_offer = {str(v).lower() for v in (person_b.get("can_offer") or [])}
    a_offer = {str(v).lower() for v in (person_a.get("can_offer") or [])}
    b_learn = {str(v).lower() for v in (person_b.get("wants_to_learn") or [])}
    shared = {str(v).lower() for v in (person_a.get("interests") or [])} & {str(v).lower() for v in (person_b.get("interests") or [])}
    overlap = len(a_learn & b_offer) + len(a_offer & b_learn)
    score = min(100, int(similarity_score * 45) + overlap * 22 + len(shared) * 6)
    edges = []
    for item in list(a_learn & b_offer)[:3]:
        edges.append({
            "kind": "learn_from",
            "label": "aprendizaje",
            "from": person_b.get("name", "Persona B"),
            "to": person_a.get("name", "Persona A"),
            "source_node": item,
            "target_node": item,
            "text": f"{person_a.get('name', 'Persona A')} quiere aprender {item} y {person_b.get('name', 'Persona B')} puede aportar experiencia en ese nodo.",
        })
    for item in list(a_offer & b_learn)[:3]:
        edges.append({
            "kind": "offer_to",
            "label": "aporte",
            "from": person_a.get("name", "Persona A"),
            "to": person_b.get("name", "Persona B"),
            "source_node": item,
            "target_node": item,
            "text": f"{person_a.get('name', 'Persona A')} puede aportar {item} y {person_b.get('name', 'Persona B')} quiere desarrollarlo.",
        })
    for item in list(shared)[:2]:
        edges.append({
            "kind": "shared_interest",
            "label": "interés compartido",
            "from": person_a.get("name", "Persona A"),
            "to": person_b.get("name", "Persona B"),
            "source_node": item,
            "target_node": item,
            "text": f"Ambos rizomas comparten interés en {item}.",
        })
    return {
        "hay_complementariedad": score >= 30,
        "score_final": score,
        "explicacion": (
            "Hay una posible complementariedad para explorar entre lo que una persona puede aportar y lo que la otra busca desarrollar."
            if score >= 30
            else "La cercanía parece más temática que práctica; no conviene priorizar este vínculo por ahora."
        ),
        "relationship_edges": edges,
    }


def evaluate_complementarity(person_a: dict, person_b: dict, similarity_score: float, rizoma_context: str = "") -> dict:
    if settings.openai_api_key:
        result = _openai_complementarity(person_a, person_b, similarity_score, rizoma_context)
        if result:
            return _normalize_complementarity(result, settings.openai_model or "openai")
    client = _anthropic_client()
    if client:
        return _normalize_complementarity(_claude_complementarity(client, person_a, person_b, similarity_score, rizoma_context), "claude-sonnet-4-6")
    return _normalize_complementarity(_local_complementarity(person_a, person_b, similarity_score), "local-heuristic")







def _actividad_prompt(ev: dict) -> str:
    a, b = ev["temas"][0]["label"], ev["temas"][1]["label"]
    area_a, area_b = ev["areas"]
    return f"""Una red de trayectorias universitarias modelada como grafo detecto una posible actividad emergente: una combinacion de dos temas de areas distintas que nadie reune todavia.

Tema A: {a} (area: {area_a})
Tema B: {b} (area: {area_b})
Personas involucradas: {ev['n_personas']}. Demanda (personas que quieren aprender alguno de los dos): {ev['demanda']}. Oferta (personas que ofrecen alguno de los dos): {ev['oferta']}.
Ninguna persona de la red tiene los dos temas a la vez.

Redacta, en espanol rioplatense neutro, el nombre y la descripcion de la actividad. Es una hipotesis para conversar, no un hecho: no afirmes certezas, no inventes datos ni personas, no hables de tendencias del mercado ni de interes o demanda 'creciente', y limitate a lo que muestran los numeros de arriba.

Responde solo JSON: {{"titulo": "maximo 80 caracteres", "descripcion": "dos frases: que podria hacerse combinando ambos temas y por que la red sugiere que vale la pena explorarlo"}}"""


def _normalize_actividad(data: dict, modelo_usado: str) -> dict:
    data = data if isinstance(data, dict) else {}
    return {
        "titulo": str(data.get("titulo") or "")[:200],
        "descripcion": str(data.get("descripcion") or "")[:900],
        "modelo_usado": modelo_usado,
    }


def _local_actividad(ev: dict) -> dict:
    a, b = ev["temas"][0]["label"], ev["temas"][1]["label"]
    return {
        "titulo": f"{a} + {b}",
        "descripcion": (
            f"Ninguna persona de la red reune hoy {a} y {b}, pero hay {ev['demanda']} personas que quieren "
            f"aprender alguno de los dos y {ev['oferta']} que ofrecen alguno. Vale la pena explorar una actividad que los combine."
        ),
    }


def describir_actividad_emergente(ev: dict) -> dict:
    """Nombra y explica una actividad emergente que ya detecto el grafo."""
    prompt = _actividad_prompt(ev)
    if settings.openai_api_key:
        result = _openai_json(prompt, 400)
        if isinstance(result, dict) and result.get("titulo"):
            return _normalize_actividad(result, settings.openai_model or "openai")
    client = _anthropic_client()
    if client:
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt + "\nSolo JSON, nada mas."}],
            )
            data = json.loads(resp.content[0].text.strip())
            if data.get("titulo"):
                return _normalize_actividad(data, "claude-sonnet-4-6")
        except Exception as e:
            logger.error("Error describiendo actividad emergente: %s", type(e).__name__)
    return _normalize_actividad(_local_actividad(ev), "local-heuristic")


def llm_json(prompt: str, max_tokens: int = 500, modelo: Optional[str] = None) -> tuple:
    """Pide JSON al primer proveedor disponible. Devuelve (dict | None, modelo)."""
    if settings.openai_api_key:
        result = _openai_json(prompt, max_tokens, modelo)
        if isinstance(result, dict):
            return result, modelo or settings.openai_model or "openai"
    client = _anthropic_client()
    if client:
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt + "\nSolo JSON, nada mas."}])
            data = json.loads(resp.content[0].text.strip())
            if isinstance(data, dict):
                return data, "claude-sonnet-4-6"
        except Exception as e:
            logger.error("Error en llm_json: %s", type(e).__name__)
    return None, "local-heuristic"


def describir_demanda_latente(ev: dict) -> dict:
    tema, areas = ev["tema"]["label"], ", ".join(ev["areas_demandantes"]) or "varias areas"
    prompt = f"""En una red de trayectorias universitarias, {ev['demanda']} personas quieren aprender "{tema}" y {ev['oferta']} lo ofrecen. Quienes lo quieren aprender vienen de: {areas}.

Propone en espanol rioplatense neutro una actividad formativa breve (curso, clinica o taller) para cubrir esa demanda. Es una hipotesis para conversar: no inventes datos, no hables de tendencias del mercado, limitate a los numeros de arriba.

Responde solo JSON: {{"titulo": "maximo 80 caracteres", "descripcion": "dos frases: que se ensenaria y a quienes serviria segun las areas indicadas"}}"""
    data, modelo = llm_json(prompt, 350)
    if data and data.get("titulo"):
        return {"titulo": str(data["titulo"])[:200], "descripcion": str(data.get("descripcion") or "")[:900], "modelo_usado": modelo}
    return {
        "titulo": f"Clinica de {tema}",
        "descripcion": f"{ev['demanda']} personas quieren aprender {tema} y {ev['oferta']} lo ofrecen; una actividad formativa breve podria cubrir esa brecha.",
        "modelo_usado": "local-heuristic",
    }
