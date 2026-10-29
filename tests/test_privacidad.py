"""Tests de privacidad: minimización, aviso versionado, seudónimos, exportación y conservación.

No tocan la base ni llaman a servicios externos.
"""
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from services import privacy_export, privacy_notice, privacy_retention, seudonimos
from services.privacy_service import anonymize_list, anonymize_text, anonymized_profile, identificadores_de

RAIZ = Path(__file__).resolve().parent.parent


# ── minimización ───────────────────────────────────────────────────────────────

def test_identificadores_incluyen_nombre_partes_y_correo():
    ids = identificadores_de("María José del Río", "mjrio@unq.edu.ar")
    assert "María José del Río" in ids and "María" in ids and "Río" in ids
    assert "del" not in ids                      # demasiado común como palabra suelta
    assert "mjrio@unq.edu.ar" in ids and "mjrio" in ids


def test_retira_el_nombre_propio_de_un_cv():
    cv = "Lucía Fernández\nLic. en Informática. Contacto: lucia.f@mail.com\nFernández trabajó en datos abiertos."
    ids = identificadores_de("Lucía Fernández", "lucia.f@mail.com")
    salida = anonymize_text(cv, identifiers=ids)
    assert "Lucía" not in salida and "Fernández" not in salida and "lucia.f" not in salida
    assert "[nombre omitido]" in salida and "datos abiertos" in salida


def test_un_correo_con_el_nombre_adentro_se_reemplaza_entero():
    salida = anonymize_text("Carla Ibáñez\ncarla.ibanez@ejemplo.com - Tel. 11 5555-1234",
                            identifiers=identificadores_de("Carla Ibáñez", "otra@cuenta.org"))
    assert salida == "[nombre omitido] [email] - Tel. [telefono]"


def test_retira_el_nombre_aunque_venga_sin_tildes():
    salida = anonymize_text("CV de Lucia Fernandez, programadora", identifiers=identificadores_de("Lucía Fernández"))
    assert "Lucia" not in salida and "Fernandez" not in salida


def test_no_corta_palabras_que_contienen_el_nombre():
    salida = anonymize_text("Ana hace análisis de datos en Anabel Group", identifiers=identificadores_de("Ana"))
    assert salida.startswith("[nombre omitido] hace análisis") and "Anabel" in salida


def test_sin_identificadores_se_comporta_como_antes():
    assert anonymize_text("escribime a x@y.com") == "escribime a [email]"


def test_el_perfil_para_el_modelo_no_lleva_el_nombre_ni_en_las_listas():
    perfil = {"name": "Bruno Cejas", "can_offer": ["economía cooperativa", "proyectos de Bruno Cejas"],
              "wants_to_learn": ["sensores"], "interests": []}
    anon = anonymized_profile(perfil, "Persona B")
    assert anon["name"] == "Persona B"
    assert all("Bruno" not in x and "Cejas" not in x for x in anon["can_offer"])
    assert "economía cooperativa" in anon["can_offer"]


def test_anonymize_list_acepta_identificadores():
    assert anonymize_list(["Python", "taller de Juan Pérez"], identifiers=identificadores_de("Juan Pérez")) == \
        ["Python", "taller de [nombre omitido]"]


# ── aviso versionado ───────────────────────────────────────────────────────────

def test_la_version_del_aviso_coincide_en_servidor_pagina_e_interfaz():
    pagina = (RAIZ / "static" / "privacidad.html").read_text(encoding="utf-8")
    assert privacy_notice.NOTICE_VERSION in pagina
    app_js = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert re.search(r"AVISO_PRIVACIDAD_VERSION = '([^']+)'", app_js).group(1) == privacy_notice.NOTICE_VERSION


def test_cambiar_el_texto_sin_subir_la_version_impide_arrancar():
    privacy_notice.verificar_publicacion(None, "abc")        # primera publicación
    privacy_notice.verificar_publicacion("abc", "abc")       # mismo texto
    with pytest.raises(RuntimeError):
        privacy_notice.verificar_publicacion("abc", "otro")


def test_el_aviso_nombra_lo_que_el_sistema_hace():
    pagina = (RAIZ / "static" / "privacidad.html").read_text(encoding="utf-8")
    for frase in ("OPEN LAB", "Ley 25.326", "OpenAI", "almacenamiento opcional", "14 copias", "Unsplash",
                  "Mis datos y privacidad", "misma institución"):
        assert frase in pagina
    assert "Google Fonts" not in pagina


# ── tipografías propias ────────────────────────────────────────────────────────

def test_la_interfaz_no_carga_tipografias_externas():
    indice = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in indice and "fonts.gstatic" not in indice
    assert "static/css/fonts.css" in indice


def test_cada_fuente_declarada_existe_y_tiene_licencia():
    css = (RAIZ / "static" / "css" / "fonts.css").read_text(encoding="utf-8")
    archivos = re.findall(r"url\(\.\./fonts/([^)]+\.woff2)\)", css)
    assert len(archivos) == 18
    for nombre in archivos:
        assert (RAIZ / "static" / "fonts" / nombre).read_bytes()[:4] == b"wOF2"
    for licencia in ("LICENSE-montserrat.txt", "LICENSE-source-sans-3.txt"):
        assert "SIL Open Font License" in (RAIZ / "static" / "fonts" / licencia).read_text(encoding="utf-8")


