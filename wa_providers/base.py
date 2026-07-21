"""Contrato comun de proveedores.

El nucleo compartido (lo que ambos motores hacen igual) es send_text / send_document.
Las capacidades especificas viven en el cliente concreto (p.ej. send_template solo
en Cloud API; grupos solo en Evolution). No se finge simetria perfecta.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from .http import PooledHTTPClient
from .schemas import SendResult

# Conserva el tipo concreto al entrar al contexto: sin esto, `async with
# EvolutionClient(...)` se ve como BaseProvider y se pierden las capacidades
# propias del motor.
_Provider = TypeVar("_Provider", bound="BaseProvider")


class BaseProvider(ABC):
    provider_name: str = "base"

    def __init__(self, http: PooledHTTPClient) -> None:
        self._http = http

    @abstractmethod
    async def send_text(self, to: str, text: str) -> SendResult: ...

    @abstractmethod
    async def send_document(
        self,
        to: str,
        *,
        link: str | None = None,
        media_id: str | None = None,
        filename: str | None = None,
        caption: str | None = None,
    ) -> SendResult: ...

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self: _Provider) -> _Provider:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()
