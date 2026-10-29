"""Limite de uso por usuario para las funciones que llaman a modelos o recalculan el grafo.

Contador en memoria, por proceso: con 2 workers el tope efectivo es el doble del
configurado. Alcanza para frenar abuso y gasto; no reemplaza un limite en el proxy.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

import models
from auth import get_current_user

_lock = threading.Lock()
_eventos = defaultdict(deque)


def consumir(clave, maximo: int, ventana: int, ahora: float = None) -> int:
    """Registra un uso. Devuelve 0 si estaba permitido o los segundos de espera si se excedio."""
    ahora = time.monotonic() if ahora is None else ahora
    with _lock:
        cola = _eventos[clave]
        while cola and ahora - cola[0] >= ventana:
            cola.popleft()
        if len(cola) >= maximo:
            return int(ventana - (ahora - cola[0])) + 1
        cola.append(ahora)
        return 0


def limitar(nombre: str, maximo: int, ventana: int = 3600):
    def dependencia(user: models.User = Depends(get_current_user)):
        espera = consumir((nombre, str(user.id)), maximo, ventana)
        if espera:
            raise HTTPException(429, f"Superaste el limite de uso de esta funcion. Proba de nuevo en {espera // 60 + 1} minutos.",
                                headers={"Retry-After": str(espera)})
    return dependencia
