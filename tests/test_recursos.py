"""Recursos puestos a disposición: validación y filtro de privacidad (sin base ni servicios externos)."""
import pytest
from fastapi import HTTPException

from services import recursos_service as rs


def test_valida_y_limpia_datos_de_contacto():
    [r] = rs.validar([{"tipo": "datos", "titulo": "Registros de turnos, escribir a ana@ejemplo.com",
                       "temas": ["gestión de turnos", "", "datos"], "detalle": "Llamar al 1145678901"}])
    assert "@" not in r["titulo"] and "1145678901" not in r["detalle"]
    assert r["temas"] == ["gestión de turnos", "datos"] and r["id"]


def test_rechaza_tipo_desconocido_y_titulo_vacio():
    with pytest.raises(HTTPException):
        rs.validar([{"tipo": "otro", "titulo": "Algo útil"}])
    with pytest.raises(HTTPException):
        rs.validar([{"tipo": "datos", "titulo": "  "}])


def test_tope_de_recursos():
    with pytest.raises(HTTPException):
        rs.validar([{"tipo": "datos", "titulo": f"Recurso {i}"} for i in range(rs.MAX_RECURSOS + 1)])


def test_una_persona_ofrecida_no_se_publica_sin_aceptar():
    [r] = rs.validar([{"tipo": "persona", "titulo": "Una colega que trabaja IA", "acepto": False}])
    assert r["acepto"] is False
    [d] = rs.validar([{"tipo": "datos", "titulo": "Series de residuos", "acepto": False}])
    assert d["acepto"] is True   # la aceptación solo cuenta para personas


def test_recursos_que_tiene_cualquiera_y_acceso_con_proposito():
    [t] = rs.validar([{"tipo": "tiempo", "titulo": "Dos horas por semana para revisar código"}])
    assert t["tipo"] == "tiempo"
    with pytest.raises(HTTPException):
        rs.validar([{"tipo": "acceso", "titulo": "Llegada a una radio comunitaria", "detalle": ""}])
    [a] = rs.validar([{"tipo": "acceso", "titulo": "Llegada a una radio comunitaria",
                       "detalle": "Para difundir proyectos de extensión"}])
    assert a["tipo"] == "acceso"


def test_resultados_del_seguimiento():
    assert set(rs.RESULTADOS) == {"hablamos", "sirvio", "no_sirvio"}
    assert rs.DIAS_SEGUIMIENTO == 14
