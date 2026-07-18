"""Cliente Evolution API (WhatsApp Web / Baileys, no oficial).

Mismo contrato que CloudAPIClient para el nucleo comun (send_text/send_document),
para que sean intercambiables desde el factory. Ajusta los paths/campos a tu
version de Evolution si difiere (aqui: v2).
"""

from __future__ import annotations

from typing import Any

from .base import BaseProvider
from .http import PooledHTTPClient
from .schemas import SendResult

_POOL_KEYS = (
    "timeout",
    "max_connections",
    "max_keepalive",
    "max_retries",
    "backoff_base",
    "backoff_max",
)


def _evo_id(data: dict[str, Any]) -> str | None:
    key = data.get("key")
    return key.get("id") if isinstance(key, dict) else None


class EvolutionClient(BaseProvider):
    provider_name = "evolution"

    def __init__(self, base_url: str, api_key: str, instance: str, **pool: Any) -> None:
        self.instance = instance
        http = PooledHTTPClient(
            base_url=base_url.rstrip("/"),
            headers={"apikey": api_key, "Content-Type": "application/json"},
            **{k: pool[k] for k in _POOL_KEYS if k in pool},
        )
        super().__init__(http)

    async def send_text(self, to: str, text: str) -> SendResult:
        payload = {"number": to, "text": text}
        data = await self._http.request(
            "POST",
            f"/message/sendText/{self.instance}",
            retry=False,
            json=payload,
        )
        return SendResult(provider="evolution", message_id=_evo_id(data), accepted=True, raw=data)

    async def send_document(
        self,
        to: str,
        *,
        link: str | None = None,
        media_id: str | None = None,  # Evolution no usa media_id; se acepta por firma comun
        filename: str | None = None,
        caption: str | None = None,
    ) -> SendResult:
        if not link:
            raise ValueError("Evolution send_document requiere link (url o base64)")
        payload = {
            "number": to,
            "mediatype": "document",
            "media": link,
            "fileName": filename,
            "caption": caption,
        }
        data = await self._http.request(
            "POST",
            f"/message/sendMedia/{self.instance}",
            retry=False,
            json=payload,
        )
        return SendResult(provider="evolution", message_id=_evo_id(data), accepted=True, raw=data)

    async def set_webhook(self, url: str, events: list[str] | None = None) -> dict[str, Any]:
        payload = {
            "url": url,
            "webhook_by_events": False,
            "events": events or ["MESSAGES_UPSERT", "MESSAGES_UPDATE"],
        }
        return await self._http.request(
            "POST",
            f"/webhook/set/{self.instance}",
            retry=True,
            json=payload,
        )