# ── cohortes ───────────────────────────────────────────────────────────────────

class _BaseFalsa:
    """Responde a la consulta de instituciones de cohortes.ids_visibles."""

    def __init__(self, instituciones):
        self.instituciones = instituciones

    def execute(self, _sql, params):
        filas = [(i, self.instituciones[i]) for i in params["ids"] if i in self.instituciones]

        class _R:
            def fetchall(self_inner):
                return filas
        return _R()


class _Persona:
    def __init__(self, role, institution):
        self.role, self.institution = role, institution


def test_cohorte_normaliza_variantes_de_la_institucion():
    from services.cohortes import cohorte_de
    assert cohorte_de("UNQ · Licenciatura en Informática") == "unq"
    assert cohorte_de("Universidad Nacional de Quilmes") == "unq"
    assert cohorte_de(" unq ") == "unq"
    assert cohorte_de("Organización de salud") == "organizacion de salud"
    assert cohorte_de("") == ""


def test_nombres_visibles_segun_rol_y_cohorte():
    from services.cohortes import ids_visibles
    base = _BaseFalsa({"a": "UNQ · Lic. en Informática", "b": "Universidad Nacional de Quilmes",
                       "c": "Universidad de Buenos Aires", "d": ""})
    ids = ["a", "b", "c", "d"]
    assert ids_visibles(base, _Persona("admin", ""), ids) == set(ids)
    assert ids_visibles(base, _Persona("teacher", "UNQ"), ids) == {"a", "b"}
    assert ids_visibles(base, _Persona("org", "Universidad de Buenos Aires"), ids) == {"c"}
    assert ids_visibles(base, _Persona("student", "UNQ"), ids) == set()
    assert ids_visibles(base, _Persona("teacher", ""), ids) == set()


def test_ocultar_nombres_respeta_los_visibles():
    from services.insights_service import ocultar_nombres
    insight = {"datos": {"personas": [{"persona": "Ana", "persona_id": "a"}, {"persona": "Beto", "persona_id": "b"}]}}
    salida = ocultar_nombres(insight, {"a"})["datos"]["personas"]
    assert salida[0]["persona"] == "Ana" and salida[1] == {"persona": "Persona 2", "persona_id": None}
    assert all(p["persona"].startswith("Persona") for p in ocultar_nombres(insight)["datos"]["personas"])


# ── seudónimos ─────────────────────────────────────────────────────────────────

def test_seudonimo_estable_y_dependiente_del_secreto():
    a = seudonimos.seudonimo("ID-1", "s1")
    assert a == seudonimos.seudonimo("id-1 ", "s1")
    assert a != seudonimos.seudonimo("id-1", "s2")
    assert re.fullmatch(r"persona-[0-9a-f]{12}", a)


# ── exportación ────────────────────────────────────────────────────────────────

def test_la_exportacion_omite_contrasenas_y_resume_el_embedding():
    fila = {"id": uuid.UUID(int=1), "email": "x@y.z", "password_hash": "$2b$...", "embedding": [0.1] * 3,
            "created_at": datetime(2026, 10, 18)}
    limpia = privacy_export._limpiar(fila)
    assert "password_hash" not in limpia
    assert limpia["embedding"].startswith("vector numérico")
    assert limpia["id"] == str(uuid.UUID(int=1)) and limpia["created_at"].startswith("2026-10-18")


def test_la_exportacion_es_una_lista_cerrada_de_tablas():
    assert "users" in privacy_export.SUJETO and "messages" in privacy_export.SUJETO
    assert all(re.fullmatch(r"[a-z_]+", t) for t in privacy_export.SUJETO)


def test_respaldo_reciente_obligatorio(tmp_path):
    with pytest.raises(ValueError):
        privacy_export.validar_respaldo(tmp_path)
    vieja = tmp_path / "alma_academica_20260101_000000.dump"
    vieja.write_bytes(b"x")
    hace_dos_dias = time.time() - 48 * 3600
    os.utime(vieja, (hace_dos_dias, hace_dos_dias))
    with pytest.raises(ValueError):
        privacy_export.validar_respaldo(tmp_path)
    nueva = tmp_path / "alma_academica_20261018_000000.dump"
    nueva.write_bytes(b"x")
    assert privacy_export.validar_respaldo(tmp_path) == nueva


# ── conservación ───────────────────────────────────────────────────────────────

def test_cortes_de_conservacion():
    ahora = datetime(2026, 10, 18)
    assert (ahora - privacy_retention.corte(12, ahora)).days == 365
    assert (ahora - privacy_retention.corte(6, ahora)).days == 183


def test_el_conjunto_de_prueba_queda_fuera_de_la_depuracion():
    assert privacy_retention.PREFIJO_EXCLUIDO == "demo.unq."
