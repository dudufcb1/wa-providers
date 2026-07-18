"""Capa HTTP compartida: cliente httpx persistente (con pool) + reintentos con
backoff.

Persistente: se crea UN AsyncClient con pool de conexiones y se reusa en todas
las llamadas (no uno-por-request), para no pagar handshake TCP+TLS cada vez.

Reintentos: solo para fallas transitorias (timeout, red, 408, 429, 5xx), con
backoff exponencial + jitter, respetando Retry-After. Por defecto se reintentan
unicamente metodos HTTP idempotentes. Los POST de mensajes no se reintentan para
evitar duplicados cuando el proveedor acepto el envio pero se perdio la respuesta.
"""

from __future__ import annotations

import asyncio
import math
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .exceptions import ProviderAPIError, ProviderTransportError

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
RETRYABLE_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PUT"})
RETRYABLE_TRANSPORT_ERRORS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.ProxyError,
    httpx.RemoteProtocolError,
)


def _safe_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {"_data": data}
    except ValueError:
        return {"_raw": resp.text}


def _parse_retry_after(value: str) -> float | None:
    try:
        delay = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at is None:
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        delay = max(
            0.0,
            (retry_at.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds(),
        )
    if not math.isfinite(delay) or delay < 0:
        return None
    return delay


class PooledHTTPClient:
    def __init__(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 20.0,
        max_connections: int = 100,
        max_keepalive: int = 20,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        backoff_max: float = 8.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries no puede ser negativo")
        if not math.isfinite(backoff_base) or backoff_base < 0:
            raise ValueError("backoff_base debe ser finito y no negativo")
        if not math.isfinite(backoff_max) or backoff_max < 0:
            raise ValueError("backoff_max debe ser finito y no negativo")

        # Un solo cliente reutilizable con pool: esto es lo que aguanta volumen.
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers or {},
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive,
            ),
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max

    async def request(
        self,
        method: str,
        path: str,
        *,
        retry: bool | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Ejecuta una solicitud con retry seguro segun el metodo HTTP.

        ``retry=None`` usa la politica por defecto: solo metodos idempotentes.
        Un caller puede habilitar o deshabilitar reintentos explicitamente cuando
        conoce la semantica del endpoint.
        """
        normalized_method = method.upper()
        retry_enabled = normalized_method in RETRYABLE_METHODS if retry is None else retry
        attempt = 0
        while True:
            try:
                resp = await self._client.request(normalized_method, path, **kwargs)
            except RETRYABLE_TRANSPORT_ERRORS as exc:
                if not retry_enabled or attempt >= self._max_retries:
                    raise ProviderTransportError(str(exc)) from exc
                await self._sleep_backoff(attempt)
                attempt += 1
                continue

            if resp.status_code in RETRYABLE_STATUS:
                if not retry_enabled or attempt >= self._max_retries:
                    raise ProviderTransportError(
                        f"HTTP {resp.status_code} tras {attempt} reintentos",
                        status_code=resp.status_code,
                        body=_safe_json(resp),
                    )
                await self._sleep_backoff(attempt, resp)
                attempt += 1
                continue

            if resp.status_code >= 400:
                raise ProviderAPIError(
                    f"HTTP {resp.status_code}",
                    status_code=resp.status_code,
                    body=_safe_json(resp),
                )

            return _safe_json(resp)

    async def _sleep_backoff(self, attempt: int, resp: httpx.Response | None = None) -> None:
        delay: float | None = None
        if resp is not None:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                delay = _parse_retry_after(retry_after)
        if delay is None:
            delay = min(self._backoff_base * (2**attempt), self._backoff_max)
            delay += random.uniform(0, delay * 0.25)  # jitter para no sincronizar reintentos
            delay = min(delay, self._backoff_max)
        else:
            delay = min(delay, self._backoff_max)
        await asyncio.sleep(delay)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "PooledHTTPClient":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()
