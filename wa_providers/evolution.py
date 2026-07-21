"""Cliente Evolution API (WhatsApp Web / Baileys, no oficial).

Mismo contrato que CloudAPIClient para el nucleo comun (send_text/send_document),
para que sean intercambiables desde el factory. Ajusta los paths/campos a tu
version de Evolution si difiere (aqui: v2).
"""

from __future__ import annotations

from typing import Any

from .base import BaseProvider
from .exceptions import ProviderTransportError
from .http import PooledHTTPClient
from .schemas import MediaDownload, SendResult

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


def _required_text(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} no puede estar vacio")
    return value


# mediatype que acepta /message/sendMedia. Las notas de voz van por
# /message/sendWhatsAppAudio, que este cliente todavia no expone.
_MEDIA_TYPES = frozenset({"image", "video", "document", "audio"})


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
        message_id = _evo_id(data)
        # Sin key.id el envio quedo ambiguo: no se puede correlacionar el estado
        # de entrega ni reconciliar un reintento. No se reporta como aceptado.
        return SendResult(
            provider="evolution",
            message_id=message_id,
            accepted=message_id is not None,
            raw=data,
        )

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
        return await self.send_media(
            to,
            link,
            media_type="document",
            filename=filename,
            caption=caption,
        )

    async def send_media(
        self,
        to: str,
        media: str,
        media_type: str = "document",
        mime_type: str | None = None,
        filename: str | None = None,
        caption: str | None = None,
    ) -> SendResult:
        _required_text(to, "to")
        _required_text(media, "media")
        _required_text(media_type, "media_type")
        if media_type not in _MEDIA_TYPES:
            raise ValueError(
                f"media_type invalido: {media_type!r}. "
                f"Validos: {', '.join(sorted(_MEDIA_TYPES))}"
            )
        payload: dict[str, Any] = {
            "number": to,
            "mediatype": media_type,
            "media": media,
        }
        if mime_type is not None:
            payload["mimetype"] = mime_type
        if filename is not None:
            payload["fileName"] = filename
        if caption is not None:
            payload["caption"] = caption
        data = await self._http.request(
            "POST",
            f"/message/sendMedia/{self.instance}",
            retry=False,
            json=payload,
        )
        message_id = _evo_id(data)
        # Sin key.id el envio quedo ambiguo: no se puede correlacionar el estado
        # de entrega ni reconciliar un reintento. No se reporta como aceptado.
        return SendResult(
            provider="evolution",
            message_id=message_id,
            accepted=message_id is not None,
            raw=data,
        )

    async def get_media_base64(
        self,
        message: dict[str, Any],
        convert_to_mp4: bool = False,
    ) -> MediaDownload:
        if not isinstance(message, dict):
            raise TypeError("message debe ser un objeto de Evolution")
        key = message.get("key")
        if not isinstance(key, dict) or not isinstance(key.get("id"), str) or not key["id"]:
            raise ValueError("message debe incluir key.id")

        data = await self._http.request(
            "POST",
            f"/chat/getBase64FromMediaMessage/{self.instance}",
            retry=False,
            json={"message": message, "convertToMp4": convert_to_mp4},
        )
        encoded_media = data.get("base64")
        if not isinstance(encoded_media, str) or not encoded_media:
            raise ProviderTransportError(
                "Evolution no devolvio contenido base64",
                body=data,
            )
        mime_type = data.get("mimetype")
        filename = data.get("fileName") or data.get("filename")
        return MediaDownload(
            provider="evolution",
            content=None,
            base64=encoded_media,
            mime_type=mime_type if isinstance(mime_type, str) else None,
            filename=filename if isinstance(filename, str) else None,
            raw=data,
        )

    async def set_webhook(
        self,
        url: str,
        events: list[str] | None = None,
        *,
        enabled: bool = True,
        by_events: bool = False,
        include_base64: bool = False,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        webhook: dict[str, Any] = {
            "enabled": enabled,
            "url": _required_text(url, "url"),
            "byEvents": by_events,
            "base64": include_base64,
            "events": events or ["MESSAGES_UPSERT", "MESSAGES_UPDATE"],
        }
        if headers is not None:
            webhook["headers"] = headers
        return await self._http.request(
            "POST",
            f"/webhook/set/{self.instance}",
            retry=True,
            json={"webhook": webhook},
        )
