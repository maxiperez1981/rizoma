"""Cohortes: quién puede ver nombres en los paneles de puentes y equipos.

La cohorte es la institución declarada, normalizada: la parte antes de «·»
("UNQ · Licenciatura en Informática" -> "unq"), sin tildes ni mayúsculas, con
alias para las variantes conocidas ("Universidad Nacional de Quilmes" -> "unq").

Reglas:
  - administración ve todos los nombres;
  - docentes y organizaciones ven solo los de personas de su misma cohorte;
  - el resto (estudiantes) no ve nombres;
  - sin institución declarada no hay cohorte: no se ve ningún nombre.
Quien no se ve aparece como «Persona N».
"""
import unicodedata

from sqlalchemy import text
from sqlalchemy.orm import Session

ALIAS = {
    "universidad nacional de quilmes": "unq",
}
ROLES_CON_COHORTE = ("teacher", "org")


def cohorte_de(institucion) -> str:
    s = unicodedata.normalize("NFD", str(institucion or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = " ".join(s.split("·")[0].split())
    return ALIAS.get(s, s)


def ids_visibles(db: Session, viewer, persona_ids) -> set:
    """Ids (como texto) cuyos nombres puede ver `viewer`."""
    ids = {str(i) for i in persona_ids if i}
    if not ids:
        return set()
    if viewer.role == "admin":
        return ids
    if viewer.role not in ROLES_CON_COHORTE:
        return set()
    propia = cohorte_de(viewer.institution)
    if not propia:
        return set()
    filas = db.execute(text("SELECT id, institution FROM users WHERE id = ANY(CAST(:ids AS uuid[]))"),
                       {"ids": sorted(ids)}).fetchall()
    return {str(i) for i, inst in filas if cohorte_de(inst) == propia}
