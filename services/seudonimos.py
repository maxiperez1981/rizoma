"""Seudónimos estables y no reversibles para registros de privacidad y exportaciones.

Salen de un secreto propio (SEUDONIMO_SECRETO) y, si no está definido, de
SECRET_KEY. El mismo id da siempre el mismo seudónimo, así un pedido de
privacidad o una auditoría de supresión se pueden seguir sin guardar el correo
ni el nombre. Seudonimizar no es anonimizar: con el secreto se puede volver a
calcular el seudónimo de una persona conocida.
"""
import hashlib
import hmac


def _secreto(secreto=None) -> bytes:
    if secreto is None:
        from config import settings

        secreto = settings.seudonimo_secreto or settings.secret_key
    if not secreto:
        raise RuntimeError("Falta SEUDONIMO_SECRETO o SECRET_KEY para calcular seudónimos")
    return str(secreto).encode("utf-8")


def seudonimo(identificador, secreto=None) -> str:
    """'persona-' + 12 hexadecimales, estable para el mismo id y el mismo secreto."""
    valor = str(identificador or "").strip().lower().encode("utf-8")
    return "persona-" + hmac.new(_secreto(secreto), valor, hashlib.sha256).hexdigest()[:12]
