"""Tests de «Qué ven los demás de mí» y de la vista previa del CV.

No tocan la base ni llaman a servicios externos.
"""
from pathlib import Path
from types import SimpleNamespace

from services import visibilidad
from services.privacy_service import anonymize_text, identificadores_de, minimizar_con_detalle

RAIZ = Path(__file__).resolve().parent.parent


def _persona(name="Marta Quiroga", role="teacher", institution="UNQ", pid="m", **prefs):
    return SimpleNamespace(id=pid, name=name, role=role, institution=institution, visibilidad=prefs)


# ── nombres ────────────────────────────────────────────────────────────────────

def test_abreviar_inicial_y_apellido():
    assert visibilidad.abreviar("Marta Quiroga") == "M. Quiroga"
    assert visibilidad.abreviar("Daniel Alberto Herrera") == "D. Herrera"
    assert visibilidad.abreviar("María José del Río") == "M. del Río"
    assert visibilidad.abreviar("Prof. Ana Gómez") == "Prof. A. Gómez"
    assert visibilidad.abreviar("Lucía") == "Lucía"
    assert visibilidad.abreviar("") == ""


def test_por_defecto_el_nombre_se_ve_abreviado():
    marta, otra = _persona(), _persona("Carla Ibáñez", "student", pid="c")
    assert visibilidad.nombre_visible(marta, otra) == "M. Quiroga"


def test_quien_elige_nombre_completo_se_ve_completo():
    assert visibilidad.nombre_visible(_persona(nombre="completo"), _persona(pid="x")) == "Marta Quiroga"


def test_la_propia_persona_y_la_administracion_ven_todo():
    marta = _persona(institucion=False, bio="nadie")
    admin = _persona("Admin", "admin", pid="adm")
    for viewer in (marta, admin):
        assert visibilidad.nombre_visible(marta, viewer) == "Marta Quiroga"
        assert visibilidad.institucion_visible(marta, viewer) == "UNQ"
        assert visibilidad.bio_visible(marta, viewer, "Docente de datos") == "Docente de datos"


def test_las_organizaciones_se_ven_con_su_nombre():
    hospital = _persona("Hospital Zonal Sur", "org", "Salud", pid="h")
    assert visibilidad.nombre_visible(hospital, _persona(pid="x")) == "Hospital Zonal Sur"


def test_quien_no_aparece_en_sugerencias_es_anonimo_como_puente():
    marta, otra = _persona(sugerencias=False), _persona(pid="x")
    assert visibilidad.nombre_visible(marta, otra, como_puente=True) == visibilidad.ANONIMO
    assert visibilidad.nombre_visible(marta, otra) == "M. Quiroga"
    assert not visibilidad.aparece_en_sugerencias(marta)


def test_institucion_y_bio_ocultables():
    marta, otra = _persona(institucion=False, bio="nadie"), _persona(pid="x")
    assert visibilidad.institucion_visible(marta, otra) == ""
    assert visibilidad.bio_visible(marta, otra, "Docente de datos") == ""
    assert visibilidad.bio_visible(_persona(), otra, "Docente de datos") == "Docente de datos"


# ── preferencias ───────────────────────────────────────────────────────────────

def test_preferencias_ignora_valores_desconocidos():
    p = visibilidad.preferencias(_persona(nombre="secreto", busqueda="no", extra=1, bio="nadie"))
    assert p == {**visibilidad.DEFAULTS, "bio": "nadie"}


def test_validar_solo_acepta_claves_y_valores_conocidos():
    assert visibilidad.validar({"nombre": "completo", "busqueda": False, "busqueda2": False, "bio": "todos",
                                "sugerencias": "false"}) == {"nombre": "completo", "busqueda": False}
    assert visibilidad.validar(None) == {}


def test_la_busqueda_mira_lo_visible_sin_tildes():
    assert visibilidad.coincide("quiroga", "M. Quiroga", "UNQ")
    assert visibilidad.coincide("ibanez", "C. Ibáñez")
    assert not visibilidad.coincide("marta", "M. Quiroga", "UNQ")   # el nombre de pila no se ve
    assert not visibilidad.coincide("  ", "M. Quiroga")


