"""Cliente WABA (WhatsApp Cloud API, oficial de Meta).

Analogia con Evolution: base_url = graph.facebook.com; "instancia" = phone_number_id;
"apikey" = access token (Bearer).
"""

from __future__ import annotations

import logging
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

LIST_MAX_ROWS = 10
LIST_ROW_TITLE_MAX = 24
LIST_ROW_DESCRIPTION_MAX = 72
LIST_ROW_ID_MAX = 200
BUTTONS_MAX = 3
BUTTON_ID_MAX = 256
BUTTON_TITLE_MAX = 20
HEADER_MAX = 60
INTERACTIVE_BODY_MAX = 1024

logger = logging.getLogger(__name__)


def _required_text(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} no puede estar vacio")
    return value


def _visible_text(value: str | None, field: str, limit: int) -> str:
    text = _required_text(value, field).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _identifier(value: str | None, field: str, limit: int) -> str:
    identifier = _required_text(value, field)
    if identifier != identifier.strip():
        raise ValueError(f"{field} no puede tener espacios al inicio o al final")
    if len(identifier) > limit:
        raise ValueError(f"{field} no puede exceder {limit} caracteres")
    return identifier


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
        self._token = token
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

    async def send_list(
        self,
        to: str,
        body: str,
        button_label: str,
        rows: list[dict[str, str]],
        header: str | None = None,
        section_title: str = "Opciones",
    ) -> SendResult:
        _required_text(to, "to")
        body_text = _visible_text(body, "body", INTERACTIVE_BODY_MAX)
        button_text = _visible_text(button_label, "button_label", BUTTON_TITLE_MAX)
        section_text = _visible_text(section_title, "section_title", LIST_ROW_TITLE_MAX)
        if not rows:
            raise ValueError("rows no puede estar vacio")
        if len(rows) > LIST_MAX_ROWS:
            logger.warning("send_list recorto %s filas al limite de %s", len(rows), LIST_MAX_ROWS)

        clean_rows: list[dict[str, str]] = []
        row_ids: set[str] = set()
        for index, row in enumerate(rows[:LIST_MAX_ROWS]):
            row_id = _identifier(
                row.get("id"),
                f"rows[{index}].id",
                LIST_ROW_ID_MAX,
            )
            if row_id in row_ids:
                raise ValueError("rows debe usar IDs unicos")
            row_ids.add(row_id)
            title = _visible_text(
                row.get("title"),
                f"rows[{index}].title",
                LIST_ROW_TITLE_MAX,
            )
            clean_row = {"id": row_id, "title": title}
            description = row.get("description")
            if isinstance(description, str) and description.strip():
                clean_row["description"] = _visible_text(
                    description,
                    f"rows[{index}].description",
                    LIST_ROW_DESCRIPTION_MAX,
                )
            clean_rows.append(clean_row)

        interactive: dict[str, Any] = {
            "type": "list",
            "body": {"text": body_text},
            "action": {
                "button": button_text,
                "sections": [{"title": section_text, "rows": clean_rows}],
            },
        }
        if header is not None and header.strip():
            interactive["header"] = {
                "type": "text",
                "text": _visible_text(header, "header", HEADER_MAX),
            }

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
        return _result(
            await self._http.request("POST", self._messages_path, retry=False, json=payload)
        )

    async def send_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, str]],
    ) -> SendResult:
        _required_text(to, "to")
        body_text = _visible_text(body, "body", INTERACTIVE_BODY_MAX)
        if not buttons:
            raise ValueError("buttons no puede estar vacio")
        if len(buttons) > BUTTONS_MAX:
            logger.warning(
                "send_buttons recorto %s botones al limite de %s",
                len(buttons),
                BUTTONS_MAX,
            )

        clean_buttons: list[dict[str, Any]] = []
        button_ids: set[str] = set()
        for index, button in enumerate(buttons[:BUTTONS_MAX]):
            button_id = _identifier(
                button.get("id"),
                f"buttons[{index}].id",
                BUTTON_ID_MAX,
            )
            if button_id in button_ids:
                raise ValueError("buttons debe usar IDs unicos")
            button_ids.add(button_id)
            title = _visible_text(
                button.get("title"),
                f"buttons[{index}].title",
                BUTTON_TITLE_MAX,
            )
            clean_buttons.append(
                {
                    "type": "reply",
                    "reply": {"id": button_id, "title": title},
                }
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": clean_buttons},
            },
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

    async def get_media(self, media_id: str) -> MediaDownload:
        media_id = _required_text(media_id, "media_id")
        metadata = await self._http.request(
            "GET",
            f"/{media_id}",
            params={"phone_number_id": self.phone_number_id},
        )
        media_url = metadata.get("url")
        if not isinstance(media_url, str) or not media_url.strip():
            raise ProviderTransportError(
                "Cloud API no devolvio una URL de descarga",
                body=metadata,
            )

        downloaded = await self._http.request_bytes(
            "GET",
            media_url,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        mime_type = metadata.get("mime_type") or downloaded.headers.get("content-type")
        filename = metadata.get("filename")
        return MediaDownload(
            provider="cloudapi",
            content=downloaded.content,
            base64=None,
            mime_type=mime_type if isinstance(mime_type, str) else None,
            filename=filename if isinstance(filename, str) else None,
            raw=metadata,
        )
