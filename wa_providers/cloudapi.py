"""Cliente WABA (WhatsApp Cloud API, oficial de Meta).

Analogia con Evolution: base_url = graph.facebook.com; "instancia" = phone_number_id;
"apikey" = access token (Bearer).
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


def _result(data: dict[str, Any]) -> SendResult:
    msg = (data.get("messages") or [{}])[0]
    return SendResult(
        provider="cloudapi",
        message_id=msg.get("id"),
        accepted=bool(msg.get("id")),
        raw=data,
    )


class CloudAPIClient(BaseProvider):
    provider_name = "cloudapi"

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        graph_version: str = "v21.0",
        **pool: Any,
    ) -> None:
        self.phone_number_id = phone_number_id
        http = PooledHTTPClient(
            base_url=f"https://graph.facebook.com/{graph_version}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            **{k: pool[k] for k in _POOL_KEYS if k in pool},
        )
        super().__init__(http)

    @property
    def _messages_path(self) -> str:
        return f"/{self.phone_number_id}/messages"

    async def send_text(self, to: str, text: str, preview_url: bool = False) -> SendResult:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": preview_url, "body": text},
        }
        return _result(
            await self._http.request("POST", self._messages_path, retry=False, json=payload)
        )

    async def send_template(
        self,
        to: str,
        name: str,
        lang: str = "es_MX",
        body_params: list[Any] | None = None,
        components: list[dict[str, Any]] | None = None,
    ) -> SendResult:
        """Plantilla aprobada (unico camino para iniciar fuera de la ventana de 24h).

        Da `components` completos para casos con header/botones, o `body_params`
        para el caso simple de solo variables del cuerpo.
        """
        template: dict[str, Any] = {"name": name, "language": {"code": lang}}
        if components is not None:
            template["components"] = components
        elif body_params:
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(p)} for p in body_params],
                }
            ]
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": template,
        }
        return _result(
            await self._http.request("POST", self._messages_path, retry=False, json=payload)
        )

    async def send_document(
        self,
        to: str,
        *,
        link: str | None = None,
        media_id: str | None = None,
        filename: str | None = None,
        caption: str | None = None,
    ) -> SendResult:
        document: dict[str, Any] = {}
        if media_id:
            document["id"] = media_id
        elif link:
            document["link"] = link
        else:
            raise ValueError("send_document requiere link o media_id")
        if filename:
            document["filename"] = filename
        if caption:
            document["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "document",
            "document": document,
        }
        return _result(
            await self._http.request("POST", self._messages_path, retry=False, json=payload)
        )

    async def mark_read(self, message_id: str) -> dict[str, Any]:
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
        return await self._http.request("POST", self._messages_path, retry=True, json=payload)

    async def health(self) -> dict[str, Any]:
        """health_status del numero: el mejor diagnostico cuando algo no llega."""
        return await self._http.request(
            "GET", f"/{self.phone_number_id}", params={"fields": "health_status"}
        )