def test_puentes_con_el_nombre_elegido():
    from services.insights_service import ocultar_nombres
    insight = {"datos": {"personas": [{"persona": "Marta Quiroga", "persona_id": "m"},
                                      {"persona": "Beto Paz", "persona_id": "b"}]}}
    salida = ocultar_nombres(insight, {"m"}, {"m": "M. Quiroga"})["datos"]["personas"]
    assert salida[0]["persona"] == "M. Quiroga" and salida[1]["persona"] == "Persona 2"


def test_el_camino_que_va_al_modelo_no_lleva_nombres():
    from services.pregunta_service import _relacion
    g = SimpleNamespace(temas_por_persona={"yo": {"t1"}, "x": {"t2"}}, etiquetas={})
    camino = {"camino": [{"tipo": "persona", "label": "Carla Ibáñez"}, {"tipo": "tema", "label": "datos"},
                         {"tipo": "persona", "label": "M. Quiroga"}, {"tipo": "tema", "label": "salud"},
                         {"tipo": "persona", "label": "N. Sosa"}]}
    rel = _relacion(g, "yo", "x", {"x": camino})
    assert rel["detalle_modelo"] == "camino: quien pregunta -> datos -> otra persona -> salud -> esta persona"
    assert "M. Quiroga" in rel["detalle"]


# ── vista previa del CV ────────────────────────────────────────────────────────

def test_vista_previa_conserva_renglones_y_cuenta_lo_retirado():
    cv = ("Lucía Fernández\nlucia.f@mail.com · Tel. 11 5555-1234\n\n\n"
          "Analista de datos (2015 - 2018) en Ejemplo SA\nwww.mi-portfolio.com")
    copia, retirado = minimizar_con_detalle(cv, identificadores_de("Lucía Fernández", "lucia.f@mail.com"))
    assert copia.splitlines()[0] == "[nombre omitido]"
    assert "\n\n\n" not in copia and "(2015 - 2018)" in copia
    assert retirado == {"correos": 1, "enlaces": 1, "nombre": 1, "telefonos": 1}


def test_vista_previa_dos_veces_no_cambia_nada():
    copia, _ = minimizar_con_detalle("Ana Paz\nana@x.org\nPython", identificadores_de("Ana Paz", "ana@x.org"))
    otra, retirado = minimizar_con_detalle(copia, identificadores_de("Ana Paz", "ana@x.org"))
    assert otra == copia and retirado == {}


def test_los_rangos_de_anios_no_son_telefonos():
    assert anonymize_text("Docente 2010-2019, tel 4252-9800 int 12") == "Docente 2010-2019, tel [telefono] int 12"
    assert anonymize_text("Desde 03/2015 - 12/2018") == "Desde 03/2015 - 12/2018"
    assert anonymize_text("Celular +54 9 11 4444-5555") == "Celular [telefono]"


# ── aviso e interfaz ───────────────────────────────────────────────────────────

def test_el_aviso_explica_visibilidad_y_seudonimizacion():
    pagina = (RAIZ / "static" / "privacidad.html").read_text(encoding="utf-8")
    for frase in ("M. Iglesias", "Qué ven los demás de mí", "Persona de la red", "seudonimización",
                  "no una anonimización", "nombre completo y tu correo"):
        assert frase in pagina


def test_la_interfaz_muestra_la_copia_antes_de_enviar():
    indice = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
    app_js = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Qué ven los demás de mí" in indice and 'id="cvRevision"' in indice
    assert "/api/copilot/vista-previa" in app_js and "/api/copilot/cv'" not in app_js
    assert "/api/users/me/visibilidad" in app_js


def test_un_ingreso_fallido_muestra_el_error():
    # Antes, cualquier 401 cerraba sesión y devolvía null: "Email o contraseña
    # incorrectos" nunca llegaba a la pantalla de ingreso.
    app_js = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "if (r.status === 401) { logout(); return null; }" not in app_js
    assert "url.startsWith('/auth/')" in app_js and app_js.count("if (sesionVencida(r, url)) return null;") == 2
