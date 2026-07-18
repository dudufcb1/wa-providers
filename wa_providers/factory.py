"""El factory: recibe un config y devuelve el motor correcto.

Es la piecita que hace el "cambia de proveedor con una linea". El resto de la app
llama a get_provider(config) y usa la interfaz comun, sin saber cual motor es.

Config esperado:
  {"provider": "cloudapi", "token": "...", "phone_number_id": "...", "graph_version": "v21.0"}
  {"provider": "evolution", "base_url": "...", "api_key": "...", "instance": "..."}

Opcionales de pool en cualquiera: timeout, max_connections, max_keepalive,
max_retries, backoff_base, backoff_max.
"""

from __future__ import annotations

from typing import Any

from .base import BaseProvider
from .cloudapi import CloudAPIClient
from .evolution import EvolutionClient

_POOL_KEYS = (
    "timeout",
    "max_connections",
    "max_keepalive",
    "max_retries",
    "backoff_base",
    "backoff_max",
)


def get_provider(config: dict[str, Any]) -> BaseProvider:
    name = (config.get("provider") or "").lower()
    pool = {k: config[k] for k in _POOL_KEYS if k in config}

    if name == "cloudapi":
        return CloudAPIClient(
            token=config["token"],
            phone_number_id=config["phone_number_id"],
            graph_version=config.get("graph_version", "v21.0"),
            **pool,
        )
    if name == "evolution":
        return EvolutionClient(
            base_url=config["base_url"],
            api_key=config["api_key"],
            instance=config["instance"],
            **pool,
        )
    raise ValueError(f"Proveedor de WhatsApp no soportado: {name!r}")
