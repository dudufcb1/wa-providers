"""Errores del paquete.

La distincion clave es para la capa de arriba (una cola/dispatcher):
- ProviderAPIError  -> 4xx: error permanente (plantilla mala, fuera de ventana,
  numero invalido). NO reintentar; mandar a dead-letter.
- ProviderTransportError -> fallo de transporte o respuesta transitoria (timeout,
  red, 408, 429, 5xx). En operaciones idempotentes se puede reintentar; en envios,
  un timeout puede dejar un resultado ambiguo y no debe re-encolarse a ciegas.
"""

from __future__ import annotations

from typing import Any


class WAProviderError(Exception):
    """Base de todos los errores del paquete."""


class ProviderAPIError(WAProviderError):
    """Respuesta 4xx del proveedor. Error permanente para ese envio."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body or {}


class ProviderTransportError(WAProviderError):
    """Fallo de transporte o respuesta transitoria.

    En operaciones idempotentes puede reintentarse a nivel sistema. En envios,
    una respuesta perdida puede significar que el proveedor ya acepto el mensaje;
    el caller debe reconciliar el resultado antes de volver a enviarlo.
    """

    def __init__(self, message: str, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body or {}
