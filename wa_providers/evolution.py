"""Cliente Evolution API (WhatsApp Web / Baileys, no oficial).

Mismo contrato que CloudAPIClient para el nucleo comun (send_text/send_document),
para que sean intercambiables desde el factory. Ajusta los paths/campos a tu
version de Evolution si difiere (aqui: v2).
"""

from __future__ import annotations

import json
from typing import Any

from .base import BaseProvider
from .exceptions import ProviderTransportError
from .http import PooledHTTPClient
from .schemas import InstanceProfile, MediaDownload, SendResult

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


def _first_instance_record(data: Any) -> dict[str, Any] | None:
    """Saca el objeto de la instancia, venga como lista o envuelto en {"instance": ...}."""
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                inner = item.get("instance")
                return inner if isinstance(inner, dict) else item
        return None
    if isinstance(data, dict):
        inner = data.get("instance")
        return inner if isinstance(inner, dict) else data
    return None


def _phone_from_jid(jid: Any) -> str | None:
    """De '5215512345678@s.whatsapp.net' saca '5215512345678'. Ignora @lid (no es numero)."""
    if not isinstance(jid, str) or "@" not in jid:
        return None
    user, _, domain = jid.partition("@")
    if domain.endswith("lid"):
        return None
    return user or None


# mediatype que acepta /message/sendMedia. Las notas de voz van por
# /message/sendWhatsAppAudio, que tiene su propio metodo (send_whatsapp_audio).
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

    async def send_whatsapp_audio(self, to: str, audio: str) -> SendResult:
        """Manda una nota de voz (PTT): se reproduce con su onda, no es un archivo.

        Evolution la separa del resto de media en `/message/sendWhatsAppAudio`; por
        `sendMedia` con `mediatype: audio` sale como archivo de audio adjunto."""
        _required_text(to, "to")
        _required_text(audio, "audio")
        data = await self._http.request(
            "POST",
            f"/message/sendWhatsAppAudio/{self.instance}",
            retry=False,
            json={"number": to, "audio": audio},
        )
        message_id = _evo_id(data)
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

    # ------------------------------------------------------------- instancias

    async def create_instance(
        self,
        instance_name: str,
        *,
        integration: str = "WHATSAPP-BAILEYS",
        with_qr: bool = True,
    ) -> dict[str, Any]:
        """Da de alta un numero nuevo. La respuesta suele traer el primer QR.

        El QR caduca en segundos: si el usuario tarda en escanearlo hay que
        pedir uno nuevo con `connect()`, no volver a crear la instancia.
        """
        payload = {
            "instanceName": _required_text(instance_name, "instance_name"),
            "integration": integration,
            "qrcode": with_qr,
        }
        return await self._http.request("POST", "/instance/create", retry=False, json=payload)

    async def connect(self, instance_name: str | None = None) -> dict[str, Any]:
        """Pide un QR (o codigo de emparejamiento) para vincular el telefono."""
        target = _required_text(instance_name or self.instance, "instance_name")
        return await self._http.request("GET", f"/instance/connect/{target}", retry=True)

    async def connection_state(self, instance_name: str | None = None) -> str | None:
        """Estado de la vinculacion: `close`, `connecting` u `open`.

        `open` es el unico estado en el que la instancia puede enviar y recibir;
        es lo que se consulta mientras el usuario tiene el QR en pantalla.
        """
        target = _required_text(instance_name or self.instance, "instance_name")
        data = await self._http.request(
            "GET",
            f"/instance/connectionState/{target}",
            retry=True,
        )
        instance = data.get("instance")
        state = instance.get("state") if isinstance(instance, dict) else data.get("state")
        return state if isinstance(state, str) else None

    async def fetch_profile(self, instance_name: str | None = None) -> InstanceProfile:
        """Numero y nombre de perfil de la instancia ya vinculada.

        Sirve para mostrar el telefono real en vez del nombre interno de la
        instancia. `fetchInstances` puede devolver una lista o un objeto segun la
        version, asi que se lee el cuerpo crudo en vez de asumir una forma.
        """
        target = _required_text(instance_name or self.instance, "instance_name")
        raw = await self._http.request_bytes(
            "GET",
            "/instance/fetchInstances",
            retry=True,
            params={"instanceName": target},
        )
        try:
            data = json.loads(raw.content or b"null")
        except (ValueError, TypeError):
            return InstanceProfile()
        record = _first_instance_record(data)
        if record is None:
            return InstanceProfile()
        profile = record.get("profileName")
        return InstanceProfile(
            phone=_phone_from_jid(record.get("ownerJid") or record.get("owner")),
            profile_name=profile if isinstance(profile, str) and profile else None,
        )

    async def logout_instance(self, instance_name: str | None = None) -> dict[str, Any]:
        """Desvincula el telefono sin borrar la instancia: se puede reconectar."""
        target = _required_text(instance_name or self.instance, "instance_name")
        return await self._http.request("DELETE", f"/instance/logout/{target}", retry=False)

    async def delete_instance(self, instance_name: str | None = None) -> dict[str, Any]:
        """Borra la instancia. Reconectar despues exige escanear un QR nuevo."""
        target = _required_text(instance_name or self.instance, "instance_name")
        return await self._http.request("DELETE", f"/instance/delete/{target}", retry=False)

    async def set_webhook(
        self,
        url: str,
        events: list[str] | None = None,
        *,
        enabled: bool = True,
        by_events: bool = False,
        include_base64: bool = False,
        headers: dict[str, str] | None = None,
        instance_name: str | None = None,
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
        target = _required_text(instance_name or self.instance, "instance_name")
        return await self._http.request(
            "POST",
            f"/webhook/set/{target}",
            retry=True,
            json={"webhook": webhook},
        )
