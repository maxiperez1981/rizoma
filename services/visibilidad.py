"""Qué ven los demás de cada persona (preferencias al estilo LinkedIn).

Cada persona elige, en «Datos base» → «Mis datos y privacidad»:
  nombre       "abreviado" (por defecto, «M. Iglesias») o "completo";
  bio          "conjunto" (por defecto: la ven las personas de su conjunto) o "nadie";
  sugerencias  aparecer en las sugerencias de otras personas (por defecto sí);
  busqueda     aparecer en la búsqueda por nombre o institución (por defecto sí);
  institucion  mostrar la institución (por defecto sí).

La propia persona y la administración ven siempre todo. Las organizaciones se
muestran con su nombre completo (no son personas). Quien no aparece en
sugerencias tampoco se nombra cuando hace de puente: se muestra como
«Persona de la red».
"""
import unicodedata
from types import SimpleNamespace

DEFAULTS = {"nombre": "abreviado", "bio": "conjunto", "sugerencias": True, "busqueda": True, "institucion": True}
OPCIONES = {"nombre": ("abreviado", "completo"), "bio": ("conjunto", "nadie")}
ANONIMO = "Persona de la red"
TITULOS = {"prof.", "prof", "dr.", "dra.", "dr", "dra", "lic.", "ing.", "mg.", "arq."}
PARTICULAS = {"de", "del", "la", "las", "los", "van", "von", "da", "do", "dos", "das", "di", "y"}


def preferencias(persona) -> dict:
    guardadas = getattr(persona, "visibilidad", None) or {}
    salida = dict(DEFAULTS)
    for clave, valor in guardadas.items():
        if clave in OPCIONES and valor in OPCIONES[clave]:
            salida[clave] = valor
        elif clave in DEFAULTS and isinstance(DEFAULTS[clave], bool) and isinstance(valor, bool):
            salida[clave] = valor
    return salida


def validar(cambios: dict) -> dict:
    """Solo claves y valores conocidos; lo demás se ignora."""
    return {k: v for k, v in (cambios or {}).items()
            if (k in OPCIONES and v in OPCIONES[k]) or (k in DEFAULTS and isinstance(DEFAULTS[k], bool) and isinstance(v, bool))}


def abreviar(nombre: str) -> str:
    """'Marta Quiroga' -> 'M. Quiroga'; 'María José del Río' -> 'M. del Río'; conserva títulos."""
    partes = str(nombre or "").split()
    titulos = []
    while partes and partes[0].lower() in TITULOS:
        titulos.append(partes.pop(0))
    if len(partes) < 2:
        return " ".join(titulos + partes)
    apellido = [partes[-1]]
    i = len(partes) - 2
    while i >= 1 and partes[i].lower() in PARTICULAS:
        apellido.insert(0, partes[i])
        i -= 1
    return " ".join(titulos + [partes[0][0].upper() + "."] + apellido)


def _privilegiado(persona, viewer) -> bool:
    return viewer is not None and (str(getattr(viewer, "id", "")) == str(getattr(persona, "id", "-"))
                                   or getattr(viewer, "role", "") == "admin")


def nombre_visible(persona, viewer, como_puente: bool = False) -> str:
    if _privilegiado(persona, viewer) or getattr(persona, "role", "") == "org":
        return persona.name
    prefs = preferencias(persona)
    if como_puente and not prefs["sugerencias"]:
        return ANONIMO
    return persona.name if prefs["nombre"] == "completo" else abreviar(persona.name)


def institucion_visible(persona, viewer) -> str:
    if _privilegiado(persona, viewer) or preferencias(persona)["institucion"]:
        return getattr(persona, "institution", "") or ""
    return ""


def bio_visible(persona, viewer, texto: str) -> str:
    if _privilegiado(persona, viewer) or preferencias(persona)["bio"] == "conjunto":
        return texto or ""
    return ""


def aparece_en_sugerencias(persona) -> bool:
    return preferencias(persona)["sugerencias"]


def aparece_en_busqueda(persona) -> bool:
    return preferencias(persona)["busqueda"]


def como_se_ve(persona, viewer) -> SimpleNamespace:
    """Objeto con `name` visible, para funciones que arman textos con .name."""
    return SimpleNamespace(id=getattr(persona, "id", None), name=nombre_visible(persona, viewer))


def nombres_para(db, viewer, ids) -> dict:
    """{id: nombre como lo ve `viewer`} para mostrar en grafos, caminos y puentes."""
    import models

    ids = list(ids)
    if not ids:
        return {}
    personas = db.query(models.User).filter(models.User.id.in_(ids)).all()
    return {p.id: nombre_visible(p, viewer, como_puente=True) for p in personas}


def _plano(texto: str) -> str:
    s = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def coincide(termino: str, *campos) -> bool:
    """Búsqueda sobre lo que se ve (nombre visible, institución visible), sin tildes."""
    t = _plano(termino).strip()
    return bool(t) and any(t in _plano(c) for c in campos if c)
