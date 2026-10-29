"""Minimización local antes de enviar texto a un proveedor. No anonimiza relatos.

Retira patrones reconocibles (correos, enlaces, documentos, teléfonos,
direcciones, cuentas) y, además, los identificadores conocidos de la persona
(su nombre completo, cada parte del nombre y su correo). Los patrones solos no
detectan nombres propios, y en un CV el nombre suele estar en la primera línea.
El filtro actúa sobre la copia que se envía o se guarda como extracto; no
garantiza anonimato, porque un relato puede permitir identificar a alguien.
"""
import re
import unicodedata
from typing import Any, Iterable, Optional

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d \t().-]{7,}\d)(?!\w)")
# Rangos de años de un CV ("2015 - 2018"): parecen teléfonos pero no lo son.
_RANGO_ANIOS_RE = re.compile(r"(?:19|20)\d{2}\s*[-–/]\s*(?:19|20)\d{2}")
DNI_RE = re.compile(r"\b(?:DNI|CUIL|CUIT|documento|legajo)\s*[:#-]?\s*[\d.\-/]{6,}\b", re.IGNORECASE)
ADDRESS_RE = re.compile(r"\b(?:calle|av\.?|avenida|domicilio|direcci[oó]n)\s+[A-ZÁÉÍÓÚÑa-záéíóúñ0-9 .'-]{3,}\b", re.IGNORECASE)
SOCIAL_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_\.]{3,}")

OMITIDO = "[nombre omitido]"
# Partes de nombre demasiado comunes como palabra suelta para retirarlas solas.
_NO_RETIRAR_SOLAS = {"del", "de", "la", "las", "los", "san", "santa", "van", "von", "dos", "das"}


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def identificadores_de(name: str = "", email: str = "") -> list[str]:
    """Nombre completo, cada parte del nombre (3+ letras) y correo (y su parte local)."""
    salida = []
    nombre = re.sub(r"\s+", " ", str(name or "")).strip()
    if nombre:
        salida.append(nombre)
        for parte in re.split(r"[\s,]+", nombre):
            if len(parte) >= 3 and parte.lower() not in _NO_RETIRAR_SOLAS:
                salida.append(parte)
    correo = str(email or "").strip()
    if "@" in correo:
        salida.append(correo)
        local = correo.split("@", 1)[0]
        if len(local) >= 4:
            salida.append(local)
    return salida


def identificadores_de_usuario(user) -> list[str]:
    return identificadores_de(getattr(user, "name", ""), getattr(user, "email", ""))


def _retirar_identificadores(text: str, identifiers: Iterable[str]) -> str:
    variantes = set()
    for ident in identifiers or ():
        ident = str(ident or "").strip()
        if len(ident) >= 3:
            variantes.add(ident)
            variantes.add(_sin_tildes(ident))
    for ident in sorted(variantes, key=len, reverse=True):
        patron = r"(?<![\w@])" + r"\s+".join(re.escape(p) for p in ident.split()) + r"(?![\w@])"
        text = re.sub(patron, OMITIDO, text, flags=re.IGNORECASE)
    return re.sub(r"(?:\[nombre omitido\][\s,]*){2,}", OMITIDO + " ", text)


def _retirar_telefonos(text: str) -> tuple[str, int]:
    """Números de 8 o más dígitos con forma de teléfono; deja los rangos de años."""
    n = 0

    def reemplazo(m):
        nonlocal n
        s = m.group(0)
        if len(re.sub(r"\D", "", s)) < 8 or _RANGO_ANIOS_RE.fullmatch(s.strip()):
            return s
        n += 1
        return "[telefono]"

    return PHONE_RE.sub(reemplazo, text), n


def anonymize_text(value: Any, max_len: Optional[int] = None, identifiers: Iterable[str] = ()) -> str:
    text = str(value or "")
    # Correos y enlaces primero, enteros: si no, una parte del nombre dentro de
    # "nombre.apellido@..." se reemplazaría sola y dejaría restos del correo.
    text = EMAIL_RE.sub("[email]", text)
    text = URL_RE.sub("[url]", text)
    text = _retirar_identificadores(text, identifiers)
    text = DNI_RE.sub("[documento]", text)
    text = _retirar_telefonos(text)[0]
    text = ADDRESS_RE.sub("[direccion]", text)
    text = SOCIAL_RE.sub("[usuario]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] if max_len else text


def minimizar_con_detalle(value: Any, identifiers: Iterable[str] = ()) -> tuple[str, dict]:
    """Lo mismo que anonymize_text, conservando los saltos de línea, y cuánto retiró de cada cosa.

    Es para la vista previa del CV: la persona ve la copia, la corrige y recién
    entonces se envía. Es seudonimización, no anonimización: empleos, fechas y
    lugares pueden seguir identificando a alguien.
    """
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    conteo = {}
    text, conteo["correos"] = EMAIL_RE.subn("[email]", text)
    text, conteo["enlaces"] = URL_RE.subn("[url]", text)
    antes = text.count(OMITIDO)
    text = _retirar_identificadores(text, identifiers)
    conteo["nombre"] = max(0, text.count(OMITIDO) - antes)
    text, conteo["documentos"] = DNI_RE.subn("[documento]", text)
    text, conteo["telefonos"] = _retirar_telefonos(text)
    text, conteo["direcciones"] = ADDRESS_RE.subn("[direccion]", text)
    text, conteo["usuarios"] = SOCIAL_RE.subn("[usuario]", text)
    lineas = [re.sub(r"[ \t\f\v]+", " ", linea).strip() for linea in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
    return text, {k: v for k, v in conteo.items() if v}


def anonymize_list(values: Any, max_items: int = 12, max_len: int = 80, identifiers: Iterable[str] = ()) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for item in values[:max_items]:
        text = anonymize_text(item, max_len=max_len, identifiers=identifiers)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def anonymized_profile(profile: dict, label: str) -> dict:
    """Perfil con etiqueta en lugar del nombre, sin el nombre propio dentro de las listas."""
    propios = identificadores_de(profile.get("name", ""), profile.get("email", ""))
    return {
        "name": label,
        "can_offer": anonymize_list(profile.get("can_offer") or [], identifiers=propios),
        "wants_to_learn": anonymize_list(profile.get("wants_to_learn") or [], identifiers=propios),
        "interests": anonymize_list(profile.get("interests") or [], identifiers=propios),
    }
